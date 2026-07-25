"""context ツールセット: 現在のユーザーとワークスペース一覧。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.toolsets._common import (
    READ,
    AutoLoginController,
    RegisterContext,
    build_query,
    wrap_tool,
)

if TYPE_CHECKING:
    from bitbucket_mcp.auth import AuthProvider


def register(
    mcp: FastMCP,
    client: BitbucketClient,
    *,
    read_only: bool,
    default_workspace: str | None = None,
    auth_provider: AuthProvider | None = None,
    oauth_client: OAuthClient | None = None,
    store: CredentialStore | None = None,
    controller: AutoLoginController | None = None,
) -> None:
    ctx = RegisterContext(
        mcp,
        client,
        read_only=read_only,
        default_workspace=default_workspace,
        wrap=wrap_tool(auth_provider, oauth_client, store, controller),
    )

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
        effective_q = q
        if administrator and effective_q:
            raise ToolError("administrator と q は同時指定できません。")
        if administrator:
            effective_q = 'permission="owner"'
        query = build_query(page, pagelen, q=effective_q, sort=sort)
        return await client.request("GET", "/user/workspaces", query=query)

    ctx.tool(get_current_user, READ)
    ctx.tool(list_workspaces, READ)
