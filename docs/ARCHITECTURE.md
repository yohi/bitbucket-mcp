# システムアーキテクチャ

Bitbucket MCP Server の内部構造、責務の分離、およびリクエストのライフサイクルを説明します。

---

## 全体構成図

```
┌─────────────────────────────────────────────────────────────┐
│                     MCP Client (Claude Desktop 等)           │
└──────────────────────────┬──────────────────────────────────┘
                           │ stdio / HTTP
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      MCP Server (FastMCP)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ bitbucket_  │  │  Toolsets   │  │   bitbucket_api     │ │
│  │   login     │  │(repos/PR/   │  │   (raw_api)         │ │
│  │  (常時登録)  │  │ issues/... )│  │   (常時登録)        │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                    │            │
│         └────────────────┴────────────────────┘            │
│                          │                                 │
│                   ┌──────┴──────┐                         │
│                   │ require_auth │                         │
│                   │   (wrapper)  │                         │
│                   └──────┬──────┘                         │
└──────────────────────────┼─────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                        Auth Layer                            │
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │  AuthProvider   │◄───│  resolve_auth_provider()        │ │
│  │   (Protocol)    │    │  OAuth > Basic > Bearer > None  │ │
│  └────────┬────────┘    └─────────────────────────────────┘ │
│           │                                                  │
│  ┌────────┴────────┐    ┌─────────────────┐                │
│  │ OAuthAuthProvider│    │ StaticAuthProv. │                │
│  │ ・Token refresh  │    │ ・Fixed header  │                │
│  │ ・CredentialStore│    │ ・No-op refresh │                │
│  └────────┬────────┘    └─────────────────┘                │
│           │                                                  │
│           ▼                                                  │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ CredentialStore │    │  OAuthClient    │                │
│  │ ・Save/Load     │    │ ・Authorize URL │                │
│  │ ・File lock     │    │ ・Exchange code │                │
│  │ ・Atomic write  │    │ ・Refresh token │                │
│  └─────────────────┘    └─────────────────┘                │
└──────────────────────────┬─────────────────────────────────┘
                           │ Authorization: Bearer/Basic
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                      HTTP Client Layer                       │
│                     ┌─────────────┐                         │
│                     │BitbucketClient│                        │
│                     │ ・httpx      │                        │
│                     │ ・Retry      │                        │
│                     │ ・401 refresh│                        │
│                     └──────┬──────┘                        │
└────────────────────────────┼────────────────────────────────┘
                             │ HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                 Bitbucket Cloud REST API v2.0               │
└─────────────────────────────────────────────────────────────┘
```

---

## 層構成と責務

### 1. Config Layer (`config.py`)

- **責務**: `BITBUCKET_*` 環境変数の読み込みと Pydantic によるバリデーション
- **出力**: `Settings` dataclass
- **特記**: `SecretStr` により `client_secret` 等の機密値はログに出力されない

### 2. Auth Layer (`auth.py`)

- **責務**: 認証情報の解決とヘッダ生成
- **主要クラス**:
  - `AuthProvider` — Protocol（抽象インターフェース）
  - `StaticAuthProvider` — 固定ヘッダ（Basic / Bearer）
  - `OAuthAuthProvider` — OAuth トークン管理・リフレッシュ
- **解決順位**:
  1. 保存済み OAuth トークン（`client_id` が一致する場合）
  2. `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` → Basic
  3. `BITBUCKET_TOKEN` → Bearer
  4. 未ログイン → ツール呼び出し時に自動ログイン発火

### 3. Credential Layer (`credentials.py`)

- **責務**: トークンの永続化
- **保存先**: `~/.config/bitbucket-mcp/credentials.json`
- **特記**:
  - ファイル権限 `0600`、ディレクトリ `0700`
  - アトミック書き込み（一時ファイル + rename）
  - ファイルロックによる複数プロセスからの同時更新防止
  - `client_secret` は保存しない

### 4. OAuth Layer (`oauth.py`)

