import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import SecretStr

from bitbucket_mcp.auth import AuthConfigError
from bitbucket_mcp.config import Settings
from bitbucket_mcp.server import (  # pyright: ignore[reportPrivateUsage]
    create_server,
    make_lifespan,
)
from bitbucket_mcp.toolsets import DEFAULT_TOOLSETS, TOOLSET_REGISTRY
from bitbucket_mcp.toolsets._common import AutoLoginController


def test_registry_has_all_default_toolsets() -> None:
    assert set(DEFAULT_TOOLSETS) == set(TOOLSET_REGISTRY)
    assert set(DEFAULT_TOOLSETS) == {
        "context",
        "repos",
        "pull_requests",
        "issues",
        "pipelines",
        "users",
    }


async def test_create_server_registers_default_tools_and_raw_api() -> None:
    settings = Settings(token=SecretStr("t"))
    mcp = create_server(settings)
    async with make_lifespan(settings)(mcp):
        names = {tool.name for tool in await mcp.list_tools()}
    assert "get_current_user" in names
    assert "list_repositories" in names
    assert "bitbucket_api" in names


async def test_create_server_respects_toolsets_selection() -> None:
    settings = Settings(token=SecretStr("t"), toolsets="context,users")
    mcp = create_server(settings)
    async with make_lifespan(settings)(mcp):
        names = {tool.name for tool in await mcp.list_tools()}
    assert "get_current_user" in names
    assert "get_user" in names
    assert "list_repositories" not in names
    assert "bitbucket_api" in names  # 常時登録


async def test_create_server_read_only_excludes_write_tools() -> None:
    settings = Settings(token=SecretStr("t"), read_only=True)
    mcp = create_server(settings)
    async with make_lifespan(settings)(mcp):
        names = {tool.name for tool in await mcp.list_tools()}
    assert "create_repository" not in names
    assert "merge_pull_request" not in names
    assert "get_repository" in names


async def test_create_server_can_exclude_raw_api() -> None:
    settings = Settings(token=SecretStr("t"), toolsets="context,-bitbucket_api")
    mcp = create_server(settings)
    async with make_lifespan(settings)(mcp):
        names = {tool.name for tool in await mcp.list_tools()}
    assert "bitbucket_api" not in names
    assert "get_current_user" in names


async def test_create_server_uses_its_own_settings() -> None:
    first = Settings(token=SecretStr("t"), toolsets="context")
    second = Settings(token=SecretStr("t"), toolsets="users")
    mcp_first = create_server(first)
    create_server(second)
    async with make_lifespan(first)(mcp_first):
        names = {tool.name for tool in await mcp_first.list_tools()}
    assert "get_current_user" in names
    assert "get_user" not in names


async def test_make_lifespan_closes_client_when_registration_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = False

    class FakeClient:
        async def aclose(self) -> None:
            nonlocal closed
            closed = True

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    def fake_client_factory(**_kwargs: object) -> FakeClient:
        return FakeClient()

    monkeypatch.setattr("bitbucket_mcp.server.BitbucketClient", fake_client_factory)
    monkeypatch.setitem(TOOLSET_REGISTRY, "context", explode)

    lifespan = make_lifespan(Settings(token=SecretStr("t")))
    with pytest.raises(RuntimeError, match="boom"):
        async with lifespan(FastMCP("bitbucket-mcp-test")):
            pass
    assert closed is True


async def test_make_lifespan_passes_shared_auth_dependencies_and_shuts_down_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, object]] = []
    shutdown_called = False

    class FakeProvider:
        pass

    class FakeStore:
        pass

    class FakeOAuthClient:
        async def aclose(self) -> None:
            pass

    async def fake_shutdown(self: AutoLoginController) -> None:
        nonlocal shutdown_called
        shutdown_called = True

    def capture_register(*args: object, **kwargs: object) -> None:
        captured.append(kwargs)

    def fake_resolve_auth_provider(_settings: Settings) -> FakeProvider:
        return FakeProvider()

    def fake_store(_path: object) -> FakeStore:
        return FakeStore()

    def fake_oauth_client(**_kwargs: object) -> FakeOAuthClient:
        return FakeOAuthClient()

    monkeypatch.setattr("bitbucket_mcp.server.resolve_auth_provider", fake_resolve_auth_provider)
    monkeypatch.setattr("bitbucket_mcp.server.CredentialStore", fake_store)
    monkeypatch.setattr("bitbucket_mcp.server.OAuthClient", fake_oauth_client)
    monkeypatch.setattr("bitbucket_mcp.server.AutoLoginController.shutdown", fake_shutdown)
    monkeypatch.setitem(TOOLSET_REGISTRY, "context", capture_register)
    monkeypatch.setattr("bitbucket_mcp.server.raw_api.register", capture_register)

    settings = Settings(token=SecretStr("t"), toolsets="context")
    async with make_lifespan(settings)(FastMCP("bitbucket-mcp-test")):
        pass

    assert len(captured) == 2
    assert {id(item["controller"]) for item in captured} == {id(captured[0]["controller"])}
    assert all("auth_provider" in item for item in captured)
    assert all("oauth_client" in item for item in captured)
    assert all("store" in item for item in captured)
    assert shutdown_called is True


async def test_server_starts_without_credentials_when_oauth_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_SECRET", "csec")
    settings = Settings()
    mcp = create_server(settings)
    async with make_lifespan(settings)(mcp):
        names = {tool.name for tool in await mcp.list_tools()}
    assert "bitbucket_login" in names


async def test_server_raises_when_no_credentials_at_all() -> None:
    settings = Settings()
    with pytest.raises(AuthConfigError):
        async with make_lifespan(settings)(create_server(settings)):
            pass
