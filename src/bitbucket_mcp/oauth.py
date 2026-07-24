"""Bitbucket OAuth 2.0 Authorization Code Grant プロトコル。"""

from __future__ import annotations

import asyncio
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Any

import httpx

from bitbucket_mcp.credentials import StoredCredentials


@dataclass(frozen=True)
class OAuthTokenResponse:
    access_token: str
    refresh_token: str
    expires_in: int
    scopes: list[str]
    token_type: str

    def to_stored(self, client_id: str, obtained_at: int) -> StoredCredentials:
        return StoredCredentials(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            expires_at=obtained_at + self.expires_in,
            scopes=self.scopes,
            token_type=self.token_type,
            client_id=client_id,
            obtained_at=obtained_at,
        )


class OAuthFlowError(RuntimeError):
    """OAuth フロー内のエラー。"""


def build_redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}/callback"


def generate_state() -> str:
    return secrets.token_urlsafe(32)


class OAuthClient:
    """Bitbucket OAuth エンドポイントとの通信。"""

    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str],
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._scopes = list(scopes)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            auth=(client_id, client_secret),
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def client_id(self) -> str:
        return self._client_id

    @property
    def redirect_uri(self) -> str:
        return self._redirect_uri

    @property
    def scopes(self) -> list[str]:
        return list(self._scopes)

    def build_authorize_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "state": state,
            "scope": " ".join(self._scopes),
        }
        query = urllib.parse.urlencode(params)
        return f"{self._base_url}/site/oauth2/authorize?{query}"

    async def exchange_code(self, code: str) -> OAuthTokenResponse:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
        }
        return await self._token_request(data)

    async def refresh_token(self, refresh_token: str) -> OAuthTokenResponse:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        return await self._token_request(data)

    async def _token_request(self, data: dict[str, str]) -> OAuthTokenResponse:
        response = await self._client.post("/site/oauth2/access_token", data=data)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        scope_text = payload.get("scopes", "")
        scopes = scope_text.split() if isinstance(scope_text, str) else list(scope_text)
        return OAuthTokenResponse(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload.get("refresh_token", "")),
            expires_in=int(payload.get("expires_in", 0)),
            scopes=scopes,
            token_type=str(payload.get("token_type", "bearer")).lower(),
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class OAuthCallbackServer:
    """loopback callback を待ち受ける HTTP サーバー。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 8976) -> None:
        self._host = host
        self._port = port
        self._server: asyncio.Server | None = None
        self._event = asyncio.Event()
        self._code: str | None = None
        self._state: str | None = None
        self._error: str | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            return self._port
        for sock in self._server.sockets:
            return sock.getsockname()[1]
        return self._port

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self._host, self._port)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line = await reader.readline()
        parts = request_line.decode().split(" ")
        path = parts[1] if len(parts) > 1 else "/"
        while True:
            line = await reader.readline()
            if line == b"\r\n":
                break

        parsed = urllib.parse.urlparse(path)
        query = urllib.parse.parse_qs(parsed.query)
        self._code = self._first(query.get("code"))
        self._state = self._first(query.get("state"))
        self._error = self._first(query.get("error"))

        body = "認証OK。タブを閉じてください。".encode()
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body
        )
        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        self._event.set()

    @staticmethod
    def _first(value: list[str] | None) -> str | None:
        if not value:
            return None
        return value[0]

    async def wait_callback(self) -> tuple[str, str | None]:
        await self._event.wait()
        if self._error:
            raise OAuthFlowError(f"OAuth callback error: {self._error}")
        if self._code is None:
            raise OAuthFlowError("callback did not include code")
        return (self._code, self._state)

    async def aclose(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
