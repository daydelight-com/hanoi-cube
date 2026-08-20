#!/usr/bin/env python3
"""実カメラ AprilTag 検出PoC計測ツール(S7)

iPhone連係カメラ(または任意のカメラ/動画)でタグを撮影し、
検出率・黒枠px・px/mm・decision_margin・追従ギャップを計測する。
仕様§2.3の実測(タグサイズ・カメラ位置)と、
DoD「中箱を速く動かして追従が破綻しない」の判定に使う。

使い方(実機PoCの手順):
    1. 印刷済みタグ(output/apriltag_sheet.pdf を実寸印刷)を箱に貼る
    2. iPhoneを三脚固定し連係カメラとしてMacに接続(USB推奨)
    3. make camera-check(= cd server && uv run python ../scripts/cv_poc.py --camera 0 --show)
       - 画角幅が約75cmになるようカメラ距離を調整(オーバーレイの px/mm 表示が
         約2.56になる位置。マット四隅タグの検出辺長から自動算出される)
       - 静止検証: 全箱を置いて mat=4/4・全タグの margin を確認
       - 追従検証: 中箱を掴んで塔間を速く動かし、箱単位の最大ギャップ(ms)を確認
    4. 終了(qキー or Ctrl-C or --duration)でサマリと判定が出る

引数例:
    --camera 0 --width 1920 --height 1080   カメラ入力(既定)
    --video path.mov                        動画ファイル入力(ギャップは動画fpsで換算)
    --synthetic                             合成動画で自己検証(カメラ不要)
    --decimate 2.0 --threads 4              検出器設定(推奨初期値)
    --margin-min 15 --hamming-max 1         受け入れ基準(合成スイープで決定)

注意:
    - 連係カメラの露出時間はOpenCVから取得・制御できない。露出は間接的に検証する:
      既知速度で中箱を動かし、ギャップの出はじめの速度から実効露出を推定する
      (ブラー限界はタグ辺の約20%。docs/cv_poc.md §3)
    - 追従ギャップは「箱単位」(同じ箱の6タグのどれかが見えていれば追従継続)と
      「タグ単位」の両方を出す。DoD判定は箱単位を使う。ギャップには計測開始から
      最初の検出までと、最後の検出から計測終了までの未検出区間も含む。

判定基準(scripts/cv_poc_synth.py の合成スイープ結果):
    黒枠 ≥20px(視線角45°)で検出率100%。正面なら16px、視線角60°は29px必要。
    追従ギャップは仕様§4.2のロスト保持(2秒)内なら破綻ではないが、
    移動中の見た目品質として最大ギャップ500ms以下を目安とする。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from pupil_apriltags import Detector

ROOT = Path(__file__).resolve().parent.parent
MAT_IDS = {200, 201, 202, 203}
MAT_BLACK_MM = 36.8  # マット四隅タグの黒枠実寸(46mm x 0.8)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cv_poc_synth import PX_PER_MM, load_tag, render  # noqa: E402


@dataclass
class TagInfo:
    label: str
    black_mm: float
    box: str | None  # 箱ラベル(マット四隅は None)


def load_master() -> dict[int, TagInfo]:
    """tag_master.json を読む。無ければ空(呼び出し側で警告)。"""
    path = ROOT / "output" / "tag_master.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    info = {
        t["id"]: TagInfo(f"{t['box_label']}/面{t['face']}", t["black_mm"], t["box_label"])
        for t in data["box_tags"]
    }
    for i, corner in enumerate(["左上", "右上", "右下", "左下"]):
        info[200 + i] = TagInfo(f"マット{corner}", MAT_BLACK_MM, None)
    return info


@dataclass
class SeenStat:
    """1タグ(または1箱)の検出統計。"""

    seen: int = 0
    first_frame: int | None = None
    last_frame: int | None = None
    max_gap_frames: int = 0
    px_sizes: list[float] = field(default_factory=list)
    margins: list[float] = field(default_factory=list)

    def update(self, frame_idx: int) -> None:
        if self.first_frame is None:
            self.first_frame = frame_idx
        if self.last_frame is not None:
            gap = frame_idx - self.last_frame - 1
            self.max_gap_frames = max(self.max_gap_frames, gap)
        self.last_frame = frame_idx
        self.seen += 1

    def final_gap_frames(self, total_frames: int) -> int:
        """先頭・末尾の未検出区間も含めた最大連続未検出フレーム数。"""
        if self.first_frame is None or self.last_frame is None:
            return total_frames
        leading = self.first_frame
        trailing = total_frames - 1 - self.last_frame
        return max(self.max_gap_frames, leading, trailing)


def side_px(corners: np.ndarray) -> float:
    """検出コーナー(黒枠正方形の外周)の平均辺長px。"""
    d = 0.0
    for i in range(4):
        d += float(np.linalg.norm(corners[i] - corners[(i + 1) % 4]))
    return d / 4


def synthetic_frames(n: int, fps: float) -> Iterator[tuple[np.ndarray, float]]:
    """自己検証用の合成動画。中箱タグ(黒枠16mm=41px)が往復移動し、
    速度に応じたモーションブラー(露出1/125s相当)がかかる。
    マット四隅タグ(黒枠36.8mm)は静止。戻り値は (frame, タグの移動速度mm/s)。
    """
    w, h = 1280, 720
    exposure_s = 1 / 125
    mat_patches = []
    for i in range(4):
        p = render(load_tag(200 + i), MAT_BLACK_MM * PX_PER_MM, 30.0, 0.0, 1.0, 3.0,
                   np.random.default_rng(i))
        ph, pw = p.shape
        mx = 20 if i in (0, 3) else w - pw - 20
        my = 20 if i in (0, 1) else h - ph - 20
        mat_patches.append((p, mx, my))
    tag22 = load_tag(22)  # 中1/面5
    for k in range(n):
        phase = 2 * np.pi * k / (fps * 2.0)  # 2秒で1往復
        x_mm = 150 * np.sin(phase)  # 振幅150mm → 最大速度 150*2π/2 ≈ 471mm/s
        v_mm_s = abs(150 * 2 * np.pi / 2.0 * np.cos(phase))
        blur_px = v_mm_s * exposure_s * PX_PER_MM
        frame = np.full((h, w), 128, np.uint8)
        for p, mx, my in mat_patches:
            frame[my : my + p.shape[0], mx : mx + p.shape[1]] = p
        patch = render(tag22, 16.0 * PX_PER_MM, 45.0, blur_px, 1.0, 3.0,
                       np.random.default_rng(k))
        x = int(w / 2 + x_mm * PX_PER_MM - patch.shape[1] / 2)
        y = int(h / 2 - patch.shape[0] / 2)
        frame[y : y + patch.shape[0], x : x + patch.shape[1]] = patch
        yield frame, v_mm_s


def open_capture(args: argparse.Namespace) -> tuple[cv2.VideoCapture, float]:
    """入力を開き (capture, ソースfps[不明なら0]) を返す。"""
    if args.video:
        cap = cv2.VideoCapture(args.video)
    else:
        cap = cv2.VideoCapture(args.camera)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        cap.set(cv2.CAP_PROP_FPS, 30)
    if not cap.isOpened():
        raise SystemExit("入力を開けない(--camera 番号 or --video パスを確認)")
    w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    print(f"入力: {w:.0f}x{h:.0f} @ {fps:.0f}fps")
    return cap, fps


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--video", type=str, default=None)
    ap.add_argument("--synthetic", action="store_true", help="合成動画で自己検証")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--decimate", type=float, default=2.0)
    ap.add_argument("--sigma", type=float, default=0.0)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--hamming-max", type=int, default=1)
    ap.add_argument("--margin-min", type=float, default=15.0)
    ap.add_argument("--duration", type=float, default=0.0, help="秒。0=無制限(q/Ctrl-Cで終了)")
    ap.add_argument("--show", action="store_true", help="検出オーバーレイ表示")
    args = ap.parse_args()

    master = load_master()
    if master:
        known_ids: set[int] | None = set(master)
    else:
        known_ids = None
        print("*** 警告: output/tag_master.json が無いため既知IDフィルタが無効 ***\n"
              "*** 受理条件が docs/cv_poc.md §4 と一致しない。scripts/generate_tag_sheet.py"
              " を先に実行すること ***")
    det = Detector(families="tag36h11", nthreads=args.threads, quad_decimate=args.decimate,
                   quad_sigma=args.sigma, refine_edges=True, decode_sharpening=0.25)

    tag_stats: dict[int, SeenStat] = defaultdict(SeenStat)
    box_stats: dict[str, SeenStat] = defaultdict(SeenStat)
    frame_times: list[float] = []
    detect_ms: list[float] = []
    speed_at_gap: dict[str, float] = {}
    px_per_mm_samples: list[float] = []
    frame_idx = 0
    t_start = time.time()
    fps_assumed = 30.0
    source_fps = 0.0

    if args.synthetic:
        n = int((args.duration or 6.0) * fps_assumed)
        source: Iterator[tuple[np.ndarray, float]] = iter(synthetic_frames(n, fps_assumed))
        cap = None
    else:
        cap, source_fps = open_capture(args)
        source = None  # type: ignore[assignment]

    try:
        while True:
            if args.synthetic:
                try:
                    gray, speed = next(source)
                except StopIteration:
                    break
            else:
                assert cap is not None
                ok, frame = cap.read()
                if not ok:
                    break
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                speed = 0.0

            t0 = time.perf_counter()
            dets = det.detect(gray)
            detect_ms.append((time.perf_counter() - t0) * 1000)

            accepted = [
                d for d in dets
                if d.hamming <= args.hamming_max
                and d.decision_margin >= args.margin_min
                and (known_ids is None or d.tag_id in known_ids)
            ]
            boxes_in_frame: set[str] = set()
            for d in accepted:
                st = tag_stats[d.tag_id]
                st.update(frame_idx)
                px = side_px(d.corners)
                st.px_sizes.append(px)
                st.margins.append(float(d.decision_margin))
                info = master.get(d.tag_id)
                if info:
                    if d.tag_id in MAT_IDS:
                        px_per_mm_samples.append(px / info.black_mm)
                    if info.box:
                        boxes_in_frame.add(info.box)
            for box in boxes_in_frame:
                bst = box_stats[box]
                prev_last = bst.last_frame
                bst.update(frame_idx)
                if prev_last is not None and frame_idx - prev_last - 1 > 0:
                    speed_at_gap[box] = max(speed_at_gap.get(box, 0.0), speed)

            frame_idx += 1
            frame_times.append(time.time())

            if args.show and not args.synthetic:
                vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                for d in accepted:
                    pts = d.corners.astype(int)
                    cv2.polylines(vis, [pts], True, (0, 255, 0), 2)
                    cv2.putText(vis, f"{d.tag_id}:{side_px(d.corners):.0f}px",
                                tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                mat_n = len({d.tag_id for d in accepted} & MAT_IDS)
                ppm = (f" px/mm={np.median(px_per_mm_samples[-40:]):.2f}(目安2.56)"
                       if px_per_mm_samples else "")
                cv2.putText(vis, f"mat {mat_n}/4  tags {len(accepted)}{ppm}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
                cv2.imshow("cv_poc", vis)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            if frame_idx % 60 == 0:
                recent = {i for i, s in tag_stats.items()
                          if s.last_frame is not None and frame_idx - s.last_frame < 30}
                print(f"  frame {frame_idx}: 検出中タグ数(直近)={len(recent)}"
                      f" mat={len(recent & MAT_IDS)}/4 detect={np.mean(detect_ms[-60:]):.0f}ms")
            if args.duration and not args.synthetic and time.time() - t_start > args.duration:
                break
    except KeyboardInterrupt:
        print("\n(中断)")
    finally:
        if cap is not None:
            cap.release()
        if args.show:
            cv2.destroyAllWindows()

    total = frame_idx
    if total == 0:
        raise SystemExit("フレームなし")
    if len(frame_times) >= 2:
        proc_fps = (len(frame_times) - 1) / max(frame_times[-1] - frame_times[0], 1e-6)
    else:
        proc_fps = fps_assumed
    # ギャップのms換算: 合成=30fps固定、動画=動画のfps、カメラ=処理fps(読み捨てなしの前提)
    if args.synthetic:
        gap_fps = fps_assumed
    elif args.video and source_fps > 0:
        gap_fps = source_fps
    else:
        gap_fps = max(proc_fps, 1.0)
    ms_per_frame = 1000.0 / gap_fps

    print(f"\n== サマリ: {total}フレーム, 処理{proc_fps:.1f}fps, "
          f"検出 {np.mean(detect_ms):.1f}ms/frame ==")
    if px_per_mm_samples:
        print(f"px/mm(マット四隅から): 中央値 {np.median(px_per_mm_samples):.2f} "
              f"(1080p・画角幅75cm の目安 2.56)")

    print(f"\n-- タグ別 --\n{'tag':>4} {'label':<10} {'seen%':>6} {'px(med)':>8} "
          f"{'margin(med/min)':>15} {'max_gap':>9}")
    for tid in sorted(tag_stats):
        st = tag_stats[tid]
        label = master[tid].label if tid in master else "?"
        print(f"{tid:>4} {label:<10} {st.seen / total * 100:5.1f}% "
              f"{np.median(st.px_sizes):8.1f} "
              f"{np.median(st.margins):7.1f}/{min(st.margins):5.1f} "
              f"{st.final_gap_frames(total) * ms_per_frame:7.0f}ms")

    print(f"\n-- 箱別(6面のいずれかが見えていれば検出扱い。先頭・末尾の未検出も含む)--\n"
          f"{'box':<8} {'seen%':>6} {'max_gap':>9}")
    all_boxes = sorted({i.box for i in master.values() if i.box}) if master else []
    for box in all_boxes or sorted(box_stats):
        bst = box_stats.get(box)
        if bst is None:
            print(f"{box:<8}   0.0%   一度も未検出(ギャップ判定不能)")
            continue
        gap_ms = bst.final_gap_frames(total) * ms_per_frame
        note = f" (ギャップ時速度~{speed_at_gap[box]:.0f}mm/s)" if box in speed_at_gap else ""
        print(f"{box:<8} {bst.seen / total * 100:5.1f}% {gap_ms:7.0f}ms{note}")

    print("\n== 判定の目安 ==")
    px_all = [p for tid, st in tag_stats.items() if tid not in MAT_IDS for p in st.px_sizes]
    if px_all:
        print(f"  箱タグ黒枠px 中央値 {np.median(px_all):.0f}px "
              f"(合成スイープ基準: 視線角45°で20px・60°で29px必要 → "
              f"{'OK' if np.median(px_all) >= 29 else 'NG: カメラを寄せる/解像度を上げる'})")
    if box_stats:
        worst_box, worst_gap = max(
            ((b, s.final_gap_frames(total) * ms_per_frame) for b, s in box_stats.items()),
            key=lambda x: x[1])
        print(f"  箱の最大追従ギャップ {worst_gap:.0f}ms ({worst_box}) "
              f"(目安500ms以下 → {'OK' if worst_gap <= 500 else '要対処(docs/cv_poc.md §3)'}; "
              f"ロスト保持2秒以内なら表示は破綻しない)")
    else:
        print("  箱タグが一度も検出されていない → 判定不能(NG)。"
              "カメラ位置・タグ印刷・照明を確認すること")


if __name__ == "__main__":
    main()
