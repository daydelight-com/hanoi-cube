"""プレイ記録・ランキングのストア(インターフェースとメモリ実装)。

本番は SQLite 永続化(app/state/sqlite_store.py、S12)を使う。MemoryStore は
テスト・開発用に残す。クラウドアップロードキューは app/cloud/uploader.py。
順位は score 降順 → fail_count 昇順(同点時の第2キー、ルールブック§6)→ played_at 昇順。
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from app.api.messages import JudgeResultKind, RankingEntry
from app.cv.interface import BoxId


class JudgementRecord(BaseModel):
    """本番プレイの判定履歴1件(screens.md §4)。"""

    seq: int
    board: str
    elapsed_ms: int
    result: JudgeResultKind
    points: int
    min_moves: int | None
    dup_of_seq: int | None = None
    # 判定時に塔にあった箱の個体(下から上)。記録画面の表示専用で、判定・重複判定には使わない
    # (firestore.md §1)。同サイズの入れ替えを見分けるために必要
    tower_box_ids: tuple[list[BoxId], list[BoxId], list[BoxId]]


class PlayRecord(BaseModel):
    """1プレイの確定結果(名前確定時に保存する)。"""

    play_id: str
    name: str
    score: int
    fail_count: int
    played_at: str
    judgements: list[JudgementRecord] = Field(default_factory=list)


class PlayStore(Protocol):
    """状態機械が使うストアのインターフェース。"""

    def save_play(self, record: PlayRecord) -> None: ...

    def ranking(self) -> list[RankingEntry]: ...

    def provisional_rank(self, score: int, fail_count: int) -> int:
        """保存済みプレイに対する暫定順位(1始まり)。"""
        ...


class MemoryStore:
    """メモリ上のPlayStore実装(S2用。プロセス再起動で消える)。"""

    def __init__(self) -> None:
        self._plays: list[PlayRecord] = []

    def save_play(self, record: PlayRecord) -> None:
        self._plays.append(record)

    def _sorted(self) -> list[PlayRecord]:
        return sorted(self._plays, key=lambda p: (-p.score, p.fail_count, p.played_at))

    def ranking(self) -> list[RankingEntry]:
        return [
            RankingEntry(
                rank=i + 1,
                name=p.name,
                score=p.score,
                fail_count=p.fail_count,
                play_id=p.play_id,
                played_at=p.played_at,
            )
            for i, p in enumerate(self._sorted())
        ]

    def provisional_rank(self, score: int, fail_count: int) -> int:
        # 完全同点の既存プレイは played_at 昇順(先勝ち)で上位になるため better に数える
        better = sum(
            1
            for p in self._plays
            if p.score > score or (p.score == score and p.fail_count <= fail_count)
        )
        return better + 1

    def play(self, play_id: str) -> PlayRecord | None:
        return next((p for p in self._plays if p.play_id == play_id), None)
