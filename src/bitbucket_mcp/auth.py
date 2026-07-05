"""認証戦略 → Authorization ヘッダ生成。"""

import base64

from bitbucket_mcp.config import Settings


class AuthConfigError(RuntimeError):
    """認証情報が不十分な場合に送出される。"""


def resolve_auth_header(settings: Settings) -> str:
    """設定から Authorization ヘッダ値を解決する。

    優先順: Basic(email + api_token)→ Bearer(token)→ エラー。
    """
    if settings.email and settings.api_token:
        raw = f"{settings.email}:{settings.api_token.get_secret_value()}".encode()
        return "Basic " + base64.b64encode(raw).decode("ascii")
    if settings.token:
        return f"Bearer {settings.token.get_secret_value()}"
    raise AuthConfigError(
        "認証情報がありません。App Password は非対応です (2026-07-28 に完全廃止予定です)。"
        " API Token(BITBUCKET_EMAIL + BITBUCKET_API_TOKEN)または"
        " Access Token(BITBUCKET_TOKEN)を設定してください。"
    )
