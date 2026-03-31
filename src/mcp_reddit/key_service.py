"""
MCP Key Service integration for Reddit MCP Server.

Provides:
- resolve_key(): Resolves usr_xxx keys to Reddit API credentials via the central key service
- KeyServiceMiddleware: Pure ASGI middleware for key extraction, resolution, and path rewriting
- get_effective_credentials(): Unified credential resolution with full priority chain
"""

import asyncio
import json
import logging
import os
import re
import time
from contextvars import ContextVar
from urllib.parse import parse_qs

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
KEY_SERVICE_URL = os.environ.get("KEY_SERVICE_URL", "").rstrip("/")
KEY_SERVICE_TOKEN = os.environ.get("KEY_SERVICE_TOKEN", "")
SERVER_ID = "reddit"
CACHE_TTL_SECONDS = 60

# ---------------------------------------------------------------------------
# ContextVar for per-request resolved credentials
# Set by KeyServiceMiddleware, read by get_effective_credentials()
# ---------------------------------------------------------------------------
_key_credentials: ContextVar[dict | None] = ContextVar(
    "key_credentials", default=None
)

# ---------------------------------------------------------------------------
# In-memory cache and per-key locks for deduplication
# ---------------------------------------------------------------------------
_cache: dict[str, tuple[dict, float]] = {}  # key -> (credentials, expiry)
_locks: dict[str, asyncio.Lock] = {}


class KeyServiceUnavailableError(RuntimeError):
    """Raised when the key service is misconfigured or temporarily unavailable."""


def _mask_key(user_key: str) -> str:
    """Return a short, non-sensitive representation of a user key for logs."""
    return f"{user_key[:12]}..."


async def resolve_key(user_key: str) -> dict | None:
    """
    Resolve a usr_xxx key to Reddit credentials via the key service.

    Returns {"client_id": "...", "client_secret": "..."} on success, None for an
    invalid/expired key. Raises KeyServiceUnavailableError for service or config
    failures. Results are cached for CACHE_TTL_SECONDS with per-key lock
    deduplication.
    """
    if not KEY_SERVICE_URL:
        return None
    if not KEY_SERVICE_TOKEN:
        raise KeyServiceUnavailableError(
            "KEY_SERVICE_TOKEN is required when KEY_SERVICE_URL is configured"
        )

    # Fast-path: check cache before acquiring any lock
    now = time.monotonic()
    cached = _cache.get(user_key)
    if cached and cached[1] > now:
        return cached[0]

    # Per-key lock prevents thundering herd for the same key
    if user_key not in _locks:
        _locks[user_key] = asyncio.Lock()

    async with _locks[user_key]:
        # Double-check after acquiring lock
        now = time.monotonic()
        cached = _cache.get(user_key)
        if cached and cached[1] > now:
            return cached[0]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{KEY_SERVICE_URL}/internal/resolve",
                    json={"key": user_key, "server_id": SERVER_ID},
                    headers={
                        "Authorization": f"Bearer {KEY_SERVICE_TOKEN}",
                        "Content-Type": "application/json",
                    },
                )
        except (httpx.RequestError, OSError) as exc:
            raise KeyServiceUnavailableError("Failed to reach key service") from exc

        if resp.status_code != 200:
            logger.error(
                "Key service returned %d while resolving %s",
                resp.status_code,
                _mask_key(user_key),
            )
            raise KeyServiceUnavailableError(
                f"Key service returned status {resp.status_code}"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise KeyServiceUnavailableError("Key service returned invalid JSON") from exc

        if not data.get("valid"):
            logger.warning("Key service says %s is invalid", _mask_key(user_key))
            return None

        credentials = data.get("credentials", {})
        if not credentials.get("client_id") or not credentials.get("client_secret"):
            logger.error(
                "Key service returned incomplete credentials for %s",
                _mask_key(user_key),
            )
            raise KeyServiceUnavailableError("Key service returned incomplete credentials")

        # Cache the result
        _cache[user_key] = (credentials, time.monotonic() + CACHE_TTL_SECONDS)
        logger.info("Resolved %s via key service", _mask_key(user_key))
        return credentials


# ---------------------------------------------------------------------------
# ASGI Middleware
# ---------------------------------------------------------------------------

# Regex to extract usr_xxx key from URL path: /mcp/usr_xxx or /mcp/usr_xxx/...
_KEY_PATH_RE = re.compile(r"^(/mcp)/(usr_[a-zA-Z0-9_-]+)(/.*)?$")


async def _send_json_error(send, status: int, error: str, code: str) -> None:
    """Send a JSON error response through the raw ASGI send callable."""
    body = json.dumps({"error": error, "code": code}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
        }
    )


