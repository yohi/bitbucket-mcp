from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import pull_requests

BASE = "https://api.bitbucket.org/2.0"


async def test_list_pull_requests_state_query(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(mcp, "list_pull_requests", {"repo_slug": "r", "state": "OPEN"})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests"
    assert request.url.params["state"] == "OPEN"


async def test_get_pull_request_details(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"id": 7, "title": "t"})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    _, structured = await call_tool(
        mcp,
        "get_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "action": "details"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7"
    assert structured == {"id": 7, "title": "t"}


async def test_get_pull_request_diff_text(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(text="diff text")
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    _, structured = await call_tool(
        mcp,
        "get_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "action": "diff"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7/diff"
    assert structured == {"content": "diff text", "format": "diff"}


async def test_get_pull_request_diffstat_json(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    _, structured = await call_tool(
        mcp,
        "get_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "action": "diffstat"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7/diffstat"
    assert structured == {"values": []}


async def test_create_pull_request_body(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"id": 1})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "create_pull_request",
        {
            "repo_slug": "r",
            "title": "T",
            "source_branch": "feat",
            "destination_branch": "main",
            "close_source_branch": True,
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests"
    assert request.read() == (
        b'{"title":"T","source":{"branch":{"name":"feat"}},'
        b'"destination":{"branch":{"name":"main"}},'
        b'"close_source_branch":true}'
    )


async def test_merge_pull_request_destructive_and_path(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"state": "MERGED"})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "merge_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "merge_strategy": "squash"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7/merge"
    assert request.read() == b'{"merge_strategy":"squash"}'


async def test_update_pull_request_path_and_body(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"id": 7})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "update_pull_request",
        {
            "repo_slug": "r",
            "pull_request_id": 7,
            "title": "new title",
            "destination_branch": "main",
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "PUT"
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7"
    assert request.read() == (b'{"title":"new title","destination":{"branch":{"name":"main"}}}')


async def test_decline_pull_request_path(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"state": "DECLINED"})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(mcp, "decline_pull_request", {"repo_slug": "r", "pull_request_id": 7})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7/decline"


async def test_review_pull_request_approve_post(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"approved": True})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "review_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "action": "approve"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7/approve"


async def test_review_pull_request_unapprove_delete(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=204)
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "review_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "action": "unrequest_changes"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "DELETE"
    assert request.url.path == ("/2.0/repositories/ws1/r/pullrequests/7/request-changes")


async def test_add_pull_request_comment_inline(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"id": 5})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "add_pull_request_comment",
        {
            "repo_slug": "r",
            "pull_request_id": 7,
            "content": "nice",
            "inline": {"path": "a.py", "to": 10},
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7/comments"
    assert request.read() == (b'{"content":{"raw":"nice"},"inline":{"path":"a.py","to":10}}')


async def test_pull_request_write_tools_absent_in_read_only(register_toolset) -> None:
    mcp, _ = register_toolset(pull_requests.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    for write_tool in (
        "create_pull_request",
        "update_pull_request",
        "merge_pull_request",
        "decline_pull_request",
        "review_pull_request",
        "add_pull_request_comment",
    ):
        assert write_tool not in names
    assert "list_pull_requests" in names
