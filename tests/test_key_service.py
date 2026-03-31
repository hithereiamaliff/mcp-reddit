"""
Tests for MCP Key Service integration: credential resolution, middleware, and priority chain.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from starlette.testclient import TestClient

from mcp_reddit.key_service import (
    KeyServiceMiddleware,
    KeyServiceUnavailableError,
    _key_credentials,
    _cache,
    get_effective_credentials,
    resolve_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_cache():
    """Clear the module-level resolve_key cache between tests."""
    _cache.clear()


def _make_send(sent_list):
    """Create an async ASGI send callable that appends messages to sent_list."""
    async def send(msg):
        sent_list.append(msg)
    return send


def _make_resolve_response(valid=True, client_id="test_id", client_secret="test_secret"):
    """Build a mock httpx.Response for the key service."""
    body = {"valid": valid}
    if valid:
        body["credentials"] = {"client_id": client_id, "client_secret": client_secret}
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = body
    return resp


# ---------------------------------------------------------------------------
# resolve_key tests
# ---------------------------------------------------------------------------

class TestResolveKey:
    def setup_method(self):
        _clear_cache()

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"KEY_SERVICE_URL": "https://keys.example.com", "KEY_SERVICE_TOKEN": "tok"})
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    @patch("mcp_reddit.key_service.KEY_SERVICE_TOKEN", "tok")
    async def test_resolve_key_success(self):
        mock_resp = _make_resolve_response()
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_reddit.key_service.httpx.AsyncClient", return_value=mock_client):
            result = await resolve_key("usr_abc123")

        assert result == {"client_id": "test_id", "client_secret": "test_secret"}
        mock_client.post.assert_called_once()
        # Verify Authorization header
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer tok"
        assert call_kwargs.kwargs["json"]["server_id"] == "reddit"

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    @patch("mcp_reddit.key_service.KEY_SERVICE_TOKEN", "tok")
    async def test_resolve_key_invalid(self):
        mock_resp = _make_resolve_response(valid=False)
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_reddit.key_service.httpx.AsyncClient", return_value=mock_client):
            result = await resolve_key("usr_bad_key")

        assert result is None

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    @patch("mcp_reddit.key_service.KEY_SERVICE_TOKEN", "tok")
    async def test_resolve_key_network_error(self):
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_reddit.key_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(KeyServiceUnavailableError):
                await resolve_key("usr_abc123")

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    @patch("mcp_reddit.key_service.KEY_SERVICE_TOKEN", "tok")
    async def test_resolve_key_incomplete_credentials_raises_unavailable(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.json.return_value = {"valid": True, "credentials": {"client_id": "only_id"}}
        mock_client = AsyncMock()
        mock_client.post.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_reddit.key_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(KeyServiceUnavailableError):
                await resolve_key("usr_incomplete")

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    @patch("mcp_reddit.key_service.KEY_SERVICE_TOKEN", "tok")
    async def test_resolve_key_caching(self):
        mock_resp = _make_resolve_response()
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_reddit.key_service.httpx.AsyncClient", return_value=mock_client):
            result1 = await resolve_key("usr_cached")
            result2 = await resolve_key("usr_cached")

        assert result1 == result2
        # httpx should only be called once; second call hits cache
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "")
    @patch("mcp_reddit.key_service.KEY_SERVICE_TOKEN", "")
    async def test_resolve_key_not_configured(self):
        result = await resolve_key("usr_abc123")
        assert result is None

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    @patch("mcp_reddit.key_service.KEY_SERVICE_TOKEN", "tok")
    async def test_resolve_key_non_200_status_raises_unavailable(self):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 500
        mock_client = AsyncMock()
        mock_client.post.return_value = resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("mcp_reddit.key_service.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(KeyServiceUnavailableError):
                await resolve_key("usr_server_err")

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    @patch("mcp_reddit.key_service.KEY_SERVICE_TOKEN", "")
    async def test_resolve_key_missing_token_raises_unavailable(self):
        with pytest.raises(KeyServiceUnavailableError):
            await resolve_key("usr_missing_token")


# ---------------------------------------------------------------------------
# get_effective_credentials tests
# ---------------------------------------------------------------------------

class TestGetEffectiveCredentials:
    def _patch_request(self, headers=None, query=None):
        request = MagicMock()
        request.headers = headers or {}
        request.query_params = query or {}
        return patch(
            "fastmcp.server.dependencies.get_http_request",
            return_value=request,
        )

    def test_priority_tool_params_first(self):
        """Explicit tool params always win."""
        token = _key_credentials.set({"client_id": "key_id", "client_secret": "key_secret"})
        try:
            cid, csecret = get_effective_credentials("tool_id", "tool_secret", "env_id", "env_secret")
            assert cid == "tool_id"
            assert csecret == "tool_secret"
        finally:
            _key_credentials.reset(token)

    def test_priority_key_service_second(self):
        """Key-service ContextVar beats env defaults."""
        token = _key_credentials.set({"client_id": "key_id", "client_secret": "key_secret"})
        try:
            cid, csecret = get_effective_credentials("", "", "env_id", "env_secret")
            assert cid == "key_id"
            assert csecret == "key_secret"
        finally:
            _key_credentials.reset(token)

    def test_priority_headers_third(self):
        """Headers beat query params and env defaults."""
        with self._patch_request(
            headers={
                "X-Reddit-Client-ID": "header_id",
                "X-Reddit-Client-Secret": "header_secret",
            },
            query={"client_id": "query_id", "client_secret": "query_secret"},
        ):
            cid, csecret = get_effective_credentials("", "", "env_id", "env_secret")
            assert cid == "header_id"
            assert csecret == "header_secret"

    def test_priority_query_fourth(self):
        """Query params beat env defaults when headers are absent."""
        with self._patch_request(
            headers={},
            query={"client_id": "query_id", "client_secret": "query_secret"},
        ):
            cid, csecret = get_effective_credentials("", "", "env_id", "env_secret")
            assert cid == "query_id"
            assert csecret == "query_secret"

    def test_priority_env_fallback(self):
        """Without tool params or key-service creds, falls back to env defaults."""
        cid, csecret = get_effective_credentials("", "", "env_id", "env_secret")
        assert cid == "env_id"
        assert csecret == "env_secret"

    def test_empty_key_service_creds_skipped(self):
        """If key-service creds are empty strings, skip to next level."""
        token = _key_credentials.set({"client_id": "", "client_secret": ""})
        try:
            cid, csecret = get_effective_credentials("", "", "env_id", "env_secret")
            assert cid == "env_id"
            assert csecret == "env_secret"
        finally:
            _key_credentials.reset(token)

    def test_partial_tool_params_use_env(self):
        """Partial overrides preserve the historical per-field fallback behavior."""
        cid, csecret = get_effective_credentials("tool_id", "", "env_id", "env_secret")
        assert cid == "tool_id"
        assert csecret == "env_secret"

    def test_partial_headers_mix_with_env_fallback(self):
        """Request-derived credentials also resolve per field."""
        with self._patch_request(
            headers={"X-Reddit-Client-ID": "header_id"},
            query={},
        ):
            cid, csecret = get_effective_credentials("", "", "env_id", "env_secret")
            assert cid == "header_id"
            assert csecret == "env_secret"


# ---------------------------------------------------------------------------
# KeyServiceMiddleware tests
# ---------------------------------------------------------------------------

class TestKeyServiceMiddleware:
    """Tests for the ASGI middleware using raw ASGI scope/send/receive."""

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    async def test_middleware_path_rewrite(self):
        """Middleware rewrites /mcp/usr_xxx to /mcp."""
        captured_scope = {}

        async def inner_app(scope, receive, send):
            captured_scope.update(scope)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = KeyServiceMiddleware(inner_app)
        scope = {
            "type": "http",
            "path": "/mcp/usr_test123",
            "raw_path": b"/mcp/usr_test123",
            "query_string": b"",
        }

        creds = {"client_id": "resolved_id", "client_secret": "resolved_secret"}
        with patch("mcp_reddit.key_service.resolve_key", new_callable=AsyncMock, return_value=creds):
            sent = []
            await middleware(scope, AsyncMock(), _make_send(sent))

        assert captured_scope["path"] == "/mcp"

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    async def test_middleware_query_key(self):
        """Middleware extracts key from ?api_key=usr_xxx."""
        resolved_creds = {"client_id": "q_id", "client_secret": "q_secret"}

        async def inner_app(scope, receive, send):
            # Verify ContextVar was set
            creds = _key_credentials.get()
            assert creds == resolved_creds
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = KeyServiceMiddleware(inner_app)
        scope = {
            "type": "http",
            "path": "/mcp",
            "raw_path": b"/mcp",
            "query_string": b"api_key=usr_query123",
        }

        with patch("mcp_reddit.key_service.resolve_key", new_callable=AsyncMock, return_value=resolved_creds):
            sent = []
            await middleware(scope, AsyncMock(), _make_send(sent))

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    async def test_middleware_passthrough_no_key(self):
        """Requests without usr_ key pass through unchanged."""
        captured_scope = {}

        async def inner_app(scope, receive, send):
            captured_scope.update(scope)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = KeyServiceMiddleware(inner_app)
        scope = {
            "type": "http",
            "path": "/mcp",
            "raw_path": b"/mcp",
            "query_string": b"",
        }

        sent = []
        await middleware(scope, AsyncMock(), _make_send(sent))
        assert captured_scope["path"] == "/mcp"

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    async def test_middleware_invalid_key_401(self):
        """Invalid key returns 401 JSON response."""
        middleware = KeyServiceMiddleware(AsyncMock())
        scope = {
            "type": "http",
            "path": "/mcp/usr_bad",
            "raw_path": b"/mcp/usr_bad",
            "query_string": b"",
        }

        sent = []

        async def mock_send(msg):
            sent.append(msg)

        with patch("mcp_reddit.key_service.resolve_key", new_callable=AsyncMock, return_value=None):
            await middleware(scope, AsyncMock(), mock_send)

        assert sent[0]["status"] == 401
        body = json.loads(sent[1]["body"])
        assert body["code"] == "INVALID_KEY"

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    async def test_middleware_service_down_503(self):
        """Key service unreachable returns 503."""
        middleware = KeyServiceMiddleware(AsyncMock())
        scope = {
            "type": "http",
            "path": "/mcp/usr_down",
            "raw_path": b"/mcp/usr_down",
            "query_string": b"",
        }

        sent = []

        async def mock_send(msg):
            sent.append(msg)

        with patch(
            "mcp_reddit.key_service.resolve_key",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("unreachable"),
        ):
            await middleware(scope, AsyncMock(), mock_send)

        assert sent[0]["status"] == 503
        body = json.loads(sent[1]["body"])
        assert body["code"] == "SERVICE_UNAVAILABLE"

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "")
    async def test_middleware_disabled_without_config(self):
        """Middleware is a no-op when KEY_SERVICE_URL is empty."""
        captured = {}

        async def inner_app(scope, receive, send):
            captured["called"] = True
            captured["path"] = scope["path"]

        middleware = KeyServiceMiddleware(inner_app)
        scope = {
            "type": "http",
            "path": "/mcp/usr_should_pass",
            "raw_path": b"/mcp/usr_should_pass",
            "query_string": b"",
        }

        await middleware(scope, AsyncMock(), AsyncMock())
        assert captured.get("called") is True
        # Path should NOT be rewritten when middleware is disabled
        assert captured["path"] == "/mcp/usr_should_pass"

    @pytest.mark.asyncio
    @patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com")
    async def test_middleware_contextvar_cleanup(self):
        """ContextVar is cleaned up after the request, even on success."""
        async def inner_app(scope, receive, send):
            # During the request, ContextVar should be set
            assert _key_credentials.get() is not None
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = KeyServiceMiddleware(inner_app)
        scope = {
            "type": "http",
            "path": "/mcp/usr_cleanup",
            "raw_path": b"/mcp/usr_cleanup",
            "query_string": b"",
        }

        creds = {"client_id": "cid", "client_secret": "csecret"}
        with patch("mcp_reddit.key_service.resolve_key", new_callable=AsyncMock, return_value=creds):
            sent = []
            await middleware(scope, AsyncMock(), _make_send(sent))

        # After the request, ContextVar should be reset to default
        assert _key_credentials.get() is None


class TestHttpServerIntegration:
    def test_error_responses_keep_cors_headers(self):
        """401 and 503 responses from KeyServiceMiddleware still include CORS headers."""
        import mcp_reddit.http_server as http_server

        with patch("mcp_reddit.key_service.KEY_SERVICE_URL", "https://keys.example.com"):
            with TestClient(http_server.app) as client:
                with patch(
                    "mcp_reddit.key_service.resolve_key",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    response = client.get("/mcp/usr_bad", headers={"Origin": "https://example.com"})
                    assert response.status_code == 401
                    assert response.headers["access-control-allow-origin"] == "*"

                with patch(
                    "mcp_reddit.key_service.resolve_key",
                    new_callable=AsyncMock,
                    side_effect=KeyServiceUnavailableError("key service down"),
                ):
                    response = client.get("/mcp/usr_bad", headers={"Origin": "https://example.com"})
                    assert response.status_code == 503
                    assert response.headers["access-control-allow-origin"] == "*"

    def test_run_http_uses_shared_app(self):
        """The console-script entrypoint runs the same app used by python -m."""
        import mcp_reddit.http_server as http_server

        with patch("uvicorn.run") as mock_run:
            http_server.run_http()

        mock_run.assert_called_once_with(
            http_server.app,
            host=http_server.HOST,
            port=http_server.PORT,
        )
