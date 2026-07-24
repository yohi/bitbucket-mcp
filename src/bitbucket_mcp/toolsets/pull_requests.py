"""pull_requests ツールセット: PR の参照・作成・更新・マージ・レビュー・コメント。"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.models import InlineComment
from bitbucket_mcp.pagination import page_params
from bitbucket_mcp.toolsets._common import resolve_workspace

_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
_WRITE = ToolAnnotations(openWorldHint=True)
_DESTRUCTIVE = ToolAnnotations(destructiveHint=True, openWorldHint=True)


def register(
    mcp: FastMCP,
    client: BitbucketClient,
    *,
    read_only: bool,
    default_workspace: str | None = None,
) -> None:
    _register_read_tools(mcp, client, default_workspace)
    if read_only:
        return
    _register_write_tools(mcp, client, default_workspace)


def _register_read_tools(
    mcp: FastMCP, client: BitbucketClient, default_workspace: str | None
) -> None:
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
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page, pagelen)
        if state:
            query["state"] = state
        if q:
            query["q"] = q
        if sort:
            query["sort"] = sort
        return await client.request(
            "GET", f"/repositories/{ws}/{repo_slug}/pullrequests", query=query
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
        ws = resolve_workspace(workspace, default_workspace)
        base = f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}"
        if action == "details":
            return await client.request("GET", base)
        if action in ("diff", "patch"):
            text = await client.request_text("GET", f"{base}/{action}")
            return {"content": text, "format": action}
        return await client.request("GET", f"{base}/{action}")

    mcp.add_tool(list_pull_requests, annotations=_READ)
    mcp.add_tool(get_pull_request, annotations=_READ)


def _register_write_tools(
    mcp: FastMCP, client: BitbucketClient, default_workspace: str | None
) -> None:
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
        ws = resolve_workspace(workspace, default_workspace)
        body = _build_pr_create_body(
            title=title,
            source_branch=source_branch,
            destination_branch=destination_branch,
            description=description,
            reviewers=reviewers,
            close_source_branch=close_source_branch,
        )
        return await client.request(
            "POST", f"/repositories/{ws}/{repo_slug}/pullrequests", body=body
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
        ws = resolve_workspace(workspace, default_workspace)
        body = _build_pr_update_body(
            title=title, description=description, destination_branch=destination_branch
        )
        return await client.request(
            "PUT",
            f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}",
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
        ws = resolve_workspace(workspace, default_workspace)
        body = _build_pr_merge_body(
            merge_strategy=merge_strategy,
            message=message,
            close_source_branch=close_source_branch,
        )
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/merge",
            body=body,
        )

    async def decline_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
    ) -> dict[str, Any]:
        """Decline a pull request."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/decline",
        )

    async def review_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        action: Literal["approve", "unapprove", "request_changes", "unrequest_changes"],
    ) -> dict[str, Any]:
        """Approve/unapprove or request/unrequest changes on a pull request."""
        ws = resolve_workspace(workspace, default_workspace)
        base = f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}"
        endpoint = "approve" if action in ("approve", "unapprove") else "request-changes"
        method = "POST" if action in ("approve", "request_changes") else "DELETE"
        return await client.request(method, f"{base}/{endpoint}")

    async def add_pull_request_comment(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        content: str,
        inline: InlineComment | None = None,
    ) -> dict[str, Any]:
        """Add a comment (optionally inline) to a pull request."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {"content": {"raw": content}}
        if inline is not None:
            body["inline"] = {"path": inline.path, "to": inline.to}
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/comments",
            body=body,
        )

    mcp.add_tool(create_pull_request, annotations=_WRITE)
    mcp.add_tool(update_pull_request, annotations=_WRITE)
    mcp.add_tool(merge_pull_request, annotations=_DESTRUCTIVE)
    mcp.add_tool(decline_pull_request, annotations=_WRITE)
    mcp.add_tool(review_pull_request, annotations=_WRITE)
    mcp.add_tool(add_pull_request_comment, annotations=_WRITE)


def _build_pr_create_body(
    *,
    title: str,
    source_branch: str,
    destination_branch: str | None,
    description: str | None,
    reviewers: list[str] | None,
    close_source_branch: bool | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": title,
        "source": {"branch": {"name": source_branch}},
    }
    if destination_branch is not None:
        body["destination"] = {"branch": {"name": destination_branch}}
    if description:
        body["description"] = description
    if reviewers:
        body["reviewers"] = [{"account_id": r} for r in reviewers]
    if close_source_branch is not None:
        body["close_source_branch"] = close_source_branch
    return body


def _build_pr_update_body(
    *,
    title: str | None,
    description: str | None,
    destination_branch: str | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if title is not None:
        body["title"] = title
    if description is not None:
        body["description"] = description
    if destination_branch:
        body["destination"] = {"branch": {"name": destination_branch}}
    return body


def _build_pr_merge_body(
    *,
    merge_strategy: str | None,
    message: str | None,
    close_source_branch: bool | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if merge_strategy:
        body["merge_strategy"] = merge_strategy
    if message:
        body["message"] = message
    if close_source_branch is not None:
        body["close_source_branch"] = close_source_branch
    return body
