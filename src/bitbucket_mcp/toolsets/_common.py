from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import time
import urllib.parse
import webbrowser
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from bitbucket_mcp.auth import AuthConfigError, AuthProvider
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthCallbackServer, OAuthClient, OAuthFlowError, generate_state

T = TypeVar("T")
logger = logging.getLogger(__name__)


def resolve_workspace(workspace: str | None, default_workspace: str | None) -> str:
    """workspace を解決する。未指定なら ToolError。"""
    resolved = workspace or default_workspace
    if not resolved:
        raise ToolError(
            "workspace が指定されていません。引数 workspace か"
            " BITBUCKET_DEFAULT_WORKSPACE を設定してください。"
        )
    return resolved


def display_available() -> bool:
    if sys.platform in ("win32", "darwin"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


class AutoLoginController:
    """未ログイン時のブラウザ自動ログインを1つだけ実行する。"""

    _TIMEOUT_SECONDS = 300

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, coro: Callable[[], Awaitable[None]]) -> bool:
        if self.is_running():
            return False
        self._task = asyncio.create_task(self._run_with_timeout(coro))
        return True

    async def _run_with_timeout(self, coro: Callable[[], Awaitable[None]]) -> None:
        try:
            async with asyncio.timeout(self._TIMEOUT_SECONDS):
                await coro()
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            logger.warning("Automatic login timed out")
        except OAuthFlowError:
            logger.warning("Automatic login OAuth flow failed")
        except Exception as exc:  # noqa: BLE001, RUF100
            logger.error("Unexpected error during automatic login (%s)", type(exc).__name__)

    async def shutdown(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task


async def perform_auto_login(
    auth_provider: AuthProvider,
    oauth_client: OAuthClient,
    store: CredentialStore,
) -> None:
    """ブラウザOAuthログインを実行する。

    全体タイムアウトは設定しないため、呼び出し側で `asyncio.timeout()` などを使用する。
    本番では `AutoLoginController` 経由で呼び出す。
    """
    server: OAuthCallbackServer | None = None
    try:
        parsed = urllib.parse.urlparse(oauth_client.redirect_uri)
        port = int(parsed.port or 8976)
        state = generate_state()
        server = OAuthCallbackServer(host="127.0.0.1", port=port, expected_state=state)
        await server.start()
        url = oauth_client.build_authorize_url(state)
        webbrowser.open(url)
        code, _returned_state = await server.wait_callback()
        tokens = await oauth_client.exchange_code(code)
        store.save(
            tokens.to_stored(
                client_id=oauth_client.client_id,
                obtained_at=int(time.time()),
            )
        )
        await auth_provider.refresh()
    finally:
        if server is not None:
            await server.aclose()


def require_auth(
    auth_provider: AuthProvider,
    controller: AutoLoginController,
    oauth_client: OAuthClient | None,
    store: CredentialStore | None,
) -> Callable[
    [Callable[..., Awaitable[T]]],
    Callable[..., Awaitable[T]],
]:
    """未ログイン時に自動ログインを試みるデコレータ。"""

    def decorator(
        fn: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            if auth_provider.is_authenticated():
                return await fn(*args, **kwargs)

            if oauth_client is None or store is None:
                raise ToolError(
                    "認証が必要です。`bitbucket-mcp auth login` を実行するか、"
                    "BITBUCKET_TOKEN 等を設定してください。"
                )

            if not display_available():
                raise ToolError(
                    "認証が必要です。headless 環境では `bitbucket-mcp auth login --manual` "
                    "を実行してください。"
                )

            login_client = oauth_client
            credential_store = store
            started = controller.start(
                lambda: perform_auto_login(auth_provider, login_client, credential_store)
            )
            if started:
                raise ToolError(
                    "Bitbucket 認証をブラウザで開始しました。同意後に操作を再実行してください。"
                )
            raise ToolError("認証処理中です。少し待って再実行してください。")

        return wrapper

    return decorator


def wrap_tool(
    auth_provider: AuthProvider | None,
    oauth_client: OAuthClient | None,
    store: CredentialStore | None,
    controller: AutoLoginController | None = None,
) -> Callable[
    [Callable[..., Awaitable[T]]],
    Callable[..., Awaitable[T]],
]:
    """toolset 共通の認証ラッパーを生成する。"""
    if auth_provider is None:
        raise AuthConfigError(
            "auth_provider が指定されていません。BITBUCKET_TOKEN 等を設定してください。"
        )
    resolved_controller = controller or AutoLoginController()
    return require_auth(
        auth_provider,
        resolved_controller,
        oauth_client,
        store,
    )


READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
WRITE = ToolAnnotations(openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(destructiveHint=True, openWorldHint=True)


def build_query(
    page: int | None = None,
    pagelen: int | None = None,
    **filters: str | None,
) -> dict[str, Any]:
    """一覧系エンドポイント向けのクエリパラメータを組み立てる。"""
    from bitbucket_mcp.pagination import page_params

    query: dict[str, Any] = page_params(page, pagelen)
    for key, value in filters.items():
        if value:
            query[key] = value
    return query


def build_body(**fields: Any) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}


async def request_repo_json(
    ctx: Any,
    workspace: str | None,
    method: str,
    repo_slug: str,
    suffix: str,
    *,
    path_params: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    form: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = _build_repo_path(ctx, workspace, repo_slug, suffix, path_params)
    return await ctx.client.request(
        method,
        path,
        query=query,
        body=body,
        form=form,
    )


async def request_repo_text(
    ctx: Any,
    workspace: str | None,
    method: str,
    repo_slug: str,
    suffix: str,
    *,
    path_params: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> str:
    path = _build_repo_path(ctx, workspace, repo_slug, suffix, path_params)
    return await ctx.client.request_text(
        method,
        path,
        query=query,
    )


def _build_repo_path(
    ctx: Any,
    workspace: str | None,
    repo_slug: str,
    suffix: str,
    path_params: dict[str, Any] | None,
) -> str:
    resolved_suffix = suffix
    for name, value in (path_params or {}).items():
        resolved_suffix = resolved_suffix.replace(f"{{{name}}}", str(value))
    workspace_slug = ctx.resolve_workspace(workspace)
    return f"/repositories/{workspace_slug}/{repo_slug}{resolved_suffix}"


class RegisterContext:
    """toolset 登録の共通コンテキスト。"""

    def __init__(
        self,
        mcp: Any,
        client: Any,
        *,
        read_only: bool,
        default_workspace: str | None = None,
        wrap: Callable[..., Any] | None = None,
    ) -> None:
        self.mcp = mcp
        self.client = client
        self.read_only = read_only
        self.default_workspace = default_workspace
        self._wrap = wrap

    def resolve_workspace(self, workspace: str | None) -> str:
        """workspace を解決する。"""
        return resolve_workspace(workspace, self.default_workspace)

    def tool(
        self,
        fn: Callable[..., Awaitable[Any]],
        annotations: ToolAnnotations,
    ) -> None:
        """ツールを登録する。"""
        wrapped = self._wrap(fn) if self._wrap else fn
        self.mcp.add_tool(wrapped, annotations=annotations)

    async def request_json(
        self,
        workspace: str | None,
        method: str,
        path_template: str,
        *,
        path_params: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        path = path_template.format(
            ws=self.resolve_workspace(workspace),
            **(path_params or {}),
        )
        return await self.client.request(
            method,
            path,
            query=query,
            body=body,
            form=form,
        )

    async def request_text(
        self,
        workspace: str | None,
        method: str,
        path_template: str,
        *,
        path_params: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> str:
        path = path_template.format(
            ws=self.resolve_workspace(workspace),
            **(path_params or {}),
        )
        return await self.client.request_text(method, path, query=query)

    def register_tools(
        self,
        *,
        read: list[tuple[Callable[..., Awaitable[Any]], ToolAnnotations]] | None = None,
        write: list[tuple[Callable[..., Awaitable[Any]], ToolAnnotations]] | None = None,
        destructive: list[tuple[Callable[..., Awaitable[Any]], ToolAnnotations]] | None = None,
        always: list[tuple[Callable[..., Awaitable[Any]], ToolAnnotations]] | None = None,
    ) -> None:
        """ツールを一括登録する。read_only の場合は write/destructive をスキップする。
        always は read_only に関係なく常に登録される。
        """
        for fn, ann in always or []:
            self.tool(fn, ann)
        for fn, ann in read or []:
            self.tool(fn, ann)
        if self.read_only:
            return
        for fn, ann in write or []:
            self.tool(fn, ann)
        for fn, ann in destructive or []:
            self.tool(fn, ann)


def create_toolset_context(
    mcp: Any,
    client: Any,
    *,
    read_only: bool,
    default_workspace: str | None = None,
    auth_provider: AuthProvider | None = None,
    oauth_client: OAuthClient | None = None,
    store: CredentialStore | None = None,
    controller: AutoLoginController | None = None,
) -> RegisterContext:
    """toolset 登録の共通コンテキストを生成する。"""
    return RegisterContext(
        mcp,
        client,
        read_only=read_only,
        default_workspace=default_workspace,
        wrap=wrap_tool(auth_provider, oauth_client, store, controller),
    )


def create_toolset_context_from_register_args(
    mcp: Any,
    client: Any,
    read_only: bool,
    default_workspace: str | None = None,
    auth_provider: AuthProvider | None = None,
    oauth_client: OAuthClient | None = None,
    store: CredentialStore | None = None,
    controller: AutoLoginController | None = None,
) -> RegisterContext:
    return create_toolset_context(
        mcp,
        client,
        read_only=read_only,
        default_workspace=default_workspace,
        auth_provider=auth_provider,
        oauth_client=oauth_client,
        store=store,
        controller=controller,
    )
