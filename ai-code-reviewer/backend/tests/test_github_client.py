"""Unit tests for the PyGithub client wrapper.

All network calls are mocked so no real GitHub token is required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from github import GithubException, UnknownObjectException

import app.github.client as gh_module
from app.github.client import get_file_content, get_pull_request, post_review_comment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_client():
    """Return a fresh MagicMock that acts as the Github() singleton."""
    return MagicMock()


# ---------------------------------------------------------------------------
# get_pull_request
# ---------------------------------------------------------------------------


def test_get_pull_request_returns_pr():
    mock_gh = _mock_client()
    mock_pr = MagicMock()
    mock_gh.get_repo.return_value.get_pull.return_value = mock_pr

    with patch.object(gh_module, "_gh", mock_gh):
        result = get_pull_request("owner/repo", 42)

    mock_gh.get_repo.assert_called_once_with("owner/repo")
    mock_gh.get_repo.return_value.get_pull.assert_called_once_with(42)
    assert result is mock_pr


# ---------------------------------------------------------------------------
# post_review_comment
# ---------------------------------------------------------------------------


def test_post_review_comment_success():
    mock_gh = _mock_client()
    mock_repo = mock_gh.get_repo.return_value
    mock_pr = mock_repo.get_pull.return_value
    mock_commit = mock_repo.get_commit.return_value

    with patch.object(gh_module, "_gh", mock_gh):
        post_review_comment(
            repo_full_name="owner/repo",
            pr_number=7,
            commit_id="abc123",
            path="src/main.py",
            line=10,
            body="Great catch!",
        )

    mock_pr.create_review_comment.assert_called_once_with(
        body="Great catch!",
        commit=mock_commit,
        path="src/main.py",
        line=10,
        side="RIGHT",
    )


def test_post_review_comment_github_exception_raises_runtime_error():
    mock_gh = _mock_client()
    mock_repo = mock_gh.get_repo.return_value
    mock_pr = mock_repo.get_pull.return_value
    mock_pr.create_review_comment.side_effect = GithubException(422, "Unprocessable", None)

    with patch.object(gh_module, "_gh", mock_gh):
        with pytest.raises(RuntimeError, match="Failed to post GitHub comment"):
            post_review_comment(
                repo_full_name="owner/repo",
                pr_number=7,
                commit_id="abc123",
                path="src/main.py",
                line=10,
                body="comment",
            )


# ---------------------------------------------------------------------------
# get_file_content — happy path
# ---------------------------------------------------------------------------


def test_get_file_content_returns_lines():
    mock_gh = _mock_client()
    mock_contents = MagicMock()
    mock_contents.decoded_content = b"line one\nline two\nline three"
    mock_gh.get_repo.return_value.get_contents.return_value = mock_contents

    with patch.object(gh_module, "_gh", mock_gh):
        lines = get_file_content("owner/repo", "src/main.py", "abc123")

    assert lines == ["line one", "line two", "line three"]


def test_get_file_content_empty_file_returns_empty_list():
    mock_gh = _mock_client()
    mock_contents = MagicMock()
    mock_contents.decoded_content = b""
    mock_gh.get_repo.return_value.get_contents.return_value = mock_contents

    with patch.object(gh_module, "_gh", mock_gh):
        lines = get_file_content("owner/repo", "README.md", "abc123")

    assert lines == []


# ---------------------------------------------------------------------------
# get_file_content — error paths
# ---------------------------------------------------------------------------


def test_get_file_content_file_not_found_returns_empty_list():
    mock_gh = _mock_client()
    mock_gh.get_repo.return_value.get_contents.side_effect = UnknownObjectException(
        404, "Not Found", None
    )

    with patch.object(gh_module, "_gh", mock_gh):
        lines = get_file_content("owner/repo", "missing.py", "abc123")

    assert lines == []


def test_get_file_content_github_exception_returns_empty_list():
    mock_gh = _mock_client()
    mock_gh.get_repo.return_value.get_contents.side_effect = GithubException(
        500, "Internal Server Error", None
    )

    with patch.object(gh_module, "_gh", mock_gh):
        lines = get_file_content("owner/repo", "src/main.py", "abc123")

    assert lines == []


def test_get_file_content_binary_file_returns_empty_list():
    mock_gh = _mock_client()
    mock_contents = MagicMock()
    # Simulate a file whose decoded_content is not valid UTF-8
    mock_contents.decoded_content = b"\xff\xfe binary \x00\x01"
    mock_gh.get_repo.return_value.get_contents.return_value = mock_contents

    with patch.object(gh_module, "_gh", mock_gh):
        lines = get_file_content("owner/repo", "image.png", "abc123")

    assert lines == []


def test_get_file_content_none_decoded_content_returns_empty_list():
    """Guard against contents objects that lack decoded_content (e.g. directories)."""
    mock_gh = _mock_client()
    mock_contents = MagicMock()
    mock_contents.decoded_content = None
    mock_gh.get_repo.return_value.get_contents.return_value = mock_contents

    with patch.object(gh_module, "_gh", mock_gh):
        lines = get_file_content("owner/repo", "somedir", "abc123")

    assert lines == []


# ---------------------------------------------------------------------------
# Lazy initialisation
# ---------------------------------------------------------------------------


def test_get_client_creates_singleton_on_first_call():
    """_get_client() must create the Github object lazily and reuse it."""
    original = gh_module._gh
    try:
        gh_module._gh = None  # reset so we exercise the lazy-init branch
        with patch("app.github.client.Github") as MockGithub, \
             patch("app.github.client.settings") as mock_settings:
            mock_settings.github_token = "tok"
            client1 = gh_module._get_client()
            client2 = gh_module._get_client()

        MockGithub.assert_called_once_with("tok")
        assert client1 is client2
    finally:
        gh_module._gh = original
