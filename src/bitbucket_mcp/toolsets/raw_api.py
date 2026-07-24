"""raw_api ツールセット: 任意の Bitbucket REST 呼び出し (エスケープハッチ)。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
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
) -> None:
    from bitbucket_mcp.auth import StaticAuthProvider

    controller = AutoLoginController()

    def _wrap(fn: Any) -> Any:
        return require_auth(
            auth_provider or StaticAuthProvider("Bearer test-token"),
            controller,
            oauth_client,
            store,
        )(fn)

    async def bitbucket_api(
        *,
        method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"],
        path: str,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call any Bitbucket REST endpoint (path relative to /2.0)."""
        if read_only and method.upper() not in ("GET", "HEAD"):
            raise ToolError("BITBUCKET_READ_ONLY=true のため GET/HEAD のみ許可されています。")
        normalized = path if path.startswith("/") else f"/{path}"
        return await client.request(method.upper(), normalized, query=query, body=body)

    mcp.add_tool(_wrap(bitbucket_api), annotations=ToolAnnotations(openWorldHint=True))
