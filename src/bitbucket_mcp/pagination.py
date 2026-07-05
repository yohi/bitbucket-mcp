"""Bitbucket の page / pagelen パラメータヘルパ。"""

DEFAULT_PAGELEN = 25
MAX_PAGELEN = 100


def page_params(page: int | None = None, pagelen: int | None = None) -> dict[str, int]:
    """一覧系エンドポイント向けの query パラメータを組み立てる。"""
    params: dict[str, int] = {}
    if page is not None:
        params["page"] = page
    effective = DEFAULT_PAGELEN if pagelen is None else pagelen
    params["pagelen"] = min(max(effective, 1), MAX_PAGELEN)
    return params
