#!/usr/bin/env python3
"""AprilTag検出限界の合成スイープ(S7 CV PoC の無人代替検証)

実カメラの代わりに、公式 tag36h11 画像を
「透視(俯瞰角)→ モーションブラー → ダウンサンプル → 露出/ノイズ」
の順で劣化させた合成画像を作り、pupil-apriltags の検出成否と
decision_margin を計測する。実機PoC(scripts/cv_poc.py)の前に
「黒枠16mmが成立する条件」を机上で絞り込むためのもの。

物理条件へのマッピング(仕様§2.3):
    1080p・画角幅75cm → 750/1920 = 0.391 mm/px(2.56 px/mm)
    黒枠16mm → 正面 41px。俯瞰45°では短軸が cos45° ≈ 29px に縮む
    移動速度 v mm/s と露出 T s → モーションブラー v*T*2.56 px

使い方:
    .venv/bin/python scripts/cv_poc_synth.py            # フルスイープ(数分)
    .venv/bin/python scripts/cv_poc_synth.py --quick    # 縮小版(動作自己検証)

出力:
    output/cv_poc_synth_results.json   全計測点(検出率・margin)
    標準出力                            集計表と物理シナリオ判定
"""

from __future__ import annotations

import argparse
import json
import time
from itertools import product
from pathlib import Path

import cv2
import numpy as np
from pupil_apriltags import Detector

ROOT = Path(__file__).resolve().parent.parent
TAG_DIR = ROOT / "scripts" / "apriltag_imgs" / "tag36h11"
OUT_DIR = ROOT / "output"

# tag36h11 公式画像: 10x10セル(黒枠正方形8x8 + 白余白1セル)
CELLS = 10
BLACK_CELLS = 8
SS = 6  # スーパーサンプリング係数(高解像度で合成→INTER_AREAで縮小=カメラ標本化の近似)

# 物理定数(仕様§2.3)
MM_PER_PX_1080P_75CM = 750.0 / 1920.0  # ≈0.391
PX_PER_MM = 1.0 / MM_PER_PX_1080P_75CM  # ≈2.56
BLACK_MM = 16.0  # 大・中箱タグの黒枠実寸


def load_tag(tag_id: int) -> np.ndarray:
    """公式10x10px画像をグレースケール(0-255)で返す。"""
    path = TAG_DIR / f"tag36_11_{tag_id:05d}.png"
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(path)
    assert img.shape == (CELLS, CELLS), img.shape
    return img


def render(
    tag_img: np.ndarray,
    black_px: float,
    angle_deg: float,
    blur_px: float,
    gain: float,
    noise_sigma: float,
    rng: np.random.Generator,
    blur_axis: str = "h",
) -> np.ndarray:
    """1条件ぶんの合成画像(グレースケール)を返す。

    black_px は最終画像上での黒枠正方形の1辺(正面時)。angle_deg は
    タグ面法線からの視線角(0=正対)。ブラーは最終画像スケールの px 長。
    blur_axis: "h"=長軸方向(射影で縮まない向き)、"v"=短軸方向(縮む向き。
    同じブラー長でもタグ辺に対する比率が大きくなり不利)。
    """
    # --- 高解像度キャンバスに タグ+白余白(印刷2mm≒1セル)+箱面+背景 を合成
    cell_hi = black_px * SS / BLACK_CELLS
    tag_hi = round(cell_hi * CELLS)
    tag_big = cv2.resize(tag_img, (tag_hi, tag_hi), interpolation=cv2.INTER_NEAREST)

    margin = round(cell_hi)  # 印刷シールの追加白余白 ≈ 2mm = 1セル
    face = round(tag_hi + margin * 2)
    canvas_hi = round(face * 1.8)
    canvas = np.full((canvas_hi, canvas_hi), 120, np.uint8)  # 背景(マット面)
    f0 = (canvas_hi - face) // 2
    canvas[f0 : f0 + face, f0 : f0 + face] = 235  # 箱の面(白地シール相当)
    t0 = (canvas_hi - tag_hi) // 2
    canvas[t0 : t0 + tag_hi, t0 : t0 + tag_hi] = tag_big

    # --- 俯瞰角: x軸回りの回転を弱透視で投影(カメラ距離=タグの20倍)
    th = np.deg2rad(angle_deg)
    h = canvas_hi
    src = np.float32([[0, 0], [h, 0], [h, h], [0, h]])
    c = h / 2.0
    dist = h * 20.0
    dst_pts = []
    for x, y in src:
        y3 = (y - c) * np.cos(th)
        z3 = (y - c) * np.sin(th)
        s = dist / (dist + z3)
        dst_pts.append([c + (x - c) * s, c + y3 * s])
    dst = np.float32(dst_pts)
    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        canvas, m, (h, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
    )

    # --- モーションブラー(最終スケール blur_px → 高解像度では *SS)
    klen = round(blur_px * SS)
    if klen >= 2:
        shape = (1, klen) if blur_axis == "h" else (klen, 1)
        kernel = np.full(shape, 1.0 / klen, np.float32)
        warped = cv2.filter2D(warped, -1, kernel, borderType=cv2.BORDER_REPLICATE)

    # --- カメラ標本化(縮小)+軽い光学ボケ
    final = round(h / SS)
    small = cv2.resize(warped, (final, final), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 0.6)

    # --- 露出(ゲイン)とセンサーノイズ
    out = small.astype(np.float32) * gain
    out += rng.normal(0.0, noise_sigma, out.shape)
    return np.clip(out, 0, 255).astype(np.uint8)


