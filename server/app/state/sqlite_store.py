"""SQLite永続化ストア(仕様§7.1 のスキーマ、契約: docs/contracts/firestore.md §2 の順序規則)。

MemoryStore と同じ PlayStore プロトコルに準拠し、加えてクラウドアップロードの
リトライキュー(uploaded フラグ、app/cloud/uploader.py が消費)を持つ。
接続はプロセスで1本。状態機械(イベントループ)とアップローダ(to_thread)の
両方から呼ばれるため、内部ロックで直列化する。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from app.api.messages import RankingEntry
from app.state.store import JudgementRecord, PlayRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS plays (
  id            TEXT PRIMARY KEY,
  player_name   TEXT NOT NULL,
  score         INTEGER NOT NULL,
  fail_count    INTEGER NOT NULL,
  played_at     TEXT NOT NULL,
  uploaded      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS judgements (
  id            INTEGER PRIMARY KEY,
  play_id       TEXT NOT NULL REFERENCES plays(id),
  seq           INTEGER NOT NULL,
  board         TEXT NOT NULL,
  elapsed_ms    INTEGER NOT NULL,
  result        TEXT NOT NULL,
  points        INTEGER NOT NULL,
  min_moves     INTEGER,
  dup_of_seq    INTEGER,
  tower_box_ids TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_judgements_play ON judgements(play_id, seq);
CREATE INDEX IF NOT EXISTS idx_plays_uploaded ON plays(uploaded);
"""

# ランキング順(firestore.md §2): スコア降順 → 失敗数昇順 → 先着順(ISO8601は辞書順=時刻順)
_ORDER = "ORDER BY score DESC, fail_count ASC, played_at ASC, id ASC"


class SqliteStore:
    """SQLite の PlayStore 実装+アップロードキュー。"""

    def __init__(self, path: str | Path) -> None:
        if isinstance(path, Path) or path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- PlayStore ----

    def save_play(self, record: PlayRecord) -> None:
        """保存と同時にアップロードキューへ入る(uploaded=0)。同一IDは全置換(冪等)。"""
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO plays (id, player_name, score, fail_count, played_at,"
                " uploaded) VALUES (?, ?, ?, ?, ?, 0)",
                (record.play_id, record.name, record.score, record.fail_count, record.played_at),
            )
            self._conn.execute("DELETE FROM judgements WHERE play_id = ?", (record.play_id,))
            self._conn.executemany(
                "INSERT INTO judgements (play_id, seq, board, elapsed_ms, result, points,"
                " min_moves, dup_of_seq, tower_box_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        record.play_id,
                        j.seq,
                        j.board,
                        j.elapsed_ms,
                        j.result,
                        j.points,
                        j.min_moves,
                        j.dup_of_seq,
                        json.dumps(list(j.tower_box_ids)),
                    )
                    for j in record.judgements
                ],
            )

    def ranking(self) -> list[RankingEntry]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, player_name, score, fail_count, played_at FROM plays {_ORDER}"
            ).fetchall()
        return [
            RankingEntry(
                rank=i + 1,
                name=name,
                score=score,
                fail_count=fail_count,
                play_id=play_id,
                played_at=played_at,
            )
            for i, (play_id, name, score, fail_count, played_at) in enumerate(rows)
        ]

    def provisional_rank(self, score: int, fail_count: int) -> int:
        # 完全同点の既存プレイは played_at 昇順(先勝ち)で上位になるため better に数える
        with self._lock:
            (better,) = self._conn.execute(
                "SELECT COUNT(*) FROM plays WHERE score > ? OR (score = ? AND fail_count <= ?)",
                (score, score, fail_count),
            ).fetchone()
        return int(better) + 1

    def play(self, play_id: str) -> PlayRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, player_name, score, fail_count, played_at FROM plays WHERE id = ?",
                (play_id,),
            ).fetchone()
            if row is None:
                return None
            judgement_rows = self._conn.execute(
                "SELECT seq, board, elapsed_ms, result, points, min_moves, dup_of_seq,"
                " tower_box_ids FROM judgements WHERE play_id = ? ORDER BY seq ASC",
                (play_id,),
            ).fetchall()
        return _to_record(row, judgement_rows)

    # ---- アップロードキュー(app/cloud/uploader.py が使う) ----

    def pending_uploads(self) -> list[PlayRecord]:
        """未アップロードのプレイを保存順(played_at 昇順)で返す。"""
        with self._lock:
            ids = [
                play_id
                for (play_id,) in self._conn.execute(
                    "SELECT id FROM plays WHERE uploaded = 0 ORDER BY played_at ASC, id ASC"
                ).fetchall()
            ]
        return [record for play_id in ids if (record := self.play(play_id)) is not None]

    def mark_uploaded(self, play_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE plays SET uploaded = 1 WHERE id = ?", (play_id,))


def _to_record(
    row: tuple[str, str, int, int, str],
    judgement_rows: list[tuple[int, str, int, str, int, int | None, int | None, str]],
) -> PlayRecord:
    play_id, name, score, fail_count, played_at = row
    judgements = [
        JudgementRecord.model_validate(
            {
                "seq": seq,
                "board": board,
                "elapsed_ms": elapsed_ms,
                "result": result,
                "points": points,
                "min_moves": min_moves,
                "dup_of_seq": dup_of_seq,
                "tower_box_ids": json.loads(tower_box_ids),
            }
        )
        for seq, board, elapsed_ms, result, points, min_moves, dup_of_seq, tower_box_ids in (
            judgement_rows
        )
    ]
    return PlayRecord(
        play_id=play_id,
        name=name,
        score=score,
        fail_count=fail_count,
        played_at=played_at,
        judgements=judgements,
    )
