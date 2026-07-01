"""Dashboard REST API.

Provides endpoints for listing repositories, paginated review history,
aggregated metrics, and per-review comment detail.

All repo-scoped routes use ``{owner}/{repo}`` path segments so that the
repository full name (e.g. ``octocat/hello-world``) maps cleanly to a URL
without requiring percent-encoding of the slash.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PullRequestReview, Repository, ReviewComment
from app.db.session import get_db

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class RepoResponse(BaseModel):
    id: int
    full_name: str
    installed_at: datetime


class ReviewSummary(BaseModel):
    id: int
    pr_number: int
    pr_title: str
    author: str
    status: str
    created_at: datetime
    issue_count: int


class ReviewListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ReviewSummary]


class CommentResponse(BaseModel):
    id: int
    file_path: str
    line_number: int
    category: str
    severity: str
    comment: str
    suggestion: str | None


class ReviewDetailResponse(BaseModel):
    id: int
    pr_number: int
    pr_title: str
    author: str
    status: str
    created_at: datetime
    comments: list[CommentResponse]


class TrendPoint(BaseModel):
    """Comment counts for a single PR, used to draw a time-series chart."""

    review_id: int
    pr_number: int
    created_at: datetime
    by_severity: dict[str, int]


class MetricsResponse(BaseModel):
    total: int
    by_category: dict[str, int]
    by_severity: dict[str, int]
    trend: list[TrendPoint]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_repo(db: AsyncSession, owner: str, repo: str) -> Repository:
    full_name = f"{owner}/{repo}"
    result = await db.execute(
        select(Repository).where(Repository.github_repo_full_name == full_name)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Repository '{full_name}' not found")
    return row


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/repos", response_model=list[RepoResponse])
async def list_repos(db: AsyncSession = Depends(get_db)) -> list[RepoResponse]:
    result = await db.execute(select(Repository).order_by(Repository.installed_at.desc()))
    repos = result.scalars().all()
    return [
        RepoResponse(id=r.id, full_name=r.github_repo_full_name, installed_at=r.installed_at)
        for r in repos
    ]


@router.get("/repos/{owner}/{repo}/reviews", response_model=ReviewListResponse)
async def list_reviews(
    owner: str,
    repo: str,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> ReviewListResponse:
    repository = await _get_repo(db, owner, repo)
    offset = (page - 1) * page_size

    total_result = await db.execute(
        select(func.count()).where(PullRequestReview.repo_id == repository.id)
    )
    total: int = total_result.scalar_one()

    # Fetch reviews and comment counts in a single join query to avoid N+1.
    count_subq = (
        select(ReviewComment.review_id, func.count().label("cnt"))
        .group_by(ReviewComment.review_id)
        .subquery()
    )
    rows_result = await db.execute(
        select(PullRequestReview, func.coalesce(count_subq.c.cnt, 0).label("issue_count"))
        .outerjoin(count_subq, PullRequestReview.id == count_subq.c.review_id)
        .where(PullRequestReview.repo_id == repository.id)
        .order_by(PullRequestReview.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    items = [
        ReviewSummary(
            id=rev.id,
            pr_number=rev.pr_number,
            pr_title=rev.pr_title,
            author=rev.author,
            status=rev.status,
            created_at=rev.created_at,
            issue_count=int(cnt),
        )
        for rev, cnt in rows_result.all()
    ]

    return ReviewListResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/repos/{owner}/{repo}/metrics", response_model=MetricsResponse)
async def get_metrics(
    owner: str, repo: str, db: AsyncSession = Depends(get_db)
) -> MetricsResponse:
    repository = await _get_repo(db, owner, repo)

    review_ids_result = await db.execute(
        select(PullRequestReview.id).where(PullRequestReview.repo_id == repository.id)
    )
    review_ids = [row[0] for row in review_ids_result.all()]

    if not review_ids:
        return MetricsResponse(by_category={}, by_severity={}, total=0, trend=[])

    cat_result = await db.execute(
        select(ReviewComment.category, func.count())
        .where(ReviewComment.review_id.in_(review_ids))
        .group_by(ReviewComment.category)
    )
    by_category: dict[str, int] = {row[0]: row[1] for row in cat_result.all()}

    sev_result = await db.execute(
        select(ReviewComment.severity, func.count())
        .where(ReviewComment.review_id.in_(review_ids))
        .group_by(ReviewComment.severity)
    )
    by_severity: dict[str, int] = {row[0]: row[1] for row in sev_result.all()}

    total_result = await db.execute(
        select(func.count()).where(ReviewComment.review_id.in_(review_ids))
    )
    total: int = total_result.scalar_one()

    # Per-PR severity breakdown for time-series trend chart.
    trend = await _build_trend(db, review_ids, repository.id)

    return MetricsResponse(
        by_category=by_category, by_severity=by_severity, total=total, trend=trend
    )


async def _build_trend(
    db: AsyncSession, review_ids: list[int], repo_id: int
) -> list[TrendPoint]:
    """Return per-PR severity counts ordered by PR creation date."""
    reviews_result = await db.execute(
        select(PullRequestReview.id, PullRequestReview.pr_number, PullRequestReview.created_at)
        .where(PullRequestReview.id.in_(review_ids))
        .order_by(PullRequestReview.created_at.asc())
    )
    reviews = reviews_result.all()

    sev_per_review_result = await db.execute(
        select(ReviewComment.review_id, ReviewComment.severity, func.count())
        .where(ReviewComment.review_id.in_(review_ids))
        .group_by(ReviewComment.review_id, ReviewComment.severity)
    )
    # Build a dict: review_id -> {severity -> count}
    sev_map: dict[int, dict[str, int]] = {}
    for rid, sev, cnt in sev_per_review_result.all():
        sev_map.setdefault(rid, {})[sev] = cnt

    return [
        TrendPoint(
            review_id=rid,
            pr_number=pr_number,
            created_at=created_at,
            by_severity=sev_map.get(rid, {}),
        )
        for rid, pr_number, created_at in reviews
    ]


@router.get("/reviews/{review_id}", response_model=ReviewDetailResponse)
async def get_review(
    review_id: int, db: AsyncSession = Depends(get_db)
) -> ReviewDetailResponse:
    result = await db.execute(
        select(PullRequestReview).where(PullRequestReview.id == review_id)
    )
    review = result.scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    comments_result = await db.execute(
        select(ReviewComment).where(ReviewComment.review_id == review_id)
    )
    comments = comments_result.scalars().all()

    return ReviewDetailResponse(
        id=review.id,
        pr_number=review.pr_number,
        pr_title=review.pr_title,
        author=review.author,
        status=review.status,
        created_at=review.created_at,
        comments=[
            CommentResponse(
                id=c.id,
                file_path=c.file_path,
                line_number=c.line_number,
                category=c.category,
                severity=c.severity,
                comment=c.comment,
                suggestion=c.suggestion,
            )
            for c in comments
        ],
    )