class KeyServiceMiddleware:
    """
    Pure ASGI middleware for mcp-key-service credential resolution.

    Detects usr_xxx keys in:
      1. URL path: /mcp/usr_xxx (rewrites path to /mcp)
      2. Query param: ?api_key=usr_xxx

    On success: sets _key_credentials ContextVar and delegates to inner app.
    On invalid key: returns 401.
    On key service unavailable: returns 503.
    No-op when KEY_SERVICE_URL is not configured.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not KEY_SERVICE_URL:
            await self.app(scope, receive, send)
            return

        user_key = None
        new_scope = scope  # default: unchanged

        # Method 1: Path-based key extraction (/mcp/usr_xxx)
        path = scope.get("path", "")
        path_match = _KEY_PATH_RE.match(path)
        if path_match:
            user_key = path_match.group(2)
            # Rewrite path: /mcp/usr_xxx -> /mcp (+ optional trailing segments)
            remaining = path_match.group(3) or ""
            new_path = path_match.group(1) + remaining
            new_scope = dict(scope)
            new_scope["path"] = new_path
            new_scope["raw_path"] = new_path.encode("utf-8")

        # Method 2: Query-based key extraction (?api_key=usr_xxx)
        if not user_key:
            query_string = scope.get("query_string", b"").decode("utf-8")
            params = parse_qs(query_string)
            api_key_list = params.get("api_key", [])
            if api_key_list and api_key_list[0].startswith("usr_"):
                user_key = api_key_list[0]

        # No key found - pass through unchanged
        if not user_key:
            await self.app(scope, receive, send)
            return

        # Resolve the key via the key service
        try:
            credentials = await resolve_key(user_key)
        except (KeyServiceUnavailableError, httpx.RequestError, OSError) as exc:
            logger.error("Key service unreachable: %s", exc)
            await _send_json_error(
                send,
                503,
                "Credential service unavailable",
                "SERVICE_UNAVAILABLE",
            )
            return

        if credentials is None:
            await _send_json_error(
                send,
                401,
                "Invalid or expired API key",
                "INVALID_KEY",
            )
            return

        # Set ContextVar and delegate to inner app
        token = _key_credentials.set(credentials)
        try:
            await self.app(new_scope, receive, send)
        finally:
            _key_credentials.reset(token)


# ---------------------------------------------------------------------------
# Credential resolution helper
# ---------------------------------------------------------------------------

def get_effective_credentials(
    tool_client_id: str,
    tool_client_secret: str,
    default_client_id: str,
    default_client_secret: str,
) -> tuple[str, str]:
    """
    Resolve Reddit credentials using the full priority chain:

    1. Explicit tool parameters
    2. Key-service resolved credentials (from ContextVar set by middleware)
    3. HTTP headers (X-Reddit-Client-ID / X-Reddit-Client-Secret)
    4. URL query params (client_id / client_secret)
    5. Environment variable defaults

    Levels 3-4 use FastMCP's get_http_request() to access the current request.
    Falls back gracefully when no HTTP context exists (e.g. stdio transport).
    """

    def _first_non_empty(*values: str) -> str:
        for value in values:
            if value:
                return value
        return ""

    key_creds = _key_credentials.get() or {}
    key_client_id = key_creds.get("client_id", "")
    key_client_secret = key_creds.get("client_secret", "")
    header_id = header_secret = query_id = query_secret = ""
    request = None

    # Priorities 3 & 4: HTTP headers and query params via FastMCP request context.
    try:
        from fastmcp.server.dependencies import get_http_request

        request = get_http_request()
    except RuntimeError:
        # No HTTP request context (e.g. stdio transport) - skip to fallback.
        request = None

    if request is not None:
        # Preserve the historical per-field override behavior instead of
        # requiring client_id and client_secret to come from the same source.
        header_id = request.headers.get("X-Reddit-Client-ID", "")
        header_secret = request.headers.get("X-Reddit-Client-Secret", "")

        query_params = dict(request.query_params)
        query_id = query_params.get("client_id", "")
        query_secret = query_params.get("client_secret", "")

    client_id = _first_non_empty(
        tool_client_id,
        key_client_id,
        header_id,
        query_id,
        default_client_id,
    )
    client_secret = _first_non_empty(
        tool_client_secret,
        key_client_secret,
        header_secret,
        query_secret,
        default_client_secret,
    )
    return client_id, client_secret
