"""CVワーカー → サーバーの検出結果型(契約: docs/contracts/cv-interface.md)。

モックCV(mock.py)と実CV(S8)はいずれもこの型を出力する。
"""

from __future__ import annotations

from typing import Literal, Protocol, cast

from pydantic import BaseModel, Field, model_validator

BoxSize = Literal["large", "medium", "small"]
Area = Literal["A", "B", "C", "staging"]
ViolationType = Literal["size_order", "duplicate_size", "overflow"]

# tag_master.json の box ID(サイズ-個体番号)。TS写し(cv.ts の BoxId)と同じく9個に限定する
BoxId = Literal[
    "large-1",
    "large-2",
    "large-3",
    "medium-1",
    "medium-2",
    "medium-3",
    "small-1",
    "small-2",
    "small-3",
]

BOX_IDS: tuple[BoxId, ...] = (
    "large-1",
    "large-2",
    "large-3",
    "medium-1",
    "medium-2",
    "medium-3",
    "small-1",
    "small-2",
    "small-3",
)

BOX_SIZE_OF: dict[BoxId, BoxSize] = {
    box_id: cast(BoxSize, box_id.split("-")[0]) for box_id in BOX_IDS
}

# サイズ文字(board.md)との対応
SIZE_CHAR: dict[BoxSize, str] = {"large": "L", "medium": "M", "small": "S"}
BOX_EDGE_MM: dict[BoxSize, float] = {"large": 75.0, "medium": 50.0, "small": 30.0}


class BoxObservation(BaseModel):
    """1箱の観測(cv-interface.md §2)。"""

    box_id: BoxId
    size: BoxSize
    pos_mm: tuple[float, float, float]
    quat: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    area: Area | None
    level: int | None
    visible: bool
    seen_tag_ids: list[int] = Field(default_factory=list)


class CvFrame(BaseModel):
    """連続ストリーム(約30fps、3D表示用)。常に9箱すべてを含む。"""

    kind: Literal["frame"] = "frame"
    t_ms: int
    mat_corners_detected: int
    boxes: list[BoxObservation]


class Violation(BaseModel):
    tower: Literal["A", "B", "C"]
    type: ViolationType


class CvBoardUpdate(BaseModel):
    """確定盤面の変化イベント(cv-interface.md §3)。"""

    kind: Literal["board"] = "board"
    t_ms: int
    towers: tuple[str, str, str]
    board: str
    legal: bool
    violations: list[Violation] = Field(default_factory=list)
    staging_box_ids: list[BoxId] = Field(default_factory=list)
    # 塔ごとの箱の個体(下から上)。判定・重複判定には使わず記録表示専用(cv-interface.md §3)
    tower_box_ids: tuple[list[BoxId], list[BoxId], list[BoxId]]

    @model_validator(mode="after")
    def _validate_box_ids_match_towers(self) -> CvBoardUpdate:
        derived = tuple(
            "".join(SIZE_CHAR[BOX_SIZE_OF[b]] for b in ids) for ids in self.tower_box_ids
        )
        if derived != self.towers:
            raise ValueError(
                f"tower_box_ids {self.tower_box_ids} does not match towers {self.towers}"
            )
        # 1個の箱が複数の場所に同時に存在することはない(塔間・塔と待機の重複を弾く)
        placed = [b for ids in self.tower_box_ids for b in ids] + self.staging_box_ids
        if len(set(placed)) != len(placed):
            raise ValueError(f"box placed in more than one area: {placed}")
        return self


CvMessage = CvFrame | CvBoardUpdate


class CvSource(Protocol):
    """サーバーが購読するCVソース。モックと実CVを差し替え可能にする。"""

    def poll(self) -> list[CvMessage]:
        """未配信のメッセージを取り出す(なければ空リスト)。約30fpsで呼ばれる。"""
        ...
