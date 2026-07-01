import hashlib
import hmac

from fastapi import HTTPException, Request

from app.config import settings


async def verify_github_signature(request: Request) -> bytes:
    """Validate the GitHub HMAC-SHA256 webhook signature.

    Raises HTTP 500 if the webhook secret is not configured (prevents silent
    acceptance of all requests when the secret is accidentally left empty).
    Raises HTTP 403 on any signature mismatch or missing header.

    Returns the raw request body so callers can avoid reading it a second time.
    """
    if not settings.github_webhook_secret:
        raise HTTPException(status_code=500, detail="Webhook secret is not configured")

    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if not signature_header.startswith("sha256="):
        raise HTTPException(status_code=403, detail="Missing or invalid signature header")

    body = await request.body()
    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(f"sha256={expected}", signature_header):
        raise HTTPException(status_code=403, detail="Signature mismatch")

    return body
