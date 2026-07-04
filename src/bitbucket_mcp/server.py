from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from bitbucket_mcp.auth import resolve_auth_header
from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.config import Settings
from bitbucket_mcp.toolsets import TOOLSET_REGISTRY, raw_api

_RAW_API_EXCLUDE = "-bitbucket_api"


def make_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(mcp: FastMCP) -> AsyncGenerator[BitbucketClient, None]:
        auth_header = resolve_auth_header(settings)
        client = BitbucketClient(base_url=settings.base_url, auth_header=auth_header)

        requested = settings.toolset_list
        for name in requested:
            register_fn = TOOLSET_REGISTRY.get(name)
            if register_fn is not None:
                register_fn(
                    mcp,
                    client,
                    read_only=settings.read_only,
                    default_workspace=settings.default_workspace,
                )

        if _RAW_API_EXCLUDE not in requested:
            raw_api.register(
                mcp,
                client,
                read_only=settings.read_only,
                default_workspace=settings.default_workspace,
            )

        try:
            yield client
        finally:
            await client.aclose()

    return lifespan


def create_server(
    settings: Settings, *, host: str = "127.0.0.1", port: int = 8000
) -> FastMCP:
    """設定から FastMCP サーバーを構築する。"""
    return FastMCP(
        "bitbucket-mcp",
        host=host,
        port=port,
        lifespan=make_lifespan(settings),
    )