- **責務**: OAuth 2.0 プロトコル実装
- **主要クラス**:
  - `OAuthClient` — authorize URL 生成、認可コード交換、リフレッシュ
  - `OAuthCallbackServer` — loopback callback リスナ
- **フロー**:
  1. `build_authorize_url(state)` → ブラウザで開く
  2. 利用者が同意 → callback で `code` + `state` を回収
  3. `exchange_code(code)` → access/refresh token 取得
  4. 期限切れ前に `refresh_token()` → 回転型トークンを更新

### 5. HTTP Client Layer (`client.py`)

- **責務**: Bitbucket API への HTTP アクセス
- **特記**:
  - リクエスト毎に `AuthProvider.authorization_header()` を取得
  - 401 応答時 → `refresh()` → 1 回だけ再試行
  - 429/502/503/504 + `RequestError` → 指数バックオフで最大 2 回リトライ
  - GET/HEAD のみリトライ対象

### 6. Error Layer (`errors.py`)

- **責務**: Bitbucket API のエラー JSON を MCP `ToolError` に変換
- **フォーマット**:
  ```
  Bitbucket API {status_code}: {message} — {detail} [{hint}] (retry after {retry_after})
  ```

### 7. Toolset Layer (`toolsets/`)

- **責務**: FastMCP へのツール登録
- **構成**:
  | モジュール | 提供ツール |
  |---|---|
  | `context.py` | get_current_user, list_workspaces |
  | `repos.py` | リポジトリ/コミット/ブランチ/タグ/差分 の参照と CRUD |
  | `pull_requests.py` | PR の参照・作成・更新・マージ・レビュー・コメント |
  | `issues.py` | イシューの参照・CRUD・コメント |
  | `pipelines.py` | パイプラインの参照・実行・停止 |
  | `users.py` | get_user |
  | `raw_api.py` | bitbucket_api（汎用 REST 呼び出し） |

- **共通ヘルパ** (`_common.py`):
  - `require_auth()` — 認証ラッパーデコレータ
  - `AutoLoginController` — 遅延ログイン制御
  - `resolve_workspace()` — workspace 省略時の解決
  - `page_params()` — page/pagelen のクランプ

### 8. Server Layer (`server.py`)

- **責務**: FastMCP インスタンスの生成と lifespan 管理
- **処理**:
  1. `create_server()` → FastMCP インスタンス生成
  2. `make_lifespan()` → lifespan コンテキスト:
     - `resolve_auth_provider()` で認証プロバイダ解決
     - `BitbucketClient` 生成
     - `TOOLSET_REGISTRY` + `raw_api` を登録
     - 未ログインでも起動は成功（ツール呼び出し時に自動ログイン）

### 9. CLI Layer (`__main__.py`)

- **責務**: コマンドラインインターフェース
- **コマンド**:
  | コマンド | 動作 |
  |---|---|
  | `bitbucket-mcp` | サーバー起動（stdio/HTTP） |
  | `bitbucket-mcp auth login` | ブラウザ OAuth |
  | `bitbucket-mcp auth status` | トークン状態確認 |
  | `bitbucket-mcp auth logout` | トークン削除 |

---

## リクエストライフサイクル

```
[1] MCP Client がツール呼び出し
        ↓
[2] FastMCP が対象ツール関数を特定
        ↓
[3] require_auth() ラッパーが実行
        ├── auth_provider.is_authenticated() をチェック
        ├── False の場合:
        │   ├── ディスプレイあり + OAuth 設定済み:
        │   │   → AutoLoginController.start() → ブラウザを開く
        │   │   → 「認証を開始しました。再実行してください」を返す
        │   └── ディスプレイなし / 設定不足:
        │       → ToolError（fallback 案内）を返す
        └── True の場合 → 次へ進む
        ↓
[4] ツール関数が実行
        ├── workspace を resolve（省略時は env またはエラー）
        ├── BitbucketClient.request() を呼び出し
        └── API レスポンスを dict[str, Any] に変換して返す
        ↓
[5] BitbucketClient が HTTP リクエストを送信
        ├── authorization_header() を取得
        │   └── OAuth の場合: 期限切れなら refresh → 保存 → 新トークンで再取得
        ├── ヘッダに Authorization を注入
        ├── httpx でリクエスト送信
        └── 401 なら refresh → 1 回再試行
        ↓
[6] Bitbucket API からレスポンス
        ↓
[7] エラーなら errors.py で ToolError に変換
        ↓
[8] MCP Client に結果を返却
```

