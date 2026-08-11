"""H/A/N/O/Iカスタムマーカーの自己テスト。

- 生成画像の再認識(ID一意)
- 4回転すべて同一IDで認識
- 画像劣化(縮小・blur・射影変換・ノイズ)への耐性
- 偽陽性(マーカーでない画像を検出しないこと)とビット誤り訂正の実測
- Hamming距離・maxCorrectionBitsの妥当性、コミット済み成果物と設計値の一致
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.detector import Detection, create_detector, detect_letters
from src.dictionary import default_max_correction_bits
from src.generator import generate_marker_image
from src.generator import generate_all
from src.marker_patterns import (
    BASE_PATTERNS,
    LABELS,
    LETTERS,
    MARKER_IDS,
    OPTIMIZED_PATTERNS_PATH,
    get_patterns,
    mutable_mask,
)
from src.optimizer import evaluate, hamming_distance, rotations

MARKERS_DIR = Path(__file__).resolve().parents[1] / "markers"


@pytest.fixture(scope="module")
def detector():
    return create_detector()


@pytest.fixture(scope="module")
def patterns():
    return get_patterns()


def _render(patterns, letter: str, cell_size: int = 40) -> np.ndarray:
    """quiet zone付きでマーカーを描画(検出テスト用)。"""
    return generate_marker_image(
        patterns[letter], cell_size=cell_size, border_bits=1, quiet_zone_bits=2
    )


def _assert_single(dets: list[Detection], letter: str, ctx: str) -> None:
    labels = [d.label for d in dets]
    assert labels == [letter], f"{ctx}: 期待 [{letter}] だが {labels}"


# ---------------------------------------------------------------- 基本

class TestRoundTrip:
    @pytest.mark.parametrize("letter", LETTERS)
    def test_generated_png_detected(self, detector, letter):
        """コミット済み markers/<letter>.png がそのIDだけで検出される。"""
        path = MARKERS_DIR / f"{letter}.png"
        assert path.exists(), f"{path} が無い(scripts/generate_markers.py を実行)"
        image = cv2.imread(str(path))
        _assert_single(detect_letters(image, detector), letter, str(path))

    @pytest.mark.parametrize("letter", LETTERS)
    def test_in_memory_render_detected(self, detector, patterns, letter):
        img = _render(patterns, letter)
        _assert_single(detect_letters(img, detector), letter, f"render {letter}")


class TestRotation:
    @pytest.mark.parametrize("letter", LETTERS)
    @pytest.mark.parametrize("k", [0, 1, 2, 3])
    def test_all_rotations_same_id(self, detector, patterns, letter, k):
        img = np.ascontiguousarray(np.rot90(_render(patterns, letter), k))
        _assert_single(detect_letters(img, detector), letter, f"{letter} rot{k*90}")


# ---------------------------------------------------------------- 劣化

class TestDegradation:
    @pytest.mark.parametrize("letter", LETTERS)
    def test_downscale(self, detector, patterns, letter):
        img = _render(patterns, letter, cell_size=40)
        small = cv2.resize(img, None, fx=0.15, fy=0.15, interpolation=cv2.INTER_AREA)
        _assert_single(detect_letters(small, detector), letter, f"{letter} resize")

    @pytest.mark.parametrize("letter", LETTERS)
    def test_gaussian_blur(self, detector, patterns, letter):
        img = _render(patterns, letter, cell_size=20)
        blurred = cv2.GaussianBlur(img, (7, 7), 2.0)
        _assert_single(detect_letters(blurred, detector), letter, f"{letter} blur")

    @pytest.mark.parametrize("letter", LETTERS)
    def test_perspective(self, detector, patterns, letter):
        img = _render(patterns, letter, cell_size=20)
        h, w = img.shape
        src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
        dst = np.float32(
            [[w * 0.08, h * 0.05], [w * 0.95, 0], [w, h * 0.92], [0, h * 0.97]]
        )
        m = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(
            img, m, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=255
        )
        _assert_single(detect_letters(warped, detector), letter, f"{letter} persp")

    @pytest.mark.parametrize("letter", LETTERS)
    def test_noise(self, detector, patterns, letter):
        img = _render(patterns, letter, cell_size=20).astype(np.int16)
        rng = np.random.default_rng(seed=MARKER_IDS[letter])
        noisy = np.clip(img + rng.normal(0, 12, img.shape), 0, 255).astype(np.uint8)
        _assert_single(detect_letters(noisy, detector), letter, f"{letter} noise")


# ------------------------------------------------------- 偽陽性・ビット誤り訂正


def _flip_cells(
    patterns, letter: str, cells: list[tuple[int, int]], cell_size: int = 40
) -> np.ndarray:
    """データ領域の指定セルを反転させたマーカー画像(quiet zone付き)。"""
    p = patterns[letter].copy()
    for r, c in cells:
        p[r, c] ^= 1
    return generate_marker_image(p, cell_size=cell_size, border_bits=1, quiet_zone_bits=2)


class TestFalsePositive:
    def test_blank_image(self, detector):
        assert detect_letters(np.full((400, 400), 255, np.uint8), detector) == []

    def test_random_noise(self, detector):
        rng = np.random.default_rng(seed=1)
        img = rng.integers(0, 256, (400, 400), dtype=np.uint8)
        assert detect_letters(img, detector) == []

    def test_unknown_marker_rejected(self, detector):
        """黒枠付きでもデータが市松模様(どの文字からも遠い)なら検出しない。"""
        checker = np.indices((7, 7)).sum(axis=0) % 2
        img = generate_marker_image(
            checker.astype(np.uint8), cell_size=40, border_bits=1, quiet_zone_bits=2
        )
        assert detect_letters(img, detector) == []


class TestBitErrorCorrection:
    """maxCorrectionBits=3 だが、実効の受理閾値は
    floor(errorCorrectionRate(既定0.6) × 3) = 1bit(README参照)。"""

    @pytest.mark.parametrize("letter", LETTERS)
    def test_one_bit_error_corrected(self, detector, patterns, letter):
        img = _flip_cells(patterns, letter, [(0, 3)])
        _assert_single(detect_letters(img, detector), letter, f"{letter} 1bit誤り")

    def test_two_bit_error_rejected_by_default(self, detector, patterns):
        img = _flip_cells(patterns, "H", [(0, 3), (5, 2)])
        assert detect_letters(img, detector) == []

    def test_three_bit_error_corrected_with_full_rate(self, patterns):
        params = cv2.aruco.DetectorParameters()
        params.errorCorrectionRate = 1.0  # 閾値 = maxCorrectionBits の3bit
        full = create_detector(parameters=params)
        img = _flip_cells(patterns, "N", [(0, 3), (5, 2), (3, 4)])
        _assert_single(detect_letters(img, full), "N", "N 3bit誤り(rate=1.0)")


# ---------------------------------------------------------------- 距離・設計制約

class TestDesign:
    def test_min_hamming_distance(self, patterns):
        """20パターン(5文字×4回転)間の最小距離が設計値以上。"""
        ev = evaluate(patterns)
        assert ev.min_distance >= 8, f"最小Hamming距離が低すぎる: {ev.min_distance}"

    def test_max_correction_bits_safe(self, patterns):
        """maxCorrectionBits が理論上界 floor((d-1)/2) 以下かつ安全上限以下。"""
        d = evaluate(patterns).min_distance
        mcb = default_max_correction_bits()
        assert 0 < mcb <= (d - 1) // 2
        assert mcb <= 3

    def test_strokes_preserved(self, patterns):
        """ベース文字のストローク(白)は最適化後も欠けていない(可読性保証)。"""
        for c in LETTERS:
            assert np.all(patterns[c][BASE_PATTERNS[c] == 1] == 1), c

    def test_changes_within_mutable_mask(self, patterns):
        for c in LETTERS:
            changed = patterns[c] != BASE_PATTERNS[c]
            assert not np.any(changed & ~mutable_mask(c)), c
            assert hamming_distance(patterns[c], BASE_PATTERNS[c]) <= 6, c

    def test_labels(self):
        assert LABELS == {0: "H", 1: "A", 2: "N", 3: "O", 4: "I"}

    def test_rotation_helper(self):
        p = get_patterns()["N"]
        rots = rotations(p)
        for k in range(4):
            assert np.array_equal(rots[k], np.rot90(p, k))
        assert hamming_distance(rots[0], rots[1]) > 0  # 回転で実際に変わる


class TestArtifactConsistency:
    """コミット済み成果物(JSON/PNG/README記載値)が実パターンと一致すること。
    パターンを再探索したら、この設計値とREADMEを併せて更新する。"""

    def test_stats_match_actual_patterns(self, patterns):
        stats = json.loads(OPTIMIZED_PATTERNS_PATH.read_text())["stats"]
        ev = evaluate(patterns)
        assert stats["min_distance"] == ev.min_distance
        assert stats["total_changed_bits"] == ev.total_changes
        assert stats["suggested_max_correction_bits"] == default_max_correction_bits()

    def test_design_values_pinned(self, patterns):
        """README記載の設計値を固定(乖離したら意識的に両方更新させる)。"""
        assert evaluate(patterns).min_distance == 10
        changed = {
            c: hamming_distance(patterns[c], BASE_PATTERNS[c]) for c in LETTERS
        }
        assert changed == {"H": 6, "A": 2, "N": 6, "O": 6, "I": 6}
        assert default_max_correction_bits() == 3

    def test_committed_pngs_match_patterns(self, tmp_path):
        """markers/*.png がJSONパターンからの再生成と一致する(陳腐化検出)。"""
        for path in generate_all(tmp_path, cell_size=100, border_bits=1, quiet_zone_bits=1):
            committed = cv2.imread(str(MARKERS_DIR / path.name), cv2.IMREAD_GRAYSCALE)
            regenerated = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            assert committed is not None, path.name
            assert np.array_equal(committed, regenerated), f"{path.name} が古い"
