"""users ツールセット: ユーザー情報の参照。"""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient


def register(
    mcp: FastMCP,
    client: BitbucketClient,
    *,
    read_only: bool,
    default_workspace: str | None = None,
) -> None:
    async def get_user(*, selected_user: str) -> dict[str, Any]:
        """Get a user's public profile by account_id or UUID."""
        return await client.request("GET", f"/users/{selected_user}")

    mcp.add_tool(
        get_user,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
