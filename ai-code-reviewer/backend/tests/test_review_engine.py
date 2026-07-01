"""Unit tests for the review engine."""
from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.diff_parser import DiffHunk, DiffLine
from app.core.llm.base import ReviewResult
from app.core.review_engine import _build_prompt, _format_comment, run_review

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SIMPLE_DIFF = """\
--- a/foo.py
+++ b/foo.py
@@ -1,2 +1,3 @@
 def hello():
+    print("hi")
     pass
"""

_RESULT = ReviewResult(
    category="bug",
    severity="critical",
    line=2,
    comment="This is a bug",
    suggestion="Fix it like this",
)

_RESULT_NO_SUGGESTION = ReviewResult(
    category="style",
    severity="info",
    line=3,
    comment="Style issue",
)


def _make_hunk(
    file_path: str = "foo.py",
    start_line: int = 1,
    lines: list[DiffLine] | None = None,
) -> DiffHunk:
    if lines is None:
        lines = [DiffLine(content="x = 1", line_number=1, kind="added")]
    return DiffHunk(file_path=file_path, start_line=start_line, lines=lines)


# ---------------------------------------------------------------------------
# _format_comment
# ---------------------------------------------------------------------------


def test_format_comment_with_suggestion_includes_all_parts():
    body = _format_comment(_RESULT)
    assert "**[BUG / CRITICAL]**" in body
    assert "This is a bug" in body
    assert "Fix it like this" in body
    assert "```" in body


def test_format_comment_without_suggestion_omits_suggestion_block():
    body = _format_comment(_RESULT_NO_SUGGESTION)
    assert "**[STYLE / INFO]**" in body
    assert "Style issue" in body
    assert "Suggestion" not in body
    assert "```" not in body


def test_format_comment_badge_uses_uppercase_category_and_severity():
    result = ReviewResult(category="security", severity="warning", line=1, comment="x")
    body = _format_comment(result)
    assert "**[SECURITY / WARNING]**" in body


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_includes_file_path():
    hunk = _make_hunk(file_path="src/auth.py")
    prompt = _build_prompt(hunk, [])
    assert "src/auth.py" in prompt


def test_build_prompt_includes_added_lines():
    hunk = _make_hunk(
        lines=[DiffLine("new_code()", line_number=5, kind="added")]
    )
    prompt = _build_prompt(hunk, [])
    assert "+ new_code()" in prompt


def test_build_prompt_includes_removed_lines():
    hunk = _make_hunk(
        lines=[DiffLine("old_code()", line_number=5, kind="removed")]
    )
    prompt = _build_prompt(hunk, [])
    assert "- old_code()" in prompt


def test_build_prompt_includes_context_lines():
    hunk = _make_hunk(
        lines=[DiffLine("unchanged()", line_number=5, kind="context")]
    )
    prompt = _build_prompt(hunk, [])
    assert "  unchanged()" in prompt


def test_build_prompt_shows_context_range():
    # hunk starts at line 30 → ctx_start = max(1, 30-20) = 10
    hunk = _make_hunk(start_line=30)
    prompt = _build_prompt(hunk, [])
    assert "10" in prompt


def test_build_prompt_ctx_start_floored_at_one():
    # hunk starts at line 5, so ctx_start = max(1, 5-20) = 1
    hunk = _make_hunk(start_line=5)
    prompt = _build_prompt(hunk, [])
    assert "1–" in prompt


def test_build_prompt_slices_context_window():
    # File has 100 lines; hunk starts at line 10.
    # ctx_start = max(1, 10-20) = 1, ctx_end = 10 + 1 + 20 = 31
    # So we expect lines 0–30 (indices), i.e. first 31 lines, not all 100.
    context_lines = [f"line{i}" for i in range(1, 101)]
    hunk = _make_hunk(start_line=10, lines=[DiffLine("x", 10, "added")])
    prompt = _build_prompt(hunk, context_lines)
    assert "line1" in prompt
    assert "line31" in prompt
    assert "line50" not in prompt  # beyond window


def test_build_prompt_context_window_centered_on_hunk():
    # hunk at line 50; ctx_start = 30, ctx_end = 50 + 1 + 20 = 71
    context_lines = [f"line{i}" for i in range(1, 101)]
    hunk = _make_hunk(start_line=50, lines=[DiffLine("x", 50, "added")])
    prompt = _build_prompt(hunk, context_lines)
    assert "line30" in prompt
    assert "line71" in prompt
    # line 1 is before the window (ctx_start=30)
    assert "line1" not in prompt
    # line 80 is after the window (ctx_end=71)
    assert "line80" not in prompt


