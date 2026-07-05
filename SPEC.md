# Bitbucket MCP Server — 仕様書 (SPEC.md)

本ドキュメントは、Bitbucket Cloud REST API v2.0 を Model Context Protocol (MCP) のツールとして公開するサーバーの正式な仕様を定義します。

---

## 1. 概要 & 仕様対象

- **対象 API**: Bitbucket **Cloud** REST API v2.0 (Server / Data Center は非対象)
- **MCP プロトコルバージョン**: `2025-11-25`
- **ベース URL**: `https://api.bitbucket.org/2.0` (環境変数 `BITBUCKET_BASE_URL` で上書き可能)

---

## 2. アーキテクチャ & 境界の定義

本システムは責務ごとに分離された層構成を採用しています。

- **`config.py`** — `BITBUCKET_*` 環境変数の読み込みと Pydantic によるバリデーション。
- **`auth.py`** — 認証情報の解決とヘッダ生成。
- **`client.py`** — `BitbucketClient` (HTTP・認証ヘッダ注入・リトライのみを知る非同期 `httpx` クライアント)。
- **`errors.py`** — Bitbucket API のエラー JSON を MCP の `ToolError` に変換。
- **`pagination.py`** — `page`/`pagelen` のパラメータ管理およびクランプ。
- **`toolsets/`** — FastMCP へのツール登録を行う個別モジュール群。

---

## 3. 認証仕様

stdio トランスポートでは、環境変数によるトークンの注入を行います。

### 認証方式の解決優先順位:
1. `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` が設定されている場合:
   - **Basic 認証** (`Authorization: Basic base64(email:api_token)`) を使用。
2. `BITBUCKET_TOKEN` (Access Token / Bearer トークン) が設定されている場合:
   - **Bearer 認証** (`Authorization: Bearer <token>`) を使用。
3. どちらも設定されていない場合:
   - 起動時に `AuthConfigError` を送出してプロセスを終了。

> [!WARNING]
> **App Password は非対応です** (2026年7月28日に完全廃止されたため)。
> 起動時に検知した場合は「App Password は廃止済み。API Token または Access Token を使用せよ」というエラーを発生させます。

---

## 4. 環境変数

| 変数名 | 用途 | 既定値 |
|---|---|---|
| `BITBUCKET_TOKEN` | Access Token / OAuth Bearer トークン | (なし) |
| `BITBUCKET_EMAIL` | Atlassian アカウントのメールアドレス (Basic 認証用) | (なし) |
| `BITBUCKET_API_TOKEN` | Atlassian API Token (Basic 認証用、`EMAIL` とペア) | (なし) |
| `BITBUCKET_DEFAULT_WORKSPACE` | ツールの引数で `workspace` を省略した場合の既定値 | (なし) |
| `BITBUCKET_TOOLSETS` | 有効化するツールセットのカンマ区切りリスト | `context,repos,pull_requests,issues,pipelines,users` |
| `BITBUCKET_READ_ONLY` | `true` の場合、書き込み/破壊ツールを一括で除外登録する | `false` |
| `BITBUCKET_BASE_URL` | API ベース URL | `https://api.bitbucket.org/2.0` |

---

## 5. ツールセット & ツール仕様

### 共通パラメータと注記
- **R** = readOnly / **W** = write / **💥** = destructive
- 全てのツールで、`workspace` が未指定かつ `BITBUCKET_DEFAULT_WORKSPACE` も設定されていない場合は `ToolError` となります。
- `BITBUCKET_READ_ONLY=true` の際、`W` または `💥` のツールは FastMCP に登録されません。

### MCP Annotations ポリシー
各ツールの登録時には、MCP クライアントへのヒントとして以下のメタデータ（`ToolAnnotations`）を付与します。
- **参照系ツール (R)**: `readOnlyHint=True`, `openWorldHint=True`
- **書き込み系ツール (W)**: `openWorldHint=True`
- **破壊的操作を伴うツール (💥)**: `destructiveHint=True`, `openWorldHint=True`
- **汎用 API エスケープハッチ (`bitbucket_api`)**: `openWorldHint=True`

### ツール戻り値の統一仕様
- 全てのツール関数は、返り値を `dict[str, Any]` に統一します。
- `diff`, `patch`, パイプラインログなどのテキストデータは、生テキストではなく `{"content": <text>, "format": <fmt>}` または `{"content": <text>}` の形式にラッピングして返却します。

### 5.1 `context`
| ツール名 | 種別 | エンドポイント | 主な引数とバリデーション |
|---|---|---|---|
| `get_current_user` | R | `GET /user` | なし |
| `list_workspaces` | R | `GET /user/workspaces` | `administrator?` (bool), `q?` (string), `sort?` (string), `page?` (int), `pagelen?` (int)<br>* `administrator` と `q` の同時指定はエラー。 |

