from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from bitbucket_mcp.auth import AuthProvider
from bitbucket_mcp.config import Settings
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.server import create_server, make_lifespan
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
    tmp_path: Path,
) -> None:
    import bitbucket_mcp.server as server

    class FakeProvider(AuthProvider):
        def is_authenticated(self) -> bool:
            return False

        async def authorization_header(self) -> str:
            return "Bearer test"

        async def refresh(self) -> None:
            pass

        async def aclose(self) -> None:
            pass

    provider = FakeProvider()
    controller = AutoLoginController()
    oauth_client = OAuthClient(
        base_url="https://bitbucket.org",
        client_id="cid",
        client_secret="csec",
        redirect_uri="http://127.0.0.1:8976/callback",
        scopes=["account"],
    )
    store = CredentialStore(tmp_path / "creds.json")
    captured: list[object] = []

    def fake_start(coro: object) -> bool:
        captured.append(coro)
        return True

    monkeypatch.setattr(controller, "start", fake_start)
    monkeypatch.setattr("bitbucket_mcp.server.display_available", lambda: True)

    try:
        assert server.bitbucket_login(provider, controller, oauth_client, store) == (
            "Bitbucket 認証をブラウザで開始しました。同意後に操作を再実行してください。"
        )
        assert len(captured) == 1
    finally:
        await oauth_client.aclose()


async def test_bitbucket_login_returns_already_logged_in() -> None:
    import bitbucket_mcp.server as server

    class AlreadyLoggedInProvider(AuthProvider):
        def is_authenticated(self) -> bool:
            return True

        async def authorization_header(self) -> str:
            return "Bearer test"

        async def refresh(self) -> None:
            pass

        async def aclose(self) -> None:
            pass

    assert (
        server.bitbucket_login(AlreadyLoggedInProvider(), AutoLoginController(), None, None)
        == "既にログインしています。"
    )


@pytest.mark.parametrize(
    ("has_oauth_client", "has_store", "display_available", "message"),
    [
        (False, True, True, "bitbucket-mcp auth login --manual"),
        (True, False, True, "bitbucket-mcp auth login --manual"),
        (
            True,
            True,
            False,
            "bitbucket-mcp auth login --manual",
        ),
    ],
)
async def test_bitbucket_login_guides_manual_login_when_browser_login_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    has_oauth_client: bool,
    has_store: bool,
    display_available: bool,
    message: str,
) -> None:
    import bitbucket_mcp.server as server

    class FakeProvider(AuthProvider):
        def is_authenticated(self) -> bool:
            return False

        async def authorization_header(self) -> str:
            return "Bearer test"

        async def refresh(self) -> None:
            pass

        async def aclose(self) -> None:
            pass

    oauth_client = (
        OAuthClient(
            base_url="https://bitbucket.org",
            client_id="cid",
            client_secret="csec",
            redirect_uri="http://127.0.0.1:8976/callback",
            scopes=["account"],
        )
        if has_oauth_client
        else None
    )
    store = CredentialStore(tmp_path / "creds.json") if has_store else None
    monkeypatch.setattr("bitbucket_mcp.server.display_available", lambda: display_available)

    provider = FakeProvider()
    controller = AutoLoginController()
    try:
        with pytest.raises(ToolError, match=message):
            server.bitbucket_login(provider, controller, oauth_client, store)
    finally:
        if oauth_client is not None:
            await oauth_client.aclose()
