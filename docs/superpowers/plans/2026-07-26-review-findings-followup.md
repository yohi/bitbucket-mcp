# レビュー指摘対応 実装計画

> **Goal:** 先に評価したレビュー指摘のうち、妥当と判断した項目を最小限の変更で対応し、テスト・型チェック・Lint を全て通過させる。

## Global Constraints

- Python 3.12+
- 型チェック: `uv run basedpyright` (strict mode)
- Linter/Formatter: `uv run ruff check .` / `uv run ruff format .`
- テスト: `uv run pytest`
- 日本語のコミットメッセージ（Conventional Commits）
- 絶対パスをコミットしない

---

## Task 1: ドキュメント表現の修正

**Files:**
- Modify: `docs/TROUBLESHOOTING.md:46`

**内容:**
- refresh_token の失効表現を「3ヶ月経過」から「3ヶ月間未使用または無効化」に変更。

---

## Task 2: 手動 OAuth モードの state 入力を可視化

**Files:**
- Modify: `src/bitbucket_mcp/__main__.py:110-111`

**内容:**
- `getpass.getpass("state: ")` を `input("state: ")` に変更。
- `authorization code` は `getpass` のままにする。
- `.strip()` や state 検証は維持。

---

## Task 3: `request_repo_json` / `request_repo_text` の suffix 内波括弧対応

**Files:**
- Modify: `src/bitbucket_mcp/toolsets/_common.py:193-232`
- Modify: `src/bitbucket_mcp/toolsets/repos.py:85-88`（動作確認・テストは維持）
- Modify: `tests/toolsets/test_common.py`（回帰テスト追加）

**内容:**
- `request_repo_json` / `request_repo_text` 内で、ベースパス `/repositories/{ws}/{repo_slug}` を先に `.format()` 解決し、そこに `suffix` を文字列連結する。
- これにより suffix 内の `{`/`}` が最終的な `.format()` で解釈されるのを防ぐ。
- `repos.py` の `get_file_or_directory` は `suffix = f"/src/{commit}/{path}"` のまま、path に波括弧が含まれても正しく動作するようになる。
- 回帰テストを追加：suffix に波括弧を含む場合でも正しいパスが生成されることを確認。

---

## Task 4: `require_auth` の未認証ブランチを `ToolError` 化

**Files:**
- Modify: `src/bitbucket_mcp/toolsets/_common.py:117-142`
- Modify: `tests/toolsets/test_common.py`（テスト修正）

**内容:**
- 未認証時の `return "..."` を `raise ToolError("...")` に変更。
- `started` / 処理中 の区別をメッセージで維持。
- 既存の認証チェック・メッセージは維持。
- テストを修正：文字列を返すことを期待していた箇所を `pytest.raises(ToolError)` に変更。

---

## Task 5: `wrap_tool` の登録時例外を `ToolError` から `AuthConfigError` に

**Files:**
- Modify: `src/bitbucket_mcp/toolsets/_common.py:156-159`
- 必要に応じて `src/bitbucket_mcp/auth.py` の import を確認

**内容:**
- `auth_provider is None` の分岐で `raise ToolError(...)` を `raise AuthConfigError(...)` に変更。
- メッセージは維持。
- `make_lifespan` や `__main__.py` の既存エラーハンドリングと整合。

---

## Task 6: `issues.py` の `register_tools` 呼び出し統合

**Files:**
- Modify: `src/bitbucket_mcp/toolsets/issues.py:77-79` およびその後の呼び出し

**内容:**
- `read` 用 `register_tools` と `write`/`destructive` 用 `register_tools` を1回に統合。
- 各ツールの分類（read/write/destructive）は維持。

---

## Task 7: `pipelines.py` の URL 構築を `request_repo_json` / `request_repo_text` に統一

**Files:**
- Modify: `src/bitbucket_mcp/toolsets/pipelines.py:57-122`

**内容:**
- `ctx.resolve_workspace` + 手組み `client.request` を `request_repo_json` / `request_repo_text` の部分適用に置き換え。
- `list_pipelines` → suffix `/pipelines/`（末尾スラッシュ維持）
- `get_pipeline` → suffix `/pipelines/{pipeline_uuid}` 等、path_params で `pipeline_uuid` を渡す。
- `run_pipeline` → suffix `/pipelines/`（POST）
- `stop_pipeline` → suffix `/pipelines/{pipeline_uuid}/stopPipeline`
- クエリ・ページングの挙動は変更しない。

---

## Task 8: `tests/test_server.py` の不要な `pass` 削除

**Files:**
- Modify: `tests/test_server.py:110-113`

**内容:**
- `FakeProvider.aclose` 内の `pass` は維持。
- クラスレベルの後続 `pass` を削除。

---

## Task 9: `tests/toolsets/test_context.py` に未認証ケース追加

**Files:**
- Modify: `tests/toolsets/test_context.py:23-33`

**内容:**
- 既存の `test_authenticated_require_auth_tool_is_registered_and_callable` に、未認証の `AuthProvider` を注入して `get_current_user` を呼び出すケースを追加または同テストに統合。
- `ToolError` または自動ログイン開始メッセージをアサート。
- `require_auth` ラッパーが削除された場合にテストが失敗するようになる。

---

## 検証フロー

各タスク後に以下を実行：

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
uv run basedpyright
```

全タスク完了後に最終検証として同コマンドを実行し、全てクリアすることを確認。

---

## コミット方針

- 各タスクを原子論的にコミット。
- コミットメッセージは日本語で Conventional Commits 形式。
- 例: `docs: refresh_token の失効表現を修正`, `fix: 手動 OAuth モードで state 入力を可視化`, `fix: request_repo_json の suffix 内波括弧を安全に連結`, など。
