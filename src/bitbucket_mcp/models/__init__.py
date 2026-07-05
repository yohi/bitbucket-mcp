"""ツール入力用 Pydantic モデル。"""

from typing import Any

from pydantic import BaseModel


class InlineComment(BaseModel):
    """PR のインラインコメント位置。"""

    path: str
    to: int | None = None


class PipelineTarget(BaseModel):
    """パイプライン実行対象の参照。"""

    ref_type: str
    ref_name: str
    selector: dict[str, Any] | None = None
