from __future__ import annotations

import json
import logging

import httpx

from app.config import settings
from app.core.llm.base import LLMProvider, ReviewResult, _parse_issues

logger = logging.getLogger(__name__)

_MODEL = "codellama"


class OllamaProvider(LLMProvider):
    async def review(self, prompt: str) -> list[ReviewResult]:
        url = f"{settings.ollama_base_url}/api/generate"
        payload = {
            "model": _MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()

        raw = resp.json().get("response", "{}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Ollama returned non-JSON content; skipping hunk")
            return []

        return _parse_issues(data)
