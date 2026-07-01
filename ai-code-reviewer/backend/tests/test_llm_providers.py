"""Unit tests for the LLM provider abstraction layer.

Covers: ReviewResult, _parse_issues, GroqProvider, OllamaProvider,
FallbackProvider, and the get_llm_provider factory.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.llm import FallbackProvider, get_llm_provider
from app.core.llm.base import (
    VALID_CATEGORIES,
    VALID_SEVERITIES,
    LLMProvider,
    ProviderRateLimitError,
    ReviewResult,
    _parse_issues,
)
from app.core.llm.groq_provider import GroqProvider
from app.core.llm.ollama_provider import OllamaProvider


# ---------------------------------------------------------------------------
# ReviewResult
# ---------------------------------------------------------------------------


def test_review_result_required_fields_are_set():
    r = ReviewResult(category="bug", severity="critical", line=10, comment="null deref")
    assert r.category == "bug"
    assert r.severity == "critical"
    assert r.line == 10
    assert r.comment == "null deref"
    assert r.suggestion is None


def test_review_result_with_suggestion():
    r = ReviewResult(
        category="security",
        severity="warning",
        line=5,
        comment="SQL injection",
        suggestion="use parameterised queries",
    )
    assert r.suggestion == "use parameterised queries"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_valid_categories_contains_expected_values():
    assert VALID_CATEGORIES == {"security", "architecture", "performance", "style", "bug"}


def test_valid_severities_contains_expected_values():
    assert VALID_SEVERITIES == {"critical", "warning", "info"}


# ---------------------------------------------------------------------------
# _parse_issues
# ---------------------------------------------------------------------------


def test_parse_issues_happy_path_returns_all_fields():
    data = {
        "issues": [
            {
                "category": "bug",
                "severity": "critical",
                "line": 42,
                "comment": "null pointer",
                "suggestion": "check for None first",
            },
            {
                "category": "style",
                "severity": "info",
                "line": 7,
                "comment": "missing blank line",
            },
        ]
    }
    results = _parse_issues(data)
    assert len(results) == 2
    assert results[0].category == "bug"
    assert results[0].line == 42
    assert results[0].suggestion == "check for None first"
    assert results[1].suggestion is None


def test_parse_issues_empty_array_returns_empty_list():
    assert _parse_issues({"issues": []}) == []


def test_parse_issues_missing_issues_key_returns_empty_list():
    assert _parse_issues({}) == []


def test_parse_issues_missing_fields_use_defaults():
    results = _parse_issues({"issues": [{}]})
    assert len(results) == 1
    assert results[0].category == "style"
    assert results[0].severity == "info"
    assert results[0].line == 1
    assert results[0].comment == ""
    assert results[0].suggestion is None


def test_parse_issues_line_is_coerced_to_int():
    results = _parse_issues(
        {"issues": [{"category": "bug", "severity": "info", "line": "99", "comment": "x"}]}
    )
    assert results[0].line == 99
    assert isinstance(results[0].line, int)


def test_parse_issues_unknown_category_is_kept_and_logged(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="app.core.llm.base"):
        results = _parse_issues(
            {"issues": [{"category": "unknown_cat", "severity": "info", "line": 1, "comment": "x"}]}
        )
    assert results[0].category == "unknown_cat"
    assert "unknown_cat" in caplog.text


def test_parse_issues_unknown_severity_is_kept_and_logged(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="app.core.llm.base"):
        results = _parse_issues(
            {"issues": [{"category": "bug", "severity": "unknown_sev", "line": 1, "comment": "x"}]}
        )
    assert results[0].severity == "unknown_sev"
    assert "unknown_sev" in caplog.text


# ---------------------------------------------------------------------------
# GroqProvider
# ---------------------------------------------------------------------------


def _make_groq_response(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


async def test_groq_provider_review_returns_parsed_results():
    payload = json.dumps(
        {"issues": [{"category": "security", "severity": "critical", "line": 5, "comment": "SQL injection"}]}
    )
    with patch("app.core.llm.groq_provider.AsyncGroq") as MockGroq:
        MockGroq.return_value.chat.completions.create = AsyncMock(
            return_value=_make_groq_response(payload)
        )
        provider = GroqProvider()
        results = await provider.review("some prompt")

    assert len(results) == 1
    assert results[0].category == "security"
    assert results[0].severity == "critical"
    assert results[0].line == 5


async def test_groq_provider_review_rate_limit_raises_provider_rate_limit_error():
    # Replace the imported exception name with a plain Exception subclass so we
    # can raise it without constructing Groq's internal httpx-backed objects.
    FakeRateLimitError = type("RateLimitError", (Exception,), {})

    with patch("app.core.llm.groq_provider.GroqRateLimitError", FakeRateLimitError), \
         patch("app.core.llm.groq_provider.AsyncGroq") as MockGroq:
        MockGroq.return_value.chat.completions.create = AsyncMock(
            side_effect=FakeRateLimitError("rate limited")
        )
        provider = GroqProvider()
        with pytest.raises(ProviderRateLimitError):
            await provider.review("prompt")


async def test_groq_provider_review_invalid_json_returns_empty_list():
    with patch("app.core.llm.groq_provider.AsyncGroq") as MockGroq:
        MockGroq.return_value.chat.completions.create = AsyncMock(
            return_value=_make_groq_response("not valid json {{{")
        )
        provider = GroqProvider()
        results = await provider.review("prompt")

    assert results == []


async def test_groq_provider_review_none_content_returns_empty_list():
    with patch("app.core.llm.groq_provider.AsyncGroq") as MockGroq:
        MockGroq.return_value.chat.completions.create = AsyncMock(
            return_value=_make_groq_response(None)  # type: ignore[arg-type]
        )
        provider = GroqProvider()
        results = await provider.review("prompt")

    assert results == []


async def test_groq_provider_review_empty_issues_array_returns_empty_list():
    with patch("app.core.llm.groq_provider.AsyncGroq") as MockGroq:
        MockGroq.return_value.chat.completions.create = AsyncMock(
            return_value=_make_groq_response(json.dumps({"issues": []}))
        )
        provider = GroqProvider()
        results = await provider.review("prompt")

    assert results == []


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


def _make_ollama_client_mock(json_body: dict) -> tuple[MagicMock, MagicMock]:
    """Return (MockAsyncClient class, configured mock response)."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_body
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)

    MockAsyncClient = MagicMock()
    MockAsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    MockAsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

    return MockAsyncClient, mock_resp


