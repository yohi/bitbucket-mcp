"""issues ツールセット: イシューの参照・作成・更新・削除・コメント。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.pagination import page_params
from bitbucket_mcp.toolsets._common import AutoLoginController, require_auth, resolve_workspace

if TYPE_CHECKING:
    from bitbucket_mcp.auth import AuthProvider

_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
_WRITE = ToolAnnotations(openWorldHint=True)
_DESTRUCTIVE = ToolAnnotations(destructiveHint=True, openWorldHint=True)


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

    async def list_issues(
        *,
        workspace: str | None = None,
        repo_slug: str,
        q: str | None = None,
        sort: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List issues in a repository."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page, pagelen)
        if q:
            query["q"] = q
        if sort:
            query["sort"] = sort
        return await client.request("GET", f"/repositories/{ws}/{repo_slug}/issues", query=query)

    async def get_issue(
        *,
        workspace: str | None = None,
        repo_slug: str,
        issue_id: int,
        action: Literal["details", "comments", "changes"] = "details",
    ) -> dict[str, Any]:
        """Get an issue or its comments/changes."""
        ws = resolve_workspace(workspace, default_workspace)
        base = f"/repositories/{ws}/{repo_slug}/issues/{issue_id}"
        if action == "details":
            return await client.request("GET", base)
        return await client.request("GET", f"{base}/{action}")

    mcp.add_tool(_wrap(list_issues), annotations=_READ)
    mcp.add_tool(_wrap(get_issue), annotations=_READ)

    if read_only:
        return

    async def create_issue(
        *,
        workspace: str | None = None,
        repo_slug: str,
        title: str,
        content: str | None = None,
        kind: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
    ) -> dict[str, Any]:
        """Create an issue."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {"title": title}
        if content:
            body["content"] = {"raw": content}
        if kind:
            body["kind"] = kind
        if priority:
            body["priority"] = priority
        if assignee:
            body["assignee"] = {"account_id": assignee}
        return await client.request("POST", f"/repositories/{ws}/{repo_slug}/issues", body=body)

    async def update_issue(
        *,
        workspace: str | None = None,
        repo_slug: str,
        issue_id: int,
        title: str | None = None,
        state: str | None = None,
        kind: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
    ) -> dict[str, Any]:
        """Update an issue."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if state is not None:
            body["state"] = state
        if kind is not None:
            body["kind"] = kind
        if priority is not None:
            body["priority"] = priority
        if assignee is not None:
            body["assignee"] = {"account_id": assignee}
        if not body:
            raise ToolError("update_issue には少なくとも1つの更新項目が必要です。")
        return await client.request(
            "PUT", f"/repositories/{ws}/{repo_slug}/issues/{issue_id}", body=body
        )

    async def delete_issue(
        *, workspace: str | None = None, repo_slug: str, issue_id: int
    ) -> dict[str, Any]:
        """Delete an issue. Destructive."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request("DELETE", f"/repositories/{ws}/{repo_slug}/issues/{issue_id}")

    async def add_issue_comment(
        *,
        workspace: str | None = None,
        repo_slug: str,
        issue_id: int,
        content: str,
    ) -> dict[str, Any]:
        """Add a comment to an issue."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/issues/{issue_id}/comments",
            body={"content": {"raw": content}},
        )

    mcp.add_tool(_wrap(create_issue), annotations=_WRITE)
    mcp.add_tool(_wrap(update_issue), annotations=_WRITE)
    mcp.add_tool(_wrap(delete_issue), annotations=_DESTRUCTIVE)
    mcp.add_tool(_wrap(add_issue_comment), annotations=_WRITE)
