# Bitbucket MCP Server — 設計ドキュメント

- **Date**: 2026-07-03
- **Status**: Approved (design phase)
- **Repository**: `git@github.com:yohi/bitbucket-mcp.git`
- **Reference**: GitHub MCP Server (`github/github-mcp-server`), Bitbucket Cloud REST API v2.0, MCP spec `2025-11-25`

---

## 1. 概要 / 目的

Bitbucket Cloud REST API 2.0 を Model Context Protocol (MCP) のツールとして公開するサーバー。LLM クライアント(Claude Desktop 等)から Bitbucket のリポジトリ・プルリクエスト・イシュー・パイプライン等を操作できるようにする。設計は公式 GitHub MCP server をリファレンスとしつつ、Bitbucket の概念(Workspace / Project / Pipelines / Snippets)に最適化する。

## 2. スコープ

- **対象**: Bitbucket **Cloud** REST API v2.0 のみ。
- **非対象**: Bitbucket Server / Data Center(API 系統が異なるため対象外)。
- **MVP(Phase1)**: `context`, `repos`, `pull_requests`, `issues`, `pipelines`, `users` の6ツールセット + 汎用 `bitbucket_api`。
- **将来(Phase2/3)**: `workspaces`, `snippets`, `admin`, `deployments`。

## 3. 技術スタック

| 項目 | 採用 |
|---|---|
| 言語 | Python 3.12+ |
| MCP SDK | 公式 `mcp` SDK 同梱の **FastMCP**(`from mcp.server.fastmcp import FastMCP`) |
| HTTP クライアント | `httpx`(非同期 `AsyncClient`) |
| データモデル/検証 | Pydantic v2 |
| パッケージ管理/配布 | `uv` / `uvx` |
| テスト | `pytest` + `pytest-httpx` |
| 型検査 | `basedpyright`(strict) |
| Lint / 整形 | `ruff` |

## 4. アーキテクチャ

責務ごとに小さく分離した層構成。各ツールセットは統一インターフェース `register(mcp, client, *, read_only)` のみを通じて疎結合に連携する(GitHub MCP server の inventory パターンを簡素化して踏襲)。

```
bitbucket-mcp/
├── pyproject.toml
├── README.md
├── src/bitbucket_mcp/
│   ├── __init__.py
│   ├── __main__.py             # python -m bitbucket_mcp / uvx エントリポイント
│   ├── server.py               # FastMCP 生成・toolset 登録・トランスポート選択
│   ├── config.py               # 環境変数設定 (Pydantic BaseSettings)
│   ├── auth.py                 # 認証戦略 → Authorization ヘッダ生成
│   ├── client.py               # BitbucketClient: httpx ラッパ(request / paginate / エラー変換)
│   ├── errors.py               # Bitbucket エラー JSON → MCP ToolError 変換
│   ├── pagination.py           # page / pagelen ヘルパ
│   ├── models/                 # Pydantic モデル(repository, pullrequest, issue, pipeline, user...)
│   │   └── __init__.py
│   └── toolsets/
│       ├── __init__.py         # レジストリ: toolset 名 → register 関数 / デフォルト集合
│       ├── context.py
│       ├── repos.py
│       ├── pull_requests.py
│       ├── issues.py
│       ├── pipelines.py
│       ├── users.py
│       ├── raw_api.py          # bitbucket_api エスケープハッチ
│       ├── workspaces.py       # Phase2
│       ├── snippets.py         # Phase3
│       ├── admin.py            # Phase3
│       └── deployments.py      # Phase3
└── tests/
    ├── conftest.py
    ├── fixtures/               # 実 API の JSON 形状サンプル
    └── toolsets/
        └── test_*.py
```

**境界の定義:**

- `client.py` — HTTP・認証・ページングのみを知る。Bitbucket のドメイン概念には依存しない。
- `toolsets/*.py` — 自分のツールを FastMCP に登録するだけの単位。`BitbucketClient` を介してのみ通信する。
- `config.py` / `auth.py` — 設定と認証を単独で完結。
- `models/` — Bitbucket リソースおよびツール入出力の Pydantic 型。

