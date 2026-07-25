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
    build_body,
    build_query,
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
        query = build_query(page, pagelen, q=q, sort=sort)
        return await ctx.request_json(
            workspace,
            "GET",
            "/repositories/{ws}/{repo_slug}/issues",
            path_params={"repo_slug": repo_slug},
            query=query,
        )

    async def get_issue(
        *,
        workspace: str | None = None,
        repo_slug: str,
        issue_id: int,
        action: Literal["details", "comments", "changes"] = "details",
    ) -> dict[str, Any]:
        """Get an issue or its comments/changes."""
        if action == "details":
            return await ctx.request_json(
                workspace,
                "GET",
                "/repositories/{ws}/{repo_slug}/issues/{issue_id}",
                path_params={"repo_slug": repo_slug, "issue_id": issue_id},
            )
        return await ctx.request_json(
            workspace,
            "GET",
            "/repositories/{ws}/{repo_slug}/issues/{issue_id}/{action}",
            path_params={
                "repo_slug": repo_slug,
                "issue_id": issue_id,
                "action": action,
            },
        )

    ctx.register_tools(
        read=[(list_issues, READ), (get_issue, READ)],
    )

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
        body = build_body(
            title=title,
            content={"raw": content} if content else None,
            kind=kind,
            priority=priority,
            assignee={"account_id": assignee} if assignee else None,
        )
        return await ctx.request_json(
            workspace,
            "POST",
            "/repositories/{ws}/{repo_slug}/issues",
            path_params={"repo_slug": repo_slug},
            body=body,
        )

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
        body = build_body(
            title=title,
            state=state,
            kind=kind,
            priority=priority,
            assignee={"account_id": assignee} if assignee is not None else None,
        )
        if not body:
            raise ToolError("update_issue には少なくとも1つの更新項目が必要です。")
        return await ctx.request_json(
            workspace,
            "PUT",
            "/repositories/{ws}/{repo_slug}/issues/{issue_id}",
            path_params={"repo_slug": repo_slug, "issue_id": issue_id},
            body=body,
        )

    async def delete_issue(
        *, workspace: str | None = None, repo_slug: str, issue_id: int
    ) -> dict[str, Any]:
        """Delete an issue. Destructive."""
        return await ctx.request_json(
            workspace,
            "DELETE",
            "/repositories/{ws}/{repo_slug}/issues/{issue_id}",
            path_params={"repo_slug": repo_slug, "issue_id": issue_id},
        )

    async def add_issue_comment(
        *,
        workspace: str | None = None,
        repo_slug: str,
        issue_id: int,
        content: str,
    ) -> dict[str, Any]:
        """Add a comment to an issue."""
        return await ctx.request_json(
            workspace,
            "POST",
            "/repositories/{ws}/{repo_slug}/issues/{issue_id}/comments",
            path_params={"repo_slug": repo_slug, "issue_id": issue_id},
            body={"content": {"raw": content}},
        )

    ctx.register_tools(
        write=[(create_issue, WRITE), (update_issue, WRITE), (add_issue_comment, WRITE)],
        destructive=[(delete_issue, DESTRUCTIVE)],
    )
