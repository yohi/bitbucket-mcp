# 開発者ガイド

Bitbucket MCP Server の開発・テスト・デバッグに必要な情報をまとめます。

---

## 前提条件

- **Python 3.12+**（`pyproject.toml` の `requires-python` 準拠）
- **uv**（パッケージマネージャ）
  ```bash
  # インストール例
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

---

## 環境構築

```bash
# 1. リポジトリをクローン
git clone https://github.com/yohi/bitbucket-mcp.git
cd bitbucket-mcp

# 2. 依存関係をインストール（仮想環境自動作成）
uv sync

# 3. 仮想環境が有効になっていることを確認
uv run python --version  # => Python 3.12.x
```

### 開発用依存関係

`uv sync` 時に以下が自動インストールされます：

| ツール | 用途 |
|---|---|
| `pytest` + `pytest-asyncio` + `pytest-httpx` | テスト実行 |
| `ruff` | Lint + Format |
| `basedpyright` | 厳格な型チェック |

---

## テスト実行

### 全テスト

```bash
uv run pytest
```

### 特定ファイル・ディレクトリ

```bash
uv run pytest tests/test_auth.py
uv run pytest tests/toolsets/
uv run pytest -k "test_auth"  # キーワードフィルタ
```

### ライブ疎通テスト（実 API に接続）

```bash
# 1. 環境変数を設定
export BITBUCKET_TEST_LIVE=1
export BITBUCKET_TOKEN="your-token"  # または Basic 認証用の EMAIL + API_TOKEN

# 2. ライブテストを実行
uv run pytest -m live  # ※ live マーカーが設定されている場合
```

> ⚠️ ライブテストは実際の Bitbucket Cloud にリクエストを送信します。書き込み系テストは実行環境に注意してください。

---

## コード品質チェック

### 一括チェック（推奨）

```bash
# lint + format check + type check + test
uv run ruff check . && uv run basedpyright && uv run pytest
```

### 個別実行

#### Lint + Format

```bash
# チェックのみ
uv run ruff check .

# 自動修正適用
uv run ruff check . --fix

# フォーマット実行
uv run ruff format .
```

#### 型チェック

```bash
uv run basedpyright
```

#### インポートソート

```bash
uv run ruff check . --select I --fix
```

---

## デバッグ方法

### MCP サーバーのログ確認

```bash
# stdio モードで起動し、標準エラー出力を確認
uv run python -m bitbucket_mcp 2>&1 | tee mcp.log
```

### Claude Desktop 連携時のデバッグ

Claude Desktop の設定に `log_level` を追加します：

```json
{
  "mcpServers": {
    "bitbucket": {
      "command": "uvx",
      "args": ["bitbucket-mcp"],
      "env": {
        "BITBUCKET_TOKEN": "your-token",
        "BITBUCKET_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

Claude Desktop のログは通常以下に出力されます：
- macOS: `~/Library/Logs/Claude/mcp.log`
- Windows: `%APPDATA%\Claude\logs\mcp.log`

### ツール実行のトレース

`client.py` のリクエスト/レスポンスを確認するには、環境変数 `HTTPX_LOG_LEVEL=debug` を設定します。

### pytest でのデバッグ

```bash
# 詳細出力
uv run pytest -v -s

# 特定テストを詳細モードで
uv run pytest tests/test_client.py::test_request_retry -v -s

# pdb によるブレークポイントデバッグ
uv run pytest tests/test_client.py -x --pdb
```

---

## パッケージビルド

```bash
# wheel / sdist を dist/ に生成
uv build

# ローカルインストールテスト
uvx --from ./dist/bitbucket_mcp-*.whl bitbucket-mcp --help
```

---

## プロジェクト構造

```
bitbucket-mcp/
├── src/bitbucket_mcp/       # コアコード
│   ├── config.py            # 環境変数・設定
│   ├── auth.py              # 認証プロバイダ抽象
│   ├── client.py            # HTTP クライアント
│   ├── oauth.py             # OAuth フロー
│   ├── credentials.py       # トークン保存
│   ├── errors.py            # エラー変換
│   ├── pagination.py        # ページネーション
│   ├── server.py            # MCP サーバー起動
│   ├── __main__.py          # CLI エントリポイント
│   └── toolsets/            # ツールセットモジュール
│       ├── _common.py       # 共通ヘルパー
│       ├── repos.py
│       ├── pull_requests.py
│       ├── issues.py
│       ├── pipelines.py
│       ├── context.py
│       ├── users.py
│       └── raw_api.py
├── tests/                   # テスト
├── docs/                    # ドキュメント
├── pyproject.toml           # プロジェクト設定
└── sonar-project.properties # SonarCloud 設定
```

---

## コントリビューション時のチェックリスト

PR を作成する前に以下を確認してください：

- [ ] `uv run ruff check .` がパスする
- [ ] `uv run basedpyright` がエラーを出さない
- [ ] `uv run pytest` が全て通過する
- [ ] 変更に対応するテストが追加されている（TDD 推奨）
- [ ] `README.md` / `SPEC.md` に影響がある場合は更新している

---

## 参考リンク

- [SPEC.md](../SPEC.md) — 技術仕様の詳細
- [OAUTH.md](OAUTH.md) — OAuth 認証の利用手順
- [ARCHITECTURE.md](ARCHITECTURE.md) — システムアーキテクチャ
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — よくある問題と解決策
