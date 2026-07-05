"""Bitbucket MCP toolset レジストリ。"""

from collections.abc import Callable

from bitbucket_mcp.toolsets import (
    context,
    issues,
    pipelines,
    pull_requests,
    repos,
    users,
)

RegisterFn = Callable[..., None]

TOOLSET_REGISTRY: dict[str, RegisterFn] = {
    "context": context.register,
    "repos": repos.register,
    "pull_requests": pull_requests.register,
    "issues": issues.register,
    "pipelines": pipelines.register,
    "users": users.register,
}

DEFAULT_TOOLSETS: list[str] = list(TOOLSET_REGISTRY)
