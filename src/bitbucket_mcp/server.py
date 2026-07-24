import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from bitbucket_mcp.auth import AuthProvider, resolve_auth_provider
from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.config import Settings
from bitbucket_mcp.toolsets import TOOLSET_REGISTRY, raw_api

_RAW_API_EXCLUDE = "-bitbucket_api"
logger = logging.getLogger(__name__)


def make_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(mcp: FastMCP) -> AsyncGenerator[BitbucketClient, None]:
        client: BitbucketClient | None = None
        auth_provider: AuthProvider | None = None
        try:
            auth_provider = resolve_auth_provider(settings)
            client = BitbucketClient(base_url=settings.base_url, auth_provider=auth_provider)

            requested = settings.toolset_list
            for name in requested:
                register_fn = TOOLSET_REGISTRY.get(name)
                if register_fn is None:
                    if name != _RAW_API_EXCLUDE:
                        logger.warning("Unknown toolset requested: %s", name)
                    continue
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

            yield client
        finally:
            if client is not None:
                await client.aclose()
            if auth_provider is not None:
                await auth_provider.aclose()

    return lifespan


def create_server(settings: Settings, *, host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    """設定から FastMCP サーバーを構築する。"""
    return FastMCP(
        "bitbucket-mcp",
        host=host,
        port=port,
        lifespan=make_lifespan(settings),
    )