## 5. 認証

stdio トランスポートでは **環境変数によるトークン注入** を基本とする(MCP 仕様に準拠)。

**方式(自動判定・優先順):**

1. `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` があれば → **Basic 認証**(`Authorization: Basic base64(email:api_token)`)
2. なければ `BITBUCKET_TOKEN`(Repository/Project/Workspace Access Token または OAuth 2.0 Bearer)→ **Bearer 認証**(`Authorization: Bearer <token>`)
3. どちらも無ければ起動時に明確なエラーを出す。

**App Password は非対応**とする(2026-07-28 に完全廃止のため)。起動時に「App Password は廃止済み。API Token または Access Token を使用せよ」と案内する。

**HTTP トランスポート採用時の OAuth 2.1**(MCP Authorization Framework, RFC 9728 / PKCE / RFC 8707)は **Phase2** で対応する。

## 6. 設定(環境変数)

| 変数 | 用途 | 既定値 |
|---|---|---|
| `BITBUCKET_TOKEN` | Access Token / OAuth Bearer トークン | (なし) |
| `BITBUCKET_EMAIL` | Atlassian アカウントのメール(Basic 認証用) | (なし) |
| `BITBUCKET_API_TOKEN` | Atlassian API Token(Basic 認証用、`EMAIL` とペア) | (なし) |
| `BITBUCKET_DEFAULT_WORKSPACE` | ツール引数で workspace を省略した場合の既定 | (なし) |
| `BITBUCKET_TOOLSETS` | 有効化する toolset のカンマ区切り | `context,repos,pull_requests,issues,pipelines,users` |
| `BITBUCKET_READ_ONLY` | `true` で書き込みツールを一括除外 | `false` |
| `BITBUCKET_BASE_URL` | API ベース URL | `https://api.bitbucket.org/2.0` |

**CLI/トランスポート:** `--transport {stdio,http}`(既定 `stdio`)、HTTP 時 `--host` / `--port`。

`bitbucket_api`(汎用ツール)は `BITBUCKET_TOOLSETS` の指定に関わらず常時登録する(明示除外を除く)。

## 7. トランスポート

- **MVP**: `stdio`(ローカル・単一クライアント。Claude Desktop 等の標準導線)。
- **Phase2**: `Streamable HTTP`(リモート・複数クライアント)。旧 HTTP+SSE は非推奨のため採用しない。
- MCP プロトコルリビジョンは `2025-11-25` を宣言。HTTP 時は `MCP-Protocol-Version` ヘッダ、`Origin` 検証、`localhost` バインドを実施。

## 8. ツールセット & ツール仕様

**設計原則:**

- **read は統合型**: `action` 引数で詳細/コメント/diff 等を分岐(ツール数を抑え LLM に優しい)。
- **write は操作別に分割**: 各書き込みを独立ツールにし、破壊的操作を明確化。
- 各ツールに MCP **annotations** を付与: `readOnlyHint`(read)、`destructiveHint`(delete/merge 等)、`idempotentHint`、外部 API アクセスに `openWorldHint`。
- `BITBUCKET_READ_ONLY=true` のとき、`readOnlyHint=false` のツールを登録しない。
- repo スコープの全ツールは `workspace` + `repo_slug` を取り、`BITBUCKET_DEFAULT_WORKSPACE` で `workspace` 省略可。
- 返却は `content[]`(人間可読サマリ)+ `structuredContent`(整形 JSON)。主要 read ツールは `outputSchema` を定義。

凡例: **R** = readOnly / **W** = write / **💥** = destructive

### 8.1 `context`(デフォルト有効)

| ツール | 種別 | エンドポイント | 主な引数 |
|---|---|---|---|
| `get_current_user` | R | `GET /user` | (なし) |
| `list_workspaces` | R | `GET /workspaces` | `role?`, `q?`, `sort?`, `page?`, `pagelen?` |

### 8.2 `repos`(デフォルト有効)

| ツール | 種別 | エンドポイント | 主な引数 |
|---|---|---|---|
| `list_repositories` | R | `GET /repositories/{workspace}` | `workspace`, `q?`, `sort?`, `role?`, `page?`, `pagelen?` |
| `get_repository` | R | `GET /repositories/{ws}/{repo}` | `workspace`, `repo_slug` |
| `get_file_or_directory` | R | `GET /repositories/{ws}/{repo}/src/{commit}/{path}` | `workspace`, `repo_slug`, `commit`, `path`, `page?` |
| `list_commits` | R | `GET /repositories/{ws}/{repo}/commits` | `workspace`, `repo_slug`, `revision?`, `path?`, `page?` |
| `get_commit` | R | `GET /repositories/{ws}/{repo}/commit/{sha}` | `workspace`, `repo_slug`, `commit` |
| `get_diff` | R | `GET .../diff|diffstat|patch/{spec}` | `workspace`, `repo_slug`, `spec`, `action=diff\|diffstat\|patch` |
| `list_branches` | R | `GET .../refs/branches` | `workspace`, `repo_slug`, `q?`, `sort?`, `page?` |
| `list_tags` | R | `GET .../refs/tags` | `workspace`, `repo_slug`, `q?`, `sort?`, `page?` |
| `create_repository` | W | `POST /repositories/{ws}/{repo}` | `workspace`, `repo_slug`, `is_private?`, `project_key?`, `scm?` |
| `delete_repository` | 💥 | `DELETE /repositories/{ws}/{repo}` | `workspace`, `repo_slug` |
| `fork_repository` | W | `POST .../forks` | `workspace`, `repo_slug`, `target_workspace?`, `name?` |
| `create_commit` | W | `POST .../src` | `workspace`, `repo_slug`, `message`, `branch?`, `files{path:content}` |
| `create_branch` | W | `POST .../refs/branches` | `workspace`, `repo_slug`, `name`, `target` |
| `delete_branch` | 💥 | `DELETE .../refs/branches/{name}` | `workspace`, `repo_slug`, `name` |
| `create_tag` | W | `POST .../refs/tags` | `workspace`, `repo_slug`, `name`, `target` |

### 8.3 `pull_requests`(デフォルト有効)

| ツール | 種別 | エンドポイント | 主な引数 |
|---|---|---|---|
| `list_pull_requests` | R | `GET .../pullrequests` | `workspace`, `repo_slug`, `state?`, `q?`, `sort?`, `page?` |
| `get_pull_request` | R | `GET .../pullrequests/{id}[/...]` | `workspace`, `repo_slug`, `pull_request_id`, `action=details\|diff\|diffstat\|patch\|commits\|activity\|statuses\|comments` |
| `create_pull_request` | W | `POST .../pullrequests` | `workspace`, `repo_slug`, `title`, `source_branch`, `destination_branch?`, `description?`, `reviewers?`, `close_source_branch?` |
| `update_pull_request` | W | `PUT .../pullrequests/{id}` | `workspace`, `repo_slug`, `pull_request_id`, `title?`, `description?`, `destination_branch?` |
| `merge_pull_request` | 💥 | `POST .../pullrequests/{id}/merge` | `workspace`, `repo_slug`, `pull_request_id`, `merge_strategy?`, `message?`, `close_source_branch?` |
| `decline_pull_request` | W | `POST .../pullrequests/{id}/decline` | `workspace`, `repo_slug`, `pull_request_id` |
| `review_pull_request` | W | `POST/DELETE .../approve` `POST/DELETE .../request-changes` | `workspace`, `repo_slug`, `pull_request_id`, `action=approve\|unapprove\|request_changes\|unrequest_changes` |
| `add_pull_request_comment` | W | `POST .../pullrequests/{id}/comments` | `workspace`, `repo_slug`, `pull_request_id`, `content`, `inline?{path,to}` |

