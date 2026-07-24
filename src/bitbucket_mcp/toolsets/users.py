"""users ツールセット: ユーザー情報の参照。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.toolsets._common import AutoLoginController, require_auth

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
    from bitbucket_mcp.auth import StaticAuthProvider

    controller = controller or AutoLoginController()

    def _wrap(fn: Any) -> Any:
        return require_auth(
            auth_provider or StaticAuthProvider("Bearer test-token"),
            controller,
            oauth_client,
            store,
        )(fn)

    async def get_user(*, selected_user: str) -> dict[str, Any]:
        """Get a user's public profile by account_id or UUID."""
        return await client.request("GET", f"/users/{selected_user}")

    mcp.add_tool(
        _wrap(get_user),
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
