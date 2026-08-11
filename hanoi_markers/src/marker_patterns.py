"""H/A/N/O/I の7×7マーカーパターン定義。

ビット規約: 1 = 白(文字ストローク), 0 = 黒(背景)。
データ領域7×7のみを持ち、黒枠(border)と白余白(quiet zone)は
generator が描画時に付ける。

- BASE_PATTERNS: 人間が読める文字のベース形(固定bitの土台)
- mutable_mask(): 変更してよいbit(ストロークに隣接する背景セル。
  白を足すとセリフ/ヒゲに見え、文字の可読性を大きく損なわない)
- get_patterns(): optimizer が書き出した最適化済みパターン
  (optimized_patterns.json)を読む。探索は scripts/optimize_markers.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

GRID = 7
LETTERS = ["H", "A", "N", "O", "I"]  # ID 0..4 の順
LABELS: dict[int, str] = {i: c for i, c in enumerate(LETTERS)}
MARKER_IDS: dict[str, int] = {c: i for i, c in enumerate(LETTERS)}

OPTIMIZED_PATTERNS_PATH = Path(__file__).resolve().parent / "optimized_patterns.json"


def _p(*rows: str) -> np.ndarray:
    """"1000001" 形式の7行からパターンを作る。"""
    a = np.array([[int(ch) for ch in row] for row in rows], dtype=np.uint8)
    assert a.shape == (GRID, GRID)
    return a


# ベース形: 人間が読める7×7ドット文字(1=白ストローク)
BASE_PATTERNS: dict[str, np.ndarray] = {
    "H": _p(
        "1000001",
        "1000001",
        "1000001",
        "1111111",
        "1000001",
        "1000001",
        "1000001",
    ),
    "A": _p(
        "0011100",
        "0100010",
        "1000001",
        "1111111",
        "1000001",
        "1000001",
        "1000001",
    ),
    "N": _p(
        "1000001",
        "1100001",
        "1010001",
        "1001001",
        "1000101",
        "1000011",
        "1000001",
    ),
    "O": _p(
        "0111110",
        "1000001",
        "1000001",
        "1000001",
        "1000001",
        "1000001",
        "0111110",
    ),
    # I は上下バーを短くしてある(フルバーだと I(90°) が H と完全一致するため)
    "I": _p(
        "0111110",
        "0001000",
        "0001000",
        "0001000",
        "0001000",
        "0001000",
        "0111110",
    ),
}


def mutable_mask(letter: str) -> np.ndarray:
    """変更可能bitのマスク(True=変更可)。

    ストローク(1)のセルは固定(文字が必ず完全な形で残る)。
    背景(0)のうちストロークに上下左右で隣接するセルだけ白に反転してよい。
    離れた孤立ドットは許さないので、追加bitはセリフ/ヒゲに見える。
    """
    base = BASE_PATTERNS[letter]
    mask = np.zeros_like(base, dtype=bool)
    for r in range(GRID):
        for c in range(GRID):
            if base[r, c] == 1:
                continue
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < GRID and 0 <= cc < GRID and base[rr, cc] == 1:
                    mask[r, c] = True
                    break
    return mask


def get_patterns(path: Path | None = None) -> dict[str, np.ndarray]:
    """最適化済みパターンを読む(letter -> 7×7 uint8)。"""
    path = path or OPTIMIZED_PATTERNS_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"{path} が無い。scripts/optimize_markers.py を実行して生成すること"
        )
    data = json.loads(path.read_text())
    out: dict[str, np.ndarray] = {}
    for letter in LETTERS:
        raw = np.array(data["patterns"][letter])
        if raw.shape != (GRID, GRID):
            raise ValueError(f"{letter} のパターン形状が不正: {raw.shape}")
        if not np.isin(raw, (0, 1)).all():
            raise ValueError(f"{letter} のパターンに0/1以外の値がある")
        out[letter] = raw.astype(np.uint8)
    return out


def save_patterns(
    patterns: dict[str, np.ndarray], stats: dict, path: Path | None = None
) -> Path:
    """最適化結果をJSONへ保存(statsには最小距離・seed等を入れる)。"""
    path = path or OPTIMIZED_PATTERNS_PATH
    payload = {
        "bit_convention": "1=white, 0=black",
        "patterns": {c: patterns[c].tolist() for c in LETTERS},
        "stats": stats,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def to_ascii(pattern: np.ndarray, *, on: str = "■", off: str = "□") -> str:
    """パターンをASCIIアート化(■=白ストローク, □=黒背景)。"""
    return "\n".join("".join(on if v else off for v in row) for row in pattern)
