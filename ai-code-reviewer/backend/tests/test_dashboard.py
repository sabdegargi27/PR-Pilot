"""Unit tests for the dashboard REST API endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PullRequestReview, Repository, ReviewComment

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

_REPO = Repository(id=1, github_repo_full_name="owner/repo", installed_at=_NOW)
_REVIEW = PullRequestReview(
    id=10,
    repo_id=1,
    pr_number=42,
    pr_title="Fix bug",
    author="dev",
    status="completed",
    created_at=_NOW,
)
_COMMENT = ReviewComment(
    id=100,
    review_id=10,
    file_path="src/main.py",
    line_number=7,
    category="bug",
    severity="critical",
    comment="Null dereference",
    suggestion="Add a None check",
)


def _scalar_result(*values):
    """Return a MagicMock whose .scalars().all() yields *values*."""
    mock = MagicMock()
    mock.scalars.return_value.all.return_value = list(values)
    mock.scalar_one_or_none.return_value = values[0] if values else None
    mock.scalar_one.return_value = values[0] if values else 0
    return mock


def _rows_result(*rows):
    """Return a MagicMock whose .all() yields *rows* (tuples)."""
    mock = MagicMock()
    mock.all.return_value = list(rows)
    return mock


@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    db.__aenter__.return_value = db
    return db


@pytest.fixture
def app_client(mock_db):
    from app.main import app
    from app.db.session import get_db

    async def _override():
        yield mock_db

    app.dependency_overrides[get_db] = _override
    yield app
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/repos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_repos_returns_all_repos(app_client, mock_db):
    mock_db.execute.return_value = _scalar_result(_REPO)

    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get("/api/repos")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["full_name"] == "owner/repo"
    assert data[0]["id"] == 1


@pytest.mark.asyncio
async def test_list_repos_returns_empty_list_when_none(app_client, mock_db):
    mock_db.execute.return_value = _scalar_result()

    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get("/api/repos")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /api/repos/{owner}/{repo}/reviews
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_reviews_returns_paginated_items(app_client, mock_db):
    # Calls: (1) _get_repo, (2) total count, (3) reviews+issue_counts join
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = _REPO

    total_result = MagicMock()
    total_result.scalar_one.return_value = 1

    # The join query returns rows of (PullRequestReview, issue_count)
    join_result = MagicMock()
    join_result.all.return_value = [(_REVIEW, 3)]

    mock_db.execute.side_effect = [repo_result, total_result, join_result]

    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get("/api/repos/owner/repo/reviews")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["pr_number"] == 42
    assert item["issue_count"] == 3
    assert item["status"] == "completed"


@pytest.mark.asyncio
async def test_list_reviews_uses_page_and_page_size(app_client, mock_db):
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = _REPO

    total_result = MagicMock()
    total_result.scalar_one.return_value = 50

    join_result = MagicMock()
    join_result.all.return_value = []

    mock_db.execute.side_effect = [repo_result, total_result, join_result]

    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get("/api/repos/owner/repo/reviews?page=3&page_size=10")

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 3
    assert body["page_size"] == 10
    assert body["total"] == 50


@pytest.mark.asyncio
async def test_list_reviews_returns_404_for_unknown_repo(app_client, mock_db):
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = None

    mock_db.execute.return_value = repo_result

    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get("/api/repos/unknown/repo/reviews")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/repos/{owner}/{repo}/metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_metrics_returns_empty_when_no_reviews(app_client, mock_db):
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = _REPO

    # review_ids query returns no rows
    ids_result = MagicMock()
    ids_result.all.return_value = []

    mock_db.execute.side_effect = [repo_result, ids_result]

    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get("/api/repos/owner/repo/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["by_category"] == {}
    assert body["by_severity"] == {}
    assert body["trend"] == []


@pytest.mark.asyncio
async def test_get_metrics_aggregates_by_category_and_severity(app_client, mock_db):
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = _REPO

    ids_result = MagicMock()
    ids_result.all.return_value = [(10,), (11,)]

    cat_result = MagicMock()
    cat_result.all.return_value = [("bug", 3), ("security", 1)]

    sev_result = MagicMock()
    sev_result.all.return_value = [("critical", 2), ("warning", 2)]

    total_result = MagicMock()
    total_result.scalar_one.return_value = 4

    # _build_trend: reviews + sev_per_review
    trend_reviews = MagicMock()
    trend_reviews.all.return_value = [(10, 42, _NOW), (11, 43, _NOW)]

    trend_sev = MagicMock()
    trend_sev.all.return_value = [(10, "critical", 2), (11, "warning", 2)]

    mock_db.execute.side_effect = [
        repo_result,
        ids_result,
        cat_result,
        sev_result,
        total_result,
        trend_reviews,
        trend_sev,
    ]

    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get("/api/repos/owner/repo/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert body["by_category"] == {"bug": 3, "security": 1}
    assert body["by_severity"] == {"critical": 2, "warning": 2}
    assert len(body["trend"]) == 2
    assert body["trend"][0]["review_id"] == 10
    assert body["trend"][0]["by_severity"] == {"critical": 2}
    assert body["trend"][1]["by_severity"] == {"warning": 2}


@pytest.mark.asyncio
async def test_get_metrics_returns_404_for_unknown_repo(app_client, mock_db):
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = repo_result

    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get("/api/repos/unknown/repo/metrics")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/reviews/{review_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_review_returns_detail_with_comments(app_client, mock_db):
    review_result = MagicMock()
    review_result.scalar_one_or_none.return_value = _REVIEW

    comments_result = MagicMock()
    comments_result.scalars.return_value.all.return_value = [_COMMENT]

    mock_db.execute.side_effect = [review_result, comments_result]

    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get("/api/reviews/10")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 10
    assert body["pr_number"] == 42
    assert len(body["comments"]) == 1
    c = body["comments"][0]
    assert c["category"] == "bug"
    assert c["severity"] == "critical"
    assert c["suggestion"] == "Add a None check"


@pytest.mark.asyncio
async def test_get_review_returns_empty_comments_list(app_client, mock_db):
    review_result = MagicMock()
    review_result.scalar_one_or_none.return_value = _REVIEW

    comments_result = MagicMock()
    comments_result.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [review_result, comments_result]

    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get("/api/reviews/10")

    assert response.status_code == 200
    assert response.json()["comments"] == []


@pytest.mark.asyncio
async def test_get_review_returns_404_when_not_found(app_client, mock_db):
    review_result = MagicMock()
    review_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = review_result

    async with AsyncClient(
        transport=ASGITransport(app=app_client), base_url="http://test"
    ) as client:
        response = await client.get("/api/reviews/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Review not found"


# ---------------------------------------------------------------------------
# _get_repo helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_repo_raises_404_with_full_name_in_detail():
    from app.api.dashboard import _get_repo
    from fastapi import HTTPException

    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await _get_repo(db, "foo", "bar")

    assert exc_info.value.status_code == 404
    assert "foo/bar" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_repo_returns_repo_when_found():
    from app.api.dashboard import _get_repo

    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = _REPO
    db.execute.return_value = result

    repo = await _get_repo(db, "owner", "repo")
    assert repo is _REPO
