# トラブルシューティングガイド

Bitbucket MCP Server の利用中に発生する可能性のある問題と、その解決方法をまとめます。

---

## 認証・ログイン関連

### `AuthConfigError: 認証情報がありません`

**原因**: 環境変数によるトークン注入も、OAuth 設定も見つからない状態。

**解決方法**:

1. OAuth 認証を使う場合:
   ```bash
   export BITBUCKET_OAUTH_CLIENT_ID="your-client-id"
   export BITBUCKET_OAUTH_CLIENT_SECRET="your-client-secret"
   bitbucket-mcp auth login
   ```

2. 静的トークンを使う場合:
   ```bash
   # Bearer トークン
   export BITBUCKET_TOKEN="your-token"

   # または Basic 認証
   export BITBUCKET_EMAIL="you@example.com"
   export BITBUCKET_API_TOKEN="your-api-token"
   ```

### `NotAuthenticatedError: Bitbucket OAuth ログインが必要です`

**原因**: OAuth 設定はあるが、ブラウザ認証がまだ実行されていない。

**解決方法**:

```bash
bitbucket-mcp auth login
```

または、Claude Desktop 等からツールを呼び出した際に自動的にブラウザ認証が起動します（ディスプレイ環境の場合）。同意後にツールを再度実行してください。

### `NotAuthenticatedError: 再ログインが必要です`

**原因**: refresh_token が失効（3ヶ月経過）または無効化された。

**解決方法**:

```bash
bitbucket-mcp auth logout
bitbucket-mcp auth login
```

### OAuth ログイン後も認証エラーが続く

**原因**:
- `BITBUCKET_OAUTH_CLIENT_ID` が変更された（保存トークンの `client_id` と不一致）
- 複数マシン/プロセスで同時にトークン更新した結果、refresh_token が無効化された

**解決方法**:

```bash
# 保存トークンをクリアして再ログイン
bitbucket-mcp auth logout
bitbucket-mcp auth login
```

---

## 環境変数関連

### `ValidationError` でサーバーが起動しない

**原因**: 環境変数の値が不正（例: `BITBUCKET_READ_ONLY=not-a-bool`）。

**解決方法**:

Bool 型の環境変数は `true` / `false`（小文字）を使用：

```bash
export BITBUCKET_READ_ONLY=true  # OK
export BITBUCKET_READ_ONLY=1     # NG（Pydantic パースエラー）
```

### ツールセットが読み込まれない

**原因**: `BITBUCKET_TOOLSETS` の指定ミス。

**解決方法**:

```bash
# カンマ区切り（スペースなし）
export BITBUCKET_TOOLSETS="context,repos,pull_requests,issues,pipelines,users"

# 確認
bitbucket-mcp --help  # toolsets 一覧は起動ログに出力される
```

### `BITBUCKET_BASE_URL` を変更したらエラー

**原因**: `https://api.bitbucket.org/2.0` 以外の URL を指定したが、パスが正しくない。

**解決方法**:

末尾に `/2.0` を含めた完全な URL を指定：

```bash
export BITBUCKET_BASE_URL="https://api.bitbucket.org/2.0"
```

---

## API・通信関連

### `ToolError: 429 Too Many Requests`

**原因**: Bitbucket Cloud のレート制限に到達。

**解決方法**:

- しばらく待ってから再試行（自動リトライ済みの場合は間隔を空ける）
- `page` / `pagelen` パラメータで一度に取得する件数を調整

### `ToolError: 401 Unauthorized`

**原因**:
- トークンが失効
- スコープ不足（write 操作に read オンリーのスコープしかない）

**解決方法**:

1. `bitbucket-mcp auth status` でトークンの状態を確認
2. 必要に応じて再ログイン
3. Bitbucket Consumer の設定で必要なスコープが付与されているか確認

### `ToolError: 502/503/504`

**原因**: Bitbucket Cloud 側の一時的な障害。

**解決方法**:

- 自動リトライ（最大 2 回）が実施済み。それでも失敗する場合は数分後に再試行
- GET / HEAD リクエストのみリトライ対象。POST 等の非べき等リクエストはリトライしません

---

## MCP 接続関連

### Claude Desktop でツールが表示されない

**原因**:
- MCP サーバーが起動に失敗している
- `BITBUCKET_TOOLSETS` で全ツールセットを除外している
- 設定ファイルの構文エラー

**解決方法**:

1. Claude Desktop の設定を確認：
   ```json
   {
     "mcpServers": {
       "bitbucket": {
         "command": "uvx",
         "args": ["bitbucket-mcp"],
         "env": {
           "BITBUCKET_TOKEN": "..."
         }
       }
     }
   }
   ```

2. ターミナルで直接起動テスト：
   ```bash
   uvx bitbucket-mcp 2>&1 | head -20
   ```

3. Claude Desktop を再起動

### `stdio` 接続がすぐ切れる

**原因**:
- 認証エラーでサーバーが即座に終了している
- 環境変数が Claude Desktop のプロセスに渡されていない

**解決方法**:

Claude Desktop の設定で `env` セクションに環境変数を明示的に記述します（OS の環境変数は自動継承されない場合があります）。

---

## OAuth 認証関連

### `bitbucket-mcp auth login` でブラウザが開かない

**原因**:
- headless 環境（SSH 接続、WSL、コンテナ等）
- ディスプレイが検出できない

**解決方法**:

```bash
# 手動モードで実行
bitbucket-mcp auth login --manual
```

表示された URL をブラウザで開き、コードと state をターミナルに貼り付けます。

### `CSRF 検証に失敗しました (state 不一致)`

**原因**:
- callback URL に付与された `state` と、サーバーが生成した `state` が不一致
- 同じ URL を複数回使用した

**解決方法**:

再度 `bitbucket-mcp auth login` を実行してください。`state` は毎回新しく生成されます。

### callback URL が拒否される

**原因**: Bitbucket Consumer の設定で、指定したポートが callback URL として登録されていない。

**解決方法**:

1. Bitbucket の Settings → OAuth consumers で callback URL を確認
2. `http://127.0.0.1:8976/callback` が登録されているか確認
3. 異なるポートを使う場合は `--port` オプションで指定：
   ```bash
   bitbucket-mcp auth login --port 3000
   ```

---

## ファイルのパス・権限関連

### `credentials.json` の権限エラー

**原因**: 保存先ディレクトリやファイルの権限が `0600` / `0700` ではない。

**解決方法**:

```bash
# ディレクトリを確認
ls -la ~/.config/bitbucket-mcp/

# 必要に応じて修復
chmod 700 ~/.config/bitbucket-mcp
chmod 600 ~/.config/bitbucket-mcp/credentials.json
```

### 設定ディレクトリの場所を知りたい

```bash
bitbucket-mcp auth status
# → 保存パスが表示される
```

または環境変数で変更：

```bash
export BITBUCKET_CONFIG_DIR="/custom/path"
```

---

## まだ解決しない場合

1. [README.md](../README.md) の「認証」セクションを再確認
2. [OAUTH.md](OAUTH.md) の詳細手順を参照
3. [GitHub Issues](https://github.com/yohi/bitbucket-mcp/issues) で類似の問題を検索
4. 新規 Issue を作成する際は、以下を含めてください：
   - 実行環境（OS、Python バージョン）
   - エラーメッセージの全文
   - 環境変数の設定状況（機密情報はマスク）
   - 再現手順
