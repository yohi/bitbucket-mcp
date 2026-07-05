import base64

import pytest

from bitbucket_mcp.auth import AuthConfigError, resolve_auth_header
from bitbucket_mcp.config import Settings


def test_basic_auth_from_email_and_api_token() -> None:
    settings = Settings(email="a@b.com", api_token="tok")
    expected = "Basic " + base64.b64encode(b"a@b.com:tok").decode("ascii")
    assert resolve_auth_header(settings) == expected


def test_bearer_from_token() -> None:
    settings = Settings(token="bear")
    assert resolve_auth_header(settings) == "Bearer bear"


def test_basic_takes_precedence_over_bearer() -> None:
    settings = Settings(email="a@b.com", api_token="tok", token="bear")
    assert resolve_auth_header(settings).startswith("Basic ")


def test_error_when_no_credentials() -> None:
    with pytest.raises(AuthConfigError):
        resolve_auth_header(Settings())


def test_error_message_mentions_app_password_deprecation() -> None:
    with pytest.raises(AuthConfigError, match="App Password"):
        resolve_auth_header(Settings())
