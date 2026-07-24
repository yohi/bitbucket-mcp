from __future__ import annotations

import asyncio
import base64
import time
from typing import Protocol

import anyio
from pydantic import SecretStr

from bitbucket_mcp.config import Settings
from bitbucket_mcp.credentials import (
    CredentialStore,
    StoredCredentials,
    default_credential_path,
)
from bitbucket_mcp.oauth import OAuthClient


class AuthConfigError(RuntimeError):
    """認証設定が不足または不正な場合に送出される。"""


class NotAuthenticatedError(RuntimeError):
    """認証が必要な操作を未認証で実行した場合に送出される。"""


class AuthProvider(Protocol):
    async def authorization_header(self) -> str: ...

    async def refresh(self) -> None: ...

    def is_authenticated(self) -> bool: ...


class StaticAuthProvider:
    def __init__(self, header: str) -> None:
        self._header = header

    async def authorization_header(self) -> str:
        return self._header

    async def refresh(self) -> None:
        return None

    def is_authenticated(self) -> bool:
        return True


class OAuthAuthProvider:
    _EXPIRY_SKEW_SECONDS = 60

    def __init__(
        self,
        *,
        store: CredentialStore,
        oauth_client: OAuthClient,
        client_id: str,
        client_secret: SecretStr,
    ) -> None:
        self._store = store
        self._oauth_client = oauth_client
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_lock = asyncio.Lock()

    def is_authenticated(self) -> bool:
        creds = self._store.load()
        return creds is not None and creds.client_id == self._client_id

    async def aclose(self) -> None:
        await self._oauth_client.aclose()

    async def authorization_header(self) -> str:
        creds = self._store.load()
        if creds is None or creds.client_id != self._client_id:
            raise NotAuthenticatedError(
                "Bitbucket OAuth ログインが必要です。"
                "`bitbucket-mcp auth login` を実行してください。"
            )
        if self._is_near_expiry(creds):
            await self.refresh()
            creds = self._store.load()
            if creds is None or creds.client_id != self._client_id:
                raise NotAuthenticatedError("トークン更新後に資格情報が見つかりません。")
        return f"Bearer {creds.access_token}"

    async def refresh(self) -> None:
        async with self._refresh_lock:

            def _locked_refresh() -> StoredCredentials:
                with self._store.locked():
                    creds = self._store.load()
                    if (
                        creds is not None
                        and creds.client_id == self._client_id
                        and not self._is_near_expiry(creds)
                    ):
                        return creds
                    if (
                        creds is None
                        or creds.client_id != self._client_id
                        or not creds.refresh_token
                    ):
                        raise NotAuthenticatedError(
                            "再ログインが必要です。`bitbucket-mcp auth login` を実行してください。"
                        )
                    client = OAuthClient(
                        base_url=self._oauth_client.base_url,
                        client_id=self._client_id,
                        client_secret=self._client_secret.get_secret_value(),
                        redirect_uri=self._oauth_client.redirect_uri,
                        scopes=self._oauth_client.scopes,
                    )
                    try:
                        new_tokens = asyncio.run(client.refresh_token(creds.refresh_token))
                    finally:
                        asyncio.run(client.aclose())
                    new_creds = new_tokens.to_stored(
                        client_id=self._client_id,
                        obtained_at=int(time.time()),
                    )
                    self._store.save(new_creds)
                    return new_creds

            await anyio.to_thread.run_sync(  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
                _locked_refresh
            )

    def _is_near_expiry(self, creds: StoredCredentials) -> bool:
        if creds.expires_at <= 0:
            return False
        return int(time.time()) >= creds.expires_at - self._EXPIRY_SKEW_SECONDS


def _build_static_header(settings: Settings) -> str | None:
    if settings.email and settings.api_token:
        raw = f"{settings.email}:{settings.api_token.get_secret_value()}".encode()
        return "Basic " + base64.b64encode(raw).decode("ascii")
    if settings.token:
        return f"Bearer {settings.token.get_secret_value()}"
    return None


def _credential_store(settings: Settings) -> CredentialStore:
    return CredentialStore(default_credential_path(settings.config_dir))


def resolve_auth_provider(settings: Settings) -> AuthProvider:
    store = _credential_store(settings)
    if settings.oauth_client_id and settings.oauth_client_secret:
        creds = store.load()
        if creds is not None and creds.client_id == settings.oauth_client_id:
            return _build_oauth_provider(settings, store)

    static_header = _build_static_header(settings)
    if static_header is not None:
        return StaticAuthProvider(static_header)

    if settings.oauth_client_id and settings.oauth_client_secret:
        return _build_oauth_provider(settings, store)

    raise AuthConfigError(
        "認証情報がありません。`bitbucket-mcp auth login` または OAuth クライアント設定が必要です。"
    )


def _build_oauth_provider(settings: Settings, store: CredentialStore) -> OAuthAuthProvider:
    client_id = settings.oauth_client_id
    client_secret = settings.oauth_client_secret
    if client_id is None or client_secret is None:
        raise AuthConfigError("OAuth client_id と client_secret が必要です。")
    return OAuthAuthProvider(
        store=store,
        oauth_client=OAuthClient(
            base_url=settings.oauth_base_url,
            client_id=client_id,
            client_secret=client_secret.get_secret_value(),
            redirect_uri=f"http://127.0.0.1:{settings.oauth_callback_port}/callback",
            scopes=settings.oauth_scopes(),
        ),
        client_id=client_id,
        client_secret=client_secret,
    )


def resolve_auth_header(settings: Settings) -> str:
    static_header = _build_static_header(settings)
    if static_header is None:
        raise AuthConfigError(
            "静的認証情報がありません。App Password は非対応です。"
            " API Token または Access Token を設定してください。"
        )
    return static_header