### 8.4 `issues`(デフォルト有効)

| ツール | 種別 | エンドポイント | 主な引数 |
|---|---|---|---|
| `list_issues` | R | `GET .../issues` | `workspace`, `repo_slug`, `q?`, `sort?`, `page?` |
| `get_issue` | R | `GET .../issues/{id}[/...]` | `workspace`, `repo_slug`, `issue_id`, `action=details\|comments\|changes` |
| `create_issue` | W | `POST .../issues` | `workspace`, `repo_slug`, `title`, `content?`, `kind?`, `priority?`, `assignee?` |
| `update_issue` | W | `PUT .../issues/{id}` | `workspace`, `repo_slug`, `issue_id`, `title?`, `state?`, `kind?`, `priority?`, `assignee?` |
| `delete_issue` | 💥 | `DELETE .../issues/{id}` | `workspace`, `repo_slug`, `issue_id` |
| `add_issue_comment` | W | `POST .../issues/{id}/comments` | `workspace`, `repo_slug`, `issue_id`, `content` |

### 8.5 `pipelines`(デフォルト有効)

| ツール | 種別 | エンドポイント | 主な引数 |
|---|---|---|---|
| `list_pipelines` | R | `GET .../pipelines` | `workspace`, `repo_slug`, `sort?`, `page?` |
| `get_pipeline` | R | `GET .../pipelines/{uuid}[/...]` | `workspace`, `repo_slug`, `pipeline_uuid`, `action=details\|steps\|step_log`, `step_uuid?` |
| `run_pipeline` | W | `POST .../pipelines` | `workspace`, `repo_slug`, `target{ref_type,ref_name,selector?}`, `variables?` |
| `stop_pipeline` | W | `POST .../pipelines/{uuid}/stopPipeline` | `workspace`, `repo_slug`, `pipeline_uuid` |

### 8.6 `users`(デフォルト有効)

| ツール | 種別 | エンドポイント | 主な引数 |
|---|---|---|---|
| `get_user` | R | `GET /users/{selected_user}` | `selected_user`(account_id / UUID) |

### 8.7 `bitbucket_api`(常時)

| ツール | 種別 | 説明 |
|---|---|---|
| `bitbucket_api` | openWorld | 任意の Bitbucket REST 呼び出し。引数 `method`(GET/POST/PUT/DELETE)、`path`(`/2.0` からの相対)、`query?`(オブジェクト)、`body?`(オブジェクト)。**`BITBUCKET_READ_ONLY=true` の場合は GET/HEAD のみ許可**し、その他は ToolError。未実装エンドポイントの網羅用エスケープハッチ。 |

### 8.8 Phase2/3(参考)

- **`workspaces`**(P2): `get_workspace`, `list_workspace_members`, `list_projects`, `get_project`, `create/update/delete_project`。
- **`snippets`**(P3): スニペット CRUD・コメント。
- **`admin`**(P3): webhooks / branch-restrictions / default-reviewers の CRUD。
- **`deployments`**(P3): デプロイ・環境の参照。

## 9. 共通データフロー & ページネーション & 構造化返却

**フロー:** `tools/call` → FastMCP が型ヒント由来の `inputSchema` で引数検証 → ツール関数が `BitbucketClient.request()` を呼ぶ → `httpx` 送信(認証ヘッダ注入)→ JSON 受信 → Pydantic で受け(必要に応じ) → `content[]`(簡潔サマリ)+ `structuredContent`(整形 JSON)を返却。

**ページネーション:** 一覧ツールは `page`(既定 1)/ `pagelen`(既定 25・最大 100)を受け取り、Bitbucket の応答封筒(`values` / `page` / `size` / `next` / `previous`)を `structuredContent` にそのまま反映する。クライアントは `next` の有無で継続を判断できる。

## 10. エラー処理 & レート制限

