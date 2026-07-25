"""認証フックのテスト。"""

import asyncio
from pathlib import Path

import pytest

from bitbucket_mcp.auth import AuthProvider, StaticAuthProvider
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.toolsets._common import (  # pyright: ignore[reportPrivateUsage]
    AutoLoginController,
    _perform_auto_login,  # pyright: ignore[reportPrivateUsage]
    require_auth,
)


async def test_require_auth_passes_when_authenticated() -> None:
    provider = StaticAuthProvider("Bearer x")
    controller = AutoLoginController()
    decorated = require_auth(provider, controller, None, None)(lambda: "ok")
    assert await decorated() == "ok"


async def test_require_auth_returns_message_when_not_authenticated_with_oauth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Unauth(AuthProvider):
        async def authorization_header(self) -> str:
            raise RuntimeError

        async def refresh(self) -> None:
            pass

        async def aclose(self) -> None:
            pass

        def is_authenticated(self) -> bool:
            return False

    monkeypatch.setattr("bitbucket_mcp.toolsets._common._display_available", lambda: True)
    store = CredentialStore(tmp_path / "creds.json")
    controller = AutoLoginController()
    oauth_client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="c",
        client_secret="s",
        redirect_uri="http://127.0.0.1:0/callback",
        scopes=["account"],
    )
    decorated = require_auth(_Unauth(), controller, oauth_client, store)(lambda: "ok")
    result = await decorated()
    assert "ブラウザ" in result
    await controller.shutdown()
    await oauth_client.aclose()


async def test_require_auth_returns_busy_when_already_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Unauth(AuthProvider):
        def is_authenticated(self) -> bool:
            return False

        async def authorization_header(self) -> str:
            raise RuntimeError

        async def refresh(self) -> None:
            pass

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("bitbucket_mcp.toolsets._common._display_available", lambda: True)
    store = CredentialStore(tmp_path / "creds.json")
    controller = AutoLoginController()
    oauth_client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="c",
        client_secret="s",
        redirect_uri="http://127.0.0.1:0/callback",
        scopes=["account"],
    )
    decorated = require_auth(_Unauth(), controller, oauth_client, store)(lambda: "ok")
    await decorated()
    result = await decorated()
    assert "処理中" in result
    await controller.shutdown()
    await oauth_client.aclose()


async def test_auto_login_releases_controller_after_unexpected_error() -> None:
    controller = AutoLoginController()
    assert controller.start(lambda: (_ for _ in ()).throw(RuntimeError("boom"))) is True
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert controller.is_running() is False


async def test_auto_login_closes_callback_server_when_start_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class _Callback:
        def __init__(self, **_kwargs: object) -> None:
            self.closed = False

        async def start(self) -> None:
            raise RuntimeError("start failed")

        async def aclose(self) -> None:
            self.closed = True

    callback = _Callback()

    def fake_callback_server(**_kwargs: object) -> _Callback:
        return callback

    monkeypatch.setattr(
        "bitbucket_mcp.toolsets._common.OAuthCallbackServer",
        fake_callback_server,
    )
    oauth_client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="c",
        client_secret="s",
        redirect_uri="http://127.0.0.1:0/callback",
        scopes=["account"],
    )
    try:
        await _perform_auto_login(  # pyright: ignore[reportPrivateUsage]
            StaticAuthProvider("Bearer x"),
            oauth_client,
            CredentialStore(tmp_path / "creds.json"),
        )
    finally:
        await oauth_client.aclose()
    assert callback.closed is True
