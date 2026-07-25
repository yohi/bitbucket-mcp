"""issues ツールセット: イシューの参照・作成・更新・削除・コメント。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.toolsets._common import (
    DESTRUCTIVE,
    READ,
    WRITE,
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
        ws = ctx.resolve_workspace(workspace)
        query = build_query(page, pagelen, q=q, sort=sort)
        return await client.request("GET", f"/repositories/{ws}/{repo_slug}/issues", query=query)

    async def get_issue(
        *,
        workspace: str | None = None,
        repo_slug: str,
        issue_id: int,
        action: Literal["details", "comments", "changes"] = "details",
    ) -> dict[str, Any]:
        """Get an issue or its comments/changes."""
        ws = ctx.resolve_workspace(workspace)
        base = f"/repositories/{ws}/{repo_slug}/issues/{issue_id}"
        if action == "details":
            return await client.request("GET", base)
        return await client.request("GET", f"{base}/{action}")

    ctx.tool(list_issues, READ)
    ctx.tool(get_issue, READ)

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
        ws = ctx.resolve_workspace(workspace)
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
        ws = ctx.resolve_workspace(workspace)
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
        ws = ctx.resolve_workspace(workspace)
        return await client.request("DELETE", f"/repositories/{ws}/{repo_slug}/issues/{issue_id}")

    async def add_issue_comment(
        *,
        workspace: str | None = None,
        repo_slug: str,
        issue_id: int,
        content: str,
    ) -> dict[str, Any]:
        """Add a comment to an issue."""
        ws = ctx.resolve_workspace(workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/issues/{issue_id}/comments",
            body={"content": {"raw": content}},
        )

    ctx.tool(create_issue, WRITE)
    ctx.tool(update_issue, WRITE)
    ctx.tool(delete_issue, DESTRUCTIVE)
    ctx.tool(add_issue_comment, WRITE)