### 5.2 `repos`
| ツール名 | 種別 | エンドポイント | 主な引数 |
|---|---|---|---|
| `list_repositories` | R | `GET /repositories/{workspace}` | `workspace?`, `q?`, `sort?`, `role?`, `page?`, `pagelen?` |
| `get_repository` | R | `GET /repositories/{workspace}/{repo_slug}` | `workspace?`, `repo_slug` |
| `get_file_or_directory` | R | `GET /repositories/{ws}/{repo}/src/{commit}/{path}` | `workspace?`, `repo_slug`, `commit`, `path`, `page?` |
| `list_commits` | R | `GET /repositories/{ws}/{repo}/commits[/{revision}]` | `workspace?`, `repo_slug`, `revision?`, `path?`, `page?`, `pagelen?` |
| `get_commit` | R | `GET /repositories/{ws}/{repo}/commit/{commit}` | `workspace?`, `repo_slug`, `commit` |
| `get_diff` | R | `GET /repositories/{ws}/{repo}/(diff\|patch\|diffstat)/{spec}` | `workspace?`, `repo_slug`, `spec`, `action` (`diff`\|`diffstat`\|`patch` のいずれか) |
| `list_branches` | R | `GET /repositories/{ws}/{repo}/refs/branches` | `workspace?`, `repo_slug`, `q?`, `sort?`, `page?`, `pagelen?` |
| `list_tags` | R | `GET /repositories/{ws}/{repo}/refs/tags` | `workspace?`, `repo_slug`, `q?`, `sort?`, `page?`, `pagelen?` |
| `create_repository` | W | `POST /repositories/{workspace}/{repo_slug}` | `workspace?`, `repo_slug`, `is_private?` (bool, 既定 true), `project_key?`, `scm?` (既定 "git") |
| `delete_repository` | 💥 | `DELETE /repositories/{workspace}/{repo_slug}` | `workspace?`, `repo_slug` |
| `fork_repository` | W | `POST /repositories/{workspace}/{repo_slug}/forks` | `workspace?`, `repo_slug`, `target_workspace?`, `name?` |
| `create_commit` | W | `POST /repositories/{workspace}/{repo_slug}/src` | `workspace?`, `repo_slug`, `message`, `files` (dict[str, str]), `branch?`<br>* `files` のキーに `message`, `branch` は使用不可。 |
| `create_branch` | W | `POST /repositories/{workspace}/{repo_slug}/refs/branches` | `workspace?`, `repo_slug`, `name`, `target` (コミットハッシュ) |
| `delete_branch` | 💥 | `DELETE /repositories/{workspace}/{repo_slug}/refs/branches/{name}` | `workspace?`, `repo_slug`, `name` |
| `create_tag` | W | `POST /repositories/{workspace}/{repo_slug}/refs/tags` | `workspace?`, `repo_slug`, `name`, `target` (コミットハッシュ) |

### 5.3 `pull_requests`
| ツール名 | 種別 | エンドポイント | 主な引数 |
|---|---|---|---|
| `list_pull_requests` | R | `GET .../pullrequests` | `workspace?`, `repo_slug`, `state?` (`OPEN`\|`MERGED`\|`DECLINED`\|`SUPERSEDED`), `q?`, `sort?`, `page?`, `pagelen?` |
| `get_pull_request` | R | `GET .../pullrequests/{id}[/{action}]` | `workspace?`, `repo_slug`, `pull_request_id`, `action` (`details`\|`diff`\|`diffstat`\|`patch`\|`commits`\|`activity`\|`statuses`\|`comments` のいずれか) |
| `create_pull_request` | W | `POST .../pullrequests` | `workspace?`, `repo_slug`, `title`, `source_branch`, `destination_branch?`, `description?`, `reviewers?` (list[str]), `close_source_branch?` |
| `update_pull_request` | W | `PUT .../pullrequests/{id}` | `workspace?`, `repo_slug`, `pull_request_id`, `title?`, `description?`, `destination_branch?` |
| `merge_pull_request` | 💥 | `POST .../pullrequests/{id}/merge` | `workspace?`, `repo_slug`, `pull_request_id`, `merge_strategy?`, `message?`, `close_source_branch?` |
| `decline_pull_request` | W | `POST .../pullrequests/{id}/decline` | `workspace?`, `repo_slug`, `pull_request_id` |
| `review_pull_request` | W | `POST/DELETE .../approve` または `.../request-changes` | `workspace?`, `repo_slug`, `pull_request_id`, `action` (`approve`\|`unapprove`\|`request_changes`\|`unrequest_changes`) |
| `add_pull_request_comment` | W | `POST .../pullrequests/{id}/comments` | `workspace?`, `repo_slug`, `pull_request_id`, `content`, `inline?` (`InlineComment` モデル) |

