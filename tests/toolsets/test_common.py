"""認証フックのテスト。"""

import asyncio
from pathlib import Path

import pytest

from bitbucket_mcp.auth import AuthProvider, StaticAuthProvider
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.toolsets._common import AutoLoginController, require_auth


def test_require_auth_passes_when_authenticated() -> None:
    provider = StaticAuthProvider("Bearer x")
    controller = AutoLoginController()
    decorated = require_auth(provider, controller, None, None)(lambda: "ok")
    assert asyncio.run(decorated()) == "ok"


async def test_require_auth_returns_message_when_not_authenticated_with_oauth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Unauth(AuthProvider):
        async def authorization_header(self) -> str:
            raise RuntimeError

        async def refresh(self) -> None:
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
