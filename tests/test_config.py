import pytest
from pydantic import SecretStr, ValidationError

from bitbucket_mcp.config import Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.base_url == "https://api.bitbucket.org/2.0"
    assert settings.read_only is False
    assert settings.token is None
    assert settings.toolset_list == [
        "context",
        "repos",
        "pull_requests",
        "issues",
        "pipelines",
        "users",
    ]


def test_toolsets_parsed_from_csv_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_TOOLSETS", "repos, pull_requests ,users")
    assert Settings().toolset_list == ["repos", "pull_requests", "users"]


def test_read_only_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_READ_ONLY", "true")
    assert Settings().read_only is True


def test_credentials_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_TOKEN", "abc")
    monkeypatch.setenv("BITBUCKET_EMAIL", "a@b.com")
    monkeypatch.setenv("BITBUCKET_API_TOKEN", "tok")
    settings = Settings()
    assert isinstance(settings.token, SecretStr)
    assert settings.token.get_secret_value() == "abc"
    assert settings.email == "a@b.com"
    assert isinstance(settings.api_token, SecretStr)
    assert settings.api_token.get_secret_value() == "tok"


def test_credentials_repr_masks_secrets() -> None:
    settings = Settings(
        token=SecretStr("alpha123"),
        email="a@b.com",
        api_token=SecretStr("beta456"),
    )
    text = repr(settings)
    assert "alpha123" not in text
    assert "beta456" not in text


def test_toolsets_reject_unknown_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_TOOLSETS", "context,unknown")
    with pytest.raises(ValidationError, match="unknown"):
        Settings()


def test_base_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_BASE_URL", "https://example.test/2.0")
    assert Settings().base_url == "https://example.test/2.0"


def test_oauth_fields_default() -> None:
    settings = Settings()
    assert settings.oauth_client_id is None
    assert settings.oauth_client_secret is None
    assert settings.oauth_callback_port == 8976
    assert settings.oauth_base_url == "https://bitbucket.org"
    assert settings.config_dir is None


def test_oauth_base_url_rejects_non_bitbucket_domain() -> None:
    with pytest.raises(ValueError, match=r"bitbucket\.org"):
        Settings(oauth_base_url="https://evil.example.com")


def test_oauth_base_url_accepts_bitbucket_subdomain() -> None:
    settings = Settings(oauth_base_url="https://api.bitbucket.org")
    assert settings.oauth_base_url == "https://api.bitbucket.org"


def test_oauth_scopes_read_only() -> None:
    settings = Settings(
        oauth_client_id="c",
        toolsets="context",
        read_only=True,
    )
    assert settings.oauth_scopes() == [
        "account",
        "repository",
        "pullrequest",
        "issue",
        "pipeline",
    ]


def test_oauth_scopes_includes_write_when_write_toolset_enabled() -> None:
    settings = Settings(
        oauth_client_id="c",
        toolsets="repos,pull_requests,issues,pipelines",
        read_only=False,
    )
    scopes = settings.oauth_scopes()
    assert "repository:write" in scopes
    assert "pullrequest:write" in scopes
    assert "issue:write" in scopes
    assert "pipeline:write" in scopes


def test_oauth_callback_port_validation() -> None:
    with pytest.raises(ValueError):
        Settings(oauth_callback_port=0)
    with pytest.raises(ValueError):
        Settings(oauth_callback_port=70000)


def test_oauth_base_url_rejects_http() -> None:
    with pytest.raises(ValueError, match=r"https"):
        Settings(oauth_base_url="http://bitbucket.org")