### 5.4 `issues`
| ツール名 | 種別 | エンドポイント | 主な引数 |
|---|---|---|---|
| `list_issues` | R | `GET .../issues` | `workspace?`, `repo_slug`, `q?`, `sort?`, `page?`, `pagelen?` |
| `get_issue` | R | `GET .../issues/{id}[/{action}]` | `workspace?`, `repo_slug`, `issue_id`, `action` (`details`\|`comments`\|`changes` のいずれか) |
| `create_issue` | W | `POST .../issues` | `workspace?`, `repo_slug`, `title`, `content?`, `kind?`, `priority?`, `assignee?` |
| `update_issue` | W | `PUT .../issues/{id}` | `workspace?`, `repo_slug`, `issue_id`, `title?`, `state?`, `kind?`, `priority?`, `assignee?`<br>* 更新項目が1つもない場合はエラー。 |
| `delete_issue` | 💥 | `DELETE .../issues/{id}` | `workspace?`, `repo_slug`, `issue_id` |
| `add_issue_comment` | W | `POST .../issues/{id}/comments` | `workspace?`, `repo_slug`, `issue_id`, `content` |

### 5.5 `pipelines`
| ツール名 | 種別 | エンドポイント | 主な引数 |
|---|---|---|---|
| `list_pipelines` | R | `GET .../pipelines/` | `workspace?`, `repo_slug`, `sort?`, `page?`, `pagelen?` |
| `get_pipeline` | R | `GET .../pipelines/{uuid}[/steps[/{step_uuid}/log]]` | `workspace?`, `repo_slug`, `pipeline_uuid`, `action` (`details`\|`steps`\|`step_log`), `step_uuid?`, `page?`, `pagelen?`<br>* `step_log` 指定時は `step_uuid` が必須。 |
| `run_pipeline` | W | `POST .../pipelines/` | `workspace?`, `repo_slug`, `target` (`PipelineTarget` モデル), `variables?` (list[dict]) |
| `stop_pipeline` | W | `POST .../pipelines/{uuid}/stopPipeline` | `workspace?`, `repo_slug`, `pipeline_uuid` |

### 5.6 `users`
| ツール名 | 種別 | エンドポイント | 主な引数 |
|---|---|---|---|
| `get_user` | R | `GET /users/{selected_user}` | `selected_user` (account_id または UUID) |

### 5.7 `bitbucket_api` (常時登録)
任意のエンドポイントを直接叩くための汎用エスケープハッチです。
- **引数**: `method` (GET/POST/PUT/DELETE/PATCH/HEAD), `path` (相対パス), `query?` (dict), `body?` (dict)
- **リードオンリー制限**: `BITBUCKET_READ_ONLY=true` の場合は、`GET` / `HEAD` のみが許可され、その他は `ToolError` を返します。

---

## 6. 共通データフロー & ページネーション

### ページネーション仕様:
- 一覧系ツールは `page` (既定 1) および `pagelen` (既定 25, 最小 1, 最大 100) を受け取りクランプします。
- Bitbucket 応答封筒 (`values` / `page` / `size` / `next` / `previous`) を `structuredContent` にそのまま反映させます。これにより、クライアント側で `next` リンクの有無に基づいて継続取得を判断できます。

---

## 7. エラー処理 & リトライ制限

### リトライロジック:
- リトライ対象メソッドは **`GET` および `HEAD` のみ** とし、非べき等な `POST` や `PUT` などに対するリトライは行いません。
- `429`, `502`, `503`, `504` ステータスおよび `RequestError` 発生時に、指数バックオフ (`backoff_base * (2^attempt)`) に基づく最大2回のリトライを内部で実行します。

### エラー情報のフォーマット:
- API エラー発生時は、以下の形式で MCP `ToolError` に変換し返却します:
  `Bitbucket API {status_code}: {message} — {detail} [{hint}] (retry after {retry_after})`
- レート制限 (`429`) 時は `X-RateLimit-Reset` を解析して `retry after` 情報を付加します。

---

## 8. リファレンス情報

開発および仕様の詳細な根拠となる主要リソースへのリンクです。
- [Bitbucket Cloud REST API v2.0 Introduction](https://developer.atlassian.com/cloud/bitbucket/rest/intro/)
- [Model Context Protocol (MCP) Specification (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/)
- [GitHub MCP Server (Reference Implementation)](https://github.com/github/github-mcp-server)
- [Atlassian App Password Deprecation notice](https://developer.atlassian.com/cloud/bitbucket/rest/intro/)
