"""環境変数によるサーバー設定。"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """BITBUCKET_* 環境変数から読み込む設定。"""

    model_config = SettingsConfigDict(env_prefix="BITBUCKET_", extra="ignore")

    token: str | None = None
    email: str | None = None
    api_token: str | None = None
    default_workspace: str | None = None
    toolsets: str = "context,repos,pull_requests,issues,pipelines,users"
    read_only: bool = False
    base_url: str = "https://api.bitbucket.org/2.0"

    @property
    def toolset_list(self) -> list[str]:
        return [item.strip() for item in self.toolsets.split(",") if item.strip()]
