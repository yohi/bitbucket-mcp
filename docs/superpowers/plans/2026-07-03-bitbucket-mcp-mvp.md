# Bitbucket MCP Server (MVP / Phase1) 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bitbucket Cloud REST API v2.0 を Model Context Protocol のツールとして公開する stdio MCP サーバー(6 ツールセット + 汎用 `bitbucket_api`、計 37 ツール)を、環境変数認証・read-only ゲーティング・uvx 配布込みで動作可能な状態まで実装する。

**Architecture:** 責務ごとに小さく分離した層構成。`config`(設定)→ `auth`(認証ヘッダ生成)→ `client`(httpx ラッパ + エラー変換 + リトライ)を土台に、各 `toolsets/*.py` が統一インターフェース `register(mcp, client, *, read_only, default_workspace=None)` を通じて FastMCP にツールを登録する。ツールは全て `BitbucketClient` を介してのみ通信し、Bitbucket ドメイン概念を `client` から排除する。

**Tech Stack:** Python 3.12+ / FastMCP(`mcp.server.fastmcp`)/ httpx(AsyncClient)/ Pydantic v2 + pydantic-settings / pytest + pytest-httpx + pytest-asyncio / basedpyright(strict)/ ruff / uv・uvx。

## Global Constraints

- 対象は Bitbucket **Cloud** REST API v2.0 のみ(Server / Data Center は非対象)。
- 言語 **Python 3.12+**。MCP SDK は公式 `mcp` の **FastMCP**(`from mcp.server.fastmcp import FastMCP`)。
- HTTP クライアントは `httpx` の非同期 `AsyncClient`。データ検証は **Pydantic v2**。
- ベース URL 既定値は `https://api.bitbucket.org/2.0`(環境変数 `BITBUCKET_BASE_URL` で上書き可)。
- 認証は環境変数注入。優先順: `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` → **Basic** / `BITBUCKET_TOKEN` → **Bearer** / どちらも無ければ起動時エラー。**App Password は非対応**。
- `BITBUCKET_READ_ONLY=true` のとき `readOnlyHint=false` のツールを登録しない。`bitbucket_api` は登録するが GET/HEAD 以外を拒否する。
- 一覧ツールは `page`(既定 1)/ `pagelen`(既定 25・**最大 100**)を受け取り、Bitbucket の応答封筒(`values`/`page`/`size`/`next`/`previous`)を `structuredContent` にそのまま反映する。
- read は `action` 引数で分岐する統合型、write は操作別に分割。各ツールに MCP annotations(`readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`)を付与。
- 全ツール関数は返り値を `dict[str, Any]` に統一する(diff/patch/ログ等のテキストは `{"content": <text>, "format": <fmt>}` に包む)。
- Bitbucket エラー JSON(`{type, error:{message, detail, ...}}`)は MCP `ToolError` に変換し、`Bitbucket API {status}: {message} — {detail}` 形式で返す。
- テストは TDD。実装前に失敗するテストを書く。`basedpyright`(strict)と `ruff` をパスすること。
- コミットは Conventional Commits(説明は日本語、リポジトリの既存慣習に合わせる)。
- リポジトリのカレントブランチは `docs/design`。実装は作業ブランチ(例 `feat/mvp-phase1`)で行うこと。

---

## ファイル構成(作成/責務)

```
bitbucket-mcp/
├── pyproject.toml                         # パッケージ定義・依存・ツール設定(uv/ruff/basedpyright/pytest)
├── README.md                              # 使い方・環境変数・uvx/Claude Desktop 設定
├── src/bitbucket_mcp/
│   ├── __init__.py                        # __version__
│   ├── __main__.py                        # CLI 引数解析・トランスポート選択・エントリポイント
│   ├── config.py                          # Settings(pydantic-settings BaseSettings)
│   ├── auth.py                            # resolve_auth_header / AuthConfigError
│   ├── errors.py                          # build_tool_error(Bitbucket エラー → ToolError)
│   ├── pagination.py                      # page_params(page/pagelen ヘルパ)
│   ├── client.py                          # BitbucketClient(request/request_text/リトライ)
│   ├── server.py                          # create_server(設定 → client → toolset 登録)
│   ├── models/
│   │   └── __init__.py                    # InlineComment / PipelineTarget(ツール入力モデル)
│   └── toolsets/
│       ├── __init__.py                    # TOOLSET_REGISTRY / DEFAULT_TOOLSETS
│       ├── _common.py                     # resolve_workspace
│       ├── context.py                     # get_current_user, list_workspaces
│       ├── repos.py                        # repo 系 read + write(15)
│       ├── pull_requests.py               # PR 系 read + write(8)
│       ├── issues.py                       # issue 系 read + write(6)
│       ├── pipelines.py                    # pipeline 系 read + write(4)
│       ├── users.py                        # get_user(1)
│       └── raw_api.py                      # bitbucket_api(常時登録)
└── tests/
    ├── conftest.py                        # env クリア / register_toolset / call_tool フィクスチャ
    ├── test_config.py
    ├── test_auth.py
    ├── test_errors.py
    ├── test_pagination.py
    ├── test_client.py
    ├── test_server.py
    ├── test_main.py
    └── toolsets/
        ├── test_context.py
        ├── test_repos.py
        ├── test_pull_requests.py
        ├── test_issues.py
        ├── test_pipelines.py
        ├── test_users.py
        └── test_raw_api.py
```

## 共有インターフェース(全タスク共通の確定シグネチャ)

後続タスクはこれらの正確な名前・型に依存する。実装時に一致させること。

```python
# config.py
class Settings(BaseSettings):
    token: str | None
    email: str | None
    api_token: str | None
    default_workspace: str | None
    toolsets: str                 # CSV 文字列
    read_only: bool
    base_url: str
    @property
    def toolset_list(self) -> list[str]: ...

# auth.py
class AuthConfigError(RuntimeError): ...
def resolve_auth_header(settings: Settings) -> str: ...      # "Basic ..." | "Bearer ..."

# errors.py
def build_tool_error(status_code: int, payload: dict[str, Any] | None, *, retry_after: str | None = None) -> ToolError: ...

# pagination.py
DEFAULT_PAGELEN = 25
MAX_PAGELEN = 100
def page_params(page: int | None = None, pagelen: int | None = None) -> dict[str, int]: ...

# client.py
class BitbucketClient:
    def __init__(self, *, base_url: str, auth_header: str, timeout: float = 30.0,
                 max_retries: int = 2, backoff_base: float = 0.5) -> None: ...
    async def request(self, method: str, path: str, *, query: dict[str, Any] | None = None,
                      body: dict[str, Any] | None = None, form: dict[str, Any] | None = None) -> dict[str, Any]: ...
    async def request_text(self, method: str, path: str, *, query: dict[str, Any] | None = None) -> str: ...
    async def aclose(self) -> None: ...

# toolsets/_common.py
def resolve_workspace(workspace: str | None, default_workspace: str | None) -> str: ...

# 各 toolset の統一インターフェース
def register(mcp: FastMCP, client: BitbucketClient, *, read_only: bool,
             default_workspace: str | None = None) -> None: ...

# server.py
def create_server(settings: Settings, *, host: str = "127.0.0.1", port: int = 8000) -> FastMCP: ...

# toolsets/__init__.py
TOOLSET_REGISTRY: dict[str, Callable[..., None]]
DEFAULT_TOOLSETS: list[str]
```

**設計メモ(仕様からの明示的リファインメント):**
- 仕様 §4 の統一インターフェースに `default_workspace: str | None = None` キーワードを追加する。理由: `client.py` を Bitbucket ドメイン概念(workspace)から独立させたまま、repo スコープのツールへ既定 workspace を届けるため。全 toolset が同一シグネチャを共有するため疎結合性は保たれる。workspace を使わない toolset(context/users)は当該引数を無視する。
- ツールは `register()` 内のクロージャとして定義し `client`/`default_workspace` を捕捉する。全パラメータはキーワード専用(`*,` 始まり)にする(任意 `workspace` の後に必須引数を置けるようにするため)。

---


## Task 1: プロジェクト雛形と開発ツール設定

**Files:**
- Create: `pyproject.toml`
- Create: `src/bitbucket_mcp/__init__.py`
- Create: `src/bitbucket_mcp/toolsets/__init__.py`（空パッケージマーカー。Task 16 で登録レジストリに置換）
- Create: `tests/conftest.py`
- Create: `tests/test_package.py`

**Interfaces:**
- Consumes: なし
- Produces: `bitbucket_mcp.__version__: str` / autouse フィクスチャ `_clean_bitbucket_env`（全テストで `BITBUCKET_*` 環境変数を除去）

- [x] **Step 1: `pyproject.toml` を作成**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "bitbucket-mcp"
version = "0.1.0"
description = "Bitbucket Cloud REST API v2.0 を公開する MCP サーバー"
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
dependencies = [
    "mcp>=1.13,<2",
    "httpx>=0.27",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
]

[project.scripts]
bitbucket-mcp = "bitbucket_mcp.__main__:main"

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "pytest-httpx>=0.30",
    "basedpyright>=1.13",
    "ruff>=0.5",
]

[tool.hatch.build.targets.wheel]
packages = ["src/bitbucket_mcp"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]

[tool.basedpyright]
pythonVersion = "3.12"
typeCheckingMode = "strict"
include = ["src", "tests"]
```

- [x] **Step 2: パッケージの `__init__.py` を作成**

`src/bitbucket_mcp/__init__.py`:

```python
"""Bitbucket Cloud REST API v2.0 を公開する MCP サーバー。"""

__version__ = "0.1.0"
```

`src/bitbucket_mcp/toolsets/__init__.py`（Task 16 まで空）:

```python
"""Bitbucket MCP toolset パッケージ。"""
```

- [x] **Step 3: `tests/conftest.py` に環境変数クリアの autouse フィクスチャを作成**

```python
import pytest

_BITBUCKET_ENV_VARS = [
    "BITBUCKET_TOKEN",
    "BITBUCKET_EMAIL",
    "BITBUCKET_API_TOKEN",
    "BITBUCKET_DEFAULT_WORKSPACE",
    "BITBUCKET_TOOLSETS",
    "BITBUCKET_READ_ONLY",
    "BITBUCKET_BASE_URL",
]


@pytest.fixture(autouse=True)
def _clean_bitbucket_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _BITBUCKET_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
```

- [x] **Step 4: 失敗するパッケージテストを書く**

`tests/test_package.py`:

```python
from bitbucket_mcp import __version__


def test_version_is_semver_string() -> None:
    assert isinstance(__version__, str)
    assert __version__.count(".") == 2
```

- [x] **Step 5: 依存を同期しテストが失敗することを確認**

Run: `uv sync`
Then: `uv run pytest tests/test_package.py -v`
Expected: `uv sync` 成功。テストは PASS（`__init__.py` を Step 2 で作成済みのため）。もし ImportError なら Step 2 のパス/内容を修正。

- [x] **Step 6: 静的解析を通す**

Run: `uv run ruff check . && uv run basedpyright`
Expected: どちらも 0 エラー。

- [x] **Step 7: コミット**

```bash
git checkout -b feat/mvp-phase1
git add pyproject.toml src/bitbucket_mcp/__init__.py src/bitbucket_mcp/toolsets/__init__.py tests/conftest.py tests/test_package.py
git commit -m "chore: プロジェクト雛形と開発ツール設定を追加"
```

---

## Task 2: `config.py` — 環境変数設定 Settings

**Files:**
- Create: `src/bitbucket_mcp/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: なし
- Produces: `Settings`(属性 `token`/`email`/`api_token`/`default_workspace`/`toolsets`/`read_only`/`base_url`, プロパティ `toolset_list -> list[str]`)

- [x] **Step 1: 失敗するテストを書く**

`tests/test_config.py`:

