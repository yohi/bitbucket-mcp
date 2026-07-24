import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from bitbucket_mcp.auth import AuthProvider, OAuthAuthProvider, resolve_auth_provider
from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.config import Settings
from bitbucket_mcp.credentials import CredentialStore, default_credential_path
from bitbucket_mcp.oauth import OAuthClient
from bitbucket_mcp.toolsets import TOOLSET_REGISTRY, raw_api
from bitbucket_mcp.toolsets._common import AutoLoginController

_RAW_API_EXCLUDE = "-bitbucket_api"
logger = logging.getLogger(__name__)


async def _bitbucket_login(auth_provider: AuthProvider) -> str:
    if auth_provider.is_authenticated():
        return "既にログインしています。"
    raise ToolError(
        "ブラウザでのログインを開始してください。"
        "(この実装では CLI `bitbucket-mcp auth login` を利用してください。)"
    )


def _oauth_client_for_login(settings: Settings) -> OAuthClient | None:
    if not settings.oauth_client_id or not settings.oauth_client_secret:
        return None
    return OAuthClient(
        base_url=settings.oauth_base_url,
        client_id=settings.oauth_client_id,
        client_secret=settings.oauth_client_secret.get_secret_value(),
        redirect_uri=f"http://127.0.0.1:{settings.oauth_callback_port}/callback",
        scopes=settings.oauth_scopes(),
    )


def make_lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(mcp: FastMCP) -> AsyncGenerator[BitbucketClient, None]:
        client: BitbucketClient | None = None
        oauth_client: OAuthClient | None = None
        auth_provider: AuthProvider | None = None
        controller = AutoLoginController()
        try:
            auth_provider = resolve_auth_provider(settings)
            store = CredentialStore(default_credential_path(settings.config_dir))
            oauth_client = _oauth_client_for_login(settings)
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
                    auth_provider=auth_provider,
                    oauth_client=oauth_client,
                    store=store,
                    controller=controller,
                )

            if _RAW_API_EXCLUDE not in requested:
                raw_api.register(
                    mcp,
                    client,
                    read_only=settings.read_only,
                    default_workspace=settings.default_workspace,
                    auth_provider=auth_provider,
                    oauth_client=oauth_client,
                    store=store,
                    controller=controller,
                )

            async def bitbucket_login() -> str:
                return await _bitbucket_login(auth_provider)

            mcp.add_tool(
                bitbucket_login,
                name="bitbucket_login",
                description="ブラウザ OAuth で Bitbucket に再ログインします。",
            )

            yield client
        finally:
            await controller.shutdown()
            if client is not None:
                await client.aclose()
            if oauth_client is not None:
                await oauth_client.aclose()
            if isinstance(auth_provider, OAuthAuthProvider):
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