def make_detector(quad_decimate: float, quad_sigma: float = 0.0) -> Detector:
    return Detector(
        families="tag36h11",
        nthreads=4,
        quad_decimate=quad_decimate,
        quad_sigma=quad_sigma,
        refine_edges=True,
        decode_sharpening=0.25,
    )


def sweep(quick: bool) -> list[dict]:
    if quick:
        black_pxs = [16.0, 29.0, 41.0]
        angles = [0.0, 45.0]
        blurs = [0.0, 10.0]
        decimates = [1.0, 2.0]
        tag_ids = [0, 22]
        seeds = [1]
        gains = [1.0]
    else:
        black_pxs = [12.0, 16.0, 20.0, 24.0, 29.0, 34.0, 41.0, 51.0, 82.0]
        angles = [0.0, 30.0, 45.0, 60.0]
        blurs = [0.0, 4.0, 8.0, 13.0, 20.0, 30.0]
        decimates = [1.0, 2.0]
        tag_ids = [0, 10, 22, 35, 47, 53]  # 大・中・小の実IDから抽出
        seeds = [1, 2]
        gains = [1.0, 0.5]  # 1.0=適正露出、0.5=暗め(会場照明が暗いケース)

    detectors = {d: make_detector(d) for d in decimates}
    tags = {tid: load_tag(tid) for tid in tag_ids}
    results: list[dict] = []
    combos = list(product(black_pxs, angles, blurs, decimates))
    t_start = time.time()
    for i, (bp, ang, bl, dec) in enumerate(combos):
        n_ok = 0
        n_all = 0
        margins: list[float] = []
        n_h12_only = 0  # 正IDだが hamming 1〜2 のみ(ビット誤り訂正)
        n_other_id = 0  # 別IDの検出(誤検出。同居含む全件を数える)
        ok_by_gain = dict.fromkeys(gains, 0)
        n_by_gain = dict.fromkeys(gains, 0)
        for tid, seed, gain in product(tag_ids, seeds, gains):
            rng = np.random.default_rng(seed * 1000 + tid)
            img = render(tags[tid], bp, ang, bl, gain, noise_sigma=3.0, rng=rng)
            dets = detectors[dec].detect(img)
            n_all += 1
            n_by_gain[gain] += 1
            n_other_id += sum(1 for d in dets if d.tag_id != tid)
            hit = [d for d in dets if d.tag_id == tid and d.hamming == 0]
            if hit:
                n_ok += 1
                ok_by_gain[gain] += 1
                margins.append(float(hit[0].decision_margin))
            elif any(d.tag_id == tid for d in dets):
                n_h12_only += 1
        results.append(
            dict(
                black_px=bp,
                angle_deg=ang,
                blur_px=bl,
                quad_decimate=dec,
                rate=n_ok / n_all,
                n=n_all,
                margin_mean=round(float(np.mean(margins)), 1) if margins else None,
                margin_min=round(float(np.min(margins)), 1) if margins else None,
                h12_only=n_h12_only,
                other_id=n_other_id,
                rate_by_gain={str(g): ok_by_gain[g] / n_by_gain[g] for g in gains},
            )
        )
        if (i + 1) % 40 == 0:
            print(f"  ... {i + 1}/{len(combos)} ({time.time() - t_start:.0f}s)")
    return results


def measure(
    black_px: float,
    angle: float,
    blur: float,
    blur_axis: str = "h",
    quad_decimate: float = 2.0,
    tag_ids: tuple[int, ...] = (0, 10, 22, 35, 47, 53),
    seeds: tuple[int, ...] = (1, 2),
    gains: tuple[float, ...] = (1.0, 0.5),
) -> float:
    """指定条件を実レンダリングして検出率を返す(グリッドへの丸めなし)。"""
    det = make_detector(quad_decimate)
    n_ok = 0
    n_all = 0
    for tid, seed, gain in product(tag_ids, seeds, gains):
        rng = np.random.default_rng(seed * 1000 + tid)
        img = render(load_tag(tid), black_px, angle, blur, gain, 3.0, rng, blur_axis)
        if any(d.tag_id == tid and d.hamming == 0 for d in det.detect(img)):
            n_ok += 1
        n_all += 1
    return n_ok / n_all


