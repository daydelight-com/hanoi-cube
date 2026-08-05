"""カメラ幾何: マット四隅タグからの自己キャリブレーションとタグ→マット座標変換。

仕様§4.1-4: マット四隅タグ(ID 200-203)からホモグラフィを推定し、箱の位置を
マット座標系(mm)へ変換する。高さはタグの見かけサイズ・姿勢から推定する。

連係カメラは内部パラメータが得られないため、主点=画像中心・正方画素を仮定して
マット平面ホモグラフィから焦点距離を自己推定する(Zhangの拘束を1平面に適用)。
推定した K でタグ1枚ごとの平面姿勢(位置+法線)を復元し、カメラ姿勢を介して
マット座標系へ変換する。

コーナー順序の規約: pupil-apriltags の detection.corners は
「タグ座標系(x=右, y=上)の (-1,-1), (+1,-1), (+1,+1), (-1,+1)」の順
(左下→右下→右上→左上)。tests/test_cv_geometry.py の合成レンダリングで
実測ピン留めしている(pupil-apriltags 1.0.4)。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import numpy.typing as npt

from app.cv.layout import FACE_CENTER_OFFSET_MM, MAT_TAG_BLACK_MM, MAT_TAG_CENTERS_MM

Arr = npt.NDArray[np.float64]

# タグ座標系(x=右, y=上, 単位=黒枠半辺)でのコーナー位置。detection.corners と同順
TAG_CORNER_LOCAL: Arr = np.array(
    [[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]], dtype=np.float64
)


def homography(src_xy: Arr, dst_xy: Arr) -> Arr:
    """DLT(正規化付き)で src→dst のホモグラフィ(3x3)を推定する。N>=4。"""
    n = src_xy.shape[0]
    if n < 4 or dst_xy.shape[0] != n:
        raise ValueError("homography には対応点が4組以上必要")

    def normalize(pts: Arr) -> tuple[Arr, Arr]:
        mean = pts.mean(axis=0)
        scale = np.sqrt(2.0) / max(float(np.mean(np.linalg.norm(pts - mean, axis=1))), 1e-12)
        t = np.array(
            [[scale, 0.0, -scale * mean[0]], [0.0, scale, -scale * mean[1]], [0.0, 0.0, 1.0]]
        )
        homog = np.hstack([pts, np.ones((pts.shape[0], 1))])
        return (t @ homog.T).T, t

    src_n, t_src = normalize(src_xy)
    dst_n, t_dst = normalize(dst_xy)
    a = np.zeros((2 * n, 9), dtype=np.float64)
    for i in range(n):
        x, y = src_n[i, 0], src_n[i, 1]
        u, v = dst_n[i, 0], dst_n[i, 1]
        a[2 * i] = [-x, -y, -1.0, 0.0, 0.0, 0.0, u * x, u * y, u]
        a[2 * i + 1] = [0.0, 0.0, 0.0, -x, -y, -1.0, v * x, v * y, v]
    _, _, vt = np.linalg.svd(a)
    h_n = vt[-1].reshape(3, 3)
    h: Arr = np.linalg.inv(t_dst) @ h_n @ t_src
    result: Arr = h / h[2, 2]
    return result


def estimate_focal(h_plane_to_img: Arr, cx: float, cy: float) -> float:
    """平面(mm)→画像(px)のホモグラフィから焦点距離を推定する。

    主点 (cx, cy)・正方画素を仮定し、回転列の直交・等長拘束から f² を解く。
    """
    h = h_plane_to_img
    u = h[0, :2] - cx * h[2, :2]
    v = h[1, :2] - cy * h[2, :2]
    w = h[2, :2]
    candidates: list[float] = []
    denom = w[0] * w[1]
    if abs(denom) > 1e-12:
        f2 = -(u[0] * u[1] + v[0] * v[1]) / denom
        if f2 > 0:
            candidates.append(f2)
    denom = w[1] ** 2 - w[0] ** 2
    if abs(denom) > 1e-12:
        f2 = (u[0] ** 2 + v[0] ** 2 - u[1] ** 2 - v[1] ** 2) / denom
        if f2 > 0:
            candidates.append(f2)
    if not candidates:
        raise ValueError("焦点距離を推定できない(退化したホモグラフィ)")
    return float(np.sqrt(np.mean(candidates)))


def pose_from_homography(h_plane_to_img: Arr, k: Arr) -> tuple[Arr, Arr]:
    """平面→画像のホモグラフィとKから平面の姿勢 (R, t) を復元する。

    X_cam = R @ X_plane + t(X_plane は平面座標 (x, y, 0))。平面がカメラ前方
    (t_z > 0)になる符号を選ぶ。
    """
    m = np.linalg.inv(k) @ h_plane_to_img
    if m[2, 2] < 0:  # 平面原点がカメラ前方に来る符号へ
        m = -m
    scale = float(np.mean([np.linalg.norm(m[:, 0]), np.linalg.norm(m[:, 1])]))
    if scale < 1e-12:
        raise ValueError("退化したホモグラフィ")
    r1 = m[:, 0] / np.linalg.norm(m[:, 0])
    r2 = m[:, 1] / np.linalg.norm(m[:, 1])
    r3 = np.cross(r1, r2)
    r_raw = np.column_stack([r1, r2, r3])
    u_svd, _, vt = np.linalg.svd(r_raw)
    r: Arr = u_svd @ np.diag([1.0, 1.0, float(np.linalg.det(u_svd @ vt))]) @ vt
    t: Arr = m[:, 2] / scale
    return r, t


@dataclass(frozen=True)
class CameraModel:
    """自己推定したカメラ: 内部K、マット→カメラの外部 (R, t)。"""

    k: Arr
    r_cam_from_mat: Arr
    t_cam_from_mat: Arr

    @property
    def focal(self) -> float:
        return float(self.k[0, 0])

    @property
    def cam_pos_mat(self) -> Arr:
        """カメラ中心のマット座標。"""
        pos: Arr = -self.r_cam_from_mat.T @ self.t_cam_from_mat
        return pos

    def to_mat(self, p_cam: Arr) -> Arr:
        result: Arr = self.r_cam_from_mat.T @ (p_cam - self.t_cam_from_mat)
        return result

    def rot_to_mat(self, r_cam: Arr) -> Arr:
        result: Arr = self.r_cam_from_mat.T @ r_cam
        return result

    def project(self, points_mat: Arr) -> Arr:
        """マット座標(N,3)→画像px(N,2)。キャリブレーションの自己検証に使う。"""
        p_cam = (self.r_cam_from_mat @ points_mat.T).T + self.t_cam_from_mat
        uvw = (self.k @ p_cam.T).T
        result: Arr = uvw[:, :2] / uvw[:, 2:3]
        return result


def calibrate(mat_tag_corners_px: dict[int, Arr], image_size: tuple[int, int]) -> CameraModel:
    """マット四隅タグの検出コーナー(px)からカメラを自己推定する。

    1パス目はタグ中心4点で概算ホモグラフィを推定し、それを使って各コーナーの
    マット座標を理想正方形へスナップ、2パス目に16点で再推定する(印刷向きに非依存)。
    """
    if len(mat_tag_corners_px) < 4:
        raise ValueError("マット四隅タグが4つ必要")
    ids = sorted(mat_tag_corners_px)
    centers_mat = np.array([MAT_TAG_CENTERS_MM[i] for i in ids], dtype=np.float64)
    centers_px = np.array([mat_tag_corners_px[i].mean(axis=0) for i in ids], dtype=np.float64)
    h0 = homography(centers_mat, centers_px)

    # 2パス目: 検出コーナーを概算Hでマット座標へ写し、理想コーナーへ最近傍スナップ
    half = MAT_TAG_BLACK_MM / 2.0
    ideal_local = TAG_CORNER_LOCAL * half
    h0_inv = np.linalg.inv(h0)
    src_pts: list[Arr] = []
    dst_pts: list[Arr] = []
    for i in ids:
        cx_mm, cy_mm = MAT_TAG_CENTERS_MM[i]
        ideal = ideal_local + np.array([cx_mm, cy_mm])
        for corner_px in mat_tag_corners_px[i]:
            v = h0_inv @ np.array([corner_px[0], corner_px[1], 1.0])
            p_mm = v[:2] / v[2]
            j = int(np.argmin(np.linalg.norm(ideal - p_mm, axis=1)))
            src_pts.append(ideal[j])
            dst_pts.append(corner_px)
    h = homography(np.array(src_pts), np.array(dst_pts))

    cx, cy = image_size[0] / 2.0, image_size[1] / 2.0
    f = estimate_focal(h, cx, cy)
    k = np.array([[f, 0.0, cx], [0.0, f, cy], [0.0, 0.0, 1.0]], dtype=np.float64)
    r, t = pose_from_homography(h, k)
    return CameraModel(k=k, r_cam_from_mat=r, t_cam_from_mat=t)


def tag_pose_mat(corners_px: Arr, black_mm: float, camera: CameraModel) -> tuple[Arr, Arr]:
    """検出コーナーからタグの (R, 中心位置) をマット座標系で返す。

    正方形平面マーカー専用の IPPE(cv2.SOLVEPNP_IPPE_SQUARE)を使う。
    タグは小さく(黒枠約40px)、汎用のホモグラフィ分解は0.5pxのコーナー誤差で
    数百mmの奥行き誤差を出すため使えない(IPPEなら同条件で誤差中央値5〜8mm)。
    R の第3列がタグ面法線。IPPEの2解の曖昧性により法線はまれに大きく誤るため、
    呼び出し側は法線を物理制約(水平か鉛直)へスナップすること。
    """
    half = black_mm / 2.0
    # IPPE_SQUARE の物体点順序は 左上→右上→右下→左下(y=上)= TAG_CORNER_LOCAL の [3,2,1,0]
    obj = np.array([[-half, half, 0.0], [half, half, 0.0], [half, -half, 0.0], [-half, -half, 0.0]])
    img_pts = corners_px[[3, 2, 1, 0]].astype(np.float64)
    _, rvecs, tvecs, _ = cv2.solvePnPGeneric(
        obj, img_pts, camera.k, None, flags=cv2.SOLVEPNP_IPPE_SQUARE
    )
    r_cam, _ = cv2.Rodrigues(rvecs[0])  # 解は再投影誤差の小さい順
    t_cam = np.asarray(tvecs[0], dtype=np.float64).ravel()
    return camera.rot_to_mat(np.asarray(r_cam, dtype=np.float64)), camera.to_mat(t_cam)


# 面法線を上面とみなす |nz| の下限(それ未満は側面として水平にスナップ)
_TOP_FACE_NZ = 0.6


def box_estimate(
    corners_px: Arr,
    black_mm: float,
    size: str,
    edge_mm: float,
    camera: CameraModel,
) -> tuple[Arr, float]:
    """タグ検出1枚から (箱の底面中心[マット座標mm], ヨー角 mod 90°[rad]) を推定する。

    位置: 面の右上隅貼り(大・中)のオフセットをタグ座標系で補正し、面中心から
    面法線の逆向きに半辺入った点を箱中心、その直下 edge/2 を底面とみなす。
    置かれた箱は軸平行に立っている前提で、法線は鉛直(上面)か水平(側面)に
    スナップしてIPPEの法線誤差・曖昧性を吸収する(持ち上げ中は近似)。

    ヨー: どの面のタグかは物理的な貼付対応が不定なため、鉛直軸まわりの回転を
    90°の剰余でのみ推定する(立方体の3D表示にはこれで十分)。側面タグは法線の
    方位角、上面タグはタグx軸の方位角を使う。
    """
    r_mat, p_mat = tag_pose_mat(corners_px, black_mm, camera)
    d = FACE_CENTER_OFFSET_MM[size]
    # タグ座標系 x=右, y=上: 面中心はタグ中心から左下 (-d, -d)
    offset: Arr = r_mat @ np.array([-d, -d, 0.0])
    face_center = p_mat + offset
    normal = r_mat[:, 2]
    to_cam = camera.cam_pos_mat - p_mat
    if float(np.dot(normal, to_cam)) < 0:
        normal = -normal
    if abs(float(normal[2])) >= _TOP_FACE_NZ:
        yaw_src = r_mat[:, 0]  # 上面: タグx軸(面内回転)から方位を取る
        normal = np.array([0.0, 0.0, 1.0])  # 上面(カメラは上方にあるため下面は見えない)
    else:
        yaw_src = normal  # 側面: 法線の方位がヨー(+面の向きの90°倍)
        normal = np.array([normal[0], normal[1], 0.0])
        normal /= max(float(np.linalg.norm(normal)), 1e-9)
    yaw_mod90 = float(np.arctan2(yaw_src[1], yaw_src[0])) % (np.pi / 2)
    box_center: Arr = face_center - normal * (edge_mm / 2.0)
    box_center[2] -= edge_mm / 2.0  # 底面中心
    return box_center, yaw_mod90
