"""pipelines ツールセット: パイプラインの参照・実行・停止。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.models import PipelineTarget
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.toolsets._common import (
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

    async def list_pipelines(
        *,
        workspace: str | None = None,
        repo_slug: str,
        sort: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List pipeline runs in a repository."""
        ws = ctx.resolve_workspace(workspace)
        query = build_query(page, pagelen, sort=sort)
        return await client.request(
            "GET", f"/repositories/{ws}/{repo_slug}/pipelines/", query=query
        )

    async def get_pipeline(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pipeline_uuid: str,
        action: Literal["details", "steps", "step_log"] = "details",
        step_uuid: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """Get a pipeline, its steps, or a step log."""
        ws = ctx.resolve_workspace(workspace)
        base = f"/repositories/{ws}/{repo_slug}/pipelines/{pipeline_uuid}"
        if action == "details":
            return await client.request("GET", base)
        if action == "steps":
            return await client.request(
                "GET",
                f"{base}/steps",
                query=build_query(page, pagelen),
            )
        if step_uuid is None:
            raise ToolError("action='step_log' には step_uuid が必要です。")
        text = await client.request_text("GET", f"{base}/steps/{step_uuid}/log")
        return {"content": text}

    ctx.tool(list_pipelines, READ)
    ctx.tool(get_pipeline, READ)

    if read_only:
        return

    async def run_pipeline(
        *,
        workspace: str | None = None,
        repo_slug: str,
        target: PipelineTarget,
        variables: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Trigger a pipeline run for a branch or tag."""
        ws = ctx.resolve_workspace(workspace)
        target_body: dict[str, Any] = {
            "ref_type": target.ref_type,
            "ref_name": target.ref_name,
            "type": "pipeline_ref_target",
        }
        if target.selector is not None:
            target_body["selector"] = target.selector
        body: dict[str, Any] = {"target": target_body}
        if variables:
            body["variables"] = variables
        return await client.request("POST", f"/repositories/{ws}/{repo_slug}/pipelines/", body=body)

    async def stop_pipeline(
        *, workspace: str | None = None, repo_slug: str, pipeline_uuid: str
    ) -> dict[str, Any]:
        """Stop a running pipeline."""
        ws = ctx.resolve_workspace(workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pipelines/{pipeline_uuid}/stopPipeline",
        )

    ctx.tool(run_pipeline, WRITE)
    ctx.tool(stop_pipeline, WRITE)
