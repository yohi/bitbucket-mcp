import base64
import time
from pathlib import Path

import pytest
from pydantic import SecretStr
from pytest_httpx import HTTPXMock

from bitbucket_mcp.auth import (
    AuthConfigError,
    NotAuthenticatedError,
    OAuthAuthProvider,
    StaticAuthProvider,
    resolve_auth_header,
    resolve_auth_provider,
)
from bitbucket_mcp.config import Settings
from bitbucket_mcp.credentials import CredentialStore, StoredCredentials
from bitbucket_mcp.oauth import OAuthClient


async def test_static_provider_returns_header_and_is_always_authenticated() -> None:
    provider = StaticAuthProvider("Bearer test")
    assert provider.is_authenticated() is True
    assert await provider.authorization_header() == "Bearer test"
    await provider.refresh()


def _store_with_token(tmp_path: Path, client_id: str = "cid") -> CredentialStore:
    store = CredentialStore(tmp_path / "credentials.json")
    now = int(time.time())
    store.save(
        StoredCredentials(
            access_token="a",
            refresh_token="r",
            expires_at=now + 3600,
            scopes=["account"],
            token_type="bearer",
            client_id=client_id,
            obtained_at=now,
        )
    )
    return store


def _oauth_client() -> OAuthClient:
    return OAuthClient(
        base_url="https://bitbucket.org",
        client_id="cid",
        client_secret="cs",
        redirect_uri="http://127.0.0.1:8976/callback",
        scopes=["account"],
    )


def test_oauth_provider_authenticated_when_valid_token_exists(tmp_path: Path) -> None:
    provider = OAuthAuthProvider(
        store=_store_with_token(tmp_path),
        oauth_client=_oauth_client(),
        client_id="cid",
        client_secret=SecretStr("cs"),
    )
    assert provider.is_authenticated() is True


async def test_oauth_provider_returns_bearer_header(tmp_path: Path) -> None:
    provider = OAuthAuthProvider(
        store=_store_with_token(tmp_path),
        oauth_client=_oauth_client(),
        client_id="cid",
        client_secret=SecretStr("cs"),
    )
    assert await provider.authorization_header() == "Bearer a"


async def test_oauth_provider_not_authenticated_when_no_token(tmp_path: Path) -> None:
    provider = OAuthAuthProvider(
        store=CredentialStore(tmp_path / "creds.json"),
        oauth_client=_oauth_client(),
        client_id="cid",
        client_secret=SecretStr("cs"),
    )
    assert provider.is_authenticated() is False
    with pytest.raises(NotAuthenticatedError):
        await provider.authorization_header()


def test_oauth_provider_requires_relogin_when_client_id_mismatched(
    tmp_path: Path,
) -> None:
    provider = OAuthAuthProvider(
        store=_store_with_token(tmp_path, client_id="old-cid"),
        oauth_client=_oauth_client(),
        client_id="cid",
        client_secret=SecretStr("cs"),
    )
    assert provider.is_authenticated() is False


def test_resolve_oauth_takes_precedence_over_basic_and_bearer(
    tmp_path: Path,
) -> None:
    _store_with_token(tmp_path, client_id="cid")
    settings = Settings(
        oauth_client_id="cid",
        oauth_client_secret=SecretStr("cs"),
        email="a@b.com",
        api_token=SecretStr("tok"),
        config_dir=tmp_path,
    )
    provider = resolve_auth_provider(settings)
    assert isinstance(provider, OAuthAuthProvider)


async def test_resolve_basic_from_email_and_api_token() -> None:
    settings = Settings(email="a@b.com", api_token=SecretStr("tok"))
    provider = resolve_auth_provider(settings)
    expected = "Basic " + base64.b64encode(b"a@b.com:tok").decode("ascii")
    assert isinstance(provider, StaticAuthProvider)
    assert await provider.authorization_header() == expected


async def test_resolve_bearer_from_token() -> None:
    provider = resolve_auth_provider(Settings(token=SecretStr("bear")))
    assert isinstance(provider, StaticAuthProvider)
    assert await provider.authorization_header() == "Bearer bear"


def test_resolve_unauthenticated_oauth_when_client_configured() -> None:
    settings = Settings(oauth_client_id="cid", oauth_client_secret=SecretStr("cs"))
    provider = resolve_auth_provider(settings)
    assert isinstance(provider, OAuthAuthProvider)
    assert provider.is_authenticated() is False


def test_resolve_raises_when_no_credentials() -> None:
    with pytest.raises(AuthConfigError, match="auth login"):
        resolve_auth_provider(Settings())


async def test_refresh_token_exchanges_and_saves_rotated_token(
    tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="https://bitbucket.org/site/oauth2/access_token",
        json={
            "access_token": "new-a",
            "refresh_token": "new-r",
            "expires_in": 3600,
            "scopes": "account",
            "token_type": "bearer",
        },
    )
    store = CredentialStore(tmp_path / "creds.json")
    now = int(time.time())
    store.save(
        StoredCredentials(
            access_token="a",
            refresh_token="r",
            expires_at=now + 30,
            scopes=["account"],
            token_type="bearer",
            client_id="cid",
            obtained_at=now,
        )
    )
    provider = OAuthAuthProvider(
        store=store,
        oauth_client=_oauth_client(),
        client_id="cid",
        client_secret=SecretStr("cs"),
    )
    await provider.refresh()
    loaded = store.load()
    assert loaded is not None
    assert loaded.access_token == "new-a"
    assert loaded.refresh_token == "new-r"


def test_resolve_auth_header_keeps_static_compatibility() -> None:
    settings = Settings(token=SecretStr("bear"))
    assert resolve_auth_header(settings) == "Bearer bear"
