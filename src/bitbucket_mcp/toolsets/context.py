"""context ツールセット: 現在のユーザーとワークスペース一覧。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.pagination import page_params
from bitbucket_mcp.toolsets._common import (
    READ,
    AutoLoginController,
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
    _wrap = wrap_tool(auth_provider, oauth_client, store, controller)

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
        if administrator and effective_q:
            raise ToolError("administrator と q は同時指定できません。")
        if administrator:
            effective_q = 'permission="owner"'
        if effective_q:
            query["q"] = effective_q
        if sort:
            query["sort"] = sort
        return await client.request("GET", "/user/workspaces", query=query)

    mcp.add_tool(
        _wrap(get_current_user),
        annotations=READ,
    )
    mcp.add_tool(
        _wrap(list_workspaces),
        annotations=READ,
    )
