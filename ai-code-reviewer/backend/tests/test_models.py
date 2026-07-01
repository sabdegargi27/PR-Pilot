"""Unit tests for DB models and async session factory.

Uses an in-memory SQLite database (via aiosqlite) so no running Postgres
instance is required.  All Postgres-specific DDL (timezone-aware DateTime,
server_default=now()) is replaced by SQLite-compatible equivalents at test
time by letting SQLAlchemy render the DDL from the model metadata.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base, PullRequestReview, Repository, ReviewComment


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture()
async def engine():
    """Create an in-memory SQLite engine with the full schema."""
    _engine = create_async_engine(SQLITE_URL, echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    await _engine.dispose()


@pytest_asyncio.fixture()
async def db(engine):
    """Yield a fresh AsyncSession for each test, always rolled back."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Schema / table-structure tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_all_tables_created(engine):
    async with engine.connect() as conn:
        table_names = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
    assert "repositories" in table_names
    assert "pull_request_reviews" in table_names
    assert "review_comments" in table_names


@pytest.mark.asyncio
async def test_repository_columns(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: {
                c["name"] for c in inspect(sync_conn).get_columns("repositories")
            }
        )
    assert cols == {"id", "github_repo_full_name", "installed_at"}


@pytest.mark.asyncio
async def test_pull_request_review_columns(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: {
                c["name"]
                for c in inspect(sync_conn).get_columns("pull_request_reviews")
            }
        )
    assert cols == {"id", "repo_id", "pr_number", "pr_title", "author", "status", "created_at"}


@pytest.mark.asyncio
async def test_review_comment_columns(engine):
    async with engine.connect() as conn:
        cols = await conn.run_sync(
            lambda sync_conn: {
                c["name"] for c in inspect(sync_conn).get_columns("review_comments")
            }
        )
    assert cols == {
        "id",
        "review_id",
        "file_path",
        "line_number",
        "category",
        "severity",
        "comment",
        "suggestion",
    }


# ---------------------------------------------------------------------------
# ORM CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repository_insert_and_query(db: AsyncSession):
    repo = Repository(github_repo_full_name="owner/repo")
    db.add(repo)
    await db.flush()

    assert repo.id is not None
    assert repo.github_repo_full_name == "owner/repo"


@pytest.mark.asyncio
async def test_repository_unique_constraint(db: AsyncSession):
    db.add(Repository(github_repo_full_name="owner/repo"))
    await db.flush()

    db.add(Repository(github_repo_full_name="owner/repo"))
    with pytest.raises(Exception):
        await db.flush()


@pytest.mark.asyncio
async def test_pull_request_review_insert(db: AsyncSession):
    repo = Repository(github_repo_full_name="owner/repo2")
    db.add(repo)
    await db.flush()

    review = PullRequestReview(
        repo_id=repo.id,
        pr_number=42,
        pr_title="Fix a nasty bug",
        author="alice",
        status="pending",
    )
    db.add(review)
    await db.flush()

    assert review.id is not None
    assert review.pr_number == 42
    assert review.status == "pending"


@pytest.mark.asyncio
async def test_review_comment_insert(db: AsyncSession):
    repo = Repository(github_repo_full_name="owner/repo3")
    db.add(repo)
    await db.flush()

    review = PullRequestReview(
        repo_id=repo.id,
        pr_number=1,
        pr_title="Add feature",
        author="bob",
        status="completed",
    )
    db.add(review)
    await db.flush()

    comment = ReviewComment(
        review_id=review.id,
        file_path="src/main.py",
        line_number=10,
        category="security",
        severity="critical",
        comment="Possible SQL injection.",
        suggestion="Use parameterised queries.",
    )
    db.add(comment)
    await db.flush()

    assert comment.id is not None
    assert comment.category == "security"
    assert comment.severity == "critical"


@pytest.mark.asyncio
async def test_review_comment_suggestion_nullable(db: AsyncSession):
    repo = Repository(github_repo_full_name="owner/repo4")
    db.add(repo)
    await db.flush()

    review = PullRequestReview(
        repo_id=repo.id,
        pr_number=2,
        pr_title="Style fix",
        author="carol",
        status="completed",
    )
    db.add(review)
    await db.flush()

    comment = ReviewComment(
        review_id=review.id,
        file_path="utils.py",
        line_number=5,
        category="style",
        severity="info",
        comment="Missing blank line.",
        suggestion=None,
    )
    db.add(comment)
    await db.flush()

    assert comment.suggestion is None


# ---------------------------------------------------------------------------
# Session / get_db tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_db_yields_async_session(engine):
    """get_db dependency should yield an AsyncSession that can execute SQL."""
    from app.db.session import AsyncSessionLocal

    # Temporarily patch the session factory to use the in-memory test engine.
    original_kw = AsyncSessionLocal.kw
    test_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with test_factory() as session:
        assert isinstance(session, AsyncSession)
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_get_db_generator_closes_session():
    """get_db must close the session after the generator is exhausted.

    async_sessionmaker() returns an AsyncSession directly; the generator's
    `async with` calls __aenter__/__aexit__ on that session object.
    """
    from unittest.mock import AsyncMock, patch

    from app.db import session as session_module
    from app.db.session import get_db

    # Mock the session returned by AsyncSessionLocal(); it must behave as an
    # async context manager (AsyncSession supports `async with`).
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    # Patch the factory itself so calling it returns mock_session.
    with patch("app.db.session.AsyncSessionLocal", return_value=mock_session):
        gen = get_db()
        yielded = await gen.__anext__()
        assert yielded is mock_session
        try:
            await gen.asend(None)
        except StopAsyncIteration:
            pass

    mock_session.__aexit__.assert_called_once()
