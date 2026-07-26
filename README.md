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

1. **保存済み OAuth トークン**（`BITBUCKET_OAUTH_CLIENT_ID` と `BITBUCKET_OAUTH_CLIENT_SECRET` が両方設定され、保存済み `client_id` が一致する場合のみ）
2. `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` → Basic 認証
3. `BITBUCKET_TOKEN` → Bearer 認証

**App Password は非対応です**（2026-07-28 に完全廃止予定）。API Token または Access Token を使用してください。

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
5. トークンは `BITBUCKET_CONFIG_DIR` → `XDG_CONFIG_HOME/bitbucket-mcp/credentials.json` → `~/.config/bitbucket-mcp/credentials.json` の順で決まる保存先に `0600` で保存されます。

headless 環境では `bitbucket-mcp auth login --manual` を使用してください。認可後は、リダイレクト URL に含まれる `code` と `state` をそれぞれプロンプトに貼り付けます。Callback URL に別のポートを登録した場合は、`--port PORT` を追加してください。

### CLI

```bash
bitbucket-mcp                           # サーバ起動（stdio）
bitbucket-mcp --transport http          # HTTP サーバ起動
bitbucket-mcp auth login                # ブラウザ OAuth ログイン
bitbucket-mcp auth login --manual       # code/state を手動入力
bitbucket-mcp auth login --manual --port 3000  # callback ポートを指定
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

`bitbucket_api`（汎用ツール）は `BITBUCKET_TOOLSETS` に関わらず既定で登録され、`-bitbucket_api` を含めると除外されます。

## CLI

```bash
bitbucket-mcp --transport {stdio,http} [--host HOST] [--port PORT]
```

- `stdio`(既定）: ローカル・単一クライアント。Claude Desktop 等の標準導線。
- `http`: Streamable HTTP（実装済み。Phase 2 では Origin 検証と transport OAuth 2.1 によるセキュリティ強化を予定）。

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
- `bitbucket_api`: `/2.0` を基準とする相対パスで任意の REST 呼び出しを行うエスケープハッチ。JSON 応答または空の応答のみ対応し、既定で登録される（`-bitbucket_api` で除外）
- `bitbucket_login`: ブラウザ OAuth の再ログインを開始し、認証状態を `str` で返す常時登録ツール

---

## 仕様詳細

各ツールの詳細な引数、エラーハンドリング、リトライ仕様、および設計ポリシーについては [SPEC.md](./SPEC.md) を参照してください。

## ドキュメント一覧

| ドキュメント | 内容 |
|---|---|
| [SPEC.md](./SPEC.md) | 技術仕様（API・認証・ツールセット・エラー処理） |
| [docs/OAUTH.md](docs/OAUTH.md) | OAuth 認証の設定と利用手順 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | システムアーキテクチャとデータフロー |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 開発者向けガイド（環境構築・テスト・デバッグ） |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | よくある問題と解決策 |