def print_matrix(results: list[dict], dec: float, gain_note: str) -> None:
    blacks = sorted({r["black_px"] for r in results})
    angles = sorted({r["angle_deg"] for r in results})
    blurs = sorted({r["blur_px"] for r in results})
    print(f"\n== 検出率マトリクス quad_decimate={dec} ({gain_note}) ==")
    for ang in angles:
        print(f"\n-- 俯瞰角 {ang:.0f}°  (行=黒枠px, 列=ブラーpx) --")
        header = "black_px | " + " | ".join(f"{b:4.0f}" for b in blurs)
        print(header)
        for bp in blacks:
            cells = []
            for bl in blurs:
                rs = [
                    r
                    for r in results
                    if r["black_px"] == bp
                    and r["angle_deg"] == ang
                    and r["blur_px"] == bl
                    and r["quad_decimate"] == dec
                ]
                cells.append(f"{rs[0]['rate'] * 100:4.0f}" if rs else "  - ")
            print(f"{bp:8.0f} | " + " | ".join(cells))


def print_scenarios() -> None:
    """物理シナリオ(仕様§2.3の想定)ごとの合否を直接計測して表示する。

    グリッドへの丸めはせず、各シナリオを実レンダリングして測る。
    移動シナリオは「視線角45°/60°(側面/上面の最悪)とブラー方向 長軸/短軸」の
    4通りの最悪値で判定する(手の移動方向・見えている面は制御できないため)。
    """
    bp = BLACK_MM * PX_PER_MM
    print("\n== 物理シナリオ判定(1080p・画角幅75cm、quad_decimate=2.0、直接計測)==")
    print(f"   黒枠16mm = 正面 {bp:.0f}px。移動系は角度45/60°とブラー方向h/vの最悪値")

    for label, ang in [("正面", 0.0), ("視線角30°", 30.0), ("視線角45°", 45.0),
                       ("視線角60°(上面の最悪)", 60.0)]:
        rate = measure(bp, ang, 0.0)
        mark = "OK " if rate >= 0.95 else ("注意" if rate >= 0.5 else "NG ")
        print(f"  [{mark}] 静止・{label:32s} → 検出率{rate * 100:3.0f}%")

    for v, vlabel in [(250, "ゆっくり"), (500, "ふつう"), (1000, "速い"), (1500, "最速")]:
        for exp_s, exp_label in [(1 / 60, "1/60s"), (1 / 125, "1/125s"), (1 / 250, "1/250s")]:
            blur = v * exp_s * PX_PER_MM
            rate = min(
                measure(bp, ang, blur, axis)
                for ang in (45.0, 60.0)
                for axis in ("h", "v")
            )
            mark = "OK " if rate >= 0.95 else ("注意" if rate >= 0.5 else "NG ")
            print(f"  [{mark}] 移動{v:4d}mm/s({vlabel})・露出{exp_label:7s}"
                  f" ブラー{blur:4.1f}px → 最悪検出率{rate * 100:3.0f}%")

    print("\n== 対処オプションの効果(静止・視線角45°で黒枠pxが変わる)==")
    for label, bp2 in [
        ("基準: 1080p・幅75cm", BLACK_MM * PX_PER_MM),
        ("寄せる: 1080p・幅60cm", BLACK_MM * 1920 / 600),
        ("4K: 幅75cm", BLACK_MM * 3840 / 750),
    ]:
        rate = measure(bp2, 45.0, 0.0)
        print(f"  {label:24s} 黒枠{bp2:3.0f}px → 検出率{rate * 100:3.0f}%")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="縮小スイープ(自己検証用)")
    args = ap.parse_args()

    print("合成スイープ開始" + ("(quick)" if args.quick else ""))
    results = sweep(args.quick)

    OUT_DIR.mkdir(exist_ok=True)
    name = "cv_poc_synth_results_quick.json" if args.quick else "cv_poc_synth_results.json"
    out_path = OUT_DIR / name
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"\n結果を保存: {out_path} ({len(results)}計測点)")

    for dec in sorted({r["quad_decimate"] for r in results}):
        print_matrix(results, dec, "全ID・全seed・全gain混合")
    if not args.quick:
        print_scenarios()


if __name__ == "__main__":
    main()
