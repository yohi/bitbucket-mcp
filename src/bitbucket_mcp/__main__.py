"""python -m bitbucket_mcp / uvx エントリポイント。"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
import time
import webbrowser

import httpx
from pydantic import SecretStr, ValidationError

from bitbucket_mcp.auth import AuthConfigError, resolve_auth_provider
from bitbucket_mcp.config import Settings
from bitbucket_mcp.credentials import (
    CredentialStore,
    StoredCredentials,
    default_credential_path,
)
from bitbucket_mcp.oauth import (
    OAuthCallbackServer,
    OAuthClient,
    OAuthFlowError,
    build_redirect_uri,
    generate_state,
)
from bitbucket_mcp.server import create_server


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bitbucket-mcp")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)

    auth = parser.add_subparsers(dest="command").add_parser(
        "auth", help="認証関連コマンド"
    )
    auth_sub = auth.add_subparsers(dest="auth_command")

    login = auth_sub.add_parser("login", help="ブラウザ OAuth でログイン")
    login.add_argument("--manual", action="store_true", help="手動貼り付けモード")
    login.add_argument(
        "--port",
        type=int,
        default=None,
        help="Bitbucket コンシューマに登録済みの callback ポート",
    )
    auth_sub.add_parser("status", help="保存済み資格情報を表示")
    auth_sub.add_parser("logout", help="保存トークンを削除")
    return parser


def _oauth_config(
    settings: Settings,
) -> tuple[str, SecretStr, int] | None:
    if not settings.oauth_client_id or not settings.oauth_client_secret:
        print(
            "BITBUCKET_OAUTH_CLIENT_ID / BITBUCKET_OAUTH_CLIENT_SECRET "
            "(client_id / client_secret)が必要です。",
            file=sys.stderr,
        )
        return None
    return (
        settings.oauth_client_id,
        settings.oauth_client_secret,
        settings.oauth_callback_port,
    )


def _display_available() -> bool:
    if sys.platform in ("win32", "darwin"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _format_status(creds: StoredCredentials | None) -> str:
    if creds is None:
        return "未ログインです。"
    from datetime import UTC, datetime

    expires = datetime.fromtimestamp(creds.expires_at, tz=UTC)
    return (
        f"client_id: {creds.client_id}\n"
        f"expires_at: {expires.isoformat()}\n"
        f"scopes: {' '.join(creds.scopes)}"
    )


async def _run_login(settings: Settings, manual: bool, port: int | None) -> int:
    config = _oauth_config(settings)
    if config is None:
        return 2
    client_id, client_secret, default_port = config
    callback_port = port if port is not None else default_port
    redirect_uri = build_redirect_uri(callback_port)
    oauth_client = OAuthClient(
        base_url=settings.oauth_base_url,
        client_id=client_id,
        client_secret=client_secret.get_secret_value(),
        redirect_uri=redirect_uri,
        scopes=settings.oauth_scopes(),
    )
    state = generate_state()
    authorize_url = oauth_client.build_authorize_url(state)
    store = CredentialStore(default_credential_path(settings.config_dir))
    server: OAuthCallbackServer | None = None

    try:
        if manual:
            print(
                "以下の URL をブラウザで開き、承認後に表示されたコードを"
                f"貼り付けてください:\n{authorize_url}"
            )
            code = getpass.getpass("authorization code: ").strip()
            returned_state = state
        else:
            if not _display_available():
                print(
                    "ディスプレイが検出できませんでした。--manual を使用してください。",
                    file=sys.stderr,
                )
                return 2
            server = OAuthCallbackServer(port=callback_port, expected_state=state)
            await server.start()
            if server.port != callback_port:
                redirect_uri = build_redirect_uri(server.port)
                oauth_client = OAuthClient(
                    base_url=settings.oauth_base_url,
                    client_id=client_id,
                    client_secret=client_secret.get_secret_value(),
                    redirect_uri=redirect_uri,
                    scopes=settings.oauth_scopes(),
                )
                authorize_url = oauth_client.build_authorize_url(state)
            print(f"ブラウザで承認してください: {authorize_url}")
            webbrowser.open(authorize_url)
            code, returned_state = await server.wait_callback()

        if returned_state != state:
            print("CSRF 検証に失敗しました (state 不一致)。", file=sys.stderr)
            return 1

        tokens = await oauth_client.exchange_code(code)
        store.save(tokens.to_stored(client_id=client_id, obtained_at=int(time.time())))
        print("ログインしました。")
        print(_format_status(store.load()))
        return 0
    except OAuthFlowError as exc:
        print(f"OAuth エラー: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPStatusError as exc:
        print(f"トークン交換に失敗しました: {exc.response.status_code}", file=sys.stderr)
        return 1
    finally:
        if server is not None:
            await server.aclose()
        await oauth_client.aclose()


def _cmd_status(settings: Settings) -> int:
    store = CredentialStore(default_credential_path(settings.config_dir))
    print(_format_status(store.load()))
    return 0


def _cmd_logout(settings: Settings) -> int:
    store = CredentialStore(default_credential_path(settings.config_dir))
    store.delete()
    print("ログアウトしました。")
    return 0


async def _async_main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"設定エラー: {exc}", file=sys.stderr)
        return 2

    if args.command == "auth":
        if args.auth_command == "login":
            return await _run_login(settings, manual=args.manual, port=args.port)
        if args.auth_command == "status":
            return _cmd_status(settings)
        if args.auth_command == "logout":
            return _cmd_logout(settings)
        build_arg_parser().parse_args(["auth", "--help"])
        return 0

    try:
        resolve_auth_provider(settings)
        mcp = create_server(settings, host=args.host, port=args.port)
    except (AuthConfigError, ValidationError) as exc:
        print(f"設定エラー: {exc}", file=sys.stderr)
        return 2
    transport = "streamable-http" if args.transport == "http" else "stdio"
    mcp.run(transport=transport)
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_async_main(argv))


if __name__ == "__main__":
    sys.exit(main())
