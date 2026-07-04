from mcp.server.fastmcp.exceptions import ToolError

from bitbucket_mcp.errors import build_tool_error


def test_returns_tool_error_instance() -> None:
    err = build_tool_error(404, {"error": {"message": "Not found"}})
    assert isinstance(err, ToolError)


def test_message_includes_status_and_message() -> None:
    err = build_tool_error(404, {"error": {"message": "Not found"}})
    assert "Bitbucket API 404" in str(err)
    assert "Not found" in str(err)


def test_message_includes_detail() -> None:
    err = build_tool_error(
        400, {"error": {"message": "Bad", "detail": "field x required"}}
    )
    assert "field x required" in str(err)


def test_status_hint_appended_for_403() -> None:
    err = build_tool_error(403, {"error": {"message": "Forbidden"}})
    assert "403" in str(err)
    assert "スコープ" in str(err)


def test_handles_missing_payload() -> None:
    err = build_tool_error(500, None)
    assert "Bitbucket API 500" in str(err)


def test_retry_after_included_for_429() -> None:
    err = build_tool_error(429, {"error": {"message": "Rate"}}, retry_after="1700000000")
    assert "1700000000" in str(err)
