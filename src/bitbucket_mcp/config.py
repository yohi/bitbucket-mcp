"""環境変数によるサーバー設定。"""

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bitbucket_mcp.toolsets import DEFAULT_TOOLSETS


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

    @field_validator("toolsets")
    @classmethod
    def validate_toolsets(cls, value: str) -> str:
        requested = [item.strip() for item in value.split(",") if item.strip()]
        known = set(DEFAULT_TOOLSETS) | {"-bitbucket_api"}
        unknown = [name for name in requested if name not in known]
        if unknown:
            raise ValueError(f"unknown toolset(s): {', '.join(unknown)}")
        return value

    @property
    def toolset_list(self) -> list[str]:
        return [item.strip() for item in self.toolsets.split(",") if item.strip()]
