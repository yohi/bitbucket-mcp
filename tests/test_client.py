import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from bitbucket_mcp.client import BitbucketClient

BASE_URL = "https://api.bitbucket.org/2.0"


def _client() -> BitbucketClient:
    return BitbucketClient(
        base_url=BASE_URL, auth_header="Bearer test-token", backoff_base=0.0
    )


async def test_request_builds_url_and_injects_auth(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE_URL}/user", json={"username": "alice"}
    )
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
    await client.request(
        "POST", "/x", query={"page": 2}, body={"title": "hi"}
    )
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
    httpx_mock.add_response(
        status_code=404, json={"error": {"message": "Not found"}}
    )
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
    ) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        request = httpx.Request(method, f"{BASE_URL}{path}")
        if attempts == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setattr(client._client, "request", fake_request)
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
