from __future__ import annotations

import json
import logging

from groq import AsyncGroq
from groq import RateLimitError as GroqRateLimitError

from app.config import settings
from app.core.llm.base import LLMProvider, ProviderRateLimitError, ReviewResult, _parse_issues

logger = logging.getLogger(__name__)

_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(LLMProvider):
    def __init__(self) -> None:
        self._client = AsyncGroq(api_key=settings.groq_api_key)

    async def review(self, prompt: str) -> list[ReviewResult]:
        try:
            response = await self._client.chat.completions.create(
                model=_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
        except GroqRateLimitError as exc:
            raise ProviderRateLimitError(str(exc)) from exc

        raw = response.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Groq returned non-JSON content; skipping hunk")
            return []

        return _parse_issues(data)