```python
import pytest

from bitbucket_mcp.config import Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.base_url == "https://api.bitbucket.org/2.0"
    assert settings.read_only is False
    assert settings.token is None
    assert settings.toolset_list == [
        "context",
        "repos",
        "pull_requests",
        "issues",
        "pipelines",
        "users",
    ]


def test_toolsets_parsed_from_csv_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_TOOLSETS", "repos, pull_requests ,users")
    assert Settings().toolset_list == ["repos", "pull_requests", "users"]


def test_read_only_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_READ_ONLY", "true")
    assert Settings().read_only is True


def test_credentials_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_TOKEN", "abc")
    monkeypatch.setenv("BITBUCKET_EMAIL", "a@b.com")
    monkeypatch.setenv("BITBUCKET_API_TOKEN", "tok")
    settings = Settings()
    assert settings.token == "abc"
    assert settings.email == "a@b.com"
    assert settings.api_token == "tok"


def test_base_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_BASE_URL", "https://example.test/2.0")
    assert Settings().base_url == "https://example.test/2.0"
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bitbucket_mcp.config'`)

- [x] **Step 3: `config.py` を実装**

`toolsets` は `list` にすると pydantic-settings が環境変数を JSON としてパースしてしまうため、CSV 文字列として保持し `toolset_list` プロパティで分割する。

```python
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
```

- [x] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS(5 件）

- [x] **Step 5: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/config.py tests/test_config.py
git commit -m "feat: 環境変数設定 Settings を追加"
```

---

## Task 3: `auth.py` — 認証ヘッダ解決

**Files:**
- Create: `src/bitbucket_mcp/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `Settings`(Task 2)
- Produces: `AuthConfigError(RuntimeError)` / `resolve_auth_header(settings: Settings) -> str`

- [x] **Step 1: 失敗するテストを書く**

`tests/test_auth.py`:

```python
import base64

import pytest

from bitbucket_mcp.auth import AuthConfigError, resolve_auth_header
from bitbucket_mcp.config import Settings


def test_basic_auth_from_email_and_api_token() -> None:
    settings = Settings(email="a@b.com", api_token="tok")
    expected = "Basic " + base64.b64encode(b"a@b.com:tok").decode("ascii")
    assert resolve_auth_header(settings) == expected


def test_bearer_from_token() -> None:
    settings = Settings(token="bear")
    assert resolve_auth_header(settings) == "Bearer bear"


def test_basic_takes_precedence_over_bearer() -> None:
    settings = Settings(email="a@b.com", api_token="tok", token="bear")
    assert resolve_auth_header(settings).startswith("Basic ")


def test_error_when_no_credentials() -> None:
    with pytest.raises(AuthConfigError):
        resolve_auth_header(Settings())


def test_error_message_mentions_app_password_deprecation() -> None:
    with pytest.raises(AuthConfigError, match="App Password"):
        resolve_auth_header(Settings())
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bitbucket_mcp.auth'`)

- [x] **Step 3: `auth.py` を実装**

```python
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
        raw = f"{settings.email}:{settings.api_token}".encode()
        return "Basic " + base64.b64encode(raw).decode("ascii")
    if settings.token:
        return f"Bearer {settings.token}"
    raise AuthConfigError(
        "認証情報がありません。App Password は非対応です（2026-07-28 に完全廃止予定です）。
        " API Token(BITBUCKET_EMAIL + BITBUCKET_API_TOKEN)または"
        " Access Token(BITBUCKET_TOKEN)を設定してください。"
    )
```

- [x] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_auth.py -v`
Expected: PASS(5 件）

- [x] **Step 5: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/auth.py tests/test_auth.py
git commit -m "feat: 認証ヘッダ解決ロジックを追加"
```

---

## Task 4: `errors.py` — Bitbucket エラー → ToolError 変換

**Files:**
- Create: `src/bitbucket_mcp/errors.py`
- Test: `tests/test_errors.py`

**Interfaces:**
- Consumes: `ToolError`(`from mcp.server.fastmcp.exceptions import ToolError`)
- Produces: `build_tool_error(status_code: int, payload: dict[str, Any] | None, *, retry_after: str | None = None) -> ToolError`

- [x] **Step 1: 失敗するテストを書く**

`tests/test_errors.py`:

```python
from mcp.server.fastmcp.exceptions import ToolError

from bitbucket_mcp.errors import build_tool_error


def test_returns_tool_error_instance() -> None:
    err = build_tool_error(404, {"error": {"message": "Not found"}})
    assert isinstance(err, ToolError)


def test_message_includes_status_and_message() -> None:
    err = build_tool_error(404, {"error": {"message": "Not found"}})
    assert "Bitbucket API 404" in str(err)
    assert "Not found" in str(err)


def test_message_includes_detail() -> None:
    err = build_tool_error(
        400, {"error": {"message": "Bad", "detail": "field x required"}}
    )
    assert "field x required" in str(err)


def test_status_hint_appended_for_403() -> None:
    err = build_tool_error(403, {"error": {"message": "Forbidden"}})
    assert "403" in str(err)
    assert "スコープ" in str(err)


def test_handles_missing_payload() -> None:
    err = build_tool_error(500, None)
    assert "Bitbucket API 500" in str(err)


def test_retry_after_included_for_429() -> None:
    err = build_tool_error(429, {"error": {"message": "Rate"}}, retry_after="1700000000")
    assert "1700000000" in str(err)
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_errors.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bitbucket_mcp.errors'`)

- [x] **Step 3: `errors.py` を実装**

```python
"""Bitbucket のエラー JSON を MCP ToolError に変換する。"""

from typing import Any

from mcp.server.fastmcp.exceptions import ToolError

_STATUS_HINTS: dict[int, str] = {
    401: "認証に失敗しました。トークンを確認してください。",
    403: "権限/スコープが不足しています。必要なスコープを付与してください。",
    404: "リソースが見つかりません。",
    409: "競合が発生しました（マージ衝突など）。",
    429: "レート制限を超過しました。しばらく待って再試行してください。",
}


def build_tool_error(
    status_code: int,
    payload: dict[str, Any] | None,
    *,
    retry_after: str | None = None,
) -> ToolError:
    """HTTP ステータスと Bitbucket エラー JSON から ToolError を構築する。"""
    message = ""
    detail = ""
    if payload:
        err = payload.get("error")
        if isinstance(err, dict):
            message = str(err.get("message", ""))
            detail = str(err.get("detail", ""))
    text = f"Bitbucket API {status_code}: {message or 'error'}"
    if detail:
        text += f" — {detail}"
    hint = _STATUS_HINTS.get(status_code)
    if hint:
        text += f" [{hint}]"
    if status_code == 429 and retry_after:
        text += f" (retry after {retry_after})"
    return ToolError(text)
```

- [x] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_errors.py -v`
Expected: PASS(6 件）

- [x] **Step 5: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/errors.py tests/test_errors.py
git commit -m "feat: Bitbucket エラーを ToolError に変換する処理を追加"
```

---

## Task 5: `pagination.py` — page/pagelen ヘルパ

**Files:**
- Create: `src/bitbucket_mcp/pagination.py`
- Test: `tests/test_pagination.py`

**Interfaces:**
- Consumes: なし
- Produces: `DEFAULT_PAGELEN = 25` / `MAX_PAGELEN = 100` / `page_params(page: int | None = None, pagelen: int | None = None) -> dict[str, int]`

- [x] **Step 1: 失敗するテストを書く**

`tests/test_pagination.py`:

```python
from bitbucket_mcp.pagination import MAX_PAGELEN, page_params


def test_default_pagelen_when_none() -> None:
    assert page_params() == {"pagelen": 25}


def test_page_included_when_given() -> None:
    assert page_params(page=2) == {"page": 2, "pagelen": 25}


def test_pagelen_clamped_to_max() -> None:
    assert page_params(pagelen=500)["pagelen"] == MAX_PAGELEN


def test_pagelen_floored_to_one() -> None:
    assert page_params(pagelen=0)["pagelen"] == 1


def test_custom_pagelen_passthrough() -> None:
    assert page_params(page=1, pagelen=50) == {"page": 1, "pagelen": 50}
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_pagination.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [x] **Step 3: `pagination.py` を実装**

```python
"""Bitbucket の page / pagelen パラメータヘルパ。"""

DEFAULT_PAGELEN = 25
MAX_PAGELEN = 100


def page_params(page: int | None = None, pagelen: int | None = None) -> dict[str, int]:
    """一覧系エンドポイント向けの query パラメータを組み立てる。"""
    params: dict[str, int] = {}
    if page is not None:
        params["page"] = page
    effective = DEFAULT_PAGELEN if pagelen is None else pagelen
    params["pagelen"] = min(max(effective, 1), MAX_PAGELEN)
    return params
```

- [x] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_pagination.py -v`
Expected: PASS(5 件）

- [x] **Step 5: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/pagination.py tests/test_pagination.py
git commit -m "feat: page/pagelen ページネーションヘルパを追加"
```

---

## Task 6: `client.py` — BitbucketClient(httpx ラッパ + リトライ + エラー変換）

**Files:**
- Create: `src/bitbucket_mcp/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `build_tool_error`(Task 4)
- Produces: `BitbucketClient`(`request`/`request_text`/`aclose`/`__aenter__`/`__aexit__`)

- [x] **Step 1: 失敗するテストを書く**

`tests/test_client.py`:

```python
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from bitbucket_mcp.client import BitbucketClient

BASE_URL = "https://api.bitbucket.org/2.0"


def _client() -> BitbucketClient:
    return BitbucketClient(
        base_url=BASE_URL, auth_header="Bearer test-token", backoff_base=0.0
    )


async def test_request_builds_url_and_injects_auth(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE_URL}/user", json={"username": "alice"}
    )
    client = _client()
    result = await client.request("GET", "/user")
    await client.aclose()
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "GET"
    assert request.url.path == "/2.0/user"
    assert request.headers["Authorization"] == "Bearer test-token"
    assert request.headers["Accept"] == "application/json"
    assert result == {"username": "alice"}


async def test_request_sends_query_and_json_body(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"ok": True})
    client = _client()
    await client.request(
        "POST", "/x", query={"page": 2}, body={"title": "hi"}
    )
    await client.aclose()
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.params["page"] == "2"
    assert request.read() == b'{"title": "hi"}'


async def test_request_sends_form_when_form_given(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={})
    client = _client()
    await client.request("POST", "/src", form={"message": "m", "a.txt": "body"})
    await client.aclose()
    request = httpx_mock.get_request()
    assert request is not None
    body = request.read().decode()
    assert "message=m" in body
    assert "a.txt=body" in body


async def test_empty_body_returns_empty_dict(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=204)
    client = _client()
    result = await client.request("DELETE", "/x")
    await client.aclose()
    assert result == {}


async def test_error_status_raises_tool_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        status_code=404, json={"error": {"message": "Not found"}}
    )
    client = _client()
    with pytest.raises(ToolError, match="404"):
        await client.request("GET", "/missing")
    await client.aclose()


async def test_retries_on_429_then_succeeds(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=429, json={"error": {"message": "rate"}})
    httpx_mock.add_response(status_code=200, json={"ok": True})
    client = _client()
    result = await client.request("GET", "/x")
    await client.aclose()
    assert result == {"ok": True}
    assert len(httpx_mock.get_requests()) == 2


async def test_no_retry_on_post_5xx(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=502)
    httpx_mock.add_response(status_code=200, json={"ok": True})
    client = _client()
    with pytest.raises(ToolError, match="502"):
        await client.request("POST", "/x", body={"name": "repo"})
    await client.aclose()
    assert len(httpx_mock.get_requests()) == 1


async def test_request_text_returns_raw_text(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(text="diff --git a b")
    client = _client()
    result = await client.request_text("GET", "/diff/spec")
    await client.aclose()
    assert result == "diff --git a b"
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_client.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bitbucket_mcp.client'`)

- [x] **Step 3: `client.py` を実装**

