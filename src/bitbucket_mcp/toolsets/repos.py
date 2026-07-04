"""repos ツールセット: リポジトリ・コミット・ブランチ・タグ・差分。"""

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient
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
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page, pagelen)
        if q:
            query["q"] = q
        if sort:
            query["sort"] = sort
        if role:
            query["role"] = role
        return await client.request("GET", f"/repositories/{ws}", query=query)

    async def get_repository(
        *, workspace: str | None = None, repo_slug: str
    ) -> dict[str, Any]:
        """Get a single repository's metadata."""
        ws = resolve_workspace(workspace, default_workspace)
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
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        text = await client.request_text(
            "GET",
            f"/repositories/{ws}/{repo_slug}/src/{commit}/{path}",
            query=query or None,
        )
        return {"content": text}

    async def list_commits(
        *,
        workspace: str | None = None,
        repo_slug: str,
        revision: str | None = None,
        path: str | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        """List commits, optionally scoped to a revision or path."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        if path:
            query["path"] = path
        endpoint = f"/repositories/{ws}/{repo_slug}/commits"
        if revision:
            endpoint = f"{endpoint}/{revision}"
        return await client.request("GET", endpoint, query=query or None)

    async def get_commit(
        *, workspace: str | None = None, repo_slug: str, commit: str
    ) -> dict[str, Any]:
        """Get a single commit by hash."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "GET", f"/repositories/{ws}/{repo_slug}/commit/{commit}"
        )

    async def get_diff(
        *,
        workspace: str | None = None,
        repo_slug: str,
        spec: str,
        action: Literal["diff", "diffstat", "patch"] = "diff",
    ) -> dict[str, Any]:
        """Get a diff, diffstat, or patch for a commit spec (e.g. 'a..b')."""
        ws = resolve_workspace(workspace, default_workspace)
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
    ) -> dict[str, Any]:
        """List branches in a repository."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page)
        if q:
            query["q"] = q
        if sort:
            query["sort"] = sort
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
    ) -> dict[str, Any]:
        """List tags in a repository."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page)
        if q:
            query["q"] = q
        if sort:
            query["sort"] = sort
        return await client.request(
            "GET", f"/repositories/{ws}/{repo_slug}/refs/tags", query=query
        )

    mcp.add_tool(list_repositories, annotations=_READ)
    mcp.add_tool(get_repository, annotations=_READ)
    mcp.add_tool(get_file_or_directory, annotations=_READ)
    mcp.add_tool(list_commits, annotations=_READ)
    mcp.add_tool(get_commit, annotations=_READ)
    mcp.add_tool(get_diff, annotations=_READ)
    mcp.add_tool(list_branches, annotations=_READ)
    mcp.add_tool(list_tags, annotations=_READ)

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
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {"scm": scm, "is_private": is_private}
        if project_key:
            body["project"] = {"key": project_key}
        return await client.request(
            "POST", f"/repositories/{ws}/{repo_slug}", body=body
        )

    async def delete_repository(
        *, workspace: str | None = None, repo_slug: str
    ) -> dict[str, Any]:
        """Delete a repository. Destructive."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "DELETE", f"/repositories/{ws}/{repo_slug}"
        )

    async def fork_repository(
        *,
        workspace: str | None = None,
        repo_slug: str,
        target_workspace: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Fork a repository."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if target_workspace:
            body["workspace"] = {"slug": target_workspace}
        return await client.request(
            "POST", f"/repositories/{ws}/{repo_slug}/forks", body=body
        )

    async def create_commit(
        *,
        workspace: str | None = None,
        repo_slug: str,
        message: str,
        files: dict[str, str],
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Create a commit by writing files on a branch."""
        ws = resolve_workspace(workspace, default_workspace)
        form: dict[str, Any] = {"message": message}
        if branch:
            form["branch"] = branch
        for file_path, content in files.items():
            form[file_path] = content
        return await client.request(
            "POST", f"/repositories/{ws}/{repo_slug}/src", form=form
        )

    async def create_branch(
        *, workspace: str | None = None, repo_slug: str, name: str, target: str
    ) -> dict[str, Any]:
        """Create a branch pointing at a target commit hash."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/refs/branches",
            body={"name": name, "target": {"hash": target}},
        )

    async def delete_branch(
        *, workspace: str | None = None, repo_slug: str, name: str
    ) -> dict[str, Any]:
        """Delete a branch. Destructive."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "DELETE", f"/repositories/{ws}/{repo_slug}/refs/branches/{name}"
        )

    async def create_tag(
        *, workspace: str | None = None, repo_slug: str, name: str, target: str
    ) -> dict[str, Any]:
        """Create a tag pointing at a target commit hash."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/refs/tags",
            body={"name": name, "target": {"hash": target}},
        )

    mcp.add_tool(create_repository, annotations=_WRITE)
    mcp.add_tool(delete_repository, annotations=_DESTRUCTIVE)
    mcp.add_tool(fork_repository, annotations=_WRITE)
    mcp.add_tool(create_commit, annotations=_WRITE)
    mcp.add_tool(create_branch, annotations=_WRITE)
    mcp.add_tool(delete_branch, annotations=_DESTRUCTIVE)
    mcp.add_tool(create_tag, annotations=_WRITE)
