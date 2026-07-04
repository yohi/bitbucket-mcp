"""context ツールセット: 現在のユーザーとワークスペース一覧。"""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.pagination import page_params


def register(
    mcp: FastMCP,
    client: BitbucketClient,
    *,
    read_only: bool,
    default_workspace: str | None = None,
) -> None:
    async def get_current_user() -> dict[str, Any]:
        """Return the currently authenticated Bitbucket user account."""
        return await client.request("GET", "/user")

    async def list_workspaces(
        *,
        administrator: bool | None = None,
        q: str | None = None,
        sort: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List workspaces the authenticated user is a member of."""
        query: dict[str, Any] = page_params(page, pagelen)
        effective_q = q
        if administrator and not effective_q:
            effective_q = 'permission="owner"'
        if effective_q:
            query["q"] = effective_q
        if sort:
            query["sort"] = sort
        return await client.request("GET", "/user/workspaces", query=query)

    mcp.add_tool(
        get_current_user,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
    mcp.add_tool(
        list_workspaces,
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
