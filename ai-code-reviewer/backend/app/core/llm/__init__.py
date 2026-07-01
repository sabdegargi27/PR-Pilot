from __future__ import annotations

import logging

from app.config import settings
from app.core.llm.base import LLMProvider, ProviderRateLimitError, ReviewResult
from app.core.llm.groq_provider import GroqProvider
from app.core.llm.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)

__all__ = [
    "FallbackProvider",
    "GroqProvider",
    "LLMProvider",
    "OllamaProvider",
    "ProviderRateLimitError",
    "ReviewResult",
    "get_llm_provider",
]


class FallbackProvider(LLMProvider):
    """Wraps a primary LLM provider with an automatic fallback on rate limiting.

    When the primary raises ``ProviderRateLimitError`` the call is transparently
    retried against the fallback provider.  All other exceptions propagate to the
    caller unchanged so they can be handled at the right abstraction level.
    """

    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    async def review(self, prompt: str) -> list[ReviewResult]:
        try:
            return await self._primary.review(prompt)
        except ProviderRateLimitError:
            logger.warning("Primary LLM provider rate-limited; switching to fallback")
            return await self._fallback.review(prompt)


def get_llm_provider() -> LLMProvider:
    """Return the configured LLM provider.

    When Groq is selected the provider is wrapped in a ``FallbackProvider`` that
    automatically switches to Ollama if Groq enforces a rate limit.  When Ollama
    is selected directly, it is returned as-is with no fallback.
    """
    if settings.llm_provider == "ollama":
        return OllamaProvider()
    return FallbackProvider(
        primary=GroqProvider(),
        fallback=OllamaProvider(),
    )
