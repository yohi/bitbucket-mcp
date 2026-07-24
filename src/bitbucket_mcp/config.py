"""環境変数によるサーバー設定。"""

from pathlib import Path
from urllib.parse import urlparse

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bitbucket_mcp.toolsets import DEFAULT_TOOLSETS

_READ_SCOPES = ["account", "repository", "pullrequest", "issue", "pipeline"]
_WRITE_TOOLSET_SCOPES: dict[str, list[str]] = {
    "repos": ["repository:write"],
    "pull_requests": ["pullrequest:write"],
    "issues": ["issue:write"],
    "pipelines": ["pipeline:write"],
}


class Settings(BaseSettings):
    """BITBUCKET_* 環境変数から読み込む設定。"""

    model_config = SettingsConfigDict(env_prefix="BITBUCKET_", extra="ignore")

    token: SecretStr | None = None
    email: str | None = None
    api_token: SecretStr | None = None
    default_workspace: str | None = None
    toolsets: str = ",".join(DEFAULT_TOOLSETS)
    read_only: bool = False
    base_url: str = "https://api.bitbucket.org/2.0"
    oauth_client_id: str | None = None
    oauth_client_secret: SecretStr | None = None
    oauth_callback_port: int = 8976
    oauth_base_url: str = "https://bitbucket.org"
    config_dir: Path | None = None

    @field_validator("toolsets")
    @classmethod
    def validate_toolsets(cls, value: str) -> str:
        requested = [item.strip() for item in value.split(",") if item.strip()]
        known = set(DEFAULT_TOOLSETS) | {"-bitbucket_api"}
        unknown = [name for name in requested if name not in known]
        if unknown:
            raise ValueError(f"unknown toolset(s): {', '.join(unknown)}")
        return value

    @field_validator("oauth_base_url")
    @classmethod
    def validate_oauth_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        hostname = parsed.hostname
        if parsed.scheme not in {"https", "http"} or hostname is None:
            raise ValueError("oauth_base_url must be a valid URL")
        if hostname != "bitbucket.org" and not hostname.endswith(".bitbucket.org"):
            raise ValueError("oauth_base_url must be under bitbucket.org domain")
        return value.rstrip("/")

    @field_validator("oauth_callback_port")
    @classmethod
    def validate_oauth_callback_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("oauth_callback_port must be 1-65535")
        return value

    @property
    def toolset_list(self) -> list[str]:
        return [item.strip() for item in self.toolsets.split(",") if item.strip()]

    def oauth_scopes(self) -> list[str]:
        """有効な toolset と read_only に応じた OAuth scope リストを返す。"""
        scopes = list(_READ_SCOPES)
        if self.read_only:
            return scopes
        requested = set(self.toolset_list)
        for toolset, write_scopes in _WRITE_TOOLSET_SCOPES.items():
            if toolset in requested:
                for scope in write_scopes:
                    if scope not in scopes:
                        scopes.append(scope)
        return scopes
