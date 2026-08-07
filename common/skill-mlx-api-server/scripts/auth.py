"""Authentication — timing-safe API key validation."""

import hmac
import logging
from functools import wraps

from flask import request, jsonify

import config

logger = logging.getLogger(__name__)


def _key_matches(provided: str) -> bool:
    """Timing-safe comparison to prevent timing attacks."""
    if not provided:
        return False
    return hmac.compare_digest(
        config.API_KEY.encode("utf-8"),
        provided.encode("utf-8"),
    )


def require_api_key(f):
    """Decorator: reject requests with missing or invalid X-API-Key header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        provided = request.headers.get("X-API-Key", "")
        if not _key_matches(provided):
            logger.warning("Unauthorized request from %s", request.remote_addr)
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated
