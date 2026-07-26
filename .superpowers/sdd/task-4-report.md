# Task 4 実装レポート

## 実装内容

- `BitbucketClient` のコンストラクタを固定 `auth_header` から `AuthProvider` 受け取りへ変更。
- リクエストごとに `authorization_header()` を呼び出して Authorization ヘッダを注入。
- 401 応答時に `auth_provider.refresh()` を一度だけ実行し、更新後のヘッダでリトライ。
- refresh 後も 401 の場合は再ログイン案内の `ToolError` を送出。
- ヘッダ取得または refresh で `NotAuthenticatedError` が発生した場合、再ログイン案内の `ToolError` に変換。
- 既存の 429/5xx および接続エラーの GET/HEAD リトライ動作を維持。
- サーバーのライフサイクルとテスト共通 fixture も新しい `AuthProvider` API に移行。

## TDD・テスト結果

1. 先に既存テストを `StaticAuthProvider` 対応へ変更し、401 refresh、refresh 後の 401、未認証の 3 ケースを追加。
2. RED を確認: 実装前は `BitbucketClient.__init__()` が `auth_provider` を受け付けず、12 テストが失敗。
3. 最小実装後、循環 import と fixture の旧 API 使用を修正。
4. GREEN を確認: `uv run pytest` が 149 passed。

検証コマンド結果:

- `uv run pytest`: 149 passed
- `uv run basedpyright src/bitbucket_mcp/client.py src/bitbucket_mcp/server.py`: 0 errors, 0 warnings, 0 notes
- `uv run ruff check src/bitbucket_mcp/client.py src/bitbucket_mcp/server.py tests/test_client.py tests/conftest.py`: All checks passed
- `uv run ruff format --check src/bitbucket_mcp/client.py src/bitbucket_mcp/server.py tests/test_client.py tests/conftest.py`: 4 files already formatted

## 変更ファイル

- `src/bitbucket_mcp/client.py`
- `src/bitbucket_mcp/server.py`
- `tests/test_client.py`
- `tests/conftest.py`

## セルフレビュー

- 認証ヘッダは AsyncClient の共有デフォルトではなく各リクエストへ渡すため、refresh 後の新しいトークンが確実に使用される。
- 401 の refresh は `refreshed` フラグで一度に制限される。
- 429/5xx の既存 retry counter と GET/HEAD 制限は変更していない。
- `auth.py` との既存循環 import を避けるため、`AuthProvider` は型チェック時のみ、`NotAuthenticatedError` はメソッド内で遅延 import している。
- 未追跡の `docs/superpowers/` は既存変更のため、コミット対象から除外する。

## 懸念事項

- Task brief の対象ファイル外でしたが、新 API を実際に利用する `server.py` と共通テスト fixture の更新が必要でした。これらを更新しない場合、サーバー起動テストおよび toolset テストが失敗します。
