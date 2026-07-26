from pathlib import Path

import pytest

from _asyncio_helpers import FakeTimeout, forbidden_wait_for
from bitbucket_mcp import __main__ as entry
from bitbucket_mcp.credentials import CredentialStore
from bitbucket_mcp.oauth import OAuthTokenResponse


def test_auth_logout_deletes_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_CONFIG_DIR", str(tmp_path))
    creds = tmp_path / "credentials.json"
    creds.write_text("{}", encoding="utf-8")
    assert entry.main(["auth", "logout"]) == 0
    assert not creds.exists()


def test_auth_status_shows_logged_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("BITBUCKET_CONFIG_DIR", str(tmp_path))
    assert entry.main(["auth", "status"]) == 0
    captured = capsys.readouterr()
    assert "未ログイン" in captured.out


def test_auth_login_requires_client_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("BITBUCKET_CONFIG_DIR", str(tmp_path))
    assert entry.main(["auth", "login"]) == 2
    captured = capsys.readouterr()
    assert "client_id" in captured.err


def test_main_returns_2_without_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 認証情報なし → AuthConfigError → 終了コード 2
    assert entry.main(["--transport", "stdio"]) == 2
    captured = capsys.readouterr()
    assert "auth login" in captured.err


def test_main_handles_settings_validation_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("BITBUCKET_READ_ONLY", "not-a-bool")
    assert entry.main(["--transport", "stdio"]) == 2
    captured = capsys.readouterr()
    assert "設定" in captured.err


def test_manual_login_rejects_mismatched_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("BITBUCKET_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(entry, "generate_state", lambda: "expected-state")
    authorization_codes = iter(["authorization-code"])

    def fake_getpass(prompt: str) -> str:
        assert prompt == "authorization code: "
        return next(authorization_codes)

    monkeypatch.setattr(entry.getpass, "getpass", fake_getpass)

    def fake_input(_: str) -> str:
        return "wrong-state"

    monkeypatch.setattr("builtins.input", fake_input)

    class FakeOAuthClient:
        def __init__(self, **_: str) -> None:
            pass

        def build_authorize_url(self, state: str) -> str:
            return f"https://bitbucket.org/authorize?state={state}"

        async def exchange_code(self, code: str) -> None:
            raise AssertionError(f"token exchange must not run: {code}")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(entry, "OAuthClient", FakeOAuthClient)

    assert entry.main(["auth", "login", "--manual"]) == 1
    assert "CSRF" in capsys.readouterr().err


def test_browser_login_times_out_after_300_seconds_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("BITBUCKET_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(entry, "_display_available", lambda: True)

    def fake_browser_open(_url: str) -> bool:
        return True

    monkeypatch.setattr(entry.webbrowser, "open", fake_browser_open)
    callback_closed = False
    client_closed = False
    class FakeOAuthClient:
        def __init__(
            self,
            *,
            base_url: str,
            client_id: str,
            client_secret: str,
            redirect_uri: str,
            scopes: list[str],
        ) -> None:
            del base_url, client_secret, redirect_uri, scopes
            self.client_id = client_id

        def build_authorize_url(self, state: str) -> str:
            return f"https://bitbucket.org/authorize?state={state}"

        async def exchange_code(self, code: str) -> None:
            raise AssertionError(f"token exchange must not run: {code}")

        async def aclose(self) -> None:
            nonlocal client_closed
            client_closed = True

    class FakeCallbackServer:
        def __init__(self, port: int, *, expected_state: str) -> None:
            del expected_state
            self.port = port

        async def start(self) -> None:
            return None

        async def wait_callback(self) -> tuple[str, str | None]:
            raise TimeoutError

        async def aclose(self) -> None:
            nonlocal callback_closed
            callback_closed = True

    def fake_timeout(timeout: float) -> FakeTimeout:
        return FakeTimeout(timeout)

    monkeypatch.setattr(entry, "OAuthClient", FakeOAuthClient)
    monkeypatch.setattr(entry, "OAuthCallbackServer", FakeCallbackServer)
    monkeypatch.setattr(entry.asyncio, "wait_for", forbidden_wait_for)
    monkeypatch.setattr(entry.asyncio, "timeout", fake_timeout)

    assert entry.main(["auth", "login"]) == 1
    captured = capsys.readouterr()
    assert "タイムアウト" in captured.err
    assert "auth login" in captured.err
    assert FakeTimeout.last_timeout == 300
    assert callback_closed is True
    assert client_closed is True


def test_browser_login_exchanges_persists_and_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BITBUCKET_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_ID", "synthetic-client-id")
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_SECRET", "synthetic-client-secret")
    monkeypatch.setattr(entry, "generate_state", lambda: "synthetic-state")
    monkeypatch.setattr(entry, "_display_available", lambda: True)
    monkeypatch.setattr(entry.time, "time", lambda: 1_000)
    browser_urls: list[str] = []
    client_closed = False
    exchanged_codes: list[str] = []
    callback_started = False
    callback_closed = False

    def fake_browser_open(url: str) -> bool:
        browser_urls.append(url)
        return True

    class FakeOAuthClient:
        def __init__(
            self,
            *,
            base_url: str,
            client_id: str,
            client_secret: str,
            redirect_uri: str,
            scopes: list[str],
        ) -> None:
            del base_url, client_id, client_secret, redirect_uri, scopes

        def build_authorize_url(self, state: str) -> str:
            return f"https://bitbucket.org/authorize?state={state}"

        async def exchange_code(self, code: str) -> OAuthTokenResponse:
            exchanged_codes.append(code)
            return OAuthTokenResponse(
                access_token="synthetic-access-token",
                refresh_token="synthetic-refresh-token",
                expires_in=600,
                scopes=["account"],
                token_type="bearer",
            )

        async def aclose(self) -> None:
            nonlocal client_closed
            client_closed = True

    class FakeCallbackServer:
        def __init__(self, port: int, *, expected_state: str) -> None:
            self.port = port
            self.expected_state = expected_state

        async def start(self) -> None:
            nonlocal callback_started
            callback_started = True

        async def wait_callback(self) -> tuple[str, str | None]:
            return ("synthetic-authorization-code", self.expected_state)

        async def aclose(self) -> None:
            nonlocal callback_closed
            callback_closed = True

    monkeypatch.setattr(entry.webbrowser, "open", fake_browser_open)
    monkeypatch.setattr(entry, "OAuthClient", FakeOAuthClient)
    monkeypatch.setattr(entry, "OAuthCallbackServer", FakeCallbackServer)

    assert entry.main(["auth", "login"]) == 0

    stored = CredentialStore(tmp_path / "credentials.json").load()
    assert browser_urls == ["https://bitbucket.org/authorize?state=synthetic-state"]
    assert exchanged_codes == ["synthetic-authorization-code"]
    assert stored is not None
    assert stored.access_token == "synthetic-access-token"
    assert stored.refresh_token == "synthetic-refresh-token"
    assert stored.expires_at == 1_600
    assert stored.client_id == "synthetic-client-id"
    assert callback_started is True
    assert callback_closed is True
    assert client_closed is True