```python
"""Bitbucket API への HTTP アクセスを担う httpx ラッパ。"""

import asyncio
from types import TracebackType
from typing import Any, NoReturn

import httpx

from bitbucket_mcp.errors import build_tool_error

_RETRY_STATUSES = {429, 502, 503, 504}
_RETRYABLE_METHODS = {"GET", "HEAD"}


class BitbucketClient:
    """HTTP・認証ヘッダ注入・リトライだけを知るクライアント。"""

    def __init__(
        self,
        *,
        base_url: str,
        auth_header: str,
        timeout: float = 30.0,
        max_retries: int = 2,
        backoff_base: float = 0.5,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": auth_header, "Accept": "application/json"},
            timeout=timeout,
        )
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    async def _send(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        attempt = 0
        while True:
            response = await self._client.request(
                method, path, params=query, json=json, data=data
            )
            if (
                response.status_code in _RETRY_STATUSES
                and method.upper() in _RETRYABLE_METHODS
                and attempt < self._max_retries
            ):
                await asyncio.sleep(self._backoff_base * (2**attempt))
                attempt += 1
                continue
            return response

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """JSON レスポンスを返すリクエスト。form 指定時は form-urlencoded で送信。"""
        response = await self._send(
            method,
            path,
            query=query,
            json=body if form is None else None,
            data=form,
        )
        if response.is_success:
            if not response.content:
                return {}
            return response.json()
        self._raise(response)

    async def request_text(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
    ) -> str:
        """テキストレスポンス（diff/patch/ログ）を返すリクエスト。"""
        response = await self._send(method, path, query=query)
        if response.is_success:
            return response.text
        self._raise(response)

    def _raise(self, response: httpx.Response) -> NoReturn:
        try:
            payload: dict[str, Any] | None = response.json()
        except (ValueError, httpx.DecodingError):
            payload = None
        raise build_tool_error(
            response.status_code,
            payload,
            retry_after=response.headers.get("X-RateLimit-Reset"),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "BitbucketClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
```

- [x] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_client.py -v`
Expected: PASS(8 件）

- [x] **Step 5: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/client.py tests/test_client.py
git commit -m "feat: BitbucketClient(httpx ラッパ・リトライ・エラー変換）を追加。GET/HEAD のみリトライ"
```

---

## Task 7: `toolsets/context.py` + トールセットテスト基盤

最初の toolset。register + クロージャ + annotations パターンと、以降全トールセットが使うテストフィクスチャ（`register_toolset` / `call_tool`）を確立する。

**Files:**
- Create: `src/bitbucket_mcp/toolsets/context.py`
- Modify: `tests/conftest.py`（Task 1 の conftest にフィクスチャを追加）
- Test: `tests/toolsets/test_context.py`
- Create: `tests/toolsets/__init__.py`（空。テストパッケージマーカー）

**Interfaces:**
- Consumes: `BitbucketClient`(Task 6)/ `page_params`(Task 5)/ `FastMCP`, `ToolAnnotations`
- Produces: `context.register(mcp, client, *, read_only, default_workspace=None) -> None`(ツール `get_current_user`, `list_workspaces`)/ テストフィクスチャ `register_toolset`, `call_tool`

- [x] **Step 1: `tests/conftest.py` にフィクスチャを追加**

Task 1 の conftest.py 末尾に以下を追加する（既存の `_clean_bitbucket_env` は残す）。`register_toolset` は各 toolset の `register` を新規 FastMCP + クライアントで直接呼び、`call_tool` は FastMCP のバージョン差を吸収して `(content, structured)` タプルを返す。

```python
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from bitbucket_mcp.client import BitbucketClient

RegisterFn = Callable[..., None]
MakeServer = Callable[..., tuple[FastMCP, BitbucketClient]]
CallTool = Callable[[FastMCP, str, dict[str, Any]], Awaitable[tuple[Any, Any]]]


@pytest.fixture
async def register_toolset() -> Any:
    clients: list[BitbucketClient] = []

    def _make(
        register_fn: RegisterFn,
        *,
        read_only: bool = False,
        default_workspace: str | None = None,
    ) -> tuple[FastMCP, BitbucketClient]:
        client = BitbucketClient(
            base_url="https://api.bitbucket.org/2.0",
            auth_header="Bearer test-token",
            backoff_base=0.0,
        )
        mcp = FastMCP("bitbucket-mcp-test")
        register_fn(
            mcp, client, read_only=read_only, default_workspace=default_workspace
        )
        clients.append(client)
        return mcp, client

    yield _make
    for client in clients:
        await client.aclose()


@pytest.fixture
def call_tool() -> CallTool:
    async def _call(
        mcp: FastMCP, name: str, arguments: dict[str, Any]
    ) -> tuple[Any, Any]:
        result = await mcp.call_tool(name, arguments)
        if isinstance(result, tuple):
            content, structured = result
            return content, structured
        return result, None

    return _call
```

さらに conftest.py 先頭の import に `import pytest` があることを確認（Task 1 で追加済み）。

- [x] **Step 2: `tests/toolsets/__init__.py`（空）を作成し、失敗するテストを書く**

`tests/toolsets/test_context.py`:

```python
from mcp.server.fastmcp import FastMCP
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import context

BASE = "https://api.bitbucket.org/2.0"


async def test_get_current_user(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/user", json={"username": "alice", "account_id": "123"}
    )
    mcp, _ = register_toolset(context.register)
    _, structured = await call_tool(mcp, "get_current_user", {})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "GET"
    assert request.url.path == "/2.0/user"
    assert structured == {"username": "alice", "account_id": "123"}


async def test_list_workspaces_clamps_pagelen(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": [], "page": 1, "size": 0})
    mcp, _ = register_toolset(context.register)
    await call_tool(mcp, "list_workspaces", {"pagelen": 500})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/user/workspaces"
    assert request.url.params["pagelen"] == "100"


async def test_list_workspaces_administrator_filter(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(context.register)
    await call_tool(mcp, "list_workspaces", {"administrator": True})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.params["q"] == 'permission="owner"'


async def test_context_registers_expected_tools_with_annotations(
    register_toolset,
) -> None:
    mcp, _ = register_toolset(context.register)
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert set(tools) == {"get_current_user", "list_workspaces"}
    assert tools["get_current_user"].annotations is not None
    assert tools["get_current_user"].annotations.readOnlyHint is True
```

> 注: MCP プロトコルの `Tool.annotations` は camelCase 属性（`readOnlyHint` 等）で公開される。`ToolAnnotations` のコンストラクタ引数は snake_case（`read_only_hint`）。

- [x] **Step 3: テストが失敗することを確認**

Run: `uv run pytest tests/toolsets/test_context.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bitbucket_mcp.toolsets.context'`)

- [x] **Step 4: `context.py` を実装**

```python
"""context ツールセット: 現在のユーザーとワークスペース一覧。"""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.pagination import page_params


def register(
    mcp: FastMCP,
    client: BitbucketClient,
    *,
    read_only: bool,
    default_workspace: str | None = None,
) -> None:
    async def get_current_user() -> dict[str, Any]:
        """Return the currently authenticated Bitbucket user account."""
        return await client.request("GET", "/user")

    async def list_workspaces(
        *,
        administrator: bool | None = None,
        q: str | None = None,
        sort: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List workspaces the authenticated user is a member of."""
        query: dict[str, Any] = page_params(page, pagelen)
        effective_q = q
        if administrator and not effective_q:
            effective_q = 'permission="owner"'
        if effective_q:
            query["q"] = effective_q
        if sort:
            query["sort"] = sort
        return await client.request("GET", "/user/workspaces", query=query)

    mcp.add_tool(
        get_current_user,
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    mcp.add_tool(
        list_workspaces,
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
```

- [x] **Step 5: テストが通ることを確認**

