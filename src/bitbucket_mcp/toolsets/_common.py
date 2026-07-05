"""toolset 共通ヘルパ。"""

from mcp.server.fastmcp.exceptions import ToolError


def resolve_workspace(workspace: str | None, default_workspace: str | None) -> str:
    """workspace を解決する。未指定なら ToolError。"""
    resolved = workspace or default_workspace
    if not resolved:
        raise ToolError(
            "workspace が指定されていません。引数 workspace か"
            " BITBUCKET_DEFAULT_WORKSPACE を設定してください。"
        )
    return resolved
