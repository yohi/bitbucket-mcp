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

優先順位:

1. **保存済み OAuth トークン**（`bitbucket-mcp auth login` で取得）
2. `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` → Basic 認証
3. `BITBUCKET_TOKEN` → Bearer 認証

**App Password は非対応です** (2026-07-28 に完全廃止予定）。API Token または Access Token を使用してください。

### ブラウザ OAuth ログイン（推奨）

1. [Bitbucket Cloud OAuth コンシューマ](https://support.atlassian.com/bitbucket-cloud/docs/use-oauth-on-bitbucket-cloud/) を自分のワークスペースに登録。
2. Callback URL に `http://127.0.0.1:8976/callback` を設定（ポートは `BITBUCKET_OAUTH_CALLBACK_PORT` で変更可）。
3. 発行された `Key` / `Secret` を環境変数に設定:
   ```bash
   export BITBUCKET_OAUTH_CLIENT_ID="<Key>"
   export BITBUCKET_OAUTH_CLIENT_SECRET="<Secret>"
   ```
4. ターミナルでログイン:
   ```bash
   bitbucket-mcp auth login
   ```
5. トークンは `BITBUCKET_CONFIG_DIR`（未設定時は `~/.config/bitbucket-mcp/credentials.json`）に `0600` で保存されます。

headless 環境では `bitbucket-mcp auth login --manual` を使用してください。

### CLI

```bash
bitbucket-mcp                           # サーバ起動（stdio）
bitbucket-mcp --transport http          # HTTP サーバ起動
bitbucket-mcp auth login                # ブラウザ OAuth ログイン
bitbucket-mcp auth login --manual       # 手動コード貼り付け
bitbucket-mcp auth status               # 保存済み資格情報を表示
bitbucket-mcp auth logout               # 保存トークンを削除
```

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
| `BITBUCKET_OAUTH_CLIENT_ID` | OAuth コンシューマの client_id | (なし) |
| `BITBUCKET_OAUTH_CLIENT_SECRET` | 同 client_secret | (なし) |
| `BITBUCKET_OAUTH_CALLBACK_PORT` | loopback 待受ポート | `8976` |
| `BITBUCKET_CONFIG_DIR` | トークン保存ディレクトリ | `~/.config/bitbucket-mcp/` |
| `BITBUCKET_OAUTH_BASE_URL` | authorize/token ホスト | `https://bitbucket.org` |

`bitbucket_api`(汎用ツール）は `BITBUCKET_TOOLSETS` に関わらず常時登録される（`-bitbucket_api` を含めると除外）。

## CLI

```bash
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

---

## 仕様詳細

各ツールの詳細な引数、エラーハンドリング、リトライ仕様、および設計ポリシーについては [SPEC.md](./SPEC.md) を参照してください。
