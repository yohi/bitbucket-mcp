"""pipelines ツールセット: パイプラインの参照・実行・停止。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.models import PipelineTarget
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.pagination import page_params
from bitbucket_mcp.toolsets._common import AutoLoginController, require_auth, resolve_workspace

if TYPE_CHECKING:
    from bitbucket_mcp.auth import AuthProvider

_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
_WRITE = ToolAnnotations(openWorldHint=True)


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
    from bitbucket_mcp.auth import StaticAuthProvider

    controller = controller or AutoLoginController()

    def _wrap(fn: Any) -> Any:
        return require_auth(
            auth_provider or StaticAuthProvider("Bearer test-token"),
            controller,
            oauth_client,
            store,
        )(fn)

    async def list_pipelines(
        *,
        workspace: str | None = None,
        repo_slug: str,
        sort: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List pipeline runs in a repository."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page, pagelen)
        if sort:
            query["sort"] = sort
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
        ws = resolve_workspace(workspace, default_workspace)
        base = f"/repositories/{ws}/{repo_slug}/pipelines/{pipeline_uuid}"
        if action == "details":
            return await client.request("GET", base)
        if action == "steps":
            return await client.request(
                "GET",
                f"{base}/steps",
                query=page_params(page, pagelen),
            )
        if step_uuid is None:
            raise ToolError("action='step_log' には step_uuid が必要です。")
        text = await client.request_text("GET", f"{base}/steps/{step_uuid}/log")
        return {"content": text}

    mcp.add_tool(_wrap(list_pipelines), annotations=_READ)
    mcp.add_tool(_wrap(get_pipeline), annotations=_READ)

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
        ws = resolve_workspace(workspace, default_workspace)
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
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pipelines/{pipeline_uuid}/stopPipeline",
        )

    mcp.add_tool(_wrap(run_pipeline), annotations=_WRITE)
    mcp.add_tool(_wrap(stop_pipeline), annotations=_WRITE)
