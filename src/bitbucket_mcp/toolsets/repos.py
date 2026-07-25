"""repos ツールセット: リポジトリ・コミット・ブランチ・タグ・差分。"""

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

    async def list_repositories(
        *,
        workspace: str | None = None,
        q: str | None = None,
        sort: str | None = None,
        role: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List repositories in a workspace."""
        ws = ctx.resolve_workspace(workspace)
        query = build_query(page, pagelen, q=q, sort=sort, role=role)
        return await client.request("GET", f"/repositories/{ws}", query=query)

    async def get_repository(*, workspace: str | None = None, repo_slug: str) -> dict[str, Any]:
        """Get a single repository's metadata."""
        ws = ctx.resolve_workspace(workspace)
        return await client.request("GET", f"/repositories/{ws}/{repo_slug}")

    async def get_file_or_directory(
        *,
        workspace: str | None = None,
        repo_slug: str,
        commit: str,
        path: str,
        page: int | None = None,
    ) -> dict[str, Any]:
        """Get file contents or a directory listing at a commit."""
        ws = ctx.resolve_workspace(workspace)
        query = build_query(page)
        text = await client.request_text(
            "GET",
            f"/repositories/{ws}/{repo_slug}/src/{commit}/{path}",
            query=query,
        )
        return {"content": text}

    async def list_commits(
        *,
        workspace: str | None = None,
        repo_slug: str,
        revision: str | None = None,
        path: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List commits, optionally scoped to a revision or path."""
        ws = ctx.resolve_workspace(workspace)
        query = build_query(page, pagelen, path=path)
        endpoint = f"/repositories/{ws}/{repo_slug}/commits"
        if revision:
            endpoint = f"{endpoint}/{revision}"
        return await client.request("GET", endpoint, query=query)

    async def get_commit(
        *, workspace: str | None = None, repo_slug: str, commit: str
    ) -> dict[str, Any]:
        """Get a single commit by hash."""
        ws = ctx.resolve_workspace(workspace)
        return await client.request("GET", f"/repositories/{ws}/{repo_slug}/commit/{commit}")

    async def get_diff(
        *,
        workspace: str | None = None,
        repo_slug: str,
        spec: str,
        action: Literal["diff", "diffstat", "patch"] = "diff",
    ) -> dict[str, Any]:
        """Get a diff, diffstat, or patch for a commit spec (e.g. 'a..b')."""
        ws = ctx.resolve_workspace(workspace)
        base = f"/repositories/{ws}/{repo_slug}"
        if action == "diffstat":
            return await client.request("GET", f"{base}/diffstat/{spec}")
        text = await client.request_text("GET", f"{base}/{action}/{spec}")
        return {"content": text, "format": action}

    async def list_branches(
        *,
        workspace: str | None = None,
        repo_slug: str,
        q: str | None = None,
        sort: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List branches in a repository."""
        ws = ctx.resolve_workspace(workspace)
        query = build_query(page, pagelen, q=q, sort=sort)
        return await client.request(
            "GET", f"/repositories/{ws}/{repo_slug}/refs/branches", query=query
        )

    async def list_tags(
        *,
        workspace: str | None = None,
        repo_slug: str,
        q: str | None = None,
        sort: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List tags in a repository."""
        ws = ctx.resolve_workspace(workspace)
        query = build_query(page, pagelen, q=q, sort=sort)
        return await client.request("GET", f"/repositories/{ws}/{repo_slug}/refs/tags", query=query)

    ctx.tool(list_repositories, READ)
    ctx.tool(get_repository, READ)
    ctx.tool(get_file_or_directory, READ)
    ctx.tool(list_commits, READ)
    ctx.tool(get_commit, READ)
    ctx.tool(get_diff, READ)
    ctx.tool(list_branches, READ)
    ctx.tool(list_tags, READ)

    if read_only:
        return

    async def create_repository(
        *,
        workspace: str | None = None,
        repo_slug: str,
        is_private: bool = True,
        project_key: str | None = None,
        scm: str = "git",
    ) -> dict[str, Any]:
        """Create a new repository."""
        ws = ctx.resolve_workspace(workspace)
        body: dict[str, Any] = {"scm": scm, "is_private": is_private}
        if project_key:
            body["project"] = {"key": project_key}
        return await client.request("POST", f"/repositories/{ws}/{repo_slug}", body=body)

    async def delete_repository(*, workspace: str | None = None, repo_slug: str) -> dict[str, Any]:
        """Delete a repository. Destructive."""
        ws = ctx.resolve_workspace(workspace)
        return await client.request("DELETE", f"/repositories/{ws}/{repo_slug}")

    async def fork_repository(
        *,
        workspace: str | None = None,
        repo_slug: str,
        target_workspace: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Fork a repository."""
        ws = ctx.resolve_workspace(workspace)
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if target_workspace:
            body["workspace"] = {"slug": target_workspace}
        return await client.request("POST", f"/repositories/{ws}/{repo_slug}/forks", body=body)

    async def create_commit(
        *,
        workspace: str | None = None,
        repo_slug: str,
        message: str,
        files: dict[str, str],
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Create a commit by writing files on a branch."""
        ws = ctx.resolve_workspace(workspace)
        reserved_fields = {"message", "branch"}
        conflict = reserved_fields.intersection(files)
        if conflict:
            joined = ", ".join(sorted(conflict))
            raise ToolError(f"files に予約済みフィールド名が含まれています: {joined}")
        form: dict[str, Any] = {"message": message}
        if branch:
            form["branch"] = branch
        for file_path, content in files.items():
            form[file_path] = content
        return await client.request("POST", f"/repositories/{ws}/{repo_slug}/src", form=form)

    async def create_branch(
        *, workspace: str | None = None, repo_slug: str, name: str, target: str
    ) -> dict[str, Any]:
        """Create a branch pointing at a target commit hash."""
        ws = ctx.resolve_workspace(workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/refs/branches",
            body={"name": name, "target": {"hash": target}},
        )

    async def delete_branch(
        *, workspace: str | None = None, repo_slug: str, name: str
    ) -> dict[str, Any]:
        """Delete a branch. Destructive."""
        ws = ctx.resolve_workspace(workspace)
        return await client.request(
            "DELETE", f"/repositories/{ws}/{repo_slug}/refs/branches/{name}"
        )

    async def create_tag(
        *, workspace: str | None = None, repo_slug: str, name: str, target: str
    ) -> dict[str, Any]:
        """Create a tag pointing at a target commit hash."""
        ws = ctx.resolve_workspace(workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/refs/tags",
            body={"name": name, "target": {"hash": target}},
        )

    ctx.tool(create_repository, WRITE)
    ctx.tool(delete_repository, DESTRUCTIVE)
    ctx.tool(fork_repository, WRITE)
    ctx.tool(create_commit, WRITE)
    ctx.tool(create_branch, WRITE)
    ctx.tool(delete_branch, DESTRUCTIVE)
    ctx.tool(create_tag, WRITE)
