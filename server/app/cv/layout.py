"""マット座標系のレイアウト定数(契約: cv-interface.md §2)。

マット左手前隅が原点、x=右、y=奥(塔)方向、z=上、単位mm。

**会場のマット実寸は環境変数 HANOI_MAT_SIZE で指定する**(例: `HANOI_MAT_SIZE=450x300`。
未指定は A3 横置き 420x297)。塔位置・待機帯・エリア判定・四隅タグ位置はすべて寸法から
導出される。寸法を変えたら:
  - 四隅タグを実物の各隅から MAT_TAG_INSET_MM 内側(タグ中心)に貼り直す
  - フロント表示の写し frontend/src/three/layout.ts も同値に合わせる
    (フロントは環境変数を読めないため、既定寸法の静的な写し)
モックCV(mock.py)の合成レイアウトも本モジュールの値を使う。
テストは 600x400 のレイアウト前提値(塔x=150/300/450 等)で書かれているため、
tests/conftest.py が HANOI_MAT_SIZE=600x400 に固定する。

600x400 のときの導出値は S8 以前の固定値と同一
(塔x=150/300/450, 塔y=280, 待機y=80, 待機帯上限170, 塔バンド±70/±80)。

寸法の目安: 塔間隔=幅/4 が大箱(75mm)より十分広く、待機帯(奥行きの約29%)に
箱(最大75mm)が収まるよう、**幅450mm x 奥行き300mm 以上を推奨**。それ未満でも
動作はするが、隣の塔と箱が物理的に干渉しやすくなる(既定のA3は推奨下限を
わずかに下回るが、塔間隔105mm・待機帯上限118.5mmで大箱75mmは収まる)。
"""

from __future__ import annotations

import os

_DEFAULT_MAT_SIZE_MM = (420.0, 297.0)


def _mat_size_from_env() -> tuple[float, float]:
    raw = os.environ.get("HANOI_MAT_SIZE")
    if not raw:
        return _DEFAULT_MAT_SIZE_MM
    try:
        # 全角の乗算記号も半角xとして許容する
        w_str, h_str = raw.lower().replace("×", "x").split("x")  # noqa: RUF001
        return (float(w_str), float(h_str))
    except ValueError as exc:
        raise ValueError(f"HANOI_MAT_SIZE の形式が不正: {raw!r}(例: 450x300)") from exc


MAT_SIZE_MM: tuple[float, float] = _mat_size_from_env()

_W, _H = MAT_SIZE_MM

# ---- 塔(A/B/C)。横に等間隔、奥側 ----
TOWER_SPACING_MM = _W / 4
TOWER_X_MM: dict[str, float] = {"A": _W / 4, "B": _W / 2, "C": _W * 3 / 4}
TOWER_Y_MM = _H * 0.7

# ---- 待機エリア(手前の帯)。モック・表示用の代表位置 ----
STAGING_Y_MM = _H * 0.2
STAGING_X0_MM = _W * 0.1
STAGING_PITCH_MM = _W * 0.1

# ---- エリア分類(実CV) ----
# 塔エリア: |x - TOWER_X_MM[t]| <= TOWER_HALF_X_MM かつ |y - TOWER_Y_MM| <= TOWER_HALF_Y_MM
# (半幅は塔間隔から導出し、隣の塔と重ならないようにする)
# 待機エリア: y <= STAGING_Y_MAX_MM(塔バンド手前に30mmの不感帯を挟む)
# どちらでもない位置(不感帯・マット外・持ち上げ中)は area=None(移動中扱い)
TOWER_HALF_X_MM = TOWER_SPACING_MM / 2 - 5.0
TOWER_HALF_Y_MM = _H * 0.2
STAGING_Y_MAX_MM = TOWER_Y_MM - TOWER_HALF_Y_MM - 30.0

# 積み判定: 下の箱(または地面)の上面と底面の差がこの範囲なら「載っている」とみなす。
# 超えていれば宙に浮いている(持ち上げ・下ろし途中)として塔に数えない。
STACK_GAP_TOL_MM = 25.0

# ---- マット四隅タグ(ID 200-203) ----
# 中心位置。「左上」は真上から見た配置(原点=左手前、y=奥)で左奥の隅を指す。
# シール50mm角(タグ46mm+余白2mm)を四隅に貼る想定で、中心を各辺から30mm内側に置く。
MAT_TAG_INSET_MM = 30.0
MAT_TAG_CENTERS_MM: dict[int, tuple[float, float]] = {
    200: (MAT_TAG_INSET_MM, _H - MAT_TAG_INSET_MM),  # 左上(左奥)
    201: (_W - MAT_TAG_INSET_MM, _H - MAT_TAG_INSET_MM),  # 右上(右奥)
    202: (_W - MAT_TAG_INSET_MM, MAT_TAG_INSET_MM),  # 右下(右手前)
    203: (MAT_TAG_INSET_MM, MAT_TAG_INSET_MM),  # 左下(左手前)
}
MAT_TAG_IDS = frozenset(MAT_TAG_CENTERS_MM)
MAT_TAG_BLACK_MM = 36.8  # マット四隅タグの黒枠実寸(46mm x 0.8)

# ---- 箱の面内タグ位置(仕様§2.3) ----
# 大・中はシール24mm角(タグ20mm+余白2mm)を面の右上隅に貼る。シールを隅に合わせると
# タグ中心は面の隅から12mm内側になり、面中心はタグ中心から (面辺/2 - 12)mm 斜め内側。
# 小は面中央貼りでオフセットなし。
# 前提: シールはタグ図柄が(貼るとき見た面に対して)正立する向きで貼ること。
# 図柄を90°回して貼るとタグ座標系だけが回り、面中心へのオフセット方向がずれて
# 位置誤差(大箱で最大約50mm)になる。貼付後に箱ごと回転・反転するのは問題ない
# (タグと面が一緒に回るため)。運用手順に「正立貼り」を明記する。
STICKER_HALF_MM = 12.0
FACE_CENTER_OFFSET_MM: dict[str, float] = {
    "large": 75.0 / 2 - STICKER_HALF_MM,  # 25.5
    "medium": 50.0 / 2 - STICKER_HALF_MM,  # 13.0
    "small": 0.0,
}