def test_build_prompt_empty_context_lines_produces_valid_prompt():
    hunk = _make_hunk()
    prompt = _build_prompt(hunk, [])
    assert "DIFF HUNK" in prompt
    assert "CONTEXT" in prompt


def test_build_prompt_returns_only_valid_json_instruction():
    hunk = _make_hunk()
    prompt = _build_prompt(hunk, [])
    assert "Return ONLY valid JSON" in prompt


# ---------------------------------------------------------------------------
# run_review — happy path
# ---------------------------------------------------------------------------


async def test_run_review_returns_results_from_llm():
    mock_provider = AsyncMock()
    mock_provider.review.return_value = [_RESULT]

    with (
        patch("app.core.review_engine.parse_diff") as mock_parse,
        patch("app.core.review_engine.get_llm_provider", return_value=mock_provider),
        patch("app.core.review_engine.gh.get_file_content", return_value=[]),
        patch("app.core.review_engine.gh.post_review_comment"),
    ):
        mock_parse.return_value = [_make_hunk()]
        results = await run_review("owner/repo", 1, "abc123", "diff content")

    assert len(results) == 1
    assert results[0].category == "bug"


async def test_run_review_posts_comment_for_each_result():
    mock_provider = AsyncMock()
    mock_provider.review.return_value = [_RESULT, _RESULT_NO_SUGGESTION]

    with (
        patch("app.core.review_engine.parse_diff") as mock_parse,
        patch("app.core.review_engine.get_llm_provider", return_value=mock_provider),
        patch("app.core.review_engine.gh.get_file_content", return_value=[]),
        patch("app.core.review_engine.gh.post_review_comment") as mock_post,
    ):
        mock_parse.return_value = [_make_hunk()]
        await run_review("owner/repo", 1, "abc123", "diff")

    assert mock_post.call_count == 2


async def test_run_review_passes_correct_args_to_post_comment():
    mock_provider = AsyncMock()
    mock_provider.review.return_value = [_RESULT]

    with (
        patch("app.core.review_engine.parse_diff") as mock_parse,
        patch("app.core.review_engine.get_llm_provider", return_value=mock_provider),
        patch("app.core.review_engine.gh.get_file_content", return_value=[]),
        patch("app.core.review_engine.gh.post_review_comment") as mock_post,
    ):
        # Hunk includes line 2 as an added line so _clamp_to_hunk doesn't adjust it.
        mock_parse.return_value = [
            _make_hunk(
                file_path="foo.py",
                lines=[DiffLine(content="x = 1", line_number=_RESULT.line, kind="added")],
            )
        ]
        await run_review("owner/repo", 42, "sha999", "diff")

    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["repo_full_name"] == "owner/repo"
    assert call_kwargs["pr_number"] == 42
    assert call_kwargs["commit_id"] == "sha999"
    assert call_kwargs["path"] == "foo.py"
    assert call_kwargs["line"] == _RESULT.line


async def test_run_review_multiple_hunks_reviews_each():
    mock_provider = AsyncMock()
    mock_provider.review.return_value = [_RESULT]

    hunk_a = _make_hunk(file_path="a.py")
    hunk_b = _make_hunk(file_path="b.py")

    with (
        patch("app.core.review_engine.parse_diff") as mock_parse,
        patch("app.core.review_engine.get_llm_provider", return_value=mock_provider),
        patch("app.core.review_engine.gh.get_file_content", return_value=[]),
        patch("app.core.review_engine.gh.post_review_comment"),
    ):
        mock_parse.return_value = [hunk_a, hunk_b]
        results = await run_review("owner/repo", 1, "sha", "diff")

    assert mock_provider.review.await_count == 2
    assert len(results) == 2


async def test_run_review_empty_diff_returns_empty_list():
    mock_provider = AsyncMock()

    with (
        patch("app.core.review_engine.parse_diff") as mock_parse,
        patch("app.core.review_engine.get_llm_provider", return_value=mock_provider),
        patch("app.core.review_engine.gh.get_file_content", return_value=[]),
        patch("app.core.review_engine.gh.post_review_comment"),
    ):
        mock_parse.return_value = []
        results = await run_review("owner/repo", 1, "sha", "")

    assert results == []
    mock_provider.review.assert_not_awaited()


# ---------------------------------------------------------------------------
# run_review — resilience
# ---------------------------------------------------------------------------


async def test_run_review_continues_when_get_file_content_raises():
    mock_provider = AsyncMock()
    mock_provider.review.return_value = [_RESULT]

    with (
        patch("app.core.review_engine.parse_diff") as mock_parse,
        patch("app.core.review_engine.get_llm_provider", return_value=mock_provider),
        patch(
            "app.core.review_engine.gh.get_file_content",
            side_effect=RuntimeError("network error"),
        ),
        patch("app.core.review_engine.gh.post_review_comment"),
    ):
        mock_parse.return_value = [_make_hunk()]
        results = await run_review("owner/repo", 1, "sha", "diff")

    # Review still runs despite failed context fetch
    assert len(results) == 1
    mock_provider.review.assert_awaited_once()


