# Bitbucket MCP Server — Agent Instructions (AGENTS.md)

An MCP (Model Context Protocol) server exposing the Bitbucket Cloud REST API v2.0 as tools for LLM clients.

## 1. WHY

Enable LLM clients (e.g., Claude Desktop) to inspect and manage Bitbucket repositories, pull requests, issues, and pipelines via MCP tools.

## 2. WHAT

| Layer | File(s) | Responsibility |
|---|---|---|
| Config | `config.py` | `BITBUCKET_*` env vars, Pydantic v2 validation |
| Auth | `auth.py` | `AuthProvider` protocol, OAuth/Basic/Bearer resolution |
| HTTP Client | `client.py` | `httpx` wrapper, retry logic, 401 refresh |
| Errors | `errors.py` | Bitbucket API errors → MCP `ToolError` |
| Toolsets | `toolsets/*.py` | FastMCP tool registration per domain |
| Tests | `tests/` | `pytest` + `pytest-httpx` suite |

- **Language**: Python 3.12+
- **Package Manager**: `uv`
- **Linter/Formatter**: `ruff`
- **Type Checker**: `basedpyright` (strict mode)

## 3. HOW

Always verify changes before claiming success:

```bash
uv run pytest           # Run the test suite
uv run basedpyright     # Strict type check
uv run ruff check .     # Lint
```

Build and CLI smoke test:

```bash
uv build
uvx --from ./dist/*.whl bitbucket-mcp --help
```

## 4. Progressive Disclosure

Read these files when working on specific areas:

| Topic | File |
|---|---|
| API specs, tool parameters, retry logic, MCP annotations | [SPEC.md](./SPEC.md) |
| Environment variables, CLI usage, OAuth setup | [README.md](./README.md) |
| Development environment, testing conventions | [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) |
| Authentication flows, token lifecycle | [docs/OAUTH.md](./docs/OAUTH.md) |
| System architecture, request lifecycle | [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) |
| Common errors and troubleshooting | [docs/TROUBLESHOOTING.md](./docs/TROUBLESHOOTING.md) |

For code style, follow existing patterns in `src/bitbucket_mcp/`. **Do not add style guidelines to this file** — `ruff` and `basedpyright` enforce correctness.
