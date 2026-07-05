import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import raw_api

BASE = "https://api.bitbucket.org/2.0"


async def test_bitbucket_api_get_passthrough(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"ok": True})
    mcp, _ = register_toolset(raw_api.register)
    _, structured = await call_tool(
        mcp,
        "bitbucket_api",
        {"method": "GET", "path": "repositories/ws1", "query": {"page": 2}},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "GET"
    assert request.url.path == "/2.0/repositories/ws1"
    assert request.url.params["page"] == "2"
    assert structured == {"ok": True}


async def test_bitbucket_api_normalizes_leading_slash(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={})
    mcp, _ = register_toolset(raw_api.register)
    await call_tool(
        mcp, "bitbucket_api", {"method": "GET", "path": "/user"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/user"


async def test_bitbucket_api_post_blocked_in_read_only(
    register_toolset, call_tool
) -> None:
    mcp, _ = register_toolset(raw_api.register, read_only=True)
    with pytest.raises(ToolError, match="READ_ONLY"):
        await call_tool(
            mcp,
            "bitbucket_api",
            {"method": "POST", "path": "/repositories/ws1/r/issues"},
        )


async def test_bitbucket_api_registered_even_in_read_only(register_toolset) -> None:
    mcp, _ = register_toolset(raw_api.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    assert "bitbucket_api" in names
