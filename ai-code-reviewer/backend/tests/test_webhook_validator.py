"""Unit tests for the GitHub webhook HMAC-SHA256 signature validator."""
from __future__ import annotations

import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.github.webhook_validator import verify_github_signature

_SECRET = "super-secret-key"
_BODY = b'{"action": "opened", "pull_request": {}}'


def _make_sig(body: bytes, secret: str = _SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _make_request(body: bytes, sig_header: str) -> AsyncMock:
    request = AsyncMock()
    request.headers = {"X-Hub-Signature-256": sig_header}
    request.body = AsyncMock(return_value=body)
    return request


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_github_signature_valid_returns_body():
    request = _make_request(_BODY, _make_sig(_BODY))
    with patch("app.github.webhook_validator.settings") as mock_settings:
        mock_settings.github_webhook_secret = _SECRET
        result = await verify_github_signature(request)
    assert result == _BODY


@pytest.mark.asyncio
async def test_verify_github_signature_empty_body():
    body = b""
    request = _make_request(body, _make_sig(body))
    with patch("app.github.webhook_validator.settings") as mock_settings:
        mock_settings.github_webhook_secret = _SECRET
        result = await verify_github_signature(request)
    assert result == b""


# ---------------------------------------------------------------------------
# Unconfigured secret → 500
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_github_signature_empty_secret_raises_500():
    request = _make_request(_BODY, _make_sig(_BODY))
    with patch("app.github.webhook_validator.settings") as mock_settings:
        mock_settings.github_webhook_secret = ""
        with pytest.raises(HTTPException) as exc_info:
            await verify_github_signature(request)
    assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Missing / malformed signature header → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_github_signature_missing_header_raises_403():
    request = AsyncMock()
    request.headers = {}
    request.body = AsyncMock(return_value=_BODY)
    with patch("app.github.webhook_validator.settings") as mock_settings:
        mock_settings.github_webhook_secret = _SECRET
        with pytest.raises(HTTPException) as exc_info:
            await verify_github_signature(request)
    assert exc_info.value.status_code == 403
    assert "Missing or invalid" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_github_signature_malformed_header_raises_403():
    request = _make_request(_BODY, "md5=somehash")
    with patch("app.github.webhook_validator.settings") as mock_settings:
        mock_settings.github_webhook_secret = _SECRET
        with pytest.raises(HTTPException) as exc_info:
            await verify_github_signature(request)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Signature mismatch → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_github_signature_wrong_secret_raises_403():
    sig = _make_sig(_BODY, secret="wrong-secret")
    request = _make_request(_BODY, sig)
    with patch("app.github.webhook_validator.settings") as mock_settings:
        mock_settings.github_webhook_secret = _SECRET
        with pytest.raises(HTTPException) as exc_info:
            await verify_github_signature(request)
    assert exc_info.value.status_code == 403
    assert "mismatch" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_verify_github_signature_tampered_body_raises_403():
    good_sig = _make_sig(_BODY)
    tampered_body = _BODY + b"extra"
    request = _make_request(tampered_body, good_sig)
    with patch("app.github.webhook_validator.settings") as mock_settings:
        mock_settings.github_webhook_secret = _SECRET
        with pytest.raises(HTTPException) as exc_info:
            await verify_github_signature(request)
    assert exc_info.value.status_code == 403
