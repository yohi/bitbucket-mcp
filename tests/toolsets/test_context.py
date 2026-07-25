import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import context

BASE = "https://api.bitbucket.org/2.0"


async def test_get_current_user(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/user", json={"username": "alice", "account_id": "123"}
    )
    mcp, _ = register_toolset(context.register)
    _, structured = await call_tool(mcp, "get_current_user", {})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "GET"
    assert request.url.path == "/2.0/user"
    assert structured == {"username": "alice", "account_id": "123"}


async def test_authenticated_require_auth_tool_is_registered_and_callable(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(url=f"{BASE}/user", json={"account_id": "123"})
    mcp, _ = register_toolset(context.register)

    tools = {tool.name for tool in await mcp.list_tools()}
    _, structured = await call_tool(mcp, "get_current_user", {})

    assert "get_current_user" in tools
    assert structured == {"account_id": "123"}


async def test_list_workspaces_clamps_pagelen(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": [], "page": 1, "size": 0})
    mcp, _ = register_toolset(context.register)
    await call_tool(mcp, "list_workspaces", {"pagelen": 500})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/user/workspaces"
    assert request.url.params["pagelen"] == "100"


async def test_list_workspaces_administrator_filter(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(context.register)
    await call_tool(mcp, "list_workspaces", {"administrator": True})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.params["q"] == 'permission="owner"'


async def test_list_workspaces_rejects_administrator_with_q(
    register_toolset, call_tool
) -> None:
    mcp, _ = register_toolset(context.register)
    with pytest.raises(ToolError, match=r"administrator|q"):
        await call_tool(mcp, "list_workspaces", {"administrator": True, "q": "foo"})


async def test_context_registers_expected_tools_with_annotations(
    register_toolset,
) -> None:
    mcp, _ = register_toolset(context.register)
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert set(tools) == {"get_current_user", "list_workspaces"}
    assert tools["get_current_user"].annotations is not None
    assert tools["get_current_user"].annotations.readOnlyHint is True
