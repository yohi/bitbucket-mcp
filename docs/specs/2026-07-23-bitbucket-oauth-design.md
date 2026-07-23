# Bitbucket MCP — ブラウザベース OAuth 認証 設計仕様

- **日付**: 2026-07-23
- **ステータス**: Draft（ユーザレビュー待ち）
- **関連**: `SPEC.md` §3 認証仕様 / §4 環境変数 / §9 ロードマップ Phase 2
- **スコープ区分**: 「MCP サーバ → Bitbucket」への **upstream OAuth 2.0（Authorization Code Grant）**。MCP トランスポート層の OAuth 2.1（Streamable HTTP 化・Phase 2）とは **別物**。

---

## 1. 目的と背景

### 現状

- 認証は `resolve_auth_header()` が環境変数から**静的トークンを読み、Authorization ヘッダを起動時に1回だけ生成**（`auth.py`）。
- `BitbucketClient` はその固定ヘッダを保持し全リクエストで使い回す（`client.py`）。**トークンの失効・更新・リフレッシュの概念がない**。
- `server.py` の lifespan は起動時に `resolve_auth_header()` を1回呼び、資格情報が無ければ `AuthConfigError` でプロセス終了。

### 動機

- App Password は 2026-07-28 に完全廃止。OAuth 2.0 が第一推奨の代替。
- 利用者に「トークンを手動発行して env に貼る」を強いる代わりに、`gh auth login` 型の**ブラウザベース OAuth** を日常利用の主軸にしたい。

### ゴール

1. ローカル利用ではブラウザ OAuth を主軸にする。
2. AI エージェントが MCP を利用開始した際、未ログインなら**自動でブラウザ認証を起動**する（遅延発火・非ブロッキング）。
3. CI・自動化・headless 用に既存のトークン/Basic 認証を非対話フォールバックとして温存する。

---

## 2. 前提: Bitbucket Cloud OAuth 制約（調査結果）

| 項目 | 事実 | 設計への影響 |
|---|---|---|
| Authorization Code Grant | 対応。authorize=`https://bitbucket.org/site/oauth2/authorize`、token=`https://bitbucket.org/site/oauth2/access_token` | フロー成立。ホストは `base_url`(api.bitbucket.org) とは別 |
| PKCE (RFC 7636) | 公式ドキュメントに記載なし＝**非対応前提** | client_secret 必須。公開バイナリに secret 同梱不可 |
| コンシューマ登録 | **ワークスペース単位でユーザ自身が登録**。共有 client_id 非推奨 | client_id/secret は利用者供給。ツールは secret を持たない |
| callback URL | 固定登録必須。**loopback(localhost) の公式明記なし** | 固定ポート loopback を主軸に、実機検証が必要（§16 リスク） |
| access token | 有効期限 **1 時間** | リフレッシュ機構が必須 |
| refresh token | **3ヶ月・回転型**（使用毎に新規発行、旧トークン再利用不可） | 更新の都度、回転後トークンを即永続化 |
| トークン送信 | 2026-05-04 以降 Authorization ヘッダ(Bearer)のみ | 現行 `client.py` は Bearer 送信で適合済み |
| スコープ | `account` / `repository`(:write) / `pullrequest`(:write) / `issue`(:write) / `pipeline`(:write) 等 | §12 参照 |

出典: developer.atlassian.com 公式ドキュメント、Atlassian Developer Community（OAuth 2.0 authentication changes）。

---

## 3. 確定した設計判断（Q1〜Q5）

| # | 論点 | 決定 | 理由 |
|---|---|---|---|
| Q1 | 利用者・配布モデル | **個人利用（A）を主軸、公開配布（C）を視野** | A と C は同一メカニズム（利用者が自コンシューマ登録し client_id/secret を供給、secret 非同梱）。A 前提で作れば C 対応は自動的に満たされる |
| Q2 | 既存トークン/Basic の扱い | **OAuth を主軸にしつつ非対話フォールバックとして温存（A）** | ブラウザ OAuth は CI/headless で動かない。既存挙動とライブテストを壊さない |
| Q3 | コード受け取り方式 | **固定ポート loopback を主軸 + 手動貼り付け(OOB) フォールバック（C 相当）** | loopback が UX 最良だが公式未文書のため、フォールバックで「動かない」事故を防ぐ |
| Q4 | トークン保存先 | **設定ディレクトリに `0600` の JSON ファイル（A）** | headless 互換・無依存・全 OS で確実。将来のキーチェーン対応（C）へ拡張余地は残す |
| Q5 | 自動ログインの発火 | **遅延発火（初回 Bitbucket ツール呼び出し時）・非ブロッキング（A）** | 実使用時のみ発火し無関係セッションでタブが開かない。init ハンドシェイクを止めない |

