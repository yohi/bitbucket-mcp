from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP

from bitbucket_mcp.auth import StaticAuthProvider
from bitbucket_mcp.client import BitbucketClient

RegisterFn = Callable[..., None]
MakeServer = Callable[..., tuple[FastMCP, BitbucketClient]]
CallTool = Callable[[FastMCP, str, dict[str, Any]], Awaitable[tuple[Any, Any]]]

_BITBUCKET_ENV_VARS = [
    "BITBUCKET_TOKEN",
    "BITBUCKET_EMAIL",
    "BITBUCKET_API_TOKEN",
    "BITBUCKET_DEFAULT_WORKSPACE",
    "BITBUCKET_TOOLSETS",
    "BITBUCKET_READ_ONLY",
    "BITBUCKET_BASE_URL",
]


@pytest.fixture(autouse=True)
def _clean_bitbucket_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _BITBUCKET_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
async def register_toolset() -> Any:
    clients: list[BitbucketClient] = []

    def _make(
        register_fn: RegisterFn,
        *,
        read_only: bool = False,
        default_workspace: str | None = None,
    ) -> tuple[FastMCP, BitbucketClient]:
        client = BitbucketClient(
            base_url="https://api.bitbucket.org/2.0",
            auth_provider=StaticAuthProvider("Bearer test-token"),
            backoff_base=0.0,
        )
        mcp = FastMCP("bitbucket-mcp-test")
        register_fn(mcp, client, read_only=read_only, default_workspace=default_workspace)
        clients.append(client)
        return mcp, client

    yield _make
    for client in clients:
        await client.aclose()


@pytest.fixture
def call_tool() -> CallTool:
    async def _call(mcp: FastMCP, name: str, arguments: dict[str, Any]) -> tuple[Any, Any]:
        result = await mcp.call_tool(name, arguments)
        if isinstance(result, tuple):
            content, structured = result
            return content, structured
        return result, None

    return _call
