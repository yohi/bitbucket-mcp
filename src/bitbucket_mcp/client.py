"""Bitbucket API への HTTP アクセスを担う httpx ラッパ。"""

from types import TracebackType
from typing import TYPE_CHECKING, Any, NoReturn

import anyio
import httpx
from mcp.server.fastmcp.exceptions import ToolError

from bitbucket_mcp.auth import NotAuthenticatedError
from bitbucket_mcp.errors import build_tool_error

if TYPE_CHECKING:
    from bitbucket_mcp.auth import AuthProvider

_RETRY_STATUSES = {429, 502, 503, 504}
_RETRYABLE_METHODS = {"GET", "HEAD"}


class BitbucketClient:
    """HTTP・認証ヘッダ注入・リトライだけを知るクライアント。"""

    def __init__(
        self,
        *,
        base_url: str,
        auth_provider: AuthProvider,
        timeout: float = 30.0,
        max_retries: int = 2,
        backoff_base: float = 0.5,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
        self._auth_provider = auth_provider
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    async def _authorization_header(self) -> str:
        try:
            return await self._auth_provider.authorization_header()
        except NotAuthenticatedError as exc:
            raise ToolError(
                f"認証が必要です。再ログインしてください。Run auth login. ({exc})"
            ) from exc

    async def _send(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        attempt = 0
        refreshed = False
        method_upper = method.upper()
        headers = {"Authorization": await self._authorization_header()}
        while True:
            try:
                response = await self._client.request(
                    method,
                    path,
                    params=query,
                    json=json,
                    data=data,
                    headers=headers,
                )
            except httpx.RequestError:
                if await self._maybe_retry(method_upper, attempt):
                    attempt += 1
                    continue
                raise
            if response.status_code == 401 and not refreshed:
                headers = await self._refresh_auth_header()
                refreshed = True
                continue
            if response.status_code == 401:
                raise ToolError("認証に失敗しました。再ログインしてください。Run auth login.")
            if await self._maybe_retry_for_status(response.status_code, method_upper, attempt):
                attempt += 1
                continue
            return response

    async def _maybe_retry(self, method_upper: str, attempt: int) -> bool:
        """通信エラー時にリトライすべきか判定し、必要なら待機する。"""
        if method_upper not in _RETRYABLE_METHODS or attempt >= self._max_retries:
            return False
        await anyio.sleep(self._backoff_base * (2**attempt))
        return True

    async def _maybe_retry_for_status(
        self, status_code: int, method_upper: str, attempt: int
    ) -> bool:
        """HTTP エラーステータス時にリトライすべきか判定し、必要なら待機する。"""
        if status_code not in _RETRY_STATUSES:
            return False
        if method_upper not in _RETRYABLE_METHODS or attempt >= self._max_retries:
            return False
        await anyio.sleep(self._backoff_base * (2**attempt))
        return True

    async def _refresh_auth_header(self) -> dict[str, str]:
        """認証を refresh し、新しい Authorization ヘッダを返す。"""
        try:
            await self._auth_provider.refresh()
        except NotAuthenticatedError as exc:
            raise ToolError(
                f"認証の更新に失敗しました。再ログインしてください。Run auth login. ({exc})"
            ) from exc
        return {"Authorization": await self._authorization_header()}

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """JSON レスポンスを返すリクエスト。form 指定時は form-urlencoded で送信。"""
        response = await self._send(
            method,
            path,
            query=query,
            json=body if form is None else None,
            data=form,
        )
        if response.is_success:
            if not response.content:
                return {}
            return response.json()
        self._raise(response)

    async def request_text(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
    ) -> str:
        """テキストレスポンス (diff/patch/ログ) を返すリクエスト。"""
        response = await self._send(method, path, query=query)
        if response.is_success:
            return response.text
        self._raise(response)

    def _raise(self, response: httpx.Response) -> NoReturn:
        try:
            payload: dict[str, Any] | None = response.json()
        except (ValueError, httpx.DecodingError):
            payload = None
        raise build_tool_error(
            response.status_code,
            payload,
            retry_after=response.headers.get("Retry-After"),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "BitbucketClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