---

## 4. アーキテクチャ

### 4.1 モジュール構成

**新規**

- **`oauth.py`** — OAuth フロー本体。認可 URL 生成（`state` による CSRF 対策 + scope）、loopback callback リスナ、手動 OOB フォールバック、認可コード交換、トークンリフレッシュ。エンドポイントは `https://bitbucket.org/site/oauth2/{authorize,access_token}`（設定で上書き可能・テスト用）。
- **`credentials.py`** — トークンストア。パス解決・アトミック書き込み・`0600` 権限・読み出し・破損耐性・削除。

**変更**

- **`auth.py`** — `AuthProvider` 抽象を導入。`resolve_auth_provider(settings)` が優先順位に従い実装を返す（§6）。
- **`client.py`** — コンストラクタを `auth_header: str` から `auth_provider: AuthProvider` へ変更。リクエスト毎にヘッダを取得し、**401 で1回だけ強制リフレッシュ→リトライ**。既存の 429/5xx リトライは維持。
- **`config.py`** — OAuth 関連の設定項目を追加（§10）。
- **`server.py`** — lifespan で `resolve_auth_provider()` を用いて `BitbucketClient(base_url, auth_provider)` を生成。**未ログインでもハードフェイルせず起動**し、ツール登録を行う。`bitbucket_login` ツールを常時登録。
- **`__main__.py`** — argparse を subparser 化し `auth` サブコマンド群を追加（§5）。サブコマンドなしは従来どおりサーバ起動（後方互換）。
- **`toolsets/`** — 遅延自動ログインのフック（初回呼び出しで未ログイン検知 → OAuth フロー起動）。共通ヘルパ `_common.py` に集約し各ツールから利用。

> 各ファイルは 250 LOC 上限（programming 規約）を守る。`oauth.py` が肥大化する場合は `oauth_flow.py`（フロー）/`oauth_token.py`（交換・更新）に分割する。

### 4.2 責務境界

- `credentials.py` は「保存/読込/削除」だけを知り、OAuth プロトコルを知らない。
- `oauth.py` は「プロトコル（URL・交換・更新・callback 回収）」だけを知り、保存先の詳細を知らない（`CredentialStore` 経由）。
- `auth.py` は「どの資格情報源を使うか（解決）」と「有効なヘッダの供給」だけを担う。
- `client.py` は「HTTP・リトライ・401時の再認証委譲」だけを知り、OAuth の中身を知らない（`AuthProvider` 経由）。

---

## 5. CLI とツール表面

### 5.1 CLI サブコマンド（`__main__.py`）

| コマンド | 動作 |
|---|---|
| `bitbucket-mcp`（サブコマンドなし） | 従来どおりサーバ起動（`--transport/--host/--port` 維持） |
| `bitbucket-mcp auth login` | ブラウザ OAuth を実行しトークン保存。オプション: `--manual`（手動貼り付け強制）, `--port N`（loopback ポート上書き） |
| `bitbucket-mcp auth status` | 保存済み資格情報の有無・アカウント・スコープ・失効時刻を表示 |
| `bitbucket-mcp auth logout` | 保存トークンを削除 |

### 5.2 MCP ツール

- **`bitbucket_login`**（常時登録・`BITBUCKET_READ_ONLY` でも除外しない） — エージェントが明示的に（再）認証を起動できる MCP ネイティブ導線。実行時にブラウザ OAuth を起動し、結果メッセージを返す。

---

## 6. 認証解決とプロバイダ抽象（`auth.py`）

### 6.1 抽象

- `AuthProvider`（インタフェース）: `async def authorization_header() -> str`、`async def refresh() -> None`。
- `StaticAuthProvider(header)`: 既存の Basic/Bearer。`refresh()` は no-op、401 は従来どおり送出。
- `OAuthAuthProvider(store, oauth_client, settings)`: 保存トークンから Bearer を返す。失効（または失効直前スキュー、例 60秒）なら `refresh_token` + client 資格で更新し、**回転後トークンを即保存**してから返す。多重リフレッシュ防止に asyncio ロックを用いる。

### 6.2 解決優先順位 `resolve_auth_provider(settings)`

1. **保存済み OAuth トークンが存在** → `OAuthAuthProvider`
2. `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` → `StaticAuthProvider`(Basic)
3. `BITBUCKET_TOKEN` → `StaticAuthProvider`(Bearer)
4. いずれも無い場合:
   - OAuth の client_id/secret が設定済みなら「**未ログイン状態の OAuthAuthProvider**」を返す（起動は成功させ、初回ツール呼び出し時に自動ログインを発火）。
   - client_id/secret も無ければ `AuthConfigError`（文言: 「`bitbucket-mcp auth login` を実行、または `BITBUCKET_OAUTH_CLIENT_ID`/`SECRET` を設定、または `BITBUCKET_TOKEN` 等を設定してください」）。

