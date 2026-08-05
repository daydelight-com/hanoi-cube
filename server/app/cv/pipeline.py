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
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from app.cv.detector import TagDetection
from app.cv.geometry import CameraModel, box_estimate, calibrate
from app.cv.interface import BOX_EDGE_MM, CvMessage
from app.cv.layout import MAT_SIZE_MM, MAT_TAG_CENTERS_MM, MAT_TAG_IDS
from app.cv.tag_master import TagMaster
from app.cv.tracker import BoardTracker, BoxSighting

logger = logging.getLogger(__name__)

# キャリブレーションの更新間隔(ms)。マット・カメラは固定だが、三脚の微動や
# 起動直後の露出変化に追従するため定期的に再推定する
CALIBRATION_REFRESH_MS = 1000
# 蓄積したコーナー観測の有効期限(ms)。再投影誤差が悪いときはこれより古い観測を捨てる
CALIBRATION_STALE_MS = 5000
# 採用条件: 検出コーナーの再投影誤差(px)。合成実測は1px未満、実機の目安として3px
CALIBRATION_MAX_REPROJ_PX = 3.0


@dataclass(frozen=True)
class _CornerObservation:
    corners_px: npt.NDArray[np.float64]
    t_ms: int


class FramePipeline:
    """検出結果列 → (キャリブレーション+幾何+盤面構成) → CvMessage 列。"""

    def __init__(self, master: TagMaster) -> None:
        self._master = master
        self._tracker = BoardTracker()
        self._camera: CameraModel | None = None
        self._image_size: tuple[int, int] | None = None
        self._mat_corners: dict[int, _CornerObservation] = {}
        self._last_calibrated_ms: int | None = None
        self._last_reject_log_ms: int | None = None

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
        self._last_calibrated_ms = None  # 四隅がそろえば新しい推定で上書きされる

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

        mat_now = 0
        for det in detections:
            if det.tag_id in MAT_TAG_IDS:
                self._mat_corners[det.tag_id] = _CornerObservation(det.corners_px, t_ms)
                mat_now += 1
        self._maybe_calibrate(t_ms)

        sightings: list[BoxSighting] = []
        if self._camera is not None:
            sightings = self._resolve_boxes(detections, self._camera)
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
        if error_px > CALIBRATION_MAX_REPROJ_PX:
            # 新旧観測の不整合(カメラ移動+遮蔽)とみなし、古い観測を捨てて
            # 前回のキャリブレーションを維持する
            self._log_reject(
                t_ms,
                f"再投影誤差 {error_px:.1f}px(閾値{CALIBRATION_MAX_REPROJ_PX}px)で棄却。"
                "誤差が大きいままの場合、四隅タグの物理配置(位置・ID対応・寸法)が"
                " layout.py の MAT_TAG_CENTERS_MM と一致しているか確認すること",
            )
            self._mat_corners = {
                tag_id: obs
                for tag_id, obs in self._mat_corners.items()
                if t_ms - obs.t_ms <= CALIBRATION_STALE_MS
            }
            return
        cam_pos = camera.cam_pos_mat
        # 初回のみINFO(1秒ごとの定期更新でログを埋めない)
        logger.log(
            logging.INFO if self._camera is None else logging.DEBUG,
            "キャリブレーション更新: 焦点距離=%.0fpx カメラ位置=(%.0f, %.0f, %.0f)mm 誤差=%.1fpx",
            camera.focal,
            cam_pos[0],
            cam_pos[1],
            cam_pos[2],
            error_px,
        )
        self._camera = camera
        self._last_calibrated_ms = t_ms

    def _log_reject(self, t_ms: int, reason: str) -> None:
        """棄却理由をログする(連続棄却で埋まらないよう更新間隔に合わせて間引く)。"""
        if (
            self._last_reject_log_ms is None
            or t_ms - self._last_reject_log_ms >= CALIBRATION_REFRESH_MS
        ):
            self._last_reject_log_ms = t_ms
            logger.warning("キャリブレーション不成立: %s", reason)

    @staticmethod
    def _reprojection_error(
        camera: CameraModel, corners: dict[int, npt.NDArray[np.float64]]
    ) -> float:
        """マット四隅タグの中心を再投影し、検出中心との最大距離(px)を返す。"""
        centers_mm = np.array([[*MAT_TAG_CENTERS_MM[tag_id], 0.0] for tag_id in sorted(corners)])
        detected = np.array([corners[tag_id].mean(axis=0) for tag_id in sorted(corners)])
        projected = camera.project(centers_mm)
        return float(np.max(np.linalg.norm(projected - detected, axis=1)))

    def _resolve_boxes(
        self, detections: list[TagDetection], camera: CameraModel
    ) -> list[BoxSighting]:
        by_box: dict[str, list[tuple[int, npt.NDArray[np.float64], float]]] = {}
        for det in detections:
            spec = self._master.box_tags.get(det.tag_id)
            if spec is None:
                continue
            pos, yaw90 = box_estimate(
                det.corners_px, spec.black_mm, spec.size, BOX_EDGE_MM[spec.size], camera
            )
            by_box.setdefault(spec.box_id, []).append((det.tag_id, pos, yaw90))
        sightings = []
        for box_id, entries in by_box.items():
            mean_pos = np.mean([pos for _, pos, _ in entries], axis=0)
            # ヨー(mod 90°)の円環平均: 4倍角の単位ベクトル平均で不連続を回避
            vec = np.mean([[np.cos(4 * y), np.sin(4 * y)] for _, _, y in entries], axis=0)
            yaw90 = float(np.arctan2(vec[1], vec[0])) / 4 % (np.pi / 2)
            sightings.append(
                BoxSighting(
                    box_id=box_id,  # type: ignore[arg-type]
                    pos_mm=(float(mean_pos[0]), float(mean_pos[1]), float(mean_pos[2])),
                    yaw90_rad=yaw90,
                    seen_tag_ids=tuple(sorted(tag_id for tag_id, _, _ in entries)),
                )
            )
        return sightings