---

## 認証フロー

### 初回ログイン（ブラウザ）

```
User: bitbucket-mcp auth login
        ↓
CLI: generate_state() → authorize URL を構築
        ↓
CLI: webbrowser.open(authorize_url)
        ↓
User: Bitbucket で「Grant access」をクリック
        ↓
Bitbucket: redirect → http://127.0.0.1:8976/callback?code=...&state=...
        ↓
OAuthCallbackServer: code + state を回収
        ↓
CLI: state を検証 → exchange_code(code)
        ↓
Bitbucket OAuth: access_token + refresh_tokenを返却
        ↓
CLI: CredentialStore.save() → credentials.json（0600）
        ↓
User: ログイン完了
```

### 自動ログイン（ツール呼び出し時）

```
MCP Tool Call（未ログイン状態）
        ↓
require_auth() wrapper
        ↓
is_authenticated() == False
        ↓
display available == True
        ↓
AutoLoginController.start()
        ├── webbrowser.open() → 認可 URL
        └── OAuthCallbackServer.start() → 背景で待受
        ↓
ToolErrorを返す（≠エラー）
「Bitbucket 認証をブラウザで開始しました。
  同意後に操作を再実行してください」
        ↓
User: ブラウザで同意
        ↓
Background: callback を回収 → トークン保存
        ↓
次回の Tool Call → is_authenticated() == True → 正常実行
```

### トークンリフレッシュ（実行時）

```
BitbucketClient.request()
        ↓
OAuthAuthProvider.authorization_header()
        ↓
期限切れ前（60秒以上）かチェック
        ↓
期限切れなら:
        ├── credentials.py locked
        ├── oauth_client.refresh_token_sync()
        ├── 新トークンを CredentialStore.save()
        └── unlock
        ↓
Bearer <new_token> を返却
        ↓
リクエスト送信
```

---

## データフロー図（ツール呼び出し時）

```
┌──────────┐     ┌─────────────┐     ┌────────────────┐     ┌────────────┐
│ MCP Tool │────▶│ Tool func   │────▶│ BitbucketClient│────▶│ Bitbucket  │
│  Call    │     │ (toolsets/) │     │ (client.py)    │     │ Cloud API  │
└──────────┘     └──────┬──────┘     └────────────────┘     └─────┬──────┘
                        │                                         │
                        │    ┌────────────┐                       │
                        └───▶│ require_auth│◄─────────────────────┘
                             │ (wrapper)   │  401 → refresh retry
                             └──────┬──────┘
                                    │
                                    ▼
                             ┌────────────┐
                             │AuthProvider│
                             │ (auth.py)  │
                             └────────────┘
```

---

## エラー処理フロー

```
HTTP エラー発生
        ↓
BitbucketClient._send()
        ├── 401 + not refreshed yet:
        │   ├── auth_provider.refresh()
        │   └── 同じリクエストを再送（1回だけ）
        ├── 401 + already refreshed:
        │   └── ToolError("認証に失敗しました。再ログインしてください。")
        ├── 429 / 502 / 503 / 504:
        │   └── 指数バックオフで最大2回リトライ
        └── その他:
            └── errors.build_tool_error() → ToolError
```

---

## 参考リンク

- [SPEC.md](../SPEC.md) — 詳細な API 仕様とツール一覧
- [OAUTH.md](OAUTH.md) — OAuth 認証の利用手順
- [DEVELOPMENT.md](DEVELOPMENT.md) — 開発環境の構築方法
