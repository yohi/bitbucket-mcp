"""OAuth トークンの永続化ストア。"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from filelock import FileLock


@dataclass(frozen=True)
class StoredCredentials:
    access_token: str
    refresh_token: str
    expires_at: int
    scopes: list[str]
    token_type: str
    client_id: str
    obtained_at: int

    def to_dict(self) -> dict[str, object]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "scopes": self.scopes,
            "token_type": self.token_type,
            "client_id": self.client_id,
            "obtained_at": self.obtained_at,
        }

    @classmethod
    def from_dict(cls, data: object) -> StoredCredentials:
        if not isinstance(data, dict):
            raise ValueError("credentials data must be a JSON object")
        payload = cast(dict[str, object], data)

        access_token = payload["access_token"]
        refresh_token = payload["refresh_token"]
        expires_at = payload["expires_at"]
        scopes = payload["scopes"]
        token_type = payload["token_type"]
        client_id = payload["client_id"]
        obtained_at = payload["obtained_at"]
        if not isinstance(access_token, str):
            raise ValueError("credentials access_token must be a string")
        if not isinstance(refresh_token, str):
            raise ValueError("credentials refresh_token must be a string")
        if not isinstance(expires_at, int) or isinstance(expires_at, bool):
            raise ValueError("credentials expires_at must be an integer")
        if not isinstance(scopes, list):
            raise ValueError("credentials scopes must be a list of strings")
        raw_scopes = cast(list[object], scopes)
        if not all(isinstance(scope, str) for scope in raw_scopes):
            raise ValueError("credentials scopes must be a list of strings")
        scopes = [cast(str, scope) for scope in raw_scopes]
        if not isinstance(token_type, str):
            raise ValueError("credentials token_type must be a string")
        if not isinstance(client_id, str):
            raise ValueError("credentials client_id must be a string")
        if not isinstance(obtained_at, int) or isinstance(obtained_at, bool):
            raise ValueError("credentials obtained_at must be an integer")
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=scopes,
            token_type=token_type,
            client_id=client_id,
            obtained_at=obtained_at,
        )


class CredentialStore:
    """ファイルシステム上の OAuth トークンを 0600 で永続化する。"""

    _DIR_MODE = 0o700
    _FILE_MODE = 0o600

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock_path = path.with_suffix(".lock")
        self._lock = FileLock(str(self._lock_path))

    @contextmanager
    def locked(self) -> Generator[None, None, None]:
        """プロセス間排他ロックを獲得するコンテキストマネージャ。"""
        with self._lock:
            yield

    def load(self) -> StoredCredentials | None:
        if not self.path.exists():
            return None
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return StoredCredentials.from_dict(data)
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def save(self, creds: StoredCredentials) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(self._DIR_MODE)

        fd, tmp_path_str = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=".creds-",
            suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(creds.to_dict(), fh, indent=2)
            os.chmod(tmp_path_str, self._FILE_MODE)
            os.replace(tmp_path_str, self.path)
        except Exception:
            with suppress(OSError):
                Path(tmp_path_str).unlink(missing_ok=True)
            raise

    def delete(self) -> None:
        with self.locked():
            self.path.unlink(missing_ok=True)


def default_credential_path(config_dir: Path | None = None) -> Path:
    """既定の credentials.json パスを返す。"""
    if config_dir is not None:
        return config_dir / "credentials.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "bitbucket-mcp" / "credentials.json"
