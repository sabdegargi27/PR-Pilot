from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)

VALID_CATEGORIES = frozenset({"security", "architecture", "performance", "style", "bug"})
VALID_SEVERITIES = frozenset({"critical", "warning", "info"})


class ProviderRateLimitError(Exception):
    """Raised by an LLM provider when it enforces a rate limit.

    Wrapping provider-specific rate-limit errors in this common type lets the
    rest of the codebase react to rate limiting without importing Groq internals.
    """


@dataclass
class ReviewResult:
    category: str   # security | architecture | performance | style | bug
    severity: str   # critical | warning | info
    line: int
    comment: str
    suggestion: str | None = None
    file_path: str = ""  # populated by run_review from the enclosing hunk


class LLMProvider(ABC):
    @abstractmethod
    async def review(self, prompt: str) -> list[ReviewResult]:
        """Send a prompt and return a list of ReviewResult objects."""


def _parse_issues(data: dict) -> list[ReviewResult]:
    """Convert a parsed JSON dict (with an ``issues`` key) to ReviewResult objects.

    Unknown category/severity values are kept as-is and logged so operators
    can detect prompt drift without crashing the review pipeline.
    """
    results: list[ReviewResult] = []
    for issue in data.get("issues", []):
        category = issue.get("category", "style")
        severity = issue.get("severity", "info")
        if category not in VALID_CATEGORIES:
            logger.warning("Unexpected issue category %r; keeping as-is", category)
        if severity not in VALID_SEVERITIES:
            logger.warning("Unexpected issue severity %r; keeping as-is", severity)
        results.append(
            ReviewResult(
                category=category,
                severity=severity,
                line=int(issue.get("line", 1)),
                comment=issue.get("comment", ""),
                suggestion=issue.get("suggestion"),
            )
        )
    return results
