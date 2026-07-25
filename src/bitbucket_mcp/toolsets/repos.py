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
    build_body,
    build_query,
    create_toolset_context_from_register_args,
    request_repo_json,
    request_repo_text,
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
        query = build_query(page, pagelen, q=q, sort=sort, role=role)
        return await ctx.request_json(
            workspace,
            "GET",
            "/repositories/{ws}",
            query=query,
        )

    async def get_repository(*, workspace: str | None = None, repo_slug: str) -> dict[str, Any]:
        """Get a single repository's metadata."""
        return await request_repo_json(ctx, workspace, "GET", repo_slug, "")

    async def get_file_or_directory(
        *,
        workspace: str | None = None,
        repo_slug: str,
        commit: str,
        path: str,
        page: int | None = None,
    ) -> dict[str, Any]:
        """Get file contents or a directory listing at a commit."""
        query = build_query(page)
        text = await request_repo_text(
            ctx,
            workspace,
            "GET",
            repo_slug,
            f"/src/{commit}/{path}",
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
        query = build_query(page, pagelen, path=path)
        path_template = "/repositories/{ws}/{repo_slug}/commits"
        path_params: dict[str, Any] = {"repo_slug": repo_slug}
        if revision:
            path_template += "/{revision}"
            path_params["revision"] = revision
        return await request_repo_json(
            ctx,
            workspace,
            "GET",
            repo_slug,
            "/commits" + (f"/{revision}" if revision else ""),
            query=query,
        )

    async def get_commit(
        *, workspace: str | None = None, repo_slug: str, commit: str
    ) -> dict[str, Any]:
        """Get a single commit by hash."""
        return await request_repo_json(ctx, workspace, "GET", repo_slug, f"/commit/{commit}")

    async def get_diff(
        *,
        workspace: str | None = None,
        repo_slug: str,
        spec: str,
        action: Literal["diff", "diffstat", "patch"] = "diff",
    ) -> dict[str, Any]:
        """Get a diff, diffstat, or patch for a commit spec (e.g. 'a..b')."""
        if action == "diffstat":
            return await request_repo_json(ctx, workspace, "GET", repo_slug, f"/diffstat/{spec}")
        text = await request_repo_text(ctx, workspace, "GET", repo_slug, f"/{action}/{spec}")
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
        query = build_query(page, pagelen, q=q, sort=sort)
        return await request_repo_json(
            ctx, workspace, "GET", repo_slug, "/refs/branches", query=query
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
        query = build_query(page, pagelen, q=q, sort=sort)
        return await request_repo_json(
            ctx, workspace, "GET", repo_slug, "/refs/tags", query=query
        )

    ctx.register_tools(
        read=[
            (list_repositories, READ),
            (get_repository, READ),
            (get_file_or_directory, READ),
            (list_commits, READ),
            (get_commit, READ),
            (get_diff, READ),
            (list_branches, READ),
            (list_tags, READ),
        ]
    )

    async def create_repository(
        *,
        workspace: str | None = None,
        repo_slug: str,
        is_private: bool = True,
        project_key: str | None = None,
        scm: str = "git",
    ) -> dict[str, Any]:
        """Create a new repository."""
        body = build_body(
            scm=scm,
            is_private=is_private,
            project={"key": project_key} if project_key else None,
        )
        return await request_repo_json(ctx, workspace, "POST", repo_slug, "", body=body)

    async def delete_repository(*, workspace: str | None = None, repo_slug: str) -> dict[str, Any]:
        """Delete a repository. Destructive."""
        return await request_repo_json(ctx, workspace, "DELETE", repo_slug, "")

    async def fork_repository(
        *,
        workspace: str | None = None,
        repo_slug: str,
        target_workspace: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Fork a repository."""
        body = build_body(
            name=name if name else None,
            workspace={"slug": target_workspace} if target_workspace else None,
        )
        return await request_repo_json(
            ctx, workspace, "POST", repo_slug, "/forks", body=body
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
        return await request_repo_json(ctx, workspace, "POST", repo_slug, "/src", form=form)

    async def create_branch(
        *, workspace: str | None = None, repo_slug: str, name: str, target: str
    ) -> dict[str, Any]:
        """Create a branch pointing at a target commit hash."""
        return await request_repo_json(
            ctx,
            workspace,
            "POST",
            repo_slug,
            "/refs/branches",
            body={"name": name, "target": {"hash": target}},
        )

    async def delete_branch(
        *, workspace: str | None = None, repo_slug: str, name: str
    ) -> dict[str, Any]:
        """Delete a branch. Destructive."""
        return await request_repo_json(
            ctx, workspace, "DELETE", repo_slug, f"/refs/branches/{name}"
        )

    async def create_tag(
        *, workspace: str | None = None, repo_slug: str, name: str, target: str
    ) -> dict[str, Any]:
        """Create a tag pointing at a target commit hash."""
        return await request_repo_json(
            ctx,
            workspace,
            "POST",
            repo_slug,
            "/refs/tags",
            body={"name": name, "target": {"hash": target}},
        )

    ctx.register_tools(
        write=[
            (create_repository, WRITE),
            (fork_repository, WRITE),
            (create_commit, WRITE),
            (create_branch, WRITE),
            (create_tag, WRITE),
        ],
        destructive=[
            (delete_repository, DESTRUCTIVE),
            (delete_branch, DESTRUCTIVE),
        ],
    )
