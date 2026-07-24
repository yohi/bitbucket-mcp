import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from bitbucket_mcp.auth import AuthProvider, NotAuthenticatedError, StaticAuthProvider
from bitbucket_mcp.client import BitbucketClient

BASE_URL = "https://api.bitbucket.org/2.0"


def _client() -> BitbucketClient:
    return BitbucketClient(
        base_url=BASE_URL,
        auth_provider=StaticAuthProvider("Bearer test-token"),
        backoff_base=0.0,
    )


async def test_request_builds_url_and_injects_auth(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE_URL}/user", json={"username": "alice"})
    client = _client()
    result = await client.request("GET", "/user")
    await client.aclose()
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "GET"
    assert request.url.path == "/2.0/user"
    assert request.headers["Authorization"] == "Bearer test-token"
    assert request.headers["Accept"] == "application/json"
    assert result == {"username": "alice"}


async def test_request_sends_query_and_json_body(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"ok": True})
    client = _client()
    await client.request("POST", "/x", query={"page": 2}, body={"title": "hi"})
    await client.aclose()
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.params["page"] == "2"
    assert request.read() == b'{"title":"hi"}'


async def test_request_sends_form_when_form_given(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={})
    client = _client()
    await client.request("POST", "/src", form={"message": "m", "a.txt": "body"})
    await client.aclose()
    request = httpx_mock.get_request()
    assert request is not None
    body = request.read().decode()
    assert "message=m" in body
    assert "a.txt=body" in body


async def test_empty_body_returns_empty_dict(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=204)
    client = _client()
    result = await client.request("DELETE", "/x")
    await client.aclose()
    assert result == {}


async def test_error_status_raises_tool_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=404, json={"error": {"message": "Not found"}})
    client = _client()
    with pytest.raises(ToolError, match="404"):
        await client.request("GET", "/missing")
    await client.aclose()


async def test_retries_on_429_then_succeeds(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=429, json={"error": {"message": "rate"}})
    httpx_mock.add_response(status_code=200, json={"ok": True})
    client = _client()
    result = await client.request("GET", "/x")
    await client.aclose()
    assert result == {"ok": True}
    assert len(httpx_mock.get_requests()) == 2


async def test_no_retry_on_post_5xx(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=502)
    client = _client()
    with pytest.raises(ToolError, match="502"):
        await client.request("POST", "/x", body={"name": "repo"})
    await client.aclose()
    assert len(httpx_mock.get_requests()) == 1


async def test_retries_on_connect_error_for_get(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    attempts = 0

    async def fake_request(
        method: str,
        path: str,
        params: dict[str, object] | None = None,
        json: dict[str, object] | None = None,
        data: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        request = httpx.Request(method, f"{BASE_URL}{path}")
        if attempts == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setattr(client._client, "request", fake_request)  # type: ignore[attr-defined]
    result = await client.request("GET", "/x")
    await client.aclose()
    assert result == {"ok": True}
    assert attempts == 2


async def test_request_text_returns_raw_text(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(text="diff --git a b")
    client = _client()
    result = await client.request_text("GET", "/diff/spec")
    await client.aclose()
    assert result == "diff --git a b"


class _RefreshableProvider(AuthProvider):
    def __init__(self) -> None:
        self.header = "Bearer old"
        self.refreshed = False

    async def authorization_header(self) -> str:
        return self.header

    async def refresh(self) -> None:
        self.refreshed = True
        self.header = "Bearer new"

    def is_authenticated(self) -> bool:
        return True


async def test_401_triggers_refresh_and_retry(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=401, json={"error": {"message": "expired"}})
    httpx_mock.add_response(status_code=200, json={"ok": True})
    provider = _RefreshableProvider()
    client = BitbucketClient(base_url=BASE_URL, auth_provider=provider, backoff_base=0.0)
    result = await client.request("GET", "/x")
    await client.aclose()
    assert result == {"ok": True}
    assert provider.refreshed is True
    requests = httpx_mock.get_requests()
    assert requests[1].headers["Authorization"] == "Bearer new"


async def test_401_after_refresh_raises_not_authenticated(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(status_code=401, json={"error": {"message": "expired"}})
    httpx_mock.add_response(status_code=401, json={"error": {"message": "still"}})
    provider = _RefreshableProvider()
    client = BitbucketClient(base_url=BASE_URL, auth_provider=provider, backoff_base=0.0)
    with pytest.raises(ToolError, match="再ログイン"):
        await client.request("GET", "/x")
    await client.aclose()


class _UnauthenticatedProvider(AuthProvider):
    async def authorization_header(self) -> str:
        raise NotAuthenticatedError("not logged in")

    async def refresh(self) -> None:
        return None

    def is_authenticated(self) -> bool:
        return False


async def test_not_authenticated_converted_to_tool_error(
    httpx_mock: HTTPXMock,
) -> None:
    client = BitbucketClient(
        base_url=BASE_URL,
        auth_provider=_UnauthenticatedProvider(),
        backoff_base=0.0,
    )
    with pytest.raises(ToolError, match="auth login"):
        await client.request("GET", "/x")
    await client.aclose()
