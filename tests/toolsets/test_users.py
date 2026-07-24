from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import users

BASE = "https://api.bitbucket.org/2.0"


async def test_get_user(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=f"{BASE}/users/account-123", json={"account_id": "account-123"})
    mcp, _ = register_toolset(users.register)
    _, structured = await call_tool(mcp, "get_user", {"selected_user": "account-123"})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/users/account-123"
    assert structured == {"account_id": "account-123"}


async def test_users_registers_read_only_tool(register_toolset) -> None:
    mcp, _ = register_toolset(users.register)
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert set(tools) == {"get_user"}
    assert tools["get_user"].annotations is not None
    assert tools["get_user"].annotations.readOnlyHint is True
