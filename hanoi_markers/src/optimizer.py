"""5文字×4回転=20パターン間の最小Hamming距離を最大化する探索。

手法: ランダム再スタート付き simulated annealing(seed固定で再現可能)。
状態は「各文字の変更可能bit(mutable_mask)のうち反転しているセルの集合」。
1文字あたりの変更bit数は MAX_CHANGES_PER_LETTER 以下に制限し、
文字の可読性(優先1)を構造的に保証する。

目的(辞書式):
  1. 20パターン間の最小Hamming距離を最大化
  2. 最小距離を取るペア数を最小化
  3. 総変更bit数を最小化
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

from src.marker_patterns import BASE_PATTERNS, LETTERS, mutable_mask

MAX_CHANGES_PER_LETTER = 6
ROTATION_DEGREES = [0, 90, 180, 270]


def hamming_distance(a: np.ndarray, b: np.ndarray) -> int:
    """2パターン間のHamming距離(異なるセル数)。"""
    return int(np.count_nonzero(a != b))


def rotations(pattern: np.ndarray) -> list[np.ndarray]:
    """0°/90°/180°/270°の4回転(np.rot90)。"""
    return [np.rot90(pattern, k) for k in range(4)]


def variant_names() -> list[str]:
    """"H(0°)" 形式の20パターン名(距離行列の行順と一致)。"""
    return [f"{c}({d}°)" for c in LETTERS for d in ROTATION_DEGREES]


def _stack_variants(patterns: dict[str, np.ndarray]) -> np.ndarray:
    """(20, 49) のビット行列。行順は variant_names() と同じ。"""
    rows = [r.reshape(-1) for c in LETTERS for r in rotations(patterns[c])]
    return np.stack(rows).astype(np.uint8)


def distance_matrix(patterns: dict[str, np.ndarray]) -> np.ndarray:
    """20×20の相互Hamming距離行列。"""
    x = _stack_variants(patterns)
    return (x[:, None, :] != x[None, :, :]).sum(axis=-1)


@dataclass(frozen=True)
class Evaluation:
    min_distance: int
    min_pairs: list[tuple[str, str]]  # 最小距離を取るペア
    total_changes: int

    @property
    def score(self) -> float:
        """SA用スカラースコア(大きいほど良い)。"""
        return (
            self.min_distance * 100_000
            - len(self.min_pairs) * 100
            - self.total_changes
        )


def evaluate(patterns: dict[str, np.ndarray]) -> Evaluation:
    d = distance_matrix(patterns)
    names = variant_names()
    off = d + np.eye(len(names), dtype=int) * 10_000  # 対角(自分自身)を除外
    dmin = int(off.min())
    pairs = [
        (names[i], names[j])
        for i in range(len(names))
        for j in range(i + 1, len(names))
        if off[i, j] == dmin
    ]
    changes = sum(
        hamming_distance(patterns[c], BASE_PATTERNS[c]) for c in LETTERS
    )
    return Evaluation(min_distance=dmin, min_pairs=pairs, total_changes=changes)


def _apply(flips: dict[str, frozenset[tuple[int, int]]]) -> dict[str, np.ndarray]:
    out = {}
    for c in LETTERS:
        p = BASE_PATTERNS[c].copy()
        for r, col in flips[c]:
            p[r, col] ^= 1
        out[c] = p
    return out


def optimize(
    seed: int = 42,
    restarts: int = 6,
    iterations: int = 20_000,
    max_changes: int = MAX_CHANGES_PER_LETTER,
    t_start: float = 3.0,
    t_end: float = 0.05,
) -> tuple[dict[str, np.ndarray], Evaluation]:
    """SAで最適化した5パターンと評価を返す(seed固定で決定的)。"""
    if restarts < 1 or iterations < 1:
        raise ValueError("restarts と iterations は1以上")
    rng = random.Random(seed)
    mutable = {c: [tuple(x) for x in np.argwhere(mutable_mask(c))] for c in LETTERS}
    if not 1 <= max_changes <= min(len(m) for m in mutable.values()):
        raise ValueError(f"max_changes が範囲外: {max_changes}")

    best_flips: dict[str, frozenset[tuple[int, int]]] | None = None
    best_eval: Evaluation | None = None

    for _ in range(restarts):
        # 初期状態: 各文字ランダムに数bit反転
        flips = {
            c: frozenset(rng.sample(mutable[c], rng.randint(1, max_changes)))
            for c in LETTERS
        }
        cur_eval = evaluate(_apply(flips))
        if best_eval is None or cur_eval.score > best_eval.score:
            best_flips, best_eval = dict(flips), cur_eval

        for i in range(iterations):
            t = t_start * (t_end / t_start) ** (i / iterations)
            c = rng.choice(LETTERS)
            cell = rng.choice(mutable[c])
            s = set(flips[c])
            if cell in s:
                s.remove(cell)
            elif len(s) >= max_changes:
                s.remove(rng.choice(sorted(s)))  # 上限なら入れ替え
                s.add(cell)
            else:
                s.add(cell)
            cand = {**flips, c: frozenset(s)}
            cand_eval = evaluate(_apply(cand))
            delta = (cand_eval.score - cur_eval.score) / 100_000  # 距離1 ≒ 1.0
            if delta >= 0 or rng.random() < math.exp(delta / max(t, 1e-9)):
                flips, cur_eval = cand, cand_eval
                if cur_eval.score > best_eval.score:
                    best_flips, best_eval = dict(flips), cur_eval

    assert best_flips is not None and best_eval is not None
    return _apply(best_flips), best_eval


def pairwise_report(patterns: dict[str, np.ndarray]) -> list[tuple[str, str, int]]:
    """全190ペアの (名前A, 名前B, 距離)。"""
    d = distance_matrix(patterns)
    names = variant_names()
    return [
        (names[i], names[j], int(d[i, j]))
        for i in range(len(names))
        for j in range(i + 1, len(names))
    ]


def suggest_max_correction_bits(min_distance: int, cap: int = 3) -> int:
    """理論上界 floor((d-1)/2) に安全側の上限capを掛けた推奨値。"""
    return max(0, min((min_distance - 1) // 2, cap))
