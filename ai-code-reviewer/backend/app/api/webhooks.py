from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.review_engine import run_review
from app.db.models import PullRequestReview, Repository, ReviewComment
from app.db.session import AsyncSessionLocal, get_db
from app.github.webhook_validator import verify_github_signature

logger = logging.getLogger(__name__)
router = APIRouter()

_HANDLED_ACTIONS = {"opened", "synchronize", "reopened"}


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    body = await verify_github_signature(request)
    event = request.headers.get("X-GitHub-Event", "")
    if event != "pull_request":
        return {"ignored": True}

    payload = json.loads(body)
    action = payload.get("action", "")
    if action not in _HANDLED_ACTIONS:
        return {"ignored": True}

    pr_data = payload["pull_request"]
    repo_data = payload["repository"]

    repo = await _get_or_create_repo(db, repo_data["full_name"])
    review = PullRequestReview(
        repo_id=repo.id,
        pr_number=pr_data["number"],
        pr_title=pr_data["title"],
        author=pr_data["user"]["login"],
        status="pending",
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    background_tasks.add_task(
        _process_review,
        review_id=review.id,
        repo_full_name=repo_data["full_name"],
        pr_number=pr_data["number"],
        head_sha=pr_data["head"]["sha"],
    )

    return {"status": "accepted", "review_id": review.id}


async def _get_or_create_repo(db: AsyncSession, full_name: str) -> Repository:
    result = await db.execute(
        select(Repository).where(Repository.github_repo_full_name == full_name)
    )
    repo = result.scalar_one_or_none()
    if repo is None:
        repo = Repository(github_repo_full_name=full_name)
        db.add(repo)
        await db.commit()
        await db.refresh(repo)
    return repo


async def _process_review(
    review_id: int,
    repo_full_name: str,
    pr_number: int,
    head_sha: str,
) -> None:
    async with AsyncSessionLocal() as db:
        try:
            auth_headers = {}
            if settings.github_token:
                auth_headers["Authorization"] = f"token {settings.github_token}"

            pr_api_url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}"
            async with httpx.AsyncClient(
                headers={**auth_headers, "Accept": "application/vnd.github+json"},
                follow_redirects=True,
            ) as client:
                pr_json = (await client.get(pr_api_url)).json()

            # Always use the current head SHA so diff lines and comment commit_id stay in sync.
            # The webhook head_sha can lag behind if multiple commits arrive quickly.
            current_head_sha = pr_json["head"]["sha"]

            async with httpx.AsyncClient(
                headers={**auth_headers, "Accept": "application/vnd.github.v3.diff"},
                follow_redirects=True,
            ) as client:
                resp = await client.get(pr_api_url)

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to fetch diff (HTTP {resp.status_code}): {pr_api_url}"
                )

            unified_diff = resp.text
            results = await run_review(repo_full_name, pr_number, current_head_sha, unified_diff)

            comments = [
                ReviewComment(
                    review_id=review_id,
                    file_path=r.file_path,
                    line_number=r.line,
                    category=r.category,
                    severity=r.severity,
                    comment=r.comment,
                    suggestion=r.suggestion or "",
                )
                for r in results
            ]
            db.add_all(comments)

            await db.execute(
                update(PullRequestReview)
                .where(PullRequestReview.id == review_id)
                .values(status="completed")
            )
            await db.commit()

        except Exception as exc:
            logger.error("Review %s failed: %s", review_id, exc)
            await db.execute(
                update(PullRequestReview)
                .where(PullRequestReview.id == review_id)
                .values(status="failed")
            )
            await db.commit()
