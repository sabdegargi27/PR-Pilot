"""Unit tests for Settings (config.py)."""
from __future__ import annotations

import os

import pytest

from app.config import Settings


def test_settings_defaults():
    """Settings must be instantiable with no .env file and sensible defaults."""
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
    )
    assert s.llm_provider == "groq"
    assert s.ollama_base_url == "http://localhost:11434"
    assert "asyncpg" in s.database_url


def test_settings_overridden_by_env(monkeypatch):
    """Environment variables take precedence over defaults."""
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-123")

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.llm_provider == "ollama"
    assert s.groq_api_key == "test-key-123"


def test_settings_database_url_overridden(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host:5432/db")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.database_url == "postgresql+asyncpg://user:pass@host:5432/db"


def test_settings_missing_secrets_are_empty_strings():
    """Missing secrets default to empty string (not None) so type is always str."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert isinstance(s.github_webhook_secret, str)
    assert isinstance(s.github_token, str)
    assert isinstance(s.groq_api_key, str)