async def test_run_review_continues_when_llm_raises(caplog):
    mock_provider = AsyncMock()
    mock_provider.review.side_effect = RuntimeError("LLM unavailable")

    with (
        patch("app.core.review_engine.parse_diff") as mock_parse,
        patch("app.core.review_engine.get_llm_provider", return_value=mock_provider),
        patch("app.core.review_engine.gh.get_file_content", return_value=[]),
        patch("app.core.review_engine.gh.post_review_comment"),
        caplog.at_level(logging.ERROR, logger="app.core.review_engine"),
    ):
        mock_parse.return_value = [_make_hunk(file_path="err.py")]
        results = await run_review("owner/repo", 1, "sha", "diff")

    assert results == []
    assert "err.py" in caplog.text


async def test_run_review_continues_when_post_comment_raises(caplog):
    mock_provider = AsyncMock()
    mock_provider.review.return_value = [_RESULT]

    with (
        patch("app.core.review_engine.parse_diff") as mock_parse,
        patch("app.core.review_engine.get_llm_provider", return_value=mock_provider),
        patch("app.core.review_engine.gh.get_file_content", return_value=[]),
        patch(
            "app.core.review_engine.gh.post_review_comment",
            side_effect=RuntimeError("GitHub API error"),
        ),
        caplog.at_level(logging.ERROR, logger="app.core.review_engine"),
    ):
        mock_parse.return_value = [_make_hunk()]
        results = await run_review("owner/repo", 1, "sha", "diff")

    # Results are still returned even if posting fails
    assert len(results) == 1
    assert "Failed to post comment" in caplog.text


async def test_run_review_second_hunk_runs_after_first_hunk_llm_fails():
    mock_provider = AsyncMock()
    mock_provider.review.side_effect = [
        RuntimeError("first hunk LLM failed"),
        [_RESULT],
    ]

    hunk_a = _make_hunk(file_path="a.py")
    hunk_b = _make_hunk(file_path="b.py")

    with (
        patch("app.core.review_engine.parse_diff") as mock_parse,
        patch("app.core.review_engine.get_llm_provider", return_value=mock_provider),
        patch("app.core.review_engine.gh.get_file_content", return_value=[]),
        patch("app.core.review_engine.gh.post_review_comment"),
    ):
        mock_parse.return_value = [hunk_a, hunk_b]
        results = await run_review("owner/repo", 1, "sha", "diff")

    # Second hunk still produces a result
    assert len(results) == 1
    assert mock_provider.review.await_count == 2


# ---------------------------------------------------------------------------
# run_review — LLM returns no issues
# ---------------------------------------------------------------------------


async def test_run_review_llm_returns_empty_list_no_comments_posted():
    mock_provider = AsyncMock()
    mock_provider.review.return_value = []

    with (
        patch("app.core.review_engine.parse_diff") as mock_parse,
        patch("app.core.review_engine.get_llm_provider", return_value=mock_provider),
        patch("app.core.review_engine.gh.get_file_content", return_value=[]),
        patch("app.core.review_engine.gh.post_review_comment") as mock_post,
    ):
        mock_parse.return_value = [_make_hunk()]
        results = await run_review("owner/repo", 1, "sha", "diff")

    assert results == []
    mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# run_review — context lines passed to prompt builder
# ---------------------------------------------------------------------------


async def test_run_review_passes_file_content_to_prompt():
    """Verify that the context fetched from GitHub is forwarded to the LLM."""
    mock_provider = AsyncMock()
    mock_provider.review.return_value = []
    captured_prompts: list[str] = []

    async def capture_review(prompt: str) -> list[ReviewResult]:
        captured_prompts.append(prompt)
        return []

    mock_provider.review.side_effect = capture_review
    file_content = ["line1", "line2", "import_secret_stuff"]

    with (
        patch("app.core.review_engine.parse_diff") as mock_parse,
        patch("app.core.review_engine.get_llm_provider", return_value=mock_provider),
        patch(
            "app.core.review_engine.gh.get_file_content",
            return_value=file_content,
        ),
        patch("app.core.review_engine.gh.post_review_comment"),
    ):
        mock_parse.return_value = [_make_hunk(start_line=1)]
        await run_review("owner/repo", 1, "sha", "diff")

    assert len(captured_prompts) == 1
    assert "line1" in captured_prompts[0]
    assert "import_secret_stuff" in captured_prompts[0]
