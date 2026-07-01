"""Unit tests for the GitHub webhook API endpoint and supporting helpers."""
from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.base import ReviewResult
from app.db.models import PullRequestReview, Repository, ReviewComment

# ---------------------------------------------------------------------------
# Shared fixtures & constants
# ---------------------------------------------------------------------------

_REPO_FULL_NAME = "owner/repo"

_PR_PAYLOAD = {
    "action": "opened",
    "pull_request": {
        "number": 42,
        "title": "My PR",
        "user": {"login": "author"},
        "head": {"sha": "abc123"},
        "diff_url": "https://github.com/owner/repo/pull/42.diff",
    },
    "repository": {"full_name": _REPO_FULL_NAME},
}

_REVIEW_RESULT = ReviewResult(
    category="bug",
    severity="critical",
    line=5,
    comment="Null dereference",
    suggestion="add a None check",
    file_path="src/foo.py",
)


def _make_mock_db() -> AsyncMock:
    """Return a mock AsyncSession whose refresh() assigns sequential IDs.

    Configuring __aenter__ to return itself ensures that code using
    `async with AsyncSessionLocal() as db:` sees the same mock inside the block.
    """
    db = AsyncMock(spec=AsyncSession)

    # Let the async context-manager protocol yield `db` itself.
    db.__aenter__.return_value = db

    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_execute_result

    _id_counter = [0]

    async def _refresh(obj):
        _id_counter[0] += 1
        obj.id = _id_counter[0]

    db.refresh.side_effect = _refresh
    return db


def _make_mock_http_client(mock_resp: MagicMock) -> MagicMock:
    """Return a mock that works as `async with httpx.AsyncClient(...) as client:`."""
    client_instance = AsyncMock()
    client_instance.get = AsyncMock(return_value=mock_resp)

    http_ctx = MagicMock()
    http_ctx.__aenter__ = AsyncMock(return_value=client_instance)
    http_ctx.__aexit__ = AsyncMock(return_value=False)
    return http_ctx


# ---------------------------------------------------------------------------
# _get_or_create_repo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_repo_creates_new_when_not_found():
    from app.api.webhooks import _get_or_create_repo

    db = _make_mock_db()
    # scalar_one_or_none returns None → triggers create path
    db.execute.return_value.scalar_one_or_none.return_value = None

    repo = await _get_or_create_repo(db, _REPO_FULL_NAME)

    assert isinstance(repo, Repository)
    assert repo.github_repo_full_name == _REPO_FULL_NAME
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_or_create_repo_returns_existing_when_found():
    from app.api.webhooks import _get_or_create_repo

    db = _make_mock_db()
    existing = Repository(id=99, github_repo_full_name=_REPO_FULL_NAME)
    db.execute.return_value.scalar_one_or_none.return_value = existing

    repo = await _get_or_create_repo(db, _REPO_FULL_NAME)

    assert repo is existing
    # No write operations when repo already exists
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    db.refresh.assert_not_awaited()


# ---------------------------------------------------------------------------
# github_webhook endpoint — event / action filtering
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    return _make_mock_db()


@pytest.fixture
def app_client(mock_db):
    """Yield an httpx AsyncClient wired to the FastAPI app with DB overridden."""
    from app.main import app
    from app.db.session import get_db

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_db
    yield app
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_github_webhook_ignores_non_pr_event(app_client):
    body = b'{"action": "ping"}'

    with patch("app.api.webhooks.verify_github_signature", return_value=body):
        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook/github",
                headers={"X-GitHub-Event": "push"},
                content=body,
            )

    assert response.status_code == 200
    assert response.json() == {"ignored": True}


@pytest.mark.asyncio
async def test_github_webhook_ignores_unhandled_pr_action(app_client):
    payload = {**_PR_PAYLOAD, "action": "closed"}
    body = json.dumps(payload).encode()

    with patch("app.api.webhooks.verify_github_signature", return_value=body):
        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook/github",
                headers={"X-GitHub-Event": "pull_request"},
                content=body,
            )

    assert response.status_code == 200
    assert response.json() == {"ignored": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["opened", "synchronize", "reopened"])
