from bitbucket_mcp.config import Settings
from bitbucket_mcp.server import create_server
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
    settings = Settings(token="t")
    mcp = create_server(settings)
    async with mcp._mcp_server.lifespan(mcp._mcp_server):
        names = {tool.name for tool in await mcp.list_tools()}
    assert "get_current_user" in names
    assert "list_repositories" in names
    assert "bitbucket_api" in names


async def test_create_server_respects_toolsets_selection() -> None:
    settings = Settings(token="t", toolsets="context,users")
    mcp = create_server(settings)
    async with mcp._mcp_server.lifespan(mcp._mcp_server):
        names = {tool.name for tool in await mcp.list_tools()}
    assert "get_current_user" in names
    assert "get_user" in names
    assert "list_repositories" not in names
    assert "bitbucket_api" in names  # 常時登録


async def test_create_server_read_only_excludes_write_tools() -> None:
    settings = Settings(token="t", read_only=True)
    mcp = create_server(settings)
    async with mcp._mcp_server.lifespan(mcp._mcp_server):
        names = {tool.name for tool in await mcp.list_tools()}
    assert "create_repository" not in names
    assert "merge_pull_request" not in names
    assert "get_repository" in names


async def test_create_server_can_exclude_raw_api() -> None:
    settings = Settings(token="t", toolsets="context,-bitbucket_api")
    mcp = create_server(settings)
    async with mcp._mcp_server.lifespan(mcp._mcp_server):
        names = {tool.name for tool in await mcp.list_tools()}
    assert "bitbucket_api" not in names
    assert "get_current_user" in names


async def test_create_server_uses_its_own_settings() -> None:
    first = Settings(token="t", toolsets="context")
    second = Settings(token="t", toolsets="users")
    mcp_first = create_server(first)
    create_server(second)
    async with mcp_first._mcp_server.lifespan(mcp_first._mcp_server):
        names = {tool.name for tool in await mcp_first.list_tools()}
    assert "get_current_user" in names
    assert "get_user" not in names
