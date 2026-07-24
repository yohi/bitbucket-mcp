import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import SecretStr

from bitbucket_mcp.config import Settings
from bitbucket_mcp.server import create_server, make_lifespan
from bitbucket_mcp.toolsets import DEFAULT_TOOLSETS, TOOLSET_REGISTRY


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

    def fake_client_factory(**_kwargs: object) -> FakeClient:
        return FakeClient()

    monkeypatch.setattr("bitbucket_mcp.server.BitbucketClient", fake_client_factory)

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setitem(TOOLSET_REGISTRY, "context", explode)

    lifespan = make_lifespan(Settings(token=SecretStr("t")))
    with pytest.raises(RuntimeError, match="boom"):
        async with lifespan(FastMCP("bitbucket-mcp-test")):
            pass
    assert closed is True
