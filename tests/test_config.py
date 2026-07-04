import pytest

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
    assert settings.token == "abc"
    assert settings.email == "a@b.com"
    assert settings.api_token == "tok"


def test_base_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_BASE_URL", "https://example.test/2.0")
    assert Settings().base_url == "https://example.test/2.0"
