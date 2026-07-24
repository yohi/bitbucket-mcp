"""OAuth プロトコルクライアントのテスト。"""

import asyncio

import httpx
import pytest
from pytest_httpx import HTTPXMock

from bitbucket_mcp.oauth import (
    OAuthCallbackServer,
    OAuthClient,
    OAuthFlowError,
    build_redirect_uri,
    generate_state,
)


def test_build_redirect_uri() -> None:
    assert build_redirect_uri(8976) == "http://127.0.0.1:8976/callback"


def test_generate_state_is_random() -> None:
    state = generate_state()
    other_state = generate_state()
    assert state != other_state
    assert len(state) >= 16


def test_oauth_client_public_properties() -> None:
    client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="c",
        client_secret="s",
        redirect_uri="http://127.0.0.1:8976/callback",
        scopes=["account", "repository"],
    )
    assert client.base_url == "https://bitbucket.org"
    assert client.client_id == "c"
    assert client.redirect_uri == "http://127.0.0.1:8976/callback"
    assert client.scopes == ["account", "repository"]


@pytest.mark.parametrize(
    "base_url",
    [
        "http://bitbucket.org",
        "https://evil.example.com",
        "https://bitbucket.org.evil.example.com",
    ],
)
def test_oauth_client_rejects_unsafe_base_url(base_url: str) -> None:
    with pytest.raises(ValueError, match="base_url"):
        OAuthClient(
            base_url=base_url,
            client_id="c",
            client_secret="s",
            redirect_uri="http://127.0.0.1:8976/callback",
            scopes=["account"],
        )


def test_oauth_client_accepts_bitbucket_subdomain() -> None:
    client = OAuthClient(
        base_url="https://api.bitbucket.org",
        client_id="c",
        client_secret="s",
        redirect_uri="http://127.0.0.1:8976/callback",
        scopes=["account"],
    )
    assert client.base_url == "https://api.bitbucket.org"


def test_callback_server_rejects_non_loopback_host() -> None:
    with pytest.raises(ValueError, match=r"127\.0\.0\.1"):
        OAuthCallbackServer(host="0.0.0.0", expected_state="expected")


def test_build_authorize_url() -> None:
    client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="c",
        client_secret="s",
        redirect_uri="http://127.0.0.1:8976/callback",
        scopes=["account", "repository"],
    )
    url = client.build_authorize_url("state-xyz")
    assert url.startswith("https://bitbucket.org/site/oauth2/authorize")
    assert "client_id=c" in url
    assert "response_type=code" in url
    assert "state=state-xyz" in url
    assert "scope=account+repository" in url
    assert "redirect_uri=" in url


async def test_exchange_code(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://bitbucket.org/site/oauth2/access_token",
        json={
            "access_token": "aaa",
            "refresh_token": "rrr",
            "expires_in": 3600,
            "scopes": "account repository",
            "token_type": "bearer",
        },
    )
    client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="c",
        client_secret="s",
        redirect_uri="http://127.0.0.1:8976/callback",
        scopes=["account"],
    )
    response = await client.exchange_code("code-123")
    assert response.access_token == "aaa"
    assert response.refresh_token == "rrr"
    assert response.expires_in == 3600
    assert response.scopes == ["account", "repository"]

    request = httpx_mock.get_request()
    assert request is not None
    body = request.read().decode()
    assert "grant_type=authorization_code" in body
    assert "code=code-123" in body
    assert "redirect_uri=" in body
    auth = request.headers.get("Authorization", "")
    assert auth.startswith("Basic ")
    await client.aclose()


async def test_refresh_token(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://bitbucket.org/site/oauth2/access_token",
        json={
            "access_token": "new-aaa",
            "refresh_token": "new-rrr",
            "expires_in": 3600,
            "scopes": "account",
            "token_type": "bearer",
        },
    )
    client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="c",
        client_secret="s",
        redirect_uri="http://127.0.0.1:8976/callback",
        scopes=["account"],
    )
    response = await client.refresh_token("old-rrr")
    assert response.access_token == "new-aaa"
    assert response.refresh_token == "new-rrr"

    request = httpx_mock.get_request()
    assert request is not None
    body = request.read().decode()
    assert "grant_type=refresh_token" in body
    assert "refresh_token=old-rrr" in body
    await client.aclose()


async def test_callback_server_collects_code_and_state() -> None:
    server = OAuthCallbackServer(port=0, expected_state="s")
    await server.start()
    port = server.port
    async with httpx.AsyncClient() as http:
        response = await http.get(
            f"http://127.0.0.1:{port}/callback",
            params={"code": "c", "state": "s"},
        )
    assert response.status_code == 200
    code, state = await server.wait_callback()
    await server.aclose()
    assert code == "c"
    assert state == "s"


async def test_callback_server_error_raises() -> None:
    server = OAuthCallbackServer(port=0, expected_state="expected")
    await server.start()
    port = server.port
    async with httpx.AsyncClient() as http:
        response = await http.get(
            f"http://127.0.0.1:{port}/callback",
            params={"error": "access_denied"},
        )
    assert response.status_code == 200
    with pytest.raises(OAuthFlowError, match="access_denied"):
        await server.wait_callback()
    await server.aclose()


async def test_callback_server_rejects_state_mismatch() -> None:
    server = OAuthCallbackServer(port=0, expected_state="expected")
    await server.start()
    port = server.port
    async with httpx.AsyncClient() as http:
        response = await http.get(
            f"http://127.0.0.1:{port}/callback",
            params={"code": "c", "state": "wrong"},
        )
    assert response.status_code == 200
    with pytest.raises(OAuthFlowError, match="state mismatch"):
        await server.wait_callback()
    await server.aclose()


async def test_callback_server_rejects_unexpected_path() -> None:
    server = OAuthCallbackServer(port=0, expected_state="expected")
    await server.start()
    port = server.port
    async with httpx.AsyncClient() as http:
        response = await http.get(
            f"http://127.0.0.1:{port}/unexpected",
        )
    assert response.status_code == 404
    async with httpx.AsyncClient() as http:
        response = await http.get(
            f"http://127.0.0.1:{port}/callback",
            params={"code": "c", "state": "expected"},
        )
    assert response.status_code == 200
    assert await server.wait_callback() == ("c", "expected")
    await server.aclose()


async def test_wait_callback_timeout() -> None:
    server = OAuthCallbackServer(port=0, expected_state="expected")
    await server.start()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.1):
            await server.wait_callback()
    await server.aclose()


async def test_callback_server_rejects_second_request() -> None:
    server = OAuthCallbackServer(port=0, expected_state="expected")
    await server.start()
    port = server.port
    async with httpx.AsyncClient() as http:
        response = await http.get(
            f"http://127.0.0.1:{port}/callback",
            params={"code": "first", "state": "expected"},
        )
    assert response.status_code == 200
    assert await server.wait_callback() == ("first", "expected")
    async with httpx.AsyncClient() as http:
        response = await http.get(
            f"http://127.0.0.1:{port}/callback",
            params={"code": "second", "state": "expected"},
        )
    assert response.status_code != 200  # Should be rejected
    await server.aclose()
