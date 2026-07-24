import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import repos
from bitbucket_mcp.toolsets._common import resolve_workspace

BASE = "https://api.bitbucket.org/2.0"


def test_resolve_workspace_prefers_explicit() -> None:
    assert resolve_workspace("explicit", "default") == "explicit"


def test_resolve_workspace_falls_back_to_default() -> None:
    assert resolve_workspace(None, "default") == "default"


def test_resolve_workspace_raises_when_both_none() -> None:
    with pytest.raises(ToolError, match="workspace"):
        resolve_workspace(None, None)


async def test_get_repository_uses_default_workspace(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(url=f"{BASE}/repositories/ws1/repo1", json={"slug": "repo1"})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    _, structured = await call_tool(mcp, "get_repository", {"repo_slug": "repo1"})
    assert structured == {"slug": "repo1"}


async def test_list_repositories_builds_query(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(repos.register)
    await call_tool(
        mcp,
        "list_repositories",
        {"workspace": "ws1", "q": 'name~"x"', "role": "member", "pagelen": 10},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1"
    assert request.url.params["role"] == "member"
    assert request.url.params["pagelen"] == "10"


async def test_get_diff_text_wrapped(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(text="diff --git a b")
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    _, structured = await call_tool(
        mcp, "get_diff", {"repo_slug": "r", "spec": "abc..def", "action": "diff"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/diff/abc..def"
    assert structured == {"content": "diff --git a b", "format": "diff"}


async def test_get_diff_diffstat_json(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"values": [{"status": "modified"}]})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    _, structured = await call_tool(
        mcp, "get_diff", {"repo_slug": "r", "spec": "abc..def", "action": "diffstat"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/diffstat/abc..def"
    assert structured == {"values": [{"status": "modified"}]}


async def test_repos_read_tools_registered(register_toolset) -> None:
    mcp, _ = register_toolset(repos.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    assert {
        "list_repositories",
        "get_repository",
        "get_file_or_directory",
        "list_commits",
        "get_commit",
        "get_diff",
        "list_branches",
        "list_tags",
    } <= names


async def test_create_repository_body(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"slug": "r"})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "create_repository",
        {"repo_slug": "r", "is_private": True, "project_key": "PRJ"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r"
    assert request.read() == (b'{"scm":"git","is_private":true,"project":{"key":"PRJ"}}')


async def test_create_commit_sends_form(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "create_commit",
        {
            "repo_slug": "r",
            "message": "msg",
            "branch": "main",
            "files": {"a.txt": "hello"},
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/src"
    assert request.headers["Content-Type"].startswith("application/x-www-form-urlencoded")
    body = request.read().decode()
    assert "message=msg" in body
    assert "branch=main" in body
    assert "a.txt=hello" in body


async def test_create_commit_rejects_reserved_file_names(register_toolset, call_tool) -> None:
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    with pytest.raises(ToolError, match=r"message|branch"):
        await call_tool(
            mcp,
            "create_commit",
            {
                "repo_slug": "r",
                "message": "msg",
                "branch": "main",
                "files": {"message": "hello"},
            },
        )


async def test_list_branches_supports_pagelen(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "list_branches",
        {"repo_slug": "r", "pagelen": 10},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/refs/branches"
    assert request.url.params["pagelen"] == "10"


async def test_list_commits_supports_pagelen(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "list_commits",
        {"repo_slug": "r", "pagelen": 10},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/commits"
    assert request.url.params["pagelen"] == "10"


async def test_list_tags_supports_pagelen(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "list_tags",
        {"repo_slug": "r", "pagelen": 10},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/refs/tags"
    assert request.url.params["pagelen"] == "10"


async def test_delete_branch_path(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=204)
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    await call_tool(mcp, "delete_branch", {"repo_slug": "r", "name": "feature/x"})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "DELETE"
    assert request.url.path == "/2.0/repositories/ws1/r/refs/branches/feature/x"


async def test_create_branch_body(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"name": "x"})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    await call_tool(mcp, "create_branch", {"repo_slug": "r", "name": "x", "target": "abc123"})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.read() == b'{"name":"x","target":{"hash":"abc123"}}'


async def test_write_tools_absent_in_read_only(register_toolset) -> None:
    mcp, _ = register_toolset(repos.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    for write_tool in (
        "create_repository",
        "delete_repository",
        "fork_repository",
        "create_commit",
        "create_branch",
        "delete_branch",
        "create_tag",
    ):
        assert write_tool not in names
    assert "get_repository" in names


async def test_delete_repository_has_destructive_hint(register_toolset) -> None:
    mcp, _ = register_toolset(repos.register)
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert tools["delete_repository"].annotations is not None
    assert tools["delete_repository"].annotations.destructiveHint is True
