"""CredentialStore のテスト。"""

import stat
from pathlib import Path

from bitbucket_mcp.credentials import CredentialStore, StoredCredentials


def _sample() -> StoredCredentials:
    return StoredCredentials(
        access_token="a",
        refresh_token="r",
        expires_at=2000000000,
        scopes=["account"],
        token_type="bearer",
        client_id="c",
        obtained_at=1999999999,
    )


def test_round_trip(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds.json")
    store.save(_sample())
    loaded = store.load()
    assert loaded == _sample()


def test_permissions(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds.json")
    store.save(_sample())
    mode = stat.S_IMODE((tmp_path / "creds.json").stat().st_mode)
    assert mode == 0o600
    dir_mode = stat.S_IMODE(tmp_path.stat().st_mode)
    assert dir_mode == 0o700


def test_corrupted_file_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "creds.json"
    path.write_text("not json", encoding="utf-8")
    store = CredentialStore(path)
    assert store.load() is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "missing.json")
    assert store.load() is None


def test_delete(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds.json")
    store.save(_sample())
    store.delete()
    assert not (tmp_path / "creds.json").exists()


def test_atomic_write(tmp_path: Path) -> None:
    path = tmp_path / "creds.json"
    store = CredentialStore(path)
    store.save(_sample())
    assert not any(tmp_path.glob(".creds-*"))