Run: `uv run pytest tests/toolsets/test_context.py -v`
Expected: PASS(4 件）。もし `call_tool` の structured が None になる場合は `mcp` バージョンが 1.13 未満の可能性 → `pyproject.toml` の `mcp>=1.13` を確認し `uv sync` する。

- [x] **Step 6: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/toolsets/context.py tests/conftest.py tests/toolsets/__init__.py tests/toolsets/test_context.py
git commit -m "feat: context ツールセットとテスト基盤を追加"
```

---

## Task 8: `toolsets/_common.py` + `toolsets/repos.py`(read ツール 8 個）

**Files:**
- Create: `src/bitbucket_mcp/toolsets/_common.py`
- Create: `src/bitbucket_mcp/toolsets/repos.py`
- Test: `tests/toolsets/test_repos.py`

**Interfaces:**
- Consumes: `BitbucketClient` / `page_params` / `FastMCP` / `ToolAnnotations`
- Produces: `resolve_workspace(workspace: str | None, default_workspace: str | None) -> str` / `repos.register(...)`(read: `list_repositories`, `get_repository`, `get_file_or_directory`, `list_commits`, `get_commit`, `get_diff`, `list_branches`, `list_tags`)
- Produces(Task 9 が依存): repos.register 内に write ツールを追加する拡張点

- [x] **Step 1: `resolve_workspace` の失敗テストを書く**

`tests/toolsets/test_repos.py`(冒頭部分）:

```python
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import repos
from bitbucket_mcp.toolsets._common import resolve_workspace

BASE = "https://api.bitbucket.org/2.0"


def test_resolve_workspace_prefers_explicit() -> None:
    assert resolve_workspace("explicit", "default") == "explicit"


def test_resolve_workspace_falls_back_to_default() -> None:
    assert resolve_workspace(None, "default") == "default"


def test_resolve_workspace_raises_when_both_none() -> None:
    with pytest.raises(ToolError, match="workspace"):
        resolve_workspace(None, None)


async def test_get_repository_uses_default_workspace(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/repositories/ws1/repo1", json={"slug": "repo1"}
    )
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    _, structured = await call_tool(mcp, "get_repository", {"repo_slug": "repo1"})
    assert structured == {"slug": "repo1"}


async def test_list_repositories_builds_query(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(repos.register)
    await call_tool(
        mcp,
        "list_repositories",
        {"workspace": "ws1", "q": 'name~"x"', "role": "member", "pagelen": 10},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1"
    assert request.url.params["role"] == "member"
    assert request.url.params["pagelen"] == "10"


async def test_get_diff_text_wrapped(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(text="diff --git a b")
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    _, structured = await call_tool(
        mcp, "get_diff", {"repo_slug": "r", "spec": "abc..def", "action": "diff"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/diff/abc..def"
    assert structured == {"content": "diff --git a b", "format": "diff"}


async def test_get_diff_diffstat_json(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": [{"status": "modified"}]})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    _, structured = await call_tool(
        mcp, "get_diff", {"repo_slug": "r", "spec": "abc..def", "action": "diffstat"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/diffstat/abc..def"
    assert structured == {"values": [{"status": "modified"}]}


async def test_repos_read_tools_registered(register_toolset) -> None:
    mcp, _ = register_toolset(repos.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    assert {
        "list_repositories",
        "get_repository",
        "get_file_or_directory",
        "list_commits",
        "get_commit",
        "get_diff",
        "list_branches",
        "list_tags",
    } <= names
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/toolsets/test_repos.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bitbucket_mcp.toolsets.repos'`)

- [x] **Step 3: `_common.py` を実装**

```python
"""toolset 共通ヘルパ。"""

from mcp.server.fastmcp.exceptions import ToolError


def resolve_workspace(workspace: str | None, default_workspace: str | None) -> str:
    """workspace を解決する。未指定なら ToolError。"""
    resolved = workspace or default_workspace
    if not resolved:
        raise ToolError(
            "workspace が指定されていません。引数 workspace か"
            " BITBUCKET_DEFAULT_WORKSPACE を設定してください。"
        )
    return resolved
```

- [x] **Step 4: `repos.py` の read ツールを実装**

```python
"""repos ツールセット: リポジトリ・コミット・ブランチ・タグ・差分。"""

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.pagination import page_params
from bitbucket_mcp.toolsets._common import resolve_workspace

_READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
_WRITE = ToolAnnotations(open_world_hint=True)
_DESTRUCTIVE = ToolAnnotations(destructive_hint=True, open_world_hint=True)


def register(
    mcp: FastMCP,
    client: BitbucketClient,
    *,
    read_only: bool,
    default_workspace: str | None = None,
) -> None:
    async def list_repositories(
        *,
        workspace: str | None = None,
        q: str | None = None,
        sort: str | None = None,
        role: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List repositories in a workspace."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page, pagelen)
        if q:
            query["q"] = q
        if sort:
            query["sort"] = sort
        if role:
            query["role"] = role
        return await client.request("GET", f"/repositories/{ws}", query=query)

    async def get_repository(
        *, workspace: str | None = None, repo_slug: str
    ) -> dict[str, Any]:
        """Get a single repository's metadata."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request("GET", f"/repositories/{ws}/{repo_slug}")

    async def get_file_or_directory(
        *,
        workspace: str | None = None,
        repo_slug: str,
        commit: str,
        path: str,
        page: int | None = None,
    ) -> dict[str, Any]:
        """Get file contents or a directory listing at a commit."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        text = await client.request_text(
            "GET",
            f"/repositories/{ws}/{repo_slug}/src/{commit}/{path}",
            query=query or None,
        )
        return {"content": text}

    async def list_commits(
        *,
        workspace: str | None = None,
        repo_slug: str,
        revision: str | None = None,
        path: str | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        """List commits, optionally scoped to a revision or path."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = {}
        if page is not None:
            query["page"] = page
        if path:
            query["path"] = path
        endpoint = f"/repositories/{ws}/{repo_slug}/commits"
        if revision:
            endpoint = f"{endpoint}/{revision}"
        return await client.request("GET", endpoint, query=query or None)

    async def get_commit(
        *, workspace: str | None = None, repo_slug: str, commit: str
    ) -> dict[str, Any]:
        """Get a single commit by hash."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "GET", f"/repositories/{ws}/{repo_slug}/commit/{commit}"
        )

    async def get_diff(
        *,
        workspace: str | None = None,
        repo_slug: str,
        spec: str,
        action: Literal["diff", "diffstat", "patch"] = "diff",
    ) -> dict[str, Any]:
        """Get a diff, diffstat, or patch for a commit spec (e.g. 'a..b')."""
        ws = resolve_workspace(workspace, default_workspace)
        base = f"/repositories/{ws}/{repo_slug}"
        if action == "diffstat":
            return await client.request("GET", f"{base}/diffstat/{spec}")
        text = await client.request_text("GET", f"{base}/{action}/{spec}")
        return {"content": text, "format": action}

    async def list_branches(
        *,
        workspace: str | None = None,
        repo_slug: str,
        q: str | None = None,
        sort: str | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        """List branches in a repository."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page)
        if q:
            query["q"] = q
        if sort:
            query["sort"] = sort
        return await client.request(
            "GET", f"/repositories/{ws}/{repo_slug}/refs/branches", query=query
        )

    async def list_tags(
        *,
        workspace: str | None = None,
        repo_slug: str,
        q: str | None = None,
        sort: str | None = None,
        page: int | None = None,
    ) -> dict[str, Any]:
        """List tags in a repository."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page)
        if q:
            query["q"] = q
        if sort:
            query["sort"] = sort
        return await client.request(
            "GET", f"/repositories/{ws}/{repo_slug}/refs/tags", query=query
        )

    mcp.add_tool(list_repositories, annotations=_READ)
    mcp.add_tool(get_repository, annotations=_READ)
    mcp.add_tool(get_file_or_directory, annotations=_READ)
    mcp.add_tool(list_commits, annotations=_READ)
    mcp.add_tool(get_commit, annotations=_READ)
    mcp.add_tool(get_diff, annotations=_READ)
    mcp.add_tool(list_branches, annotations=_READ)
    mcp.add_tool(list_tags, annotations=_READ)

    # write ツールは Task 9 で `if read_only: return` ガードの後にここへ追加する。
```

> 注: `_WRITE` / `_DESTRUCTIVE` は Task 9 で使用するためここで定義済み。Task 8 単体では ruff の未使用検知対象外（モジュールレベル定数）だが、basedpyright で未使用変数警告が出る場合は Task 9 を同一コミットに含めるか、Task 9 実装まで `_WRITE`/`_DESTRUCTIVE` 定義を Task 9 に移す。

- [x] **Step 5: テストが通ることを確認**

Run: `uv run pytest tests/toolsets/test_repos.py -v`
Expected: PASS(8 件）

- [x] **Step 6: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/toolsets/_common.py src/bitbucket_mcp/toolsets/repos.py tests/toolsets/test_repos.py
git commit -m "feat: repos ツールセットの read 系ツールを追加"
```

---

## Task 9: `toolsets/repos.py`(write ツール 7 個）

**Files:**
- Modify: `src/bitbucket_mcp/toolsets/repos.py`(register 内の read 登録の直後に write ブロックを追加）
- Test: `tests/toolsets/test_repos.py`(write テストを追加）

**Interfaces:**
- Consumes: `resolve_workspace`, `client.request`(form 対応）、`_WRITE`/`_DESTRUCTIVE`(Task 8 で定義済み）
- Produces: repos.register に write ツールを追加(`create_repository`, `delete_repository`, `fork_repository`, `create_commit`, `create_branch`, `delete_branch`, `create_tag`)。`read_only=True` 時は未登録。

- [x] **Step 1: write テストを追加**

`tests/toolsets/test_repos.py` 末尾に追加:

```python
async def test_create_repository_body(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"slug": "r"})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "create_repository",
        {"repo_slug": "r", "is_private": True, "project_key": "PRJ"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r"
    assert request.read() == (
        b'{"scm": "git", "is_private": true, "project": {"key": "PRJ"}}'
    )


async def test_create_commit_sends_form(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "create_commit",
        {
            "repo_slug": "r",
            "message": "msg",
            "branch": "main",
            "files": {"a.txt": "hello"},
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/src"
    body = request.read().decode()
    assert "message=msg" in body
    assert "branch=main" in body
    assert "a.txt=hello" in body


async def test_delete_branch_path(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=204)
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    await call_tool(
        mcp, "delete_branch", {"repo_slug": "r", "name": "feature/x"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "DELETE"
    assert request.url.path == "/2.0/repositories/ws1/r/refs/branches/feature/x"


async def test_create_branch_body(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"name": "x"})
    mcp, _ = register_toolset(repos.register, default_workspace="ws1")
    await call_tool(
        mcp, "create_branch", {"repo_slug": "r", "name": "x", "target": "abc123"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.read() == b'{"name": "x", "target": {"hash": "abc123"}}'


async def test_write_tools_absent_in_read_only(register_toolset) -> None:
    mcp, _ = register_toolset(repos.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    for write_tool in (
        "create_repository",
        "delete_repository",
        "fork_repository",
        "create_commit",
        "create_branch",
        "delete_branch",
        "create_tag",
    ):
        assert write_tool not in names
    assert "get_repository" in names


async def test_delete_repository_has_destructive_hint(register_toolset) -> None:
    mcp, _ = register_toolset(repos.register)
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert tools["delete_repository"].annotations is not None
    assert tools["delete_repository"].annotations.destructiveHint is True
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/toolsets/test_repos.py -v`
Expected: FAIL(write ツール未登録 → `Unknown tool: create_repository` 等）

- [x] **Step 3: `repos.py` の register 末尾（read の `mcp.add_tool(...)` 群の直後、コメント行の位置）に write ブロックを実装**

```python
    if read_only:
        return

    async def create_repository(
        *,
        workspace: str | None = None,
        repo_slug: str,
        is_private: bool = True,
        project_key: str | None = None,
        scm: str = "git",
    ) -> dict[str, Any]:
        """Create a new repository."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {"scm": scm, "is_private": is_private}
        if project_key:
            body["project"] = {"key": project_key}
        return await client.request(
            "POST", f"/repositories/{ws}/{repo_slug}", body=body
        )

    async def delete_repository(
        *, workspace: str | None = None, repo_slug: str
    ) -> dict[str, Any]:
        """Delete a repository. Destructive."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "DELETE", f"/repositories/{ws}/{repo_slug}"
        )

    async def fork_repository(
        *,
        workspace: str | None = None,
        repo_slug: str,
        target_workspace: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Fork a repository."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {}
        if name:
            body["name"] = name
        if target_workspace:
            body["workspace"] = {"slug": target_workspace}
        return await client.request(
            "POST", f"/repositories/{ws}/{repo_slug}/forks", body=body
        )

    async def create_commit(
        *,
        workspace: str | None = None,
        repo_slug: str,
        message: str,
        files: dict[str, str],
        branch: str | None = None,
    ) -> dict[str, Any]:
        """Create a commit by writing files on a branch."""
        ws = resolve_workspace(workspace, default_workspace)
        form: dict[str, Any] = {"message": message}
        if branch:
            form["branch"] = branch
        for file_path, content in files.items():
            form[file_path] = content
        return await client.request(
            "POST", f"/repositories/{ws}/{repo_slug}/src", form=form
        )

    async def create_branch(
        *, workspace: str | None = None, repo_slug: str, name: str, target: str
    ) -> dict[str, Any]:
        """Create a branch pointing at a target commit hash."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/refs/branches",
            body={"name": name, "target": {"hash": target}},
        )

    async def delete_branch(
        *, workspace: str | None = None, repo_slug: str, name: str
    ) -> dict[str, Any]:
        """Delete a branch. Destructive."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "DELETE", f"/repositories/{ws}/{repo_slug}/refs/branches/{name}"
        )

    async def create_tag(
        *, workspace: str | None = None, repo_slug: str, name: str, target: str
    ) -> dict[str, Any]:
        """Create a tag pointing at a target commit hash."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/refs/tags",
            body={"name": name, "target": {"hash": target}},
        )

    mcp.add_tool(create_repository, annotations=_WRITE)
    mcp.add_tool(delete_repository, annotations=_DESTRUCTIVE)
    mcp.add_tool(fork_repository, annotations=_WRITE)
    mcp.add_tool(create_commit, annotations=_WRITE)
    mcp.add_tool(create_branch, annotations=_WRITE)
    mcp.add_tool(delete_branch, annotations=_DESTRUCTIVE)
    mcp.add_tool(create_tag, annotations=_WRITE)
```

このブロックは Task 8 の `# write ツールは Task 9 で ...` コメント行を置き換える形で、register 関数の末尾に配置する。

- [x] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/toolsets/test_repos.py -v`
Expected: PASS(14 件）

- [x] **Step 5: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/toolsets/repos.py tests/toolsets/test_repos.py
git commit -m "feat: repos ツールセットの write 系ツールと read-only ゲーティングを追加"
```

---

## Task 10: `toolsets/pull_requests.py`(read ツール 2 個）

**Files:**
- Create: `src/bitbucket_mcp/toolsets/pull_requests.py`
- Test: `tests/toolsets/test_pull_requests.py`

**Interfaces:**
- Consumes: `resolve_workspace`, `page_params`, `client`
- Produces: `pull_requests.register(...)`(read: `list_pull_requests`, `get_pull_request`)。module レベル定数 `_READ`/`_WRITE`/`_DESTRUCTIVE`(Task 11 で使用）
- Produces(Task 11 が依存): register 内に write ツールを追加する拡張点

- [x] **Step 1: 失敗するテストを書く**

`tests/toolsets/test_pull_requests.py`(read 部分）:

```python
import pytest
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import pull_requests

BASE = "https://api.bitbucket.org/2.0"


async def test_list_pull_requests_state_query(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp, "list_pull_requests", {"repo_slug": "r", "state": "OPEN"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests"
    assert request.url.params["state"] == "OPEN"


async def test_get_pull_request_details(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"id": 7, "title": "t"})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    _, structured = await call_tool(
        mcp,
        "get_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "action": "details"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7"
    assert structured == {"id": 7, "title": "t"}


async def test_get_pull_request_diff_text(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(text="diff text")
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    _, structured = await call_tool(
        mcp,
        "get_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "action": "diff"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7/diff"
    assert structured == {"content": "diff text", "format": "diff"}


@pytest.mark.parametrize("action", ["diffstat", "commits", "activity", "statuses", "comments"])
async def test_get_pull_request_json_subpaths(
    action: str, register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "get_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "action": action},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == f"/2.0/repositories/ws1/r/pullrequests/7/{action}"
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/toolsets/test_pull_requests.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bitbucket_mcp.toolsets.pull_requests'`)

- [x] **Step 3: `pull_requests.py` の read ツールを実装**

```python
"""pull_requests ツールセット: PR の参照・作成・更新・マージ・レビュー・コメント。"""

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.models import InlineComment
from bitbucket_mcp.pagination import page_params
from bitbucket_mcp.toolsets._common import resolve_workspace

_READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
_WRITE = ToolAnnotations(open_world_hint=True)
_DESTRUCTIVE = ToolAnnotations(destructive_hint=True, open_world_hint=True)


def register(
    mcp: FastMCP,
    client: BitbucketClient,
    *,
    read_only: bool,
    default_workspace: str | None = None,
) -> None:
    async def list_pull_requests(
        *,
        workspace: str | None = None,
        repo_slug: str,
        state: str | None = None,
        q: str | None = None,
        sort: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List pull requests, optionally filtered by state."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page, pagelen)
        if state:
            query["state"] = state
        if q:
            query["q"] = q
        if sort:
            query["sort"] = sort
        return await client.request(
            "GET", f"/repositories/{ws}/{repo_slug}/pullrequests", query=query
        )

    async def get_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        action: Literal[
            "details",
            "diff",
            "diffstat",
            "patch",
            "commits",
            "activity",
            "statuses",
            "comments",
        ] = "details",
    ) -> dict[str, Any]:
        """Get a pull request or one of its sub-resources."""
        ws = resolve_workspace(workspace, default_workspace)
        base = f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}"
        if action == "details":
            return await client.request("GET", base)
        if action in ("diff", "patch"):
            text = await client.request_text("GET", f"{base}/{action}")
            return {"content": text, "format": action}
        return await client.request("GET", f"{base}/{action}")

    mcp.add_tool(list_pull_requests, annotations=_READ)
    mcp.add_tool(get_pull_request, annotations=_READ)

    # write ツールは Task 11 で `if read_only: return` ガードの後にここへ追加する。
```

> 注: このファイルは `from bitbucket_mcp.models import InlineComment` を import するが、`InlineComment` は Task 11 で作成する。したがって **Task 10 と Task 11 は連続して実装**し、Task 10 単体で import エラーを避けるためには、この import 行を Task 11 までコメントアウトするか、先に Task 11 Step 1 の `models/__init__.py` を作成すること。本計画では **Task 11 Step 1 の models 作成を先に行う** ことを推奨する（Task 10 Step 4 実行前に models を用意）。

- [x] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/toolsets/test_pull_requests.py -v`
Expected: PASS(8 件: parametrize 5 + 3）

- [x] **Step 5: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/toolsets/pull_requests.py tests/toolsets/test_pull_requests.py
git commit -m "feat: pull_requests ツールセットの read 系ツールを追加"
```

---

## Task 11: `models/__init__.py`(InlineComment)+ `toolsets/pull_requests.py`(write ツール 6 個）

**Files:**
- Create: `src/bitbucket_mcp/models/__init__.py`
- Modify: `src/bitbucket_mcp/toolsets/pull_requests.py`(register 内に write ブロックを追加）
- Test: `tests/toolsets/test_pull_requests.py`(write テストを追加）

**Interfaces:**
- Consumes: `resolve_workspace`, `client`, `_WRITE`/`_DESTRUCTIVE`(Task 10）
- Produces: `InlineComment`(Pydantic モデル: `path: str`, `to: int | None = None`)/ pull_requests.register に write ツール追加(`create_pull_request`, `update_pull_request`, `merge_pull_request`, `decline_pull_request`, `review_pull_request`, `add_pull_request_comment`)

- [x] **Step 1: `models/__init__.py` を作成(InlineComment)**

```python
"""ツール入力用 Pydantic モデル。"""

from pydantic import BaseModel


class InlineComment(BaseModel):
    """PR のインラインコメント位置。"""

    path: str
    to: int | None = None
```

- [x] **Step 2: write テストを追加**

`tests/toolsets/test_pull_requests.py` 末尾に追加:

```python
async def test_create_pull_request_body(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"id": 1})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "create_pull_request",
        {
            "repo_slug": "r",
            "title": "T",
            "source_branch": "feat",
            "destination_branch": "main",
            "close_source_branch": True,
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests"
    assert request.read() == (
        b'{"title": "T", "source": {"branch": {"name": "feat"}},'
        b' "destination": {"branch": {"name": "main"}},'
        b' "close_source_branch": true}'
    )


async def test_merge_pull_request_destructive_and_path(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"state": "MERGED"})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "merge_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "merge_strategy": "squash"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7/merge"
    assert request.read() == b'{"merge_strategy": "squash"}'


async def test_review_pull_request_approve_post(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"approved": True})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "review_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "action": "approve"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7/approve"


async def test_review_pull_request_unapprove_delete(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=204)
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "review_pull_request",
        {"repo_slug": "r", "pull_request_id": 7, "action": "unrequest_changes"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "DELETE"
    assert request.url.path == (
        "/2.0/repositories/ws1/r/pullrequests/7/request-changes"
    )


async def test_add_pull_request_comment_inline(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"id": 5})
    mcp, _ = register_toolset(pull_requests.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "add_pull_request_comment",
        {
            "repo_slug": "r",
            "pull_request_id": 7,
            "content": "nice",
            "inline": {"path": "a.py", "to": 10},
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pullrequests/7/comments"
    assert request.read() == (
        b'{"content": {"raw": "nice"}, "inline": {"path": "a.py", "to": 10}}'
    )


async def test_pull_request_write_tools_absent_in_read_only(register_toolset) -> None:
    mcp, _ = register_toolset(pull_requests.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    for write_tool in (
        "create_pull_request",
        "update_pull_request",
        "merge_pull_request",
        "decline_pull_request",
        "review_pull_request",
        "add_pull_request_comment",
    ):
        assert write_tool not in names
    assert "list_pull_requests" in names
```

- [x] **Step 3: テストが失敗することを確認**

Run: `uv run pytest tests/toolsets/test_pull_requests.py -v`
Expected: FAIL(write ツール未登録）

- [x] **Step 4: `pull_requests.py` の register 末尾（read 登録の直後、コメント行の位置）に write ブロックを実装**

```python
    if read_only:
        return

    async def create_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        title: str,
        source_branch: str,
        destination_branch: str | None = None,
        description: str | None = None,
        reviewers: list[str] | None = None,
        close_source_branch: bool | None = None,
    ) -> dict[str, Any]:
        """Create a pull request."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {
            "title": title,
            "source": {"branch": {"name": source_branch}},
        }
        if destination_branch:
            body["destination"] = {"branch": {"name": destination_branch}}
        if description:
            body["description"] = description
        if reviewers:
            body["reviewers"] = [{"account_id": r} for r in reviewers]
        if close_source_branch is not None:
            body["close_source_branch"] = close_source_branch
        return await client.request(
            "POST", f"/repositories/{ws}/{repo_slug}/pullrequests", body=body
        )

    async def update_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        title: str | None = None,
        description: str | None = None,
        destination_branch: str | None = None,
    ) -> dict[str, Any]:
        """Update a pull request's title, description, or destination."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if destination_branch:
            body["destination"] = {"branch": {"name": destination_branch}}
        return await client.request(
            "PUT",
            f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}",
            body=body,
        )

    async def merge_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        merge_strategy: str | None = None,
        message: str | None = None,
        close_source_branch: bool | None = None,
    ) -> dict[str, Any]:
        """Merge a pull request. Destructive."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {}
        if merge_strategy:
            body["merge_strategy"] = merge_strategy
        if message:
            body["message"] = message
        if close_source_branch is not None:
            body["close_source_branch"] = close_source_branch
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/merge",
            body=body,
        )

    async def decline_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
    ) -> dict[str, Any]:
        """Decline a pull request."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/decline",
        )

    async def review_pull_request(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        action: Literal[
            "approve", "unapprove", "request_changes", "unrequest_changes"
        ],
    ) -> dict[str, Any]:
        """Approve/unapprove or request/unrequest changes on a pull request."""
        ws = resolve_workspace(workspace, default_workspace)
        base = (
            f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}"
        )
        endpoint = (
            "approve"
            if action in ("approve", "unapprove")
            else "request-changes"
        )
        method = "POST" if action in ("approve", "request_changes") else "DELETE"
        return await client.request(method, f"{base}/{endpoint}")

    async def add_pull_request_comment(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pull_request_id: int,
        content: str,
        inline: InlineComment | None = None,
    ) -> dict[str, Any]:
        """Add a comment (optionally inline) to a pull request."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {"content": {"raw": content}}
        if inline is not None:
            body["inline"] = {"path": inline.path, "to": inline.to}
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pullrequests/{pull_request_id}/comments",
            body=body,
        )

    mcp.add_tool(create_pull_request, annotations=_WRITE)
    mcp.add_tool(update_pull_request, annotations=_WRITE)
    mcp.add_tool(merge_pull_request, annotations=_DESTRUCTIVE)
    mcp.add_tool(decline_pull_request, annotations=_WRITE)
    mcp.add_tool(review_pull_request, annotations=_WRITE)
    mcp.add_tool(add_pull_request_comment, annotations=_WRITE)
```

- [x] **Step 5: テストが通ることを確認**

Run: `uv run pytest tests/toolsets/test_pull_requests.py -v`
Expected: PASS(14 件）

- [x] **Step 6: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/models/__init__.py src/bitbucket_mcp/toolsets/pull_requests.py tests/toolsets/test_pull_requests.py
git commit -m "feat: pull_requests の write 系ツールと InlineComment モデルを追加"
```

---

## Task 12: `toolsets/issues.py`(read 2 + write 4)

**Files:**
- Create: `src/bitbucket_mcp/toolsets/issues.py`
- Test: `tests/toolsets/test_issues.py`

**Interfaces:**
- Consumes: `resolve_workspace`, `page_params`, `client`
- Produces: `issues.register(...)`(read: `list_issues`, `get_issue` / write: `create_issue`, `update_issue`, `delete_issue`, `add_issue_comment`)

- [x] **Step 1: 失敗するテストを書く**

`tests/toolsets/test_issues.py`:

```python
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import issues

BASE = "https://api.bitbucket.org/2.0"


async def test_list_issues(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    await call_tool(mcp, "list_issues", {"repo_slug": "r", "q": 'state="new"'})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/issues"
    assert request.url.params["q"] == 'state="new"'


async def test_get_issue_changes_subpath(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    await call_tool(
        mcp, "get_issue", {"repo_slug": "r", "issue_id": 3, "action": "changes"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/issues/3/changes"


async def test_create_issue_body(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"id": 1})
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "create_issue",
        {"repo_slug": "r", "title": "Bug", "content": "desc", "kind": "bug"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/issues"
    assert request.read() == (
        b'{"title": "Bug", "content": {"raw": "desc"}, "kind": "bug"}'
    )


async def test_add_issue_comment_body(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"id": 9})
    mcp, _ = register_toolset(issues.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "add_issue_comment",
        {"repo_slug": "r", "issue_id": 3, "content": "hi"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/issues/3/comments"
    assert request.read() == b'{"content": {"raw": "hi"}}'


async def test_delete_issue_destructive(register_toolset) -> None:
    mcp, _ = register_toolset(issues.register)
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert tools["delete_issue"].annotations is not None
    assert tools["delete_issue"].annotations.destructiveHint is True


async def test_issue_write_tools_absent_in_read_only(register_toolset) -> None:
    mcp, _ = register_toolset(issues.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    for write_tool in (
        "create_issue",
        "update_issue",
        "delete_issue",
        "add_issue_comment",
    ):
        assert write_tool not in names
    assert "list_issues" in names
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/toolsets/test_issues.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bitbucket_mcp.toolsets.issues'`)

- [x] **Step 3: `issues.py` を実装**

```python
"""issues ツールセット: イシューの参照・作成・更新・削除・コメント。"""

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.pagination import page_params
from bitbucket_mcp.toolsets._common import resolve_workspace

_READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
_WRITE = ToolAnnotations(open_world_hint=True)
_DESTRUCTIVE = ToolAnnotations(destructive_hint=True, open_world_hint=True)


def register(
    mcp: FastMCP,
    client: BitbucketClient,
    *,
    read_only: bool,
    default_workspace: str | None = None,
) -> None:
    async def list_issues(
        *,
        workspace: str | None = None,
        repo_slug: str,
        q: str | None = None,
        sort: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List issues in a repository."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page, pagelen)
        if q:
            query["q"] = q
        if sort:
            query["sort"] = sort
        return await client.request(
            "GET", f"/repositories/{ws}/{repo_slug}/issues", query=query
        )

    async def get_issue(
        *,
        workspace: str | None = None,
        repo_slug: str,
        issue_id: int,
        action: Literal["details", "comments", "changes"] = "details",
    ) -> dict[str, Any]:
        """Get an issue or its comments/changes."""
        ws = resolve_workspace(workspace, default_workspace)
        base = f"/repositories/{ws}/{repo_slug}/issues/{issue_id}"
        if action == "details":
            return await client.request("GET", base)
        return await client.request("GET", f"{base}/{action}")

    mcp.add_tool(list_issues, annotations=_READ)
    mcp.add_tool(get_issue, annotations=_READ)

    if read_only:
        return

    async def create_issue(
        *,
        workspace: str | None = None,
        repo_slug: str,
        title: str,
        content: str | None = None,
        kind: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
    ) -> dict[str, Any]:
        """Create an issue."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {"title": title}
        if content:
            body["content"] = {"raw": content}
        if kind:
            body["kind"] = kind
        if priority:
            body["priority"] = priority
        if assignee:
            body["assignee"] = {"account_id": assignee}
        return await client.request(
            "POST", f"/repositories/{ws}/{repo_slug}/issues", body=body
        )

    async def update_issue(
        *,
        workspace: str | None = None,
        repo_slug: str,
        issue_id: int,
        title: str | None = None,
        state: str | None = None,
        kind: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
    ) -> dict[str, Any]:
        """Update an issue."""
        ws = resolve_workspace(workspace, default_workspace)
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if state is not None:
            body["state"] = state
        if kind is not None:
            body["kind"] = kind
        if priority is not None:
            body["priority"] = priority
        if assignee is not None:
            body["assignee"] = {"account_id": assignee}
        return await client.request(
            "PUT", f"/repositories/{ws}/{repo_slug}/issues/{issue_id}", body=body
        )

    async def delete_issue(
        *, workspace: str | None = None, repo_slug: str, issue_id: int
    ) -> dict[str, Any]:
        """Delete an issue. Destructive."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "DELETE", f"/repositories/{ws}/{repo_slug}/issues/{issue_id}"
        )

    async def add_issue_comment(
        *,
        workspace: str | None = None,
        repo_slug: str,
        issue_id: int,
        content: str,
    ) -> dict[str, Any]:
        """Add a comment to an issue."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/issues/{issue_id}/comments",
            body={"content": {"raw": content}},
        )

    mcp.add_tool(create_issue, annotations=_WRITE)
    mcp.add_tool(update_issue, annotations=_WRITE)
    mcp.add_tool(delete_issue, annotations=_DESTRUCTIVE)
    mcp.add_tool(add_issue_comment, annotations=_WRITE)
```

- [x] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/toolsets/test_issues.py -v`
Expected: PASS(6 件）

- [x] **Step 5: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/toolsets/issues.py tests/toolsets/test_issues.py
git commit -m "feat: issues ツールセット（read/write）を追加"
```

---

## Task 13: `models/__init__.py`(PipelineTarget 追加)+ `toolsets/pipelines.py`(read 2 + write 2)

**Files:**
- Modify: `src/bitbucket_mcp/models/__init__.py`(`PipelineTarget` を追加）
- Create: `src/bitbucket_mcp/toolsets/pipelines.py`
- Test: `tests/toolsets/test_pipelines.py`

**Interfaces:**
- Consumes: `resolve_workspace`, `page_params`, `client`
- Produces: `PipelineTarget`(Pydantic: `ref_type: str`, `ref_name: str`, `selector: dict[str, Any] | None = None`)/ `pipelines.register(...)`(read: `list_pipelines`, `get_pipeline` / write: `run_pipeline`, `stop_pipeline`)

- [x] **Step 1: `models/__init__.py` に PipelineTarget を追加**

既存の `models/__init__.py`(InlineComment 定義済み）の末尾に追加:

```python
from typing import Any


class PipelineTarget(BaseModel):
    """パイプライン実行対象の参照。"""

    ref_type: str
    ref_name: str
    selector: dict[str, Any] | None = None
```

> 注: ファイル先頭の import は `from typing import Any` と `from pydantic import BaseModel` の両方が必要。`from typing import Any` をファイル先頭の import ブロックに移動し重複を避けること（ruff I が検知する）。最終形:

```python
"""ツール入力用 Pydantic モデル。"""

from typing import Any

from pydantic import BaseModel


class InlineComment(BaseModel):
    """PR のインラインコメント位置。"""

    path: str
    to: int | None = None


class PipelineTarget(BaseModel):
    """パイプライン実行対象の参照。"""

    ref_type: str
    ref_name: str
    selector: dict[str, Any] | None = None
```

- [x] **Step 2: 失敗するテストを書く**

`tests/toolsets/test_pipelines.py`:

```python
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import pipelines

BASE = "https://api.bitbucket.org/2.0"


async def test_list_pipelines(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    await call_tool(mcp, "list_pipelines", {"repo_slug": "r", "sort": "-created_on"})
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pipelines/"
    assert request.url.params["sort"] == "-created_on"


async def test_get_pipeline_steps(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"values": []})
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "get_pipeline",
        {"repo_slug": "r", "pipeline_uuid": "{u}", "action": "steps"},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pipelines/{u}/steps"


async def test_get_pipeline_step_log_text(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(text="log output")
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    _, structured = await call_tool(
        mcp,
        "get_pipeline",
        {
            "repo_slug": "r",
            "pipeline_uuid": "{u}",
            "action": "step_log",
            "step_uuid": "{s}",
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/repositories/ws1/r/pipelines/{u}/steps/{s}/log"
    assert structured == {"content": "log output"}


async def test_run_pipeline_body(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"uuid": "{u}"})
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    await call_tool(
        mcp,
        "run_pipeline",
        {
            "repo_slug": "r",
            "target": {"ref_type": "branch", "ref_name": "main"},
        },
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/pipelines/"
    assert request.read() == (
        b'{"target": {"ref_type": "branch", "ref_name": "main",'
        b' "type": "pipeline_ref_target"}}'
    )


async def test_stop_pipeline_path(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(status_code=204)
    mcp, _ = register_toolset(pipelines.register, default_workspace="ws1")
    await call_tool(
        mcp, "stop_pipeline", {"repo_slug": "r", "pipeline_uuid": "{u}"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "POST"
    assert request.url.path == "/2.0/repositories/ws1/r/pipelines/{u}/stopPipeline"


async def test_pipeline_write_tools_absent_in_read_only(register_toolset) -> None:
    mcp, _ = register_toolset(pipelines.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    assert "run_pipeline" not in names
    assert "stop_pipeline" not in names
    assert "list_pipelines" in names
```

- [x] **Step 3: テストが失敗することを確認**

Run: `uv run pytest tests/toolsets/test_pipelines.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bitbucket_mcp.toolsets.pipelines'`)

- [x] **Step 4: `pipelines.py` を実装**

```python
"""pipelines ツールセット: パイプラインの参照・実行・停止。"""

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.models import PipelineTarget
from bitbucket_mcp.pagination import page_params
from bitbucket_mcp.toolsets._common import resolve_workspace

_READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
_WRITE = ToolAnnotations(open_world_hint=True)


def register(
    mcp: FastMCP,
    client: BitbucketClient,
    *,
    read_only: bool,
    default_workspace: str | None = None,
) -> None:
    async def list_pipelines(
        *,
        workspace: str | None = None,
        repo_slug: str,
        sort: str | None = None,
        page: int | None = None,
        pagelen: int | None = None,
    ) -> dict[str, Any]:
        """List pipeline runs in a repository."""
        ws = resolve_workspace(workspace, default_workspace)
        query: dict[str, Any] = page_params(page, pagelen)
        if sort:
            query["sort"] = sort
        return await client.request(
            "GET", f"/repositories/{ws}/{repo_slug}/pipelines/", query=query
        )

    async def get_pipeline(
        *,
        workspace: str | None = None,
        repo_slug: str,
        pipeline_uuid: str,
        action: Literal["details", "steps", "step_log"] = "details",
        step_uuid: str | None = None,
    ) -> dict[str, Any]:
        """Get a pipeline, its steps, or a step log."""
        ws = resolve_workspace(workspace, default_workspace)
        base = f"/repositories/{ws}/{repo_slug}/pipelines/{pipeline_uuid}"
        if action == "details":
            return await client.request("GET", base)
        if action == "steps":
            return await client.request("GET", f"{base}/steps")
        if step_uuid is None:
            raise ToolError("action='step_log' には step_uuid が必要です。")
        text = await client.request_text(
            "GET", f"{base}/steps/{step_uuid}/log"
        )
        return {"content": text}

    mcp.add_tool(list_pipelines, annotations=_READ)
    mcp.add_tool(get_pipeline, annotations=_READ)

    if read_only:
        return

    async def run_pipeline(
        *,
        workspace: str | None = None,
        repo_slug: str,
        target: PipelineTarget,
        variables: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Trigger a pipeline run for a branch or tag."""
        ws = resolve_workspace(workspace, default_workspace)
        target_body: dict[str, Any] = {
            "ref_type": target.ref_type,
            "ref_name": target.ref_name,
            "type": "pipeline_ref_target",
        }
        if target.selector is not None:
            target_body["selector"] = target.selector
        body: dict[str, Any] = {"target": target_body}
        if variables:
            body["variables"] = variables
        return await client.request(
            "POST", f"/repositories/{ws}/{repo_slug}/pipelines/", body=body
        )

    async def stop_pipeline(
        *, workspace: str | None = None, repo_slug: str, pipeline_uuid: str
    ) -> dict[str, Any]:
        """Stop a running pipeline."""
        ws = resolve_workspace(workspace, default_workspace)
        return await client.request(
            "POST",
            f"/repositories/{ws}/{repo_slug}/pipelines/{pipeline_uuid}/stopPipeline",
        )

    mcp.add_tool(run_pipeline, annotations=_WRITE)
    mcp.add_tool(stop_pipeline, annotations=_WRITE)
```

- [x] **Step 5: テストが通ることを確認**

Run: `uv run pytest tests/toolsets/test_pipelines.py -v`
Expected: PASS(6 件）

- [x] **Step 6: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/models/__init__.py src/bitbucket_mcp/toolsets/pipelines.py tests/toolsets/test_pipelines.py
git commit -m "feat: pipelines ツールセットと PipelineTarget モデルを追加"
```

---

## Task 14: `toolsets/users.py`(get_user)

**Files:**
- Create: `src/bitbucket_mcp/toolsets/users.py`
- Test: `tests/toolsets/test_users.py`

**Interfaces:**
- Consumes: `client`, `FastMCP`, `ToolAnnotations`
- Produces: `users.register(...)`(read: `get_user`)

- [x] **Step 1: 失敗するテストを書く**

`tests/toolsets/test_users.py`:

```python
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import users

BASE = "https://api.bitbucket.org/2.0"


async def test_get_user(register_toolset, call_tool, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url=f"{BASE}/users/account-123", json={"account_id": "account-123"}
    )
    mcp, _ = register_toolset(users.register)
    _, structured = await call_tool(
        mcp, "get_user", {"selected_user": "account-123"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/users/account-123"
    assert structured == {"account_id": "account-123"}


async def test_users_registers_read_only_tool(register_toolset) -> None:
    mcp, _ = register_toolset(users.register)
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert set(tools) == {"get_user"}
    assert tools["get_user"].annotations is not None
    assert tools["get_user"].annotations.readOnlyHint is True
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/toolsets/test_users.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bitbucket_mcp.toolsets.users'`)

- [x] **Step 3: `users.py` を実装**

```python
"""users ツールセット: ユーザー情報の参照。"""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient


def register(
    mcp: FastMCP,
    client: BitbucketClient,
    *,
    read_only: bool,
    default_workspace: str | None = None,
) -> None:
    async def get_user(*, selected_user: str) -> dict[str, Any]:
        """Get a user's public profile by account_id or UUID."""
        return await client.request("GET", f"/users/{selected_user}")

    mcp.add_tool(
        get_user,
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
```

- [x] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/toolsets/test_users.py -v`
Expected: PASS(2 件）

- [x] **Step 5: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/toolsets/users.py tests/toolsets/test_users.py
git commit -m "feat: users ツールセットを追加"
```

---

## Task 15: `toolsets/raw_api.py`(bitbucket_api エスケープハッチ）

**Files:**
- Create: `src/bitbucket_mcp/toolsets/raw_api.py`
- Test: `tests/toolsets/test_raw_api.py`

**Interfaces:**
- Consumes: `client`, `ToolError`, `FastMCP`, `ToolAnnotations`
- Produces: `raw_api.register(...)`(ツール `bitbucket_api`)。`read_only=True` のときも登録されるが GET/HEAD 以外を ToolError で拒否

- [x] **Step 1: 失敗するテストを書く**

`tests/toolsets/test_raw_api.py`:

```python
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pytest_httpx import HTTPXMock

from bitbucket_mcp.toolsets import raw_api

BASE = "https://api.bitbucket.org/2.0"


async def test_bitbucket_api_get_passthrough(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={"ok": True})
    mcp, _ = register_toolset(raw_api.register)
    _, structured = await call_tool(
        mcp,
        "bitbucket_api",
        {"method": "GET", "path": "repositories/ws1", "query": {"page": 2}},
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.method == "GET"
    assert request.url.path == "/2.0/repositories/ws1"
    assert request.url.params["page"] == "2"
    assert structured == {"ok": True}


async def test_bitbucket_api_normalizes_leading_slash(
    register_toolset, call_tool, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(json={})
    mcp, _ = register_toolset(raw_api.register)
    await call_tool(
        mcp, "bitbucket_api", {"method": "GET", "path": "/user"}
    )
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/2.0/user"


async def test_bitbucket_api_post_blocked_in_read_only(
    register_toolset, call_tool
) -> None:
    mcp, _ = register_toolset(raw_api.register, read_only=True)
    with pytest.raises(ToolError, match="READ_ONLY"):
        await call_tool(
            mcp,
            "bitbucket_api",
            {"method": "POST", "path": "/repositories/ws1/r/issues"},
        )


async def test_bitbucket_api_registered_even_in_read_only(register_toolset) -> None:
    mcp, _ = register_toolset(raw_api.register, read_only=True)
    names = {tool.name for tool in await mcp.list_tools()}
    assert "bitbucket_api" in names
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/toolsets/test_raw_api.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'bitbucket_mcp.toolsets.raw_api'`)

- [x] **Step 3: `raw_api.py` を実装**

```python
"""raw_api ツールセット: 任意の Bitbucket REST 呼び出し（エスケープハッチ）。"""

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from bitbucket_mcp.client import BitbucketClient


def register(
    mcp: FastMCP,
    client: BitbucketClient,
    *,
    read_only: bool,
    default_workspace: str | None = None,
) -> None:
    async def bitbucket_api(
        *,
        method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"],
        path: str,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call any Bitbucket REST endpoint (path relative to /2.0)."""
        if read_only and method.upper() not in ("GET", "HEAD"):
            raise ToolError(
                "BITBUCKET_READ_ONLY=true のため GET/HEAD のみ許可されています。"
            )
        normalized = path if path.startswith("/") else f"/{path}"
        return await client.request(
            method.upper(), normalized, query=query, body=body
        )

    mcp.add_tool(
        bitbucket_api, annotations=ToolAnnotations(open_world_hint=True)
    )
```

- [x] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/toolsets/test_raw_api.py -v`
Expected: PASS(4 件）

- [x] **Step 5: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/toolsets/raw_api.py tests/toolsets/test_raw_api.py
git commit -m "feat: bitbucket_api エスケープハッチを追加"
```

---

## Task 16: `toolsets/__init__.py`(レジストリ）+ `server.py`(create_server)

**Files:**
- Modify: `src/bitbucket_mcp/toolsets/__init__.py`(Task 1 の空パッケージをレジストリに置換）
- Create: `src/bitbucket_mcp/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: 全 toolset の `register`(Task 7-15）/ `resolve_auth_header`(Task 3）/ `BitbucketClient`(Task 6）/ `Settings`(Task 2）
- Produces: `TOOLSET_REGISTRY: dict[str, Callable[..., None]]` / `DEFAULT_TOOLSETS: list[str]` / `create_server(settings, *, host='127.0.0.1', port=8000) -> FastMCP`

- [x] **Step 1: 失敗するテストを書く**

`tests/test_server.py`:

```python
from bitbucket_mcp.config import Settings
from bitbucket_mcp.server import create_server
from bitbucket_mcp.toolsets import DEFAULT_TOOLSETS, TOOLSET_REGISTRY


def test_registry_has_all_default_toolsets() -> None:
    assert set(DEFAULT_TOOLSETS) == set(TOOLSET_REGISTRY)
    assert set(DEFAULT_TOOLSETS) == {
        "context",
        "repos",
        "pull_requests",
        "issues",
        "pipelines",
        "users",
    }


async def test_create_server_registers_default_tools_and_raw_api() -> None:
    settings = Settings(token="t")
    mcp = create_server(settings)
    names = {tool.name for tool in await mcp.list_tools()}
    assert "get_current_user" in names
    assert "list_repositories" in names
    assert "bitbucket_api" in names


async def test_create_server_respects_toolsets_selection() -> None:
    settings = Settings(token="t", toolsets="context,users")
    mcp = create_server(settings)
    names = {tool.name for tool in await mcp.list_tools()}
    assert "get_current_user" in names
    assert "get_user" in names
    assert "list_repositories" not in names
    assert "bitbucket_api" in names  # 常時登録


async def test_create_server_read_only_excludes_write_tools() -> None:
    settings = Settings(token="t", read_only=True)
    mcp = create_server(settings)
    names = {tool.name for tool in await mcp.list_tools()}
    assert "create_repository" not in names
    assert "merge_pull_request" not in names
    assert "get_repository" in names


async def test_create_server_can_exclude_raw_api() -> None:
    settings = Settings(token="t", toolsets="context,-bitbucket_api")
    mcp = create_server(settings)
    names = {tool.name for tool in await mcp.list_tools()}
    assert "bitbucket_api" not in names
    assert "get_current_user" in names
```

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL(`ImportError: cannot import name 'TOOLSET_REGISTRY'` または `No module named 'bitbucket_mcp.server'`)

- [x] **Step 3: `toolsets/__init__.py` をレジストリに置換**

```python
"""Bitbucket MCP toolset レジストリ。"""

from collections.abc import Callable

from bitbucket_mcp.toolsets import (
    context,
    issues,
    pipelines,
    pull_requests,
    repos,
    users,
)

RegisterFn = Callable[..., None]

TOOLSET_REGISTRY: dict[str, RegisterFn] = {
    "context": context.register,
    "repos": repos.register,
    "pull_requests": pull_requests.register,
    "issues": issues.register,
    "pipelines": pipelines.register,
    "users": users.register,
}

DEFAULT_TOOLSETS: list[str] = [
    "context",
    "repos",
    "pull_requests",
    "issues",
    "pipelines",
    "users",
]
```

- [x] **Step 4: `server.py` を実装**

`bitbucket_api` は `toolset_list` に `-bitbucket_api` が含まれない限り常時登録する。

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from bitbucket_mcp.auth import resolve_auth_header
from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.config import Settings
from bitbucket_mcp.toolsets import TOOLSET_REGISTRY, raw_api

_settings: Settings | None = None
_RAW_API_EXCLUDE = "-bitbucket_api"


@asynccontextmanager
async def lifespan(mcp: FastMCP) -> AsyncIterator[BitbucketClient]:
    """httpx クライアントをサーバー稼働期間だけ保持し、終了時に閉じる。"""
    if _settings is None:
        raise RuntimeError("create_server() で settings が設定されていません")
    auth_header = resolve_auth_header(_settings)
    client = BitbucketClient(base_url=_settings.base_url, auth_header=auth_header)

    requested = _settings.toolset_list
    for name in requested:
        register_fn = TOOLSET_REGISTRY.get(name)
        if register_fn is not None:
            register_fn(
                mcp,
                client,
                read_only=_settings.read_only,
                default_workspace=_settings.default_workspace,
            )

    if _RAW_API_EXCLUDE not in requested:
        raw_api.register(
            mcp,
            client,
            read_only=_settings.read_only,
            default_workspace=_settings.default_workspace,
        )

    try:
        yield client
    finally:
        await client.aclose()

def create_server(
    settings: Settings, *, host: str = "127.0.0.1", port: int = 8000
) -> FastMCP:
    """設定から FastMCP サーバーを構築する。"""
    global _settings
    _settings = settings
    return FastMCP("bitbucket-mcp", host=host, port=port, lifespan=lifespan)
```

- [x] **Step 5: テストが通ることを確認**

Run: `uv run pytest tests/test_server.py -v`
Expected: PASS(5 件）

- [x] **Step 6: 全テスト & 静的解析 & コミット**

```bash
uv run pytest -v
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/toolsets/__init__.py src/bitbucket_mcp/server.py tests/test_server.py
git commit -m "feat: toolset レジストリと create_server 配線を追加"
```

---

## Task 17: `__main__.py`(CLI 引数解析・トランスポート選択・エントリポイント）

**Files:**
- Create: `src/bitbucket_mcp/__main__.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `Settings`(Task 2）/ `create_server`(Task 16）/ `AuthConfigError`(Task 3）
- Produces: `build_arg_parser() -> argparse.ArgumentParser` / `main(argv: list[str] | None = None) -> int`

- [x] **Step 1: 失敗するテストを書く**

`tests/test_main.py`。`main()` は最終的に `mcp.run()`（ブロッキング）を呼ぶため、`run` を monkeypatch して検証する。

```python
import pytest

from bitbucket_mcp import __main__ as entry


def test_arg_parser_defaults() -> None:
    args = entry.build_arg_parser().parse_args([])
    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 8000


def test_arg_parser_http() -> None:
    args = entry.build_arg_parser().parse_args(
        ["--transport", "http", "--host", "0.0.0.0", "--port", "9000"]
    )
    assert args.transport == "http"
    assert args.host == "0.0.0.0"
    assert args.port == 9000


def test_main_returns_2_without_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 認証情報なし → AuthConfigError → 終了コード 2
    assert entry.main(["--transport", "stdio"]) == 2
    captured = capsys.readouterr()
    assert "App Password" in captured.err


def test_main_runs_stdio_when_credentials_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BITBUCKET_TOKEN", "t")
    called: dict[str, object] = {}

    def fake_run(self: object, *args: object, **kwargs: object) -> None:
        called["transport"] = kwargs.get("transport", args[0] if args else None)

    monkeypatch.setattr("mcp.server.fastmcp.FastMCP.run", fake_run)
    assert entry.main(["--transport", "stdio"]) == 0
    assert called["transport"] == "stdio"
```

> 注: `test_main_returns_2_without_credentials` は autouse の `_clean_bitbucket_env` により環境変数がクリアされている前提。

- [x] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL(`AttributeError: module 'bitbucket_mcp.__main__' has no attribute 'build_arg_parser'`)

- [x] **Step 3: `__main__.py` を実装**

MVP の主導級は stdio。`--transport http` は Streamable HTTP で起動するが、Origin 検証・OAuth 2.1 等のハードニングは Phase2。

```python
"""python -m bitbucket_mcp / uvx エントリポイント。"""

import argparse
import sys

from bitbucket_mcp.auth import AuthConfigError
from bitbucket_mcp.config import Settings
from bitbucket_mcp.server import create_server


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bitbucket-mcp")
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default="stdio"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        settings = Settings()
    except AuthConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    transport = "streamable-http" if args.transport == "http" else "stdio"
    mcp = create_server(settings, host=args.host, port=args.port)
    mcp.run(transport=transport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [x] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_main.py -v`
Expected: PASS(4 件）

- [x] **Step 5: 実際に起動する（手動スモーク）**

認証情報なしでエラー終了を確認:

Run: `uv run python -m bitbucket_mcp --transport stdio`
Expected: stderr に App Password 非対応案内を含むメッセージを出し、終了コード 2 で終了（`echo $?` で 2）。

ダミートークンで stdio 起動を確認（tools/list が応答すること）:

```bash
BITBUCKET_TOKEN=dummy uv run python - <<'PY'
import json, subprocess
proc = subprocess.Popen(
    ["uv", "run", "python", "-m", "bitbucket_mcp"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
)
init = {"jsonrpc":"2.0","id":1,"method":"initialize",
        "params":{"protocolVersion":"2025-11-25","capabilities":{},
                  "clientInfo":{"name":"smoke","version":"0"}}}
listed = {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
assert proc.stdin is not None and proc.stdout is not None
proc.stdin.write(json.dumps(init) + "\n"); proc.stdin.flush()
print("init:", proc.stdout.readline()[:80])
proc.stdin.write(json.dumps(listed) + "\n"); proc.stdin.flush()
print("tools:", proc.stdout.readline()[:200])
proc.terminate()
PY
```
Expected: `init:` 行と `tools:` 行が出力され、tools 応答に `get_current_user` 等のツール名が含まれる。（プロトコルのハンドシェイク差異で行が増える場合は複数行読むこと。）

- [x] **Step 6: 静的解析 & コミット**

```bash
uv run ruff check . && uv run basedpyright
git add src/bitbucket_mcp/__main__.py tests/test_main.py
git commit -m "feat: CLI 引数解析とエントリポイントを追加"
```

---

## Task 18: `README.md`(使い方・環境変数・uvx / Claude Desktop 設定）

**Files:**
- Create: `README.md`
- Test: なし（ドキュメント）。代わりに記載した JSON スニペットが妥当であることを目視確認する

**Interfaces:**
- Consumes: これまでの全タスクの成果物（環境変数名・CLI・ツールセット名）
- Produces: なし

- [x] **Step 1: `README.md` を作成**

以下の内容を書く（環境変数表・認証・uvx / Claude Desktop 設定例・ツールセット一覧）。値は仕様書§§5-8 と一致させること。

````markdown
# bitbucket-mcp

Bitbucket Cloud REST API v2.0 を Model Context Protocol のツールとして公開する MCP サーバー。

## インストール & 起動（uvx）

```bash
uvx bitbucket-mcp
```

またはローカル開発:

```bash
uv sync
uv run python -m bitbucket_mcp
```

## 認証

環境変数でトークンを注入する（優先順）:

1. `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` → Basic 認証
2. `BITBUCKET_TOKEN`(Access Token / OAuth Bearer）→ Bearer 認証

**App Password は非対応です**（2026-07-28 に完全廃止予定）。API Token または Access Token を使用してください。

## 環境変数

| 変数 | 用途 | 既定値 |
|---|---|---|
| `BITBUCKET_TOKEN` | Access Token / OAuth Bearer | (なし) |
| `BITBUCKET_EMAIL` | Atlassian アカウントのメール(Basic) | (なし) |
| `BITBUCKET_API_TOKEN` | Atlassian API Token(Basic, EMAIL とペア) | (なし) |
| `BITBUCKET_DEFAULT_WORKSPACE` | workspace 省略時の既定 | (なし) |
| `BITBUCKET_TOOLSETS` | 有効化する toolset（CSV） | `context,repos,pull_requests,issues,pipelines,users` |
| `BITBUCKET_READ_ONLY` | `true` で書き込みツールを一括除外 | `false` |
| `BITBUCKET_BASE_URL` | API ベース URL | `https://api.bitbucket.org/2.0` |

`bitbucket_api`(汎用ツール）は `BITBUCKET_TOOLSETS` に関わらず常時登録される（`-bitbucket_api` を含めると除外）。

## CLI

```
bitbucket-mcp --transport {stdio,http} [--host HOST] [--port PORT]
```

- `stdio`(既定）: ローカル・単一クライアント。Claude Desktop 等の標準導線。
- `http`: Streamable HTTP（Phase2 で Origin 検証・OAuth 2.1 を強化予定）。

## Claude Desktop 設定例

```json
{
  "mcpServers": {
    "bitbucket": {
      "command": "uvx",
      "args": ["bitbucket-mcp"],
      "env": {
        "BITBUCKET_EMAIL": "you@example.com",
        "BITBUCKET_API_TOKEN": "<api-token>",
        "BITBUCKET_DEFAULT_WORKSPACE": "my-workspace"
      }
    }
  }
}
```

## ツールセット（MVP）

- `context`: get_current_user, list_workspaces
- `repos`: リポジトリ/コミット/ブランチ/タグ/差分 の参照と CRUD
- `pull_requests`: PR の参照・作成・更新・マージ・レビュー・コメント
- `issues`: イシューの参照・CRUD・コメント
- `pipelines`: パイプラインの参照・実行・停止
- `users`: get_user
- `bitbucket_api`: 任意の REST 呼び出し（エスケープハッチ、常時）
````

- [x] **Step 2: JSON とリンクの妥当性を目視確認**

Run: `uv run python -c "import json,pathlib,re; t=pathlib.Path('README.md').read_text(); blocks=re.findall(r'```json\n(.*?)```', t, re.S); [json.loads(b) for b in blocks]; print('json ok:', len(blocks))"`
Expected: `json ok: 1`(README 内の JSON ブロックがパースできる）

- [x] **Step 3: コミット**

```bash
git add README.md
git commit -m "docs: README(使い方・環境変数・uvx/Claude Desktop 設定）を追加"
```

---

## 最終検証（全タスク完了後）

- [x] **全テスト**: `uv run pytest -v` → 全件 PASS。
- [x] **型検査**: `uv run basedpyright` → 0 エラー。
- [x] **Lint/整形**: `uv run ruff check .` → 0 エラー。
- [x] **パッケージビルド**: `uv build` → wheel/sdist 生成成功。
- [x] **uvx 疺通**: ビルド済み wheel を `uvx --from ./dist/bitbucket_mcp-0.1.0-py3-none-any.whl bitbucket-mcp --help` で起動できる（または `--help` 相当の引数エラーが出る）ことを確認。
- [x] **stdio 手動 QA**(Task 17 Step 5 のスモーク）: `initialize` → `tools/list` で 37 ツール（read-only 非有効時）が列挙されることを確認。

> 注: 2026-07-05 時点で `SecretStr` 関連の型エラーは解消済み。`pytest` / `ruff` / `basedpyright` / `uv build` / `uvx` / stdio 手動 QA を確認済み。

---

## Self-Review(計画作成後の自己レビュー結果）

**1. スペック網羅性（仕様§→タスク対応）:**

| 仕様セクション | 対応タスク |
|---|---|
| §3 技術スタック | Task 1(pyproject: Python3.12/mcp/httpx/pydantic/uv/ruff/basedpyright/pytest）|
| §4 アーキテクチャ(層分離/境界) | Task 2-6(config/auth/errors/pagination/client）+ Task 7-16(toolsets/server）|
| §5 認証(Basic/Bearer/App Password 非対応) | Task 3(auth.py）|
| §6 設定環境変数 | Task 2(Settings）+ Task 18(README 表）|
| §7 トランスポート(stdio MVP / http Phase2) | Task 17(）|
| §8.1 context | Task 7 |
| §8.2 repos(read/write) | Task 8, 9 |
| §8.3 pull_requests(read/write) | Task 10, 11 |
| §8.4 issues | Task 12 |
| §8.5 pipelines | Task 13 |
| §8.6 users | Task 14 |
| §8.7 bitbucket_api(read-only ゲート) | Task 15 |
| §9 データフロー/ページネーション/構造化返却 | Task 5(page_params）+ 各 toolset(structuredContent）|
| §10 エラー処理/レート制限 | Task 4(build_tool_error）+ Task 6(リトライ/X-RateLimit）|
| §11 テスト&品質(TDD/pytest-httpx/basedpyright/ruff) | 全タスクの TDD ステップ |
| §12 MVP スコープ(uvx 配布) | Task 1(scripts）+ 最終検証(uv build/uvx）|

**ギャップ(意図的な MVP 除外・仕様準拠）:**
- Phase2/3(`workspaces`/`snippets`/`admin`/`deployments`/OAuth 2.1/HTTP ハードニング/pipeline 変数）は仕様§2,§12 で明示的に将来スコープ → 本計画対象外。
- `outputSchema` は全ツールが `dict[str, Any]` 返却で FastMCP が自動生成するレベルに統一(仕様§8 の「主要 read は outputSchema 定義」はこの自動生成で充足。厳密なリソース型モデリングは YAGNI で見送り）。
- `list_workspaces` の `administrator` は `q='permission="owner"'` にマップ(BBQL)。実 API との整合は任意スモークテスト(仕様§11 `BITBUCKET_TEST_LIVE=1`)で検証。

**2. プレースホルダー走査:** 本計画に "TBD"/"TODO"/"implement later"/"add error handling"(抽象的）/コード無しの「テストを書く」は無し。各コードステップは完全なコードを提示。

**3. 型整合性:** `register(mcp, client, *, read_only, default_workspace=None)` は全 7 toolset(context/repos/pull_requests/issues/pipelines/users/raw_api)で一致。`client.request(method, path, *, query, body, form)` / `client.request_text(method, path, *, query)` の呼び出しは全 toolset で一致。`resolve_workspace(workspace, default_workspace)` の引数順も全箱所で一致。`ToolAnnotations` コンストラクタは snake_case(`read_only_hint`)、検証側の `Tool.annotations` は camelCase(`readOnlyHint`/`destructiveHint`)で統一。

**注意点(実装時に確認すべきバージョン依存):**
- `mcp.call_tool()` の戻り値形状（`(content, structured)` タプル vs `content` のみ）は `mcp` SDK バージョンで差異。`call_tool` フィクスチャが両形式を吸収済み。structured が None になる場合は `mcp>=1.13` を `uv sync` で確保。
- FastMCP の `list_tools()` が返す `Tool.annotations` 属性名が camelCase でない場合は、SDK バージョンの `ToolAnnotations` 定義を確認してテストの属性名を合わせる。

---

## 実行の引き継ぎ

計画は `docs/superpowers/plans/2026-07-03-bitbucket-mcp-mvp.md` に保存しました。実行方法は 2 つあります。

**1. Subagent-Driven(推奨）** - タスクごとに新規サブエージェントを派遣し、タスク間でレビューして高速に反復。REQUIRED SUB-SKILL: superpowers:subagent-driven-development。

**2. Inline Execution** - このセッションで superpowers:executing-plans を使い、チェックポイント付きのバッチ実行。

どちらのアプローチで進めますか？