async def test_github_webhook_accepted_for_handled_actions(app_client, action):
    payload = {**_PR_PAYLOAD, "action": action}
    body = json.dumps(payload).encode()
    mock_repo = Repository(id=1, github_repo_full_name=_REPO_FULL_NAME)

    with (
        patch("app.api.webhooks.verify_github_signature", return_value=body),
        patch(
            "app.api.webhooks._get_or_create_repo",
            new=AsyncMock(return_value=mock_repo),
        ),
        patch("app.api.webhooks._process_review", new=AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook/github",
                headers={"X-GitHub-Event": "pull_request"},
                content=body,
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert "review_id" in data


@pytest.mark.asyncio
async def test_github_webhook_invalid_signature_returns_403(app_client):
    with patch(
        "app.api.webhooks.verify_github_signature",
        side_effect=HTTPException(status_code=403, detail="Signature mismatch"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test"
        ) as client:
            response = await client.post(
                "/webhook/github",
                headers={"X-GitHub-Event": "pull_request"},
                content=b"{}",
            )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_github_webhook_creates_review_with_pending_status(app_client, mock_db):
    body = json.dumps(_PR_PAYLOAD).encode()
    mock_repo = Repository(id=1, github_repo_full_name=_REPO_FULL_NAME)

    added_objects: list = []

    def capture_add(obj):
        added_objects.append(obj)

    mock_db.add.side_effect = capture_add

    with (
        patch("app.api.webhooks.verify_github_signature", return_value=body),
        patch(
            "app.api.webhooks._get_or_create_repo",
            new=AsyncMock(return_value=mock_repo),
        ),
        patch("app.api.webhooks._process_review", new=AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test"
        ) as client:
            await client.post(
                "/webhook/github",
                headers={"X-GitHub-Event": "pull_request"},
                content=body,
            )

    pr_reviews = [o for o in added_objects if isinstance(o, PullRequestReview)]
    assert len(pr_reviews) == 1
    review = pr_reviews[0]
    assert review.pr_number == 42
    assert review.pr_title == "My PR"
    assert review.author == "author"
    assert review.status == "pending"


@pytest.mark.asyncio
async def test_github_webhook_dispatches_background_task_with_correct_args(
    app_client,
):
    body = json.dumps(_PR_PAYLOAD).encode()
    mock_repo = Repository(id=1, github_repo_full_name=_REPO_FULL_NAME)

    mock_process = AsyncMock()

    with (
        patch("app.api.webhooks.verify_github_signature", return_value=body),
        patch(
            "app.api.webhooks._get_or_create_repo",
            new=AsyncMock(return_value=mock_repo),
        ),
        patch("app.api.webhooks._process_review", mock_process),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app_client), base_url="http://test"
        ) as client:
            await client.post(
                "/webhook/github",
                headers={"X-GitHub-Event": "pull_request"},
                content=body,
            )

    mock_process.assert_awaited_once()
    kwargs = mock_process.await_args.kwargs
    assert kwargs["repo_full_name"] == _REPO_FULL_NAME
    assert kwargs["pr_number"] == 42
    assert kwargs["head_sha"] == "abc123"


# ---------------------------------------------------------------------------
# _process_review — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_review_creates_comments_and_marks_completed():
    from app.api.webhooks import _process_review

    mock_db = _make_mock_db()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n+x = 1\n"

    mock_http = _make_mock_http_client(mock_resp)

    with (
        patch("app.api.webhooks.AsyncSessionLocal", return_value=mock_db),
        patch("app.api.webhooks.httpx.AsyncClient", return_value=mock_http),
        patch(
            "app.api.webhooks.run_review", new=AsyncMock(return_value=[_REVIEW_RESULT])
        ),
        patch("app.api.webhooks.settings") as mock_settings,
    ):
        mock_settings.github_token = ""
        await _process_review(
                review_id=10,
                repo_full_name=_REPO_FULL_NAME,
                pr_number=42,
                head_sha="abc123",
            )

    mock_db.add_all.assert_called_once()
    (comments,) = mock_db.add_all.call_args.args
    assert len(comments) == 1
    assert comments[0].file_path == "src/foo.py"
    assert comments[0].category == "bug"
    assert comments[0].severity == "critical"
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_process_review_includes_github_token_in_auth_header():
    from app.api.webhooks import _process_review

    mock_db = _make_mock_db()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = ""

    captured_kwargs: list[dict] = []

    def fake_async_client(**kwargs):
        captured_kwargs.append(kwargs)
        return _make_mock_http_client(mock_resp)

    with (
        patch("app.api.webhooks.AsyncSessionLocal", return_value=mock_db),
        patch("app.api.webhooks.httpx.AsyncClient", fake_async_client),
        patch("app.api.webhooks.run_review", new=AsyncMock(return_value=[])),
        patch("app.api.webhooks.settings") as mock_settings,
    ):
        mock_settings.github_token = "ghp_testtoken"
        await _process_review(
            review_id=10,
            repo_full_name=_REPO_FULL_NAME,
            pr_number=42,
            head_sha="abc123",
        )

    # Implementation makes two httpx calls: one to fetch PR JSON, one to fetch the diff.
    assert len(captured_kwargs) == 2
    assert all(k["headers"].get("Authorization") == "token ghp_testtoken" for k in captured_kwargs)


@pytest.mark.asyncio
async def test_process_review_no_auth_header_when_token_empty():
    from app.api.webhooks import _process_review

    mock_db = _make_mock_db()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = ""

    captured_kwargs: list[dict] = []

    def fake_async_client(**kwargs):
        captured_kwargs.append(kwargs)
        return _make_mock_http_client(mock_resp)

    with (
        patch("app.api.webhooks.AsyncSessionLocal", return_value=mock_db),
        patch("app.api.webhooks.httpx.AsyncClient", fake_async_client),
        patch("app.api.webhooks.run_review", new=AsyncMock(return_value=[])),
        patch("app.api.webhooks.settings") as mock_settings,
    ):
        mock_settings.github_token = ""
        await _process_review(
            review_id=10,
            repo_full_name=_REPO_FULL_NAME,
            pr_number=42,
            head_sha="abc123",
        )

    # Implementation makes two httpx calls; neither should carry an auth header.
    assert len(captured_kwargs) == 2
    assert all("Authorization" not in k["headers"] for k in captured_kwargs)


# ---------------------------------------------------------------------------
# _process_review — error resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_review_marks_failed_on_non_200_diff_response(caplog):
    from app.api.webhooks import _process_review

    mock_db = _make_mock_db()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_http = _make_mock_http_client(mock_resp)

    with (
        patch("app.api.webhooks.AsyncSessionLocal", return_value=mock_db),
        patch("app.api.webhooks.httpx.AsyncClient", return_value=mock_http),
        patch("app.api.webhooks.settings") as mock_settings,
        caplog.at_level(logging.ERROR, logger="app.api.webhooks"),
    ):
        mock_settings.github_token = ""
        await _process_review(
            review_id=5,
            repo_full_name=_REPO_FULL_NAME,
            pr_number=1,
            head_sha="sha",
        )

    assert "5" in caplog.text
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_process_review_marks_failed_when_run_review_raises(caplog):
    from app.api.webhooks import _process_review

    mock_db = _make_mock_db()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "diff content"
    mock_http = _make_mock_http_client(mock_resp)

    with (
        patch("app.api.webhooks.AsyncSessionLocal", return_value=mock_db),
        patch("app.api.webhooks.httpx.AsyncClient", return_value=mock_http),
        patch(
            "app.api.webhooks.run_review",
            new=AsyncMock(side_effect=RuntimeError("LLM exploded")),
        ),
        patch("app.api.webhooks.settings") as mock_settings,
        caplog.at_level(logging.ERROR, logger="app.api.webhooks"),
    ):
        mock_settings.github_token = ""
        await _process_review(
            review_id=7,
            repo_full_name=_REPO_FULL_NAME,
            pr_number=1,
            head_sha="sha",
        )

    assert "7" in caplog.text
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_process_review_marks_failed_when_httpx_raises(caplog):
    from app.api.webhooks import _process_review

    mock_db = _make_mock_db()

    # Simulate the inner client raising on .get()
    client_instance = AsyncMock()
    client_instance.get = AsyncMock(side_effect=RuntimeError("network error"))
    mock_http = MagicMock()
    mock_http.__aenter__ = AsyncMock(return_value=client_instance)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.api.webhooks.AsyncSessionLocal", return_value=mock_db),
        patch("app.api.webhooks.httpx.AsyncClient", return_value=mock_http),
        patch("app.api.webhooks.settings") as mock_settings,
        caplog.at_level(logging.ERROR, logger="app.api.webhooks"),
    ):
        mock_settings.github_token = ""
        await _process_review(
            review_id=9,
            repo_full_name=_REPO_FULL_NAME,
            pr_number=1,
            head_sha="sha",
        )

    assert "9" in caplog.text
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_process_review_empty_diff_creates_no_comments():
    from app.api.webhooks import _process_review

    mock_db = _make_mock_db()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = ""
    mock_http = _make_mock_http_client(mock_resp)

    with (
        patch("app.api.webhooks.AsyncSessionLocal", return_value=mock_db),
        patch("app.api.webhooks.httpx.AsyncClient", return_value=mock_http),
        patch("app.api.webhooks.run_review", new=AsyncMock(return_value=[])),
        patch("app.api.webhooks.settings") as mock_settings,
    ):
        mock_settings.github_token = ""
        await _process_review(
            review_id=11,
            repo_full_name=_REPO_FULL_NAME,
            pr_number=1,
            head_sha="sha",
        )

    mock_db.add_all.assert_called_once()
    (comments,) = mock_db.add_all.call_args.args
    assert comments == []
