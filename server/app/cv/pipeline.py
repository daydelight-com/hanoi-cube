"""1フレームぶんのタグ検出 → CvMessage 列への変換(仕様§4.1)。

worker.py(別プロセス)がフレームごとに呼ぶ。カメラ・プロセスに依存しないため
テストでは合成画像を直接流せる。

キャリブレーションはマット四隅タグの「最後に見えたコーナー」をフレームを跨いで
蓄積し、4隅そろった時点で行う(マットは静止しているため合成してよい)。
待機エリアに箱が並ぶと手前の隅タグが遮蔽されることがあり、同一フレームで
4隅そろうことを要求すると起動時(全箱待機)に一生キャリブレーションできない。

カメラ・三脚が微動した場合、遮蔽中の古いコーナー観測と新しい観測が混ざると
誤ったカメラ推定になる。そのため推定結果は再投影誤差で自己検証し、閾値超過なら
採用せず古い観測を破棄して(全隅が新しく見えるまで)前回のキャリブレーションを
使い続ける。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

import numpy as np
import numpy.typing as npt

from app.cv.detector import TagDetection
from app.cv.geometry import CameraModel, box_estimate, calibrate
from app.cv.ground_autocal import (
    GROUND_CAL_MAX_MM,
    GROUND_CAL_SETTLE_STEPS,
    next_ground_offset_mm,
    resting_reference_error_mm,
)
from app.cv.interface import BOX_EDGE_MM, CvMessage
from app.cv.layout import MAT_SIZE_MM, MAT_TAG_BLACK_MM, MAT_TAG_CENTERS_MM, MAT_TAG_IDS
from app.cv.tag_master import TagMaster
from app.cv.tracker import BoardTracker, BoxSighting

logger = logging.getLogger(__name__)

# キャリブレーションの更新間隔(ms)。マット・カメラは固定だが、三脚の微動や
# 起動直後の露出変化に追従するため定期的に再推定する
CALIBRATION_REFRESH_MS = 1000
# 蓄積したコーナー観測の有効期限(ms)。再投影誤差が悪いときはこれより古い観測を捨てる
CALIBRATION_STALE_MS = 5000
# 採用条件: 検出コーナーの再投影誤差の実寸換算(mm)。タグ貼付・印刷スケールの
# 誤差は許容し、カメラのズレや配置の取り違え(数十mm以上)は棄却する。px固定に
# しないのはカメラ距離(px/mm)に依存させないため。
# 実測(A3印刷マット)では印刷歪み+貼付誤差で7mm台の残差が出るため、現物の
# 工作精度を許容できる値にしている(超過時はタグ別の想定→実測がログに出る)。
# 上限側の根拠: カメラ30mmずれ+コーナー1つ遮蔽の新旧混在で残差は約12mmになる
# (test_calibration_rejects_mixed_stale_observations)ため、それ未満に保つこと
CALIBRATION_MAX_REPROJ_MM = 9.0


@dataclass(frozen=True)
class _CornerObservation:
    corners_px: npt.NDArray[np.float64]
    t_ms: int


def _mean_yaw(yaws: list[float]) -> float:
    """ヨーの円環平均(単位ベクトル平均で ±π の不連続を回避)。

    観測同士が打ち消し合う縮退(例: 0°と180°)ではベクトル和がほぼゼロになり、
    丸め誤差だけから任意の角度が出てしまうため、先頭の観測値へフォールバックする
    (タグ誤推定・貼付規約違反時に表示が不定に暴れないための保険)。
    """
    vec = np.mean([[np.cos(y), np.sin(y)] for y in yaws], axis=0)
    if float(np.linalg.norm(vec)) < 0.5:
        return yaws[0]
    return float(np.arctan2(vec[1], vec[0]))


class FramePipeline:
    """検出結果列 → (キャリブレーション+幾何+盤面構成) → CvMessage 列。"""

    def __init__(
        self,
        master: TagMaster,
        *,
        expected_camera_side: str | None = None,
        ground_autocal: bool = True,
    ) -> None:
        self._master = master
        self._tracker = BoardTracker()
        self._camera: CameraModel | None = None
        self._image_size: tuple[int, int] | None = None
        self._mat_corners: dict[int, _CornerObservation] = {}
        self._last_calibrated_ms: int | None = None
        self._last_reject_log_ms: int | None = None
        # HANOI_CAMERA_SIDE の設定値("back"/"front")。None はチェックなし(テスト等)。
        # 設定と実測カメラ位置が食い違えば警告し、設営ミス(表示の180°逆)に気付けるようにする
        self._expected_camera_side = expected_camera_side
        # 接地自動校正(ground_autocal.py)。補正量は観測zから一様に引く。
        # 推定は調整ウィンドウ中のみ(起動時に自動で開き、収束したら固定)
        self._ground_autocal = ground_autocal
        self._ground_offset_mm = 0.0
        self._ground_cal_active = True
        self._ground_cal_steps = 0

    @property
    def calibrated(self) -> bool:
        return self._camera is not None

    @property
    def has_fresh_calibration(self) -> bool:
        """このプロセスで(復元でなく)実際に推定が成立したか。保存の判断に使う。"""
        return self._last_calibrated_ms is not None

    @property
    def tracker(self) -> BoardTracker:
        return self._tracker

    @property
    def ground_offset_mm(self) -> float:
        """接地自動校正の現在の補正量(mm)。ワーカーの再保存判定・診断用。"""
        return self._ground_offset_mm

    # ---- キャリブレーションの保存・復元(カメラ・マットは固定の前提) ----
    # マットが小さい会場では箱に隠れて四隅がそろいにくい。一度成立した推定を
    # ファイルに保存し、再起動時は空マットを見せなくても動けるようにする。

    def export_calibration(self) -> dict[str, object] | None:
        if self._camera is None or self._image_size is None:
            return None
        return {
            "mat_size_mm": list(MAT_SIZE_MM),
            "image_size": list(self._image_size),
            "k": self._camera.k.tolist(),
            "r_cam_from_mat": self._camera.r_cam_from_mat.tolist(),
            "t_cam_from_mat": self._camera.t_cam_from_mat.tolist(),
            "ground_offset_mm": self._ground_offset_mm,
        }

    def restore_calibration(self, data: dict[str, object]) -> None:
        """保存済みキャリブレーションを復元する。レイアウト・解像度が合わなければ ValueError。"""
        mat_size = data["mat_size_mm"]
        if not isinstance(mat_size, list) or [float(v) for v in mat_size] != list(MAT_SIZE_MM):
            raise ValueError(
                f"マット寸法が不一致(保存={mat_size} 現在={list(MAT_SIZE_MM)})。"
                "layout.py 変更後は再キャリブレーションが必要"
            )
        image_size = data["image_size"]
        if not isinstance(image_size, list) or len(image_size) != 2:
            raise ValueError("キャリブレーションデータの image_size が不正")
        camera = CameraModel(
            k=np.asarray(data["k"], dtype=np.float64),
            r_cam_from_mat=np.asarray(data["r_cam_from_mat"], dtype=np.float64),
            t_cam_from_mat=np.asarray(data["t_cam_from_mat"], dtype=np.float64),
        )
        if camera.k.shape != (3, 3) or camera.r_cam_from_mat.shape != (3, 3):
            raise ValueError("キャリブレーションデータの形が不正")
        self._camera = camera
        self._image_size = (int(image_size[0]), int(image_size[1]))
        # 旧形式のファイルにはキーが無いため 0 扱い(以後の観測で再収束する)。
        # 壊れた値が恒久適用されないよう更新時と同じ上限でクランプする
        raw_offset = float(data.get("ground_offset_mm", 0.0))  # type: ignore[arg-type]
        self._ground_offset_mm = max(-GROUND_CAL_MAX_MM, min(GROUND_CAL_MAX_MM, raw_offset))
        self._last_calibrated_ms = None  # 四隅がそろえば新しい推定で上書きされる
        self._warn_if_side_mismatch(camera)

    def process(
        self,
        detections: list[TagDetection],
        t_ms: int,
        image_size: tuple[int, int],
    ) -> list[CvMessage]:
        if image_size != self._image_size:
            # 解像度が変わったら幾何は無効(通常は起動時の1回だけ)
            self._image_size = image_size
            self._camera = None
            self._mat_corners.clear()
            self._last_calibrated_ms = None
            self._ground_offset_mm = 0.0
            self._ground_cal_active = True
            self._ground_cal_steps = 0

        mat_now = 0
        for det in detections:
            if det.tag_id in MAT_TAG_IDS:
                self._mat_corners[det.tag_id] = _CornerObservation(det.corners_px, t_ms)
                mat_now += 1
        self._maybe_calibrate(t_ms)

        sightings: list[BoxSighting] = []
        if self._camera is not None:
            sightings = self._resolve_boxes(detections, self._camera)
            if self._ground_autocal:
                sightings = self._apply_ground_autocal(sightings, t_ms)
        return self._tracker.process(t_ms, sightings, mat_now, self.calibrated)

    # ---- 内部 ----

    def _maybe_calibrate(self, t_ms: int) -> None:
        if len(self._mat_corners) < len(MAT_TAG_IDS):
            return
        if (
            self._last_calibrated_ms is not None
            and t_ms - self._last_calibrated_ms < CALIBRATION_REFRESH_MS
        ):
            return
        assert self._image_size is not None
        corners = {tag_id: obs.corners_px for tag_id, obs in self._mat_corners.items()}
        try:
            camera = calibrate(corners, self._image_size)
        except ValueError as exc:
            # 退化配置(誤検出等)。次のフレームで再試行する
            self._log_reject(t_ms, f"推定失敗: {exc}")
            return
        error_px = self._reprojection_error(camera, corners)
        px_per_mm = self._px_per_mm(corners)
        error_mm = error_px / px_per_mm
        if error_mm > CALIBRATION_MAX_REPROJ_MM:
            # 新旧観測の不整合(カメラ移動+遮蔽)や配置の取り違えとみなし、
            # 古い観測を捨てて前回のキャリブレーションを維持する
            self._log_reject(
                t_ms,
                f"再投影誤差 {error_mm:.1f}mm相当({error_px:.1f}px, "
                f"閾値{CALIBRATION_MAX_REPROJ_MM}mm)で棄却。誤差が大きいままの場合、"
                "四隅タグの物理配置(位置・ID対応・寸法)が layout.py の"
                " MAT_TAG_CENTERS_MM と一致しているか確認すること。"
                f" タグ別の想定→実測(mm): {self._describe_offsets(camera, corners)}",
            )
            self._mat_corners = {
                tag_id: obs
                for tag_id, obs in self._mat_corners.items()
                if t_ms - obs.t_ms <= CALIBRATION_STALE_MS
            }
            return
        cam_pos = camera.cam_pos_mat
        if self._camera is None:  # 初回成立時のみ(定期更新で警告を繰り返さない)
            self._warn_if_side_mismatch(camera)
        # 初回のみINFO(1秒ごとの定期更新でログを埋めない)
        logger.log(
            logging.INFO if self._camera is None else logging.DEBUG,
            "キャリブレーション更新: 焦点距離=%.0fpx カメラ位置=(%.0f, %.0f, %.0f)mm"
            " 誤差=%.1fmm相当 スケール=%.2fpx/mm",
            camera.focal,
            cam_pos[0],
            cam_pos[1],
            cam_pos[2],
            error_mm,
            px_per_mm,
        )
        self._camera = camera
        self._last_calibrated_ms = t_ms

    def _warn_if_side_mismatch(self, camera: CameraModel) -> None:
        """カメラ位置の実測が HANOI_CAMERA_SIDE と食い違えば警告する(表示の180°逆対策)。"""
        if self._expected_camera_side is None:
            return
        cam_pos = camera.cam_pos_mat
        actual = "front" if cam_pos[1] < MAT_SIZE_MM[1] / 2 else "back"
        if actual != self._expected_camera_side:
            logger.warning(
                "カメラ側の設定と実測が食い違う: HANOI_CAMERA_SIDE=%s だがカメラ位置"
                " y=%.0fmm は %s 側(マット奥行き %.0fmm)。表示がプレイヤーから180°逆に"
                "見える。環境変数かマットの向き(待機エリア=プレイヤー側)を確認すること",
                self._expected_camera_side,
                cam_pos[1],
                actual,
                MAT_SIZE_MM[1],
            )

    def _log_reject(self, t_ms: int, reason: str) -> None:
        """棄却理由をログする(連続棄却で埋まらないよう更新間隔に合わせて間引く)。"""
        if (
            self._last_reject_log_ms is None
            or t_ms - self._last_reject_log_ms >= CALIBRATION_REFRESH_MS
        ):
            self._last_reject_log_ms = t_ms
            logger.warning("キャリブレーション不成立: %s", reason)

    @staticmethod
    def _px_per_mm(corners: dict[int, npt.NDArray[np.float64]]) -> float:
        """マット四隅タグの見かけ辺長から画像スケール(px/mm)を推定する。"""
        scales = []
        for c in corners.values():
            side = sum(float(np.linalg.norm(c[i] - c[(i + 1) % 4])) for i in range(4)) / 4
            scales.append(side / MAT_TAG_BLACK_MM)
        return max(float(np.median(scales)), 1e-6)

    @staticmethod
    def measured_mat_centers(
        camera: CameraModel, corners: dict[int, npt.NDArray[np.float64]]
    ) -> dict[int, tuple[float, float]]:
        """検出したタグ中心をマット平面(z=0)へ逆投影し、マット座標(mm)で返す。

        棄却時の現場診断用: どのタグが想定からどちらへずれているかを示す。
        推定カメラ自体が妥協解のため絶対値ではなく相対パターンを読むこと
        (全タグが外向き=印刷が想定より大きい、1つだけ大=そのタグの貼付ずれ、等)。
        """
        k_inv = np.linalg.inv(camera.k)
        origin = camera.cam_pos_mat
        result: dict[int, tuple[float, float]] = {}
        for tag_id, c in corners.items():
            uv = c.mean(axis=0)
            ray = camera.r_cam_from_mat.T @ (k_inv @ np.array([uv[0], uv[1], 1.0]))
            if abs(ray[2]) < 1e-9:
                continue
            p = origin + (-origin[2] / ray[2]) * ray
            result[tag_id] = (float(p[0]), float(p[1]))
        return result

    @classmethod
    def _describe_offsets(
        cls, camera: CameraModel, corners: dict[int, npt.NDArray[np.float64]]
    ) -> str:
        measured = cls.measured_mat_centers(camera, corners)
        parts = []
        for tag_id in sorted(measured):
            ex, ey = MAT_TAG_CENTERS_MM[tag_id]
            mx, my = measured[tag_id]
            parts.append(f"{tag_id}: ({ex:.0f},{ey:.0f})→({mx:.0f},{my:.0f})")
        return " / ".join(parts)

    @staticmethod
    def _reprojection_error(
        camera: CameraModel, corners: dict[int, npt.NDArray[np.float64]]
    ) -> float:
        """マット四隅タグの中心を再投影し、検出中心との最大距離(px)を返す。"""
        centers_mm = np.array([[*MAT_TAG_CENTERS_MM[tag_id], 0.0] for tag_id in sorted(corners)])
        detected = np.array([corners[tag_id].mean(axis=0) for tag_id in sorted(corners)])
        projected = camera.project(centers_mm)
        return float(np.max(np.linalg.norm(projected - detected, axis=1)))

    def _apply_ground_autocal(self, sightings: list[BoxSighting], t_ms: int) -> list[BoxSighting]:
        """接地自動校正(ground_autocal.py)。調整ウィンドウ中は推定し、常に補正を適用する。"""
        del t_ms  # 確定は参照つき更新の回数で数える(途切れた時間を収束に数えない)
        if self._ground_cal_active:
            error = resting_reference_error_mm(sightings, self._tracker.elevated_box_ids())
            if error is not None:
                self._ground_offset_mm = next_ground_offset_mm(self._ground_offset_mm, error)
                self._ground_cal_steps += 1
            if self._ground_cal_steps >= GROUND_CAL_SETTLE_STEPS:
                self._ground_cal_active = False
                logger.info(
                    "接地校正を確定した: 高さ補正 %.1fmm(再調整は make ground-cal)",
                    self._ground_offset_mm,
                )
        offset = self._ground_offset_mm
        if offset != 0.0:
            sightings = [
                replace(s, pos_mm=(s.pos_mm[0], s.pos_mm[1], s.pos_mm[2] - offset))
                for s in sightings
            ]
        return sightings

    def restart_ground_autocal(self) -> None:
        """接地校正の調整ウィンドウを開き直す(make ground-cal のトリガーから呼ばれる)。

        現在の補正量を初期値として、マット上の箱から推定をやり直す。
        呼ぶ前にマット上の箱が全てきちんと置かれていることが前提(運用手順)。
        """
        self._ground_cal_active = True
        self._ground_cal_steps = 0
        logger.info("接地校正をやり直す(現在の補正 %.1fmm から再推定)", self._ground_offset_mm)

    def _resolve_boxes(
        self, detections: list[TagDetection], camera: CameraModel
    ) -> list[BoxSighting]:
        by_box: dict[str, list[tuple[int, npt.NDArray[np.float64], int, float]]] = {}
        for det in detections:
            spec = self._master.box_tags.get(det.tag_id)
            if spec is None:
                continue
            pos, up_face, yaw = box_estimate(
                det.corners_px,
                spec.black_mm,
                spec.size,
                BOX_EDGE_MM[spec.size],
                camera,
                face=spec.face,
            )
            by_box.setdefault(spec.box_id, []).append((det.tag_id, pos, up_face, yaw))
        sightings = []
        for box_id, entries in by_box.items():
            mean_pos = np.mean([pos for _, pos, _, _ in entries], axis=0)
            # 上面は多数決(同数なら面番号の小さい方)。複数タグは剛体なので本来一致する。
            # 食い違いは持ち上げ・傾き中の近似か、貼付規約(TAG_IN_BOX)違反の兆候
            counts: dict[int, int] = {}
            for _, _, f, _ in entries:
                counts[f] = counts.get(f, 0) + 1
            up_face = min(counts, key=lambda f: (-counts[f], f))
            yaw = _mean_yaw([y for _, _, f, y in entries if f == up_face])
            sightings.append(
                BoxSighting(
                    box_id=box_id,  # type: ignore[arg-type]
                    pos_mm=(float(mean_pos[0]), float(mean_pos[1]), float(mean_pos[2])),
                    up_face=up_face,
                    yaw_rad=yaw,
                    seen_tag_ids=tuple(sorted(tag_id for tag_id, _, _, _ in entries)),
                )
            )
        return sightings