> 補足: 将来 CI 等で「明示 env トークンを OAuth より優先」したい要望が出れば順序反転オプションを追加可能。今回は合意どおり OAuth 優先。

---

## 7. トークンストア（`credentials.py`）

- **パス解決**: `BITBUCKET_CONFIG_DIR` → `$XDG_CONFIG_HOME/bitbucket-mcp/` → `~/.config/bitbucket-mcp/`。ファイル名 `credentials.json`。
- **権限**: ディレクトリ `0700`、ファイル `0600`。一時ファイル + rename でアトミック書き込み。
- **スキーマ**（JSON）:
  ```json
  {
    "access_token": "…",
    "refresh_token": "…",
    "expires_at": 1750000000,
    "scopes": ["account", "repository", "..."],
    "token_type": "bearer",
    "client_id": "…",
    "obtained_at": 1749996400
  }
  ```
- **client_secret は保存しない**（実行時に config から供給）。`client_id` を保存し、設定と不一致なら再ログインを促す。
- 破損/欠損時は `None` を返し、未ログイン扱いにする。

---

## 8. データフロー

### 8.1 明示ログイン（`auth login`・対話端末）

1. config から client_id/secret を読む（無ければ設定手順を案内して終了）。
2. `state`（乱数）と scope を付与した認可 URL を生成。
3. 固定ポートで loopback リスナ起動 → `webbrowser.open()`。`--manual` 時はリスナを起動せず URL を表示。
4. 利用者が同意 → Bitbucket が `http://localhost:PORT/callback?code=…&state=…` へリダイレクト → リスナが回収（`--manual` は端末貼り付け）。
5. `state` 検証 → 認可コードを交換（`grant_type=authorization_code`, Basic client 資格） → access/refresh/expires/scopes 取得。
6. `CredentialStore` に保存 → アカウント・スコープ・失効時刻を表示。

### 8.2 自動ログイン（Q5=A: 遅延・非ブロッキング）

- **トリガ**: 初回の Bitbucket ツール呼び出しで未ログインを検知。
- **条件**: ローカル stdio + ディスプレイ有 + OAuth client_id/secret 設定済み。
- **挙動（非ブロッキング）**: `webbrowser.open()` + 背景 loopback リスナ起動。当該ツール呼び出しは待たずに「Bitbucket 認証をブラウザで開始しました。同意後に操作を再実行してください」を返す。背景で callback を回収しトークンを保存 → 次回呼び出しから成功。
- **多重起動防止**: フロー実行中はロック/フラグで管理。実行中の追加呼び出しは「認証処理中です。少し待って再実行してください」を返す。
- **条件を満たさない場合**（headless・ディスプレイなし・client 未設定）: ブラウザを開かず、トークン fallback（`BITBUCKET_TOKEN`）または `auth login` 手順を案内する `ToolError`。

### 8.3 実行時トークン更新

- 各リクエスト前に `OAuthAuthProvider.authorization_header()` を取得。失効直前なら事前リフレッシュ。
- `401` 応答時は `refresh()` を1回強制実行し再送。それでも 401 なら `ToolError`（再ログイン案内）。
- リフレッシュ成功の都度、回転後 refresh_token を保存。

---

## 9. エラー処理

| ケース | 挙動 / メッセージ |
|---|---|
| 資格情報が一切ない | `AuthConfigError`（起動時）: login か client_id/secret かトークン設定を案内 |
| OAuth 設定済み・未ログイン（対話可） | 自動ログイン発火（§8.2） |
| OAuth 設定済み・未ログイン（headless） | `ToolError`: トークン fallback か `auth login` を案内 |
| refresh 失効(>3ヶ月/失効) | `ToolError`/CLI エラー: 「再ログイン（`auth login`）が必要」 |
| loopback ポート競合 | エラー: `--port` 変更または `--manual` を案内 |
| `state` 不一致 | 中断（CSRF 疑い）。再試行を案内 |
| callback URL 拒否（Bitbucket） | `--manual` と、コンシューマ callback 登録確認を案内 |

---

## 10. 設定追加（`config.py` / 環境変数）

