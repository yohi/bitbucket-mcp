# OAuth 認証ガイド

Bitbucket MCP Server は、ブラウザベースの OAuth 2.0 認証に対応しています。
CLI からのログイン、トークン管理、自動ログインの仕組みについて説明します。

---

## 認証方式の概要

Bitbucket MCP Server は以下の 3 つの認証方式をサポートしています：

| 優先順位 | 方式 | 用途 | 対話不要 |
|---|---|---|---|
| 1 | **OAuth 2.0**（推奨） | ブラウザ認証。トークンの自動更新。 | ×（初回のみ対話） |
| 2 | **Basic 認証** | EMAIL + API Token | ○ |
| 3 | **Bearer 認証** | Access Token / OAuth Bearer | ○ |

> 複数の認証情報が設定されている場合、**OAuth が最優先**で使用されます。

---

## 事前準備：Bitbucket Consumer の登録

### 1. Consumer を作成

1. Bitbucket Cloud にログイン
2. 任意のワークスペースの **Settings → OAuth consumers** を開く
3. **Add consumer** をクリック
4. 以下を設定：
   - **Name**: 任意（例: `bitbucket-mcp`）
   - **Callback URL**: `http://127.0.0.1:8976/callback`
   - **Permissions**: アカウント・リポジトリ・プルリクエスト・Issue・Pipeline の読み取り/書き込み権限を付与
5. **Save** して **Key**（Client ID）と **Secret** を控える

### 2. 環境変数を設定

```bash
export BITBUCKET_OAUTH_CLIENT_ID="your-client-id"
export BITBUCKET_OAUTH_CLIENT_SECRET="your-client-secret"
```

> これらの値は `.bashrc` や `.zshrc` に書き込むか、Claude Desktop の設定に記述してください。

---

## CLI コマンド

### `auth login` — ブラウザ OAuth でログイン

```bash
bitbucket-mcp auth login
```

実行すると：
1. ブラウザで Bitbucket の認可画面が開く
2. 利用者が「Grant access」をクリック
3. トークンがローカルに保存される
4. ターミナルにログイン情報が表示される

#### `--manual` オプション

headless 環境（SSH、WSL、コンテナ）ではブラウザが開けないため、手動モードを使います：

```bash
bitbucket-mcp auth login --manual
```

表示された URL をブラウザで開き、承認後に表示された **code** と **state** をターミナルに貼り付けます。

#### `--port` オプション

Consumer の callback URL で異なるポートを登録している場合：

```bash
bitbucket-mcp auth login --port 3000
```

> Bitbucket の Consumer 設定で `http://127.0.0.1:{PORT}/callback` が登録されている必要があります。

---

### `auth status` — 保存済みトークンの状態確認

```bash
bitbucket-mcp auth status
```

出力例：

```
client_id: your-client-id
expires_at: 2025-08-01T12:00:00+00:00
scopes: account repository pullrequest issue pipeline
```

未ログイン時：

```
未ログインです。
```

---

### `auth logout` — 保存トークンの削除

```bash
bitbucket-mcp auth logout
```

`~/.config/bitbucket-mcp/credentials.json`（または `BITBUCKET_CONFIG_DIR` で指定したパス）が削除されます。

---

## トークンの保存仕様

### 保存場所

- **既定**: `~/.config/bitbucket-mcp/credentials.json`
- **上書き**: `BITBUCKET_CONFIG_DIR` 環境変数

### ファイル権限

- ディレクトリ: `0700`（所有者のみ読み書き実行）
- ファイル: `0600`（所有者のみ読み書き）

### スキーマ

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_at": 1750000000,
  "scopes": ["account", "repository", "..."],
  "token_type": "bearer",
  "client_id": "...",
  "obtained_at": 1749996400
}
```

> `client_secret` はファイルに保存されません。実行時に環境変数から供給されます。

---

## 自動ログイン（遅延発火・非ブロッキング）

MCP クライアント（Claude Desktop 等）から初めて Bitbucket ツールを呼び出した際、未ログイン状態であれば**自動的にブラウザ認証が起動**します。

### 動作条件

- ローカル stdio 接続
- ディスプレイ環境（`DISPLAY` または `WAYLAND_DISPLAY` が設定済み）
- `BITBUCKET_OAUTH_CLIENT_ID` / `SECRET` が設定済み

### 動作フロー

```
1. ツール呼び出し
2. 未ログイン検知
3. ブラウザを非同期で開く
4. 即座に「Bitbucket 認証をブラウザで開始しました。
   同意後に操作を再実行してください」を返す
5. ユーザーがブラウザで同意
6. トークンが自動保存
7. 次回のツール呼び出しから成功
```

> 自動ログイン中に再度ツールを呼び出すと「認証処理中です。少し待って再実行してください」が返されます。

### タイムアウト

背景リスナは 5 分でタイムアウトします。タイムアウト後は次回のツール呼び出しで再試行されます。

---

## トークンの自動更新

- access_token の有効期限は **1 時間**
- 期限切れ前（60 秒前）に **自動リフレッシュ**が実行されます
- refresh_token は **回転型**（使用毎に新規発行、旧トークンは無効化）
- 更新後のトークンは即座にファイルに保存されます
- ファイルロックにより複数プロセスからの同時更新を防ぎます

---

## スコープ

Bitbucket MCP Server は、有効化されているツールセットに応じて必要なスコープを自動算出します。

### 既定スコープ（最小権限）

```
account repository pullrequest issue pipeline
```

### write スコープの追加条件

`BITBUCKET_READ_ONLY=false` かつ、書き込み系ツールを含むツールセットが有効な場合：

```
repository:write pullrequest:write issue:write pipeline:write
```

### 削除系ツールを使う場合

Bitbucket Consumer の設定で **Delete repositories** 等の権限を追加で付与する必要があります。

---

## トラブルシューティング

| 症状 | 原因 | 解決方法 |
|---|---|---|
| ブラウザが開かない | headless 環境 | `--manual` を使用 |
| `state mismatch` | CSRF 検証失敗 | 再度 `auth login` を実行 |
| callback URL 拒否 | Consumer に未登録のポート | `--port` で登録済みポートを指定 |
| 再ログインを要求される | refresh_token 失効 | `auth logout` → `auth login` |
| `client_id` 不一致 | OAuth Client ID が変更された | `auth logout` → `auth login` |

詳細は [TROUBLESHOOTING.md](TROUBLESHOOTING.md) を参照してください。

---

## セキュリティ注意事項

- `client_secret` は環境変数でのみ管理し、トークンファイルには含めない
- `credentials.json` の権限は `0600` に設定済み
- loopback リスナは `127.0.0.1` のみにバインド
- CSRF 対策に `state` を必須検証
- `BITBUCKET_OAUTH_BASE_URL` は `bitbucket.org` ドメインのみ許可

---

## 参考リンク

- [Bitbucket Cloud OAuth 2.0 ドキュメント](https://developer.atlassian.com/cloud/bitbucket/oauth-2/)
- [SPEC.md](../SPEC.md) §3 認証仕様
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) 認証エラーの詳細
