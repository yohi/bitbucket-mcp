"""pull_requests ツールセット: PR の参照・作成・更新・マージ・レビュー・コメント。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp import FastMCP

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.models import InlineComment
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

    async def list_pull_requests(
        *,
        workspace: str | None = None,
        repo_slug: str,
        state: str | None = None,
        q: str | None = None,
        sort: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List pull requests, optionally filtered by state."""
        query = build_query(page, pagelen, state=state, q=q, sort=sort)
        return await ctx.request_json(
            workspace,
            "GET",
            "/repositories/{ws}/{repo_slug}/pullrequests",
            path_params={"repo_slug": repo_slug},
            query=query,
        )

    async def get_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        action: Literal[
            "details",
            "diff",
            "diffstat",
            "patch",
            "commits",
            "activity",
            "statuses",
            "comments",
        ] = "details",
    ) -> dict[str, Any]:
        """Get a pull request or one of its sub-resources."""
        if action == "details":
            return await ctx.request_json(
                workspace,
                "GET",
                "/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}",
                path_params={"repo_slug": repo_slug, "pull_request_id": pull_request_id},
            )
        if action in ("diff", "patch"):
            text = await ctx.request_text(
                workspace,
                "GET",
                "/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/{action}",
                path_params={
                    "repo_slug": repo_slug,
                    "pull_request_id": pull_request_id,
                    "action": action,
                },
            )
            return {"content": text, "format": action}
        return await ctx.request_json(
            workspace,
            "GET",
            "/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/{action}",
            path_params={
                "repo_slug": repo_slug,
                "pull_request_id": pull_request_id,
                "action": action,
            },
        )

    ctx.register_tools(
        read=[
            (list_pull_requests, READ),
            (get_pull_request, READ),
        ]
    )

    async def create_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        title: str,
        source_branch: str,
        destination_branch: str | None = None,
        description: str | None = None,
        reviewers: list[str] | None = None,
        close_source_branch: bool | None = None,
    ) -> dict[str, Any]:
        """Create a pull request."""
        body = build_body(
            title=title,
            source={"branch": {"name": source_branch}},
            destination=(
                {"branch": {"name": destination_branch}} if destination_branch is not None else None
            ),
            description=description if description else None,
            reviewers=([{"account_id": r} for r in reviewers] if reviewers else None),
            close_source_branch=close_source_branch,
        )
        return await ctx.request_json(
            workspace,
            "POST",
            "/repositories/{ws}/{repo_slug}/pullrequests",
            path_params={"repo_slug": repo_slug},
            body=body,
        )

    async def update_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        title: str | None = None,
        description: str | None = None,
        destination_branch: str | None = None,
    ) -> dict[str, Any]:
        """Update a pull request's title, description, or destination."""
        body = build_body(
            title=title,
            description=description,
            destination=({"branch": {"name": destination_branch}} if destination_branch else None),
        )
        return await ctx.request_json(
            workspace,
            "PUT",
            "/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}",
            path_params={"repo_slug": repo_slug, "pull_request_id": pull_request_id},
            body=body,
        )

    async def merge_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        merge_strategy: str | None = None,
        message: str | None = None,
        close_source_branch: bool | None = None,
    ) -> dict[str, Any]:
        """Merge a pull request. Destructive."""
        body = build_body(
            merge_strategy=merge_strategy if merge_strategy else None,
            message=message if message else None,
            close_source_branch=close_source_branch,
        )
        return await ctx.request_json(
            workspace,
            "POST",
            "/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/merge",
            path_params={"repo_slug": repo_slug, "pull_request_id": pull_request_id},
            body=body,
        )

    async def decline_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
    ) -> dict[str, Any]:
        """Decline a pull request."""
        return await ctx.request_json(
            workspace,
            "POST",
            "/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/decline",
            path_params={"repo_slug": repo_slug, "pull_request_id": pull_request_id},
        )

    async def review_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        action: Literal["approve", "unapprove", "request_changes", "unrequest_changes"],
    ) -> dict[str, Any]:
        """Approve/unapprove or request/unrequest changes on a pull request."""
        endpoint = "approve" if action in ("approve", "unapprove") else "request-changes"
        method = "POST" if action in ("approve", "request_changes") else "DELETE"
        return await ctx.request_json(
            workspace,
            method,
            "/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/{endpoint}",
            path_params={
                "repo_slug": repo_slug,
                "pull_request_id": pull_request_id,
                "endpoint": endpoint,
            },
        )

    async def add_pull_request_comment(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        content: str,
        inline: InlineComment | None = None,
    ) -> dict[str, Any]:
        """Add a comment (optionally inline) to a pull request."""
        body: dict[str, Any] = {"content": {"raw": content}}
        if inline is not None:
            body["inline"] = {"path": inline.path, "to": inline.to}
        return await ctx.request_json(
            workspace,
            "POST",
            "/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/comments",
            path_params={"repo_slug": repo_slug, "pull_request_id": pull_request_id},
            body=body,
        )

    ctx.register_tools(
        write=[
            (create_pull_request, WRITE),
            (update_pull_request, WRITE),
            (decline_pull_request, WRITE),
            (review_pull_request, WRITE),
            (add_pull_request_comment, WRITE),
        ],
        destructive=[(merge_pull_request, DESTRUCTIVE)],
    )
