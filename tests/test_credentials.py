"""CredentialStore のテスト。"""

import json
import stat
from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("access_token", None),
        ("refresh_token", True),
        ("expires_at", "2000000000"),
        ("token_type", None),
        ("client_id", 123),
        ("obtained_at", False),
        ("scopes", ["account", 1]),
    ],
)
def test_malformed_field_types_return_none(tmp_path: Path, field: str, value: object) -> None:
    path = tmp_path / "creds.json"
    payload = _sample().to_dict()
    payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert CredentialStore(path).load() is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "missing.json")
    assert store.load() is None


def test_delete(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds.json")
    store.save(_sample())
    store.delete()
    assert not (tmp_path / "creds.json").exists()
    assert (tmp_path / "creds.lock").exists()


def test_atomic_write(tmp_path: Path) -> None:
    path = tmp_path / "creds.json"
    store = CredentialStore(path)
    store.save(_sample())
    assert not any(tmp_path.glob(".creds-*"))
