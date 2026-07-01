from __future__ import annotations

import logging

from app.core.diff_parser import DiffHunk, parse_diff
from app.core.llm import get_llm_provider
from app.core.llm.base import ReviewResult
from app.github import client as gh

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are an expert code reviewer. Analyze the following code diff and surrounding context,
then return a JSON object with an "issues" array.

Each issue must have these fields:
  - category: one of security | architecture | performance | style | bug
  - severity:  one of critical | warning | info
  - line:      the line number in the new file where the issue occurs
  - comment:   a concise explanation of the problem
  - suggestion: (optional) a concrete fix or refactored snippet

File: {file_path}

--- CONTEXT (lines {ctx_start}–{ctx_end}) ---
{context}

--- DIFF HUNK ---
{diff_hunk}

Return ONLY valid JSON. Example:
{{"issues": [{{"category": "security", "severity": "critical", "line": 42,
               "comment": "SQL injection risk", "suggestion": "use parameterised queries"}}]}}
"""


def _build_prompt(hunk: DiffHunk, context_lines: list[str]) -> str:
    ctx_start = max(1, hunk.start_line - 20)
    ctx_end = hunk.start_line + len(hunk.lines) + 20
    # Slice to ±20 lines around the hunk; ctx_start is 1-indexed.
    window = context_lines[ctx_start - 1 : ctx_end]
    hunk_text = "\n".join(
        f"{'+ ' if l.kind == 'added' else '- ' if l.kind == 'removed' else '  '}{l.content}"
        for l in hunk.lines
    )
    return _PROMPT_TEMPLATE.format(
        file_path=hunk.file_path,
        ctx_start=ctx_start,
        ctx_end=ctx_end,
        context="\n".join(window),
        diff_hunk=hunk_text,
    )


async def run_review(
    repo_full_name: str,
    pr_number: int,
    head_sha: str,
    unified_diff: str,
) -> list[ReviewResult]:
    hunks = parse_diff(unified_diff)
    all_results: list[ReviewResult] = []

    # Rate-limit fallback is handled transparently inside the provider returned
    # by get_llm_provider(); review_engine does not need to know about it.
    provider = get_llm_provider()

    for hunk in hunks:
        try:
            context_lines = gh.get_file_content(repo_full_name, hunk.file_path, head_sha)
        except Exception:
            context_lines = []

        prompt = _build_prompt(hunk, context_lines)

        try:
            results = await provider.review(prompt)
        except Exception as exc:
            logger.error("LLM review failed for hunk in %s: %s", hunk.file_path, exc)
            results = []

        for result in results:
            result.file_path = hunk.file_path

        for result in results:
            try:
                gh.post_review_comment(
                    repo_full_name=repo_full_name,
                    pr_number=pr_number,
                    commit_id=head_sha,
                    path=hunk.file_path,
                    line=_clamp_to_hunk(result.line, hunk),
                    body=_format_comment(result),
                )
                logger.info("Posted comment on %s line %s", hunk.file_path, result.line)
            except Exception as exc:
                logger.error("Failed to post comment on %s: %s", hunk.file_path, exc)

        all_results.extend(results)

    return all_results


def _clamp_to_hunk(line: int, hunk: DiffHunk) -> int:
    """Clamp an LLM-returned line number to the nearest line actually in the diff."""
    valid = [l.line_number for l in hunk.lines if l.kind in ("added", "context") and l.line_number > 0]
    if not valid:
        return hunk.start_line
    if line in valid:
        return line
    return min(valid, key=lambda x: abs(x - line))


def _format_comment(result: ReviewResult) -> str:
    badge = f"**[{result.category.upper()} / {result.severity.upper()}]**"
    body = f"{badge}\n\n{result.comment}"
    if result.suggestion:
        body += f"\n\n**Suggestion:**\n```\n{result.suggestion}\n```"
    return body
