import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import issues

BASE = "https://api.bitbucket.org/2.0"


async def test_list_issues(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    await call_tool(mcp, "list_issues", {"repo_slug": "r", "q": 'state="new"'})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/issues"
    assert request.url.params["q"] == 'state="new"'


async def test_get_issue_changes_subpath(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    await call_tool(mcp, "get_issue", {"repo_slug": "r", "issue_id": 3, "action": "changes"})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/issues/3/changes"


async def test_create_issue_body(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"id": 1})
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "create_issue",
        {"repo_slug": "r", "title": "Bug", "content": "desc", "kind": "bug"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/issues"
    assert request.read() == (b'{"title":"Bug","content":{"raw":"desc"},"kind":"bug"}')


async def test_create_issue_includes_assignee(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"id": 1})
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "create_issue",
        {"repo_slug": "r", "title": "Bug", "assignee": "acct-1"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.read() == b'{"title":"Bug","assignee":{"account_id":"acct-1"}}'


async def test_add_issue_comment_body(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"id": 9})
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "add_issue_comment",
        {"repo_slug": "r", "issue_id": 3, "content": "hi"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/issues/3/comments"
    assert request.read() == b'{"content":{"raw":"hi"}}'


async def test_update_issue_body_and_assignee(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"id": 1})
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "update_issue",
        {
            "repo_slug": "r",
            "issue_id": 3,
            "title": "New",
            "state": "open",
            "assignee": "acct-1",
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "PUT"
    assert request.url.path == "/2.0/repositories/ws1/r/issues/3"
    assert request.read() == (b'{"title":"New","state":"open","assignee":{"account_id":"acct-1"}}')


async def test_update_issue_rejects_empty_body(register_toolset, call_tool) -> None:
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    with pytest.raises(ToolError, match="少なくとも1つ"):
        await call_tool(mcp, "update_issue", {"repo_slug": "r", "issue_id": 3})


async def test_delete_issue_destructive(register_toolset) -> None:
    mcp, _ = register_toolset(issues.register)
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert tools["delete_issue"].annotations is not None
    assert tools["delete_issue"].annotations.destructiveHint is True


async def test_delete_issue_request_path(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=204)
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    await call_tool(mcp, "delete_issue", {"repo_slug": "r", "issue_id": 3})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "DELETE"
    assert request.url.path == "/2.0/repositories/ws1/r/issues/3"


async def test_issue_write_tools_absent_in_read_only(register_toolset) -> None:
    mcp, _ = register_toolset(issues.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    for write_tool in (
        "create_issue",
        "update_issue",
        "delete_issue",
        "add_issue_comment",
    ):
        assert write_tool not in names
    assert "list_issues" in names
