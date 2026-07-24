from pathlib import Path

import pytest

from bitbucket_mcp import __main__ as entry


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


def test_manual_login_rejects_mismatched_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("BITBUCKET_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("BITBUCKET_OAUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(entry, "generate_state", lambda: "expected-state")
    pasted_values = iter(["authorization-code", "wrong-state"])

    def fake_getpass(_: str) -> str:
        return next(pasted_values)

    monkeypatch.setattr(entry.getpass, "getpass", fake_getpass)

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