| 変数 | 用途 | 既定値 |
|---|---|---|
| `BITBUCKET_OAUTH_CLIENT_ID` | OAuth コンシューマの client_id | (なし) |
| `BITBUCKET_OAUTH_CLIENT_SECRET` | 同 client_secret（`SecretStr`） | (なし) |
| `BITBUCKET_OAUTH_CALLBACK_PORT` | loopback 待受ポート | `8976` |
| `BITBUCKET_CONFIG_DIR` | トークン保存ディレクトリ上書き | (XDG 既定) |
| `BITBUCKET_OAUTH_BASE_URL` | authorize/token のホスト（テスト用上書き） | `https://bitbucket.org` |

既存変数（`BITBUCKET_TOKEN` / `EMAIL` / `API_TOKEN` / `DEFAULT_WORKSPACE` / `TOOLSETS` / `READ_ONLY` / `BASE_URL`）は不変。

---

## 11. スコープ方針

- 既定要求スコープ: `account repository repository:write pullrequest pullrequest:write issue issue:write pipeline pipeline:write`。
- `BITBUCKET_READ_ONLY=true` の場合は read 系のみ要求（`account repository pullrequest issue pipeline`）。
- 削除系ツール（`delete_repository` 等）を使う場合は、コンシューマ登録時に `repository:admin` 等を付与する旨を文書化。
- スコープはコンシューマ登録時に付与されている必要があり、authorize 要求はその部分集合。

---

## 12. セキュリティ考慮

- `client_secret` は env のみで保持し、**トークンファイルには書かない**。
- トークンファイルは `0600`、親ディレクトリ `0700`。
- CSRF 対策に `state` を必須検証。
- loopback リスナは `127.0.0.1` にのみバインド（外部公開しない）。
- ログにアクセストークン/リフレッシュトークン/secret を出力しない（既存のエラーフォーマットにトークンが混入しないことも確認）。

---

## 13. テスト方針（TDD / pytest + pytest-httpx）

- **oauth**: 認可 URL 生成（client_id/scope/state/response_type）、コード交換のリクエスト組み立てとレスポンス解釈、リフレッシュ要求と回転トークンの保存。
- **credentials**: 保存/読込ラウンドトリップ、`0600` 権限、パス解決（XDG/env）、アトミック書き込み、破損ファイル耐性、削除。
- **auth provider**: 解決優先順位（OAuth > Basic > Bearer > 未ログイン/エラー）、失効検知とリフレッシュ発火、`StaticAuthProvider` の非更新。
- **client**: リクエスト毎ヘッダ注入、401→refresh→1回リトライ、既存 429/5xx リトライ維持。
- **auto-login**: 未ログイン検知時のフロー起動判定（対話/headless 分岐）、多重起動防止、非ブロッキング返却メッセージ。
- **loopback ハンドラ**: `code`/`state` 付き callback の処理と `state` 検証。
- **ライブ**: `auth login` はブラウザ対話のため手順書化。自動ライブテスト（`BITBUCKET_TEST_LIVE`）はトークン fallback で継続。

---

## 14. 非対象（YAGNI）

- OS キーチェーン保存（将来 C 拡張の余地は残すが今回は対象外）。
- MCP トランスポート層 OAuth 2.1（http 化・SPEC Phase 2。本仕様は upstream OAuth）。
- Implicit Grant / Client Credentials Grant。
- 無関係なリファクタリング。

---

## 15. 未解決リスク / 実機検証項目

1. **Bitbucket の loopback callback 実機挙動** — `http://localhost:PORT/callback` がコンシューマ callback として受理されるか要検証。不可なら固定 callback ページ運用 or `--manual` を主導線に切替。
2. **MCP クライアントのツール呼び出しタイムアウト** と非ブロッキング返却の相性（Claude Desktop 等）。
3. **`webbrowser` の環境依存**（WSL/リモートデスクトップ/複数ディスプレイ）でのディスプレイ判定精度。
4. **argparse subparser 化**による既存 CLI 起動の後方互換（`--transport` 等がサブコマンドなしで従来どおり効くか）。

---

## 16. ドキュメント更新対象（実装時）

- `README.md`: 認証節（OAuth login 手順・コンシューマ登録・callback URL・新 env 変数・保存場所）。
- `SPEC.md`: §3 認証仕様（解決順の更新）、§4 環境変数（追加）、§9 ロードマップ（upstream OAuth と transport OAuth 2.1 の区別を明記）。

---

## 17. 変更ファイル一覧（見積り）

- 新規: `src/bitbucket_mcp/oauth.py`, `src/bitbucket_mcp/credentials.py`
- 変更: `src/bitbucket_mcp/auth.py`, `client.py`, `config.py`, `server.py`, `__main__.py`, `toolsets/_common.py`（+ `toolsets/__init__.py` に `bitbucket_login` 登録）
- テスト: 上記に対応する `tests/` 配下の新規/更新
- ドキュメント: `README.md`, `SPEC.md`