- Bitbucket のエラー JSON(`{type, error:{message, detail, id, fields}}`)を **MCP ToolError(`isError=true`)** に変換し、`Bitbucket API {status}: {message} — {detail}` 形式のメッセージを返す。
- HTTP ステータス対応: `401` 認証失敗 / `403` スコープ不足(必要スコープを提示) / `404` 未検出 / `409` 競合(マージ衝突等) / `429` レート超過。
- レート制限: `X-RateLimit-*` ヘッダを解釈。`429` 時は `X-RateLimit-Reset` を基に retry ヒントを返す。`429` / `5xx` は指数バックオフで小数回の内部リトライ(設定可能)。
- 引数不正は Pydantic 検証で捕捉し、JSON-RPC の invalid params として返す。

## 11. テスト & 品質

- **TDD 前提**: 実装前に失敗するテストを書く。
- `pytest` + `pytest-httpx` で Bitbucket API をモックし、各ツールごとに **(1) 入力→リクエスト組立、(2) レスポンス→`structuredContent` 変換、(3) エラー変換** を検証。
- `tests/fixtures/` に実 API の JSON 形状サンプルを保持。
- 型検査 `basedpyright`(strict)、Lint/整形 `ruff` をパスすること。
- 実ワークスペースへの疎通確認は `BITBUCKET_TEST_LIVE=1` でゲートした任意スモークテスト。

## 12. MVP スコープと段階

| フェーズ | 内容 |
|---|---|
| **Phase1(MVP)** | stdio / 環境変数認証(Basic・Bearer)/ toolset ゲーティング + read-only / 🟢6ツールセット(`context`,`repos`,`pull_requests`,`issues`,`pipelines`,`users`)+ `bitbucket_api` / フルテスト / uvx 配布 |
| **Phase2** | `workspaces` / Streamable HTTP / OAuth 2.1 / pipeline 変数 |
| **Phase3** | `snippets` / `admin`(webhooks・branch-restrictions・default-reviewers)/ `deployments` |

## 13. リファレンス(確定事実)

**MCP 仕様(`2025-11-25`):**
- トランスポート: `stdio` / `Streamable HTTP`(旧 HTTP+SSE は非推奨)。
- ツール定義: `name` / `title` / `description` / `inputSchema` / `outputSchema` / `annotations`(`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`)。
- 結果: `content[]` + `isError` + `structuredContent`。MCP プロトコルの一覧メソッド(`tools/list` 等)はカーソル方式(`nextCursor`)。ツール結果内のデータ一覧は Bitbucket ネイティブのページング(§9)を `structuredContent` で返す。
- 認証: HTTP は OAuth 2.1(RFC 9728 / PKCE / RFC 8707)、stdio は環境変数。

**Bitbucket Cloud REST API:**
- ベース URL: `https://api.bitbucket.org/2.0`(2026-05-04 以降 OAuth は `api.bitbucket.org` 必須)。
- 認証: API Token(Basic, email+token)/ Access Token(Bearer, repo/project/workspace)/ OAuth 2.0(Bearer)。
- **App Password 廃止**: 2025-09-09 新規作成停止 → 2026-06-09 ブラウンアウト → **2026-07-28 完全廃止**。
- ページング: `values` / `page` / `pagelen`(最大100) / `size` / `next` / `previous`。
- フィルタ: BBQL(`q`, `sort`, `fields`)。
- レート制限: 認証済 60,000/時(100/分)、`X-RateLimit-*` ヘッダ、超過は `429`。
- エラー: `{type:"error", error:{message, detail, id, fields}}`。
- OpenAPI 仕様: `https://dac-static.atlassian.com/cloud/bitbucket/swagger.v3.json`(型自動生成に活用可能)。

**主要ドキュメント URL:**
- Bitbucket REST intro / 認証: `https://developer.atlassian.com/cloud/bitbucket/rest/intro/`
- MCP 仕様: `https://modelcontextprotocol.io/specification/2025-11-25/`
- GitHub MCP server: `https://github.com/github/github-mcp-server`
