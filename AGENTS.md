# Bitbucket MCP Server — Agent Instructions (AGENTS.md)

This file contains crucial onboarding context for AI coding agents. Follow these guidelines for all tasks.

---

## 1. WHY (Purpose)
This project is an MCP (Model Context Protocol) server that exposes the Bitbucket Cloud REST API v2.0 as tools. It enables LLM clients (such as Claude Desktop) to inspect and manage Bitbucket repositories, pull requests, issues, and pipelines.

---

## 2. WHAT (Tech Stack & Structure)
- **Language**: Python 3.12+
- **MCP Framework**: FastMCP (`mcp.server.fastmcp`)
- **HTTP Client**: `httpx` (Asynchronous AsyncClient)
- **Data validation**: `Pydantic v2` + `pydantic-settings`
- **Structure**:
  - `src/bitbucket_mcp/` — Core codebase (split into `config.py`, `auth.py`, `client.py`, `errors.py`, and `toolsets/` registry).
  - `tests/` — Test suite mapped to the implementation.

---

## 3. HOW (Development Workflows)

### Dependency Management & Tooling
- We use **`uv`** as the package manager.
- Formatting and linting: **`ruff`**
- Strict type checking: **`basedpyright`** (strict mode)

### Common Commands
Run these commands locally via `uv` to verify changes:
```bash
# Sync dependencies
uv sync

# Run the test suite (always run before claiming success)
uv run pytest

# Check code styles and formatting
uv run ruff check .
uv run ruff format .

# Check types
uv run basedpyright
```

---

## 4. Progressive Disclosure (References)

To keep this file lightweight and avoid context bloat, read the following specialized documents when working on tasks:

- **API & Tool Specifications**: For details about specific tool parameters, error formatting, retry limits, and MCP annotations, see [SPEC.md](file:///home/y_ohi/program/bitbucket-mcp/SPEC.md).
- **Setup & CLI Usage**: For environment variables, transport configurations (`stdio`/`http`), and Claude Desktop config examples, see [README.md](file:///home/y_ohi/program/bitbucket-mcp/README.md).