async def test_ollama_provider_review_returns_parsed_results():
    issues = [{"category": "performance", "severity": "warning", "line": 20, "comment": "slow loop"}]
    MockAsyncClient, _ = _make_ollama_client_mock(
        {"response": json.dumps({"issues": issues})}
    )

    with patch("app.core.llm.ollama_provider.httpx.AsyncClient", MockAsyncClient):
        provider = OllamaProvider()
        results = await provider.review("prompt")

    assert len(results) == 1
    assert results[0].category == "performance"
    assert results[0].line == 20


async def test_ollama_provider_review_invalid_json_returns_empty_list():
    MockAsyncClient, _ = _make_ollama_client_mock({"response": "not json {{{"})

    with patch("app.core.llm.ollama_provider.httpx.AsyncClient", MockAsyncClient):
        provider = OllamaProvider()
        results = await provider.review("prompt")

    assert results == []


async def test_ollama_provider_review_missing_response_key_returns_empty_list():
    # When Ollama returns a dict without "response", we treat it as an empty object.
    MockAsyncClient, _ = _make_ollama_client_mock({})

    with patch("app.core.llm.ollama_provider.httpx.AsyncClient", MockAsyncClient):
        provider = OllamaProvider()
        results = await provider.review("prompt")

    assert results == []


async def test_ollama_provider_review_http_error_propagates():
    import httpx

    MockAsyncClient = MagicMock()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    MockAsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    MockAsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.llm.ollama_provider.httpx.AsyncClient", MockAsyncClient):
        provider = OllamaProvider()
        with pytest.raises(httpx.ConnectError):
            await provider.review("prompt")


# ---------------------------------------------------------------------------
# FallbackProvider
# ---------------------------------------------------------------------------


async def test_fallback_provider_uses_primary_when_successful():
    primary = AsyncMock(spec=LLMProvider)
    fallback = AsyncMock(spec=LLMProvider)
    primary.review.return_value = [
        ReviewResult(category="bug", severity="info", line=1, comment="x")
    ]

    provider = FallbackProvider(primary=primary, fallback=fallback)
    results = await provider.review("prompt")

    primary.review.assert_awaited_once_with("prompt")
    fallback.review.assert_not_awaited()
    assert len(results) == 1


async def test_fallback_provider_switches_to_fallback_on_rate_limit():
    primary = AsyncMock(spec=LLMProvider)
    fallback = AsyncMock(spec=LLMProvider)
    primary.review.side_effect = ProviderRateLimitError("rate limited")
    fallback.review.return_value = [
        ReviewResult(category="style", severity="info", line=2, comment="y")
    ]

    provider = FallbackProvider(primary=primary, fallback=fallback)
    results = await provider.review("prompt")

    primary.review.assert_awaited_once_with("prompt")
    fallback.review.assert_awaited_once_with("prompt")
    assert len(results) == 1
    assert results[0].category == "style"


async def test_fallback_provider_propagates_non_rate_limit_errors():
    primary = AsyncMock(spec=LLMProvider)
    fallback = AsyncMock(spec=LLMProvider)
    primary.review.side_effect = RuntimeError("unexpected crash")

    provider = FallbackProvider(primary=primary, fallback=fallback)
    with pytest.raises(RuntimeError, match="unexpected crash"):
        await provider.review("prompt")

    fallback.review.assert_not_awaited()


async def test_fallback_provider_passes_prompt_to_fallback_unchanged():
    primary = AsyncMock(spec=LLMProvider)
    fallback = AsyncMock(spec=LLMProvider)
    primary.review.side_effect = ProviderRateLimitError("rate limited")
    fallback.review.return_value = []

    provider = FallbackProvider(primary=primary, fallback=fallback)
    await provider.review("my specific prompt")

    fallback.review.assert_awaited_once_with("my specific prompt")


# ---------------------------------------------------------------------------
# get_llm_provider factory
# ---------------------------------------------------------------------------


def test_get_llm_provider_groq_returns_fallback_provider():
    with patch("app.core.llm.groq_provider.AsyncGroq"), \
         patch("app.core.llm.settings") as mock_settings:
        mock_settings.llm_provider = "groq"
        mock_settings.groq_api_key = "test-key"
        provider = get_llm_provider()

    assert isinstance(provider, FallbackProvider)
    assert isinstance(provider._primary, GroqProvider)
    assert isinstance(provider._fallback, OllamaProvider)


def test_get_llm_provider_ollama_returns_ollama_provider():
    with patch("app.core.llm.settings") as mock_settings:
        mock_settings.llm_provider = "ollama"
        provider = get_llm_provider()

    assert isinstance(provider, OllamaProvider)


def test_get_llm_provider_unknown_value_defaults_to_fallback_provider():
    with patch("app.core.llm.groq_provider.AsyncGroq"), \
         patch("app.core.llm.settings") as mock_settings:
        mock_settings.llm_provider = "unknown_provider"
        mock_settings.groq_api_key = "test-key"
        provider = get_llm_provider()

    assert isinstance(provider, FallbackProvider)
