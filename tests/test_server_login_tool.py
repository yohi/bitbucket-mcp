from typing import cast

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from bitbucket_mcp.auth import AuthProvider
from bitbucket_mcp.config import Settings
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.server import (  # pyright: ignore[reportPrivateUsage]
    _bitbucket_login,  # pyright: ignore[reportPrivateUsage]
    create_server,
    make_lifespan,
)
from bitbucket_mcp.toolsets._common import AutoLoginController


async def test_bitbucket_login_tool_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_SECRET", "csec")
    settings = Settings(read_only=True)
    mcp = create_server(settings)
    async with make_lifespan(settings)(mcp):
        tools = await mcp.list_tools()
    assert any(tool.name == "bitbucket_login" for tool in tools)


async def test_bitbucket_login_starts_browser_login_with_shared_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProvider:
        def is_authenticated(self) -> bool:
            return False

    provider = cast(AuthProvider, FakeProvider())
    controller = AutoLoginController()
    oauth_client = cast(OAuthClient, object())
    store = cast(CredentialStore, object())
    captured: list[object] = []

    def fake_start(coro: object) -> bool:
        captured.append(coro)
        return True

    monkeypatch.setattr(controller, "start", fake_start)
    monkeypatch.setattr("bitbucket_mcp.server._display_available", lambda: True)

    assert _bitbucket_login(provider, controller, oauth_client, store) == (
        "Bitbucket 認証をブラウザで開始しました。同意後に操作を再実行してください。"
    )
    assert len(captured) == 1


async def test_bitbucket_login_returns_already_logged_in() -> None:
    class AlreadyLoggedInProvider:
        def is_authenticated(self) -> bool:
            return True

    assert _bitbucket_login(
        cast(AuthProvider, AlreadyLoggedInProvider()),
        AutoLoginController(),
        cast(OAuthClient, object()),
        cast(CredentialStore, object()),
    ) == "既にログインしています。"


@pytest.mark.parametrize(
    ("oauth_client", "store", "display_available", "message"),
    [
        (None, cast(CredentialStore, object()), True, "bitbucket-mcp auth login --manual"),
        (cast(OAuthClient, object()), None, True, "bitbucket-mcp auth login --manual"),
        (
            cast(OAuthClient, object()),
            cast(CredentialStore, object()),
            False,
            "bitbucket-mcp auth login --manual",
        ),
    ],
)
async def test_bitbucket_login_guides_manual_login_when_browser_login_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    oauth_client: OAuthClient | None,
    store: CredentialStore | None,
    display_available: bool,
    message: str,
) -> None:
    class FakeProvider:
        def is_authenticated(self) -> bool:
            return False

    monkeypatch.setattr("bitbucket_mcp.server._display_available", lambda: display_available)

    fake_provider = cast(AuthProvider, FakeProvider())
    controller = AutoLoginController()
    with pytest.raises(ToolError, match=message):
        _bitbucket_login(fake_provider, controller, oauth_client, store)
