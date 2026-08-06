"""docs/game/score_ranking.md を事前計算テーブルから再生成する。

得点対象クラス(鏡像同一視)を得点降順に並べた一覧。クリア条件を変更したら
`uv run python -m app.core.precompute`(server ディレクトリ)で precompute.json を
再生成したうえで本スクリプトを実行する。

実行: cd server && uv run python ../scripts/generate_score_ranking.py
(依存は server/pyproject.toml にあるため server の uv 環境で動かす)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.core.board import box_count, parse_board  # noqa: E402
from app.core.precompute import load_table  # noqa: E402

OUT_PATH = REPO_ROOT / "docs" / "game" / "score_ranking.md"

_CHAR_TO_KANJI = {"L": "大", "M": "中", "S": "小"}
_EMPTY = "－"  # noqa: RUF001 -- 表の空塔表記(全角ハイフン)


def _cell(tower: str) -> str:
    return _EMPTY if not tower else ",".join(_CHAR_TO_KANJI[c] for c in tower)


def main() -> None:
    table = load_table()
    # 代表は canonical_key(board.md §5)。同得点内は円盤数昇順→正準キーの辞書順で安定化
    keys = sorted({e.canonical_key for e in table.boards if e.clearable})
    rows = []
    for key in keys:
        entry = table.entry(key)
        assert entry.min_moves is not None
        boxes = box_count(key)
        rows.append((boxes * entry.min_moves, boxes, entry.min_moves, key))
    rows.sort(key=lambda r: (-r[0], r[1], r[3]))

    lines = [
        f"# 得点ランキング(鏡像同一視版): {len(rows)}クラス",
        "",
        "得点=円盤数×最短手数。左右反転(鏡像)の配置は同一とみなし、代表1つのみ記載する"
        "(代表は board.md §5 の正準キー)。並び順は得点降順→円盤数昇順→正準キーの辞書順。",
        "",
        "このファイルは `scripts/generate_score_ranking.py` で生成する(手で編集しない)。",
        "",
        "| 順位 | 得点 | 円盤数 | 最短手数 | A | B | C |",
        "|---|---|---|---|---|---|---|",
    ]
    for rank, (points, boxes, moves, key) in enumerate(rows, start=1):
        a, b, c = (_cell(t) for t in parse_board(key))
        lines.append(f"| {rank} | {points} | {boxes} | {moves} | {a} | {b} | {c} |")
    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(rows)} classes)")


if __name__ == "__main__":
    main()
