"""Bitbucket API への HTTP アクセスを担う httpx ラッパ。"""

import asyncio
from types import TracebackType
from typing import Any, NoReturn

import httpx

from bitbucket_mcp.errors import build_tool_error

_RETRY_STATUSES = {429, 502, 503, 504}
_RETRYABLE_METHODS = {"GET", "HEAD"}


class BitbucketClient:
    """HTTP・認証ヘッダ注入・リトライだけを知るクライアント。"""

    def __init__(
        self,
        *,
        base_url: str,
        auth_header: str,
        timeout: float = 30.0,
        max_retries: int = 2,
        backoff_base: float = 0.5,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": auth_header, "Accept": "application/json"},
            timeout=timeout,
        )
        self._max_retries = max_retries
        self._backoff_base = backoff_base

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
        while True:
            response = await self._client.request(
                method, path, params=query, json=json, data=data
            )
            if (
                response.status_code in _RETRY_STATUSES
                and method.upper() in _RETRYABLE_METHODS
                and attempt < self._max_retries
            ):
                await asyncio.sleep(self._backoff_base * (2**attempt))
                attempt += 1
                continue
            return response

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
            retry_after=response.headers.get("X-RateLimit-Reset"),
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
