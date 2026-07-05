"""Bitbucket のエラー JSON を MCP ToolError に変換する。"""

from typing import Any, cast

from mcp.server.fastmcp.exceptions import ToolError

_STATUS_HINTS: dict[int, str] = {
    401: "認証に失敗しました。トークンを確認してください。",
    403: "権限/スコープが不足しています。必要なスコープを付与してください。",
    404: "リソースが見つかりません。",
    409: "競合が発生しました (マージ衝突など)。",
    429: "レート制限を超過しました。しばらく待って再試行してください。",
}


def _valid_retry_after(retry_after: str | None) -> str | None:
    if retry_after is None:
        return None
    value = retry_after.strip()
    if not value or not value.isdigit():
        return None
    if int(value) <= 0:
        return None
    return value


def build_tool_error(
    status_code: int,
    payload: dict[str, Any] | None,
    *,
    retry_after: str | None = None,
) -> ToolError:
    """HTTP ステータスと Bitbucket エラー JSON から ToolError を構築する。"""
    message = ""
    detail = ""
    if payload:
        err = payload.get("error")
        if isinstance(err, dict):
            err_dict = cast(dict[str, Any], err)
            message = str(err_dict.get("message", ""))
            detail = str(err_dict.get("detail", ""))
    text = f"Bitbucket API {status_code}: {message or 'error'}"
    if detail:
        text += f" — {detail}"
    hint = _STATUS_HINTS.get(status_code)
    if hint:
        text += f" [{hint}]"
    valid_retry_after = _valid_retry_after(retry_after)
    if status_code == 429 and valid_retry_after:
        text += f" (retry after {valid_retry_after})"
    return ToolError(text)
