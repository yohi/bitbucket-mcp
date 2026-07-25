"""users ツールセット: ユーザー情報の参照。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.toolsets._common import (
    READ,
    AutoLoginController,
    create_toolset_context_from_register_args,
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
    ctx = create_toolset_context_from_register_args(
        mcp,
        client,
        read_only,
        default_workspace,
        auth_provider,
        oauth_client,
        store,
        controller,
    )

    async def get_user(*, selected_user: str) -> dict[str, Any]:
        """Get a user's public profile by account_id or UUID."""
        return await client.request("GET", f"/users/{selected_user}")

    ctx.register_tools(read=[(get_user, READ)])
