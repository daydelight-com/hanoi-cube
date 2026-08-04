#!/usr/bin/env python3
"""AprilTag印刷シート生成スクリプト

箱に貼るAprilTag(tag36h11)を実寸で印刷するためのPDFと、
ID→(箱・面)対応のマスタデータ(JSON)を生成する。

使い方:
    .venv/bin/python scripts/generate_tag_sheet.py

出力:
    output/apriltag_sheet.pdf   印刷用シート(A4・実寸100%で印刷すること)
    output/tag_master.json      IDマスタ(CV認識・3Dテクスチャ生成で共用)

仕様変更時は下の設定(BOX_GROUPS等)を書き換えて再実行する。
タグ画像は初回実行時に AprilRobotics/apriltag-imgs から取得し
scripts/apriltag_imgs/ にキャッシュする(2回目以降はオフラインで動く)。
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ---------------------------------------------------------------- 設定

TAG_FAMILY = "tag36h11"
TAG_IMG_URL = (
    "https://raw.githubusercontent.com/AprilRobotics/apriltag-imgs/"
    "master/tag36h11/tag36_11_{id:05d}.png"
)

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(__file__).resolve().parent / "apriltag_imgs" / TAG_FAMILY
OUT_DIR = ROOT / "output"

FACES_PER_BOX = 6

# 箱グループ定義。仕様変更時はここを書き換える(§2.3 参照)。
#   tag_mm    : タグ画像の1辺。tag36h11の公式画像は10x10セルで、
#               黒枠正方形は8/10(80%)、白余白1セル分を画像内に含む
#   margin_mm : 画像の外側にさらに足す白余白
#   corner    : タグを貼る隅(top_right)。省略時は面中央
BLACK_RATIO = 0.8  # 黒枠正方形 / 画像1辺(tag36h11)

BOX_GROUPS = [
    dict(key="large", name="大", box_mm=75, count=3, tag_mm=20.0,
         margin_mm=2.0, corner="top_right",
         note="各面の右上隅に貼る。ロゴは面中央。"),
    dict(key="medium", name="中", box_mm=50, count=3, tag_mm=20.0,
         margin_mm=2.0, corner="top_right",
         note="各面の右上隅に貼る。ロゴは面中央。"),
    dict(key="small", name="小", box_mm=30, count=3, tag_mm=26.0,
         margin_mm=2.0,
         note="各面の中央に貼る(面のほぼ全体を覆う)。ロゴなし。"),
]

# マット四隅のキャリブレーション用タグ
MAT_TAGS = dict(tag_mm=46.0, margin_mm=2.0,
                corners=["左上", "右上", "右下", "左下"], id_base=200)

# ID割当: 箱タグは (箱通し番号)*6 + (面-1)。0〜53。
# 54〜107 は「対角隅に2枚目を追加する場合」の予約帯(§2.3)。
SECOND_CORNER_ID_OFFSET = 54

LABEL_STRIP_MM = 4.0     # ラベル帯の高さ
PAGE_MARGIN_MM = 14.0
GAP_MM = 4.0             # シール間隔
FONT = "HeiseiKakuGo-W5"

# ---------------------------------------------------------------- タグ画像

def fetch_tag_image(tag_id: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url = TAG_IMG_URL.format(id=tag_id)
    path = CACHE_DIR / url.rsplit("/", 1)[-1]
    if not path.exists():
        print(f"  download id={tag_id} <- {url}")
        urllib.request.urlretrieve(url, path)
    return path


def tag_image_reader(tag_id: int, px: int = 450) -> ImageReader:
    """9x9pxの公式画像を最近傍補間で拡大して返す(輪郭をシャープに保つ)。"""
    im = Image.open(fetch_tag_image(tag_id)).convert("L")
    im = im.resize((px, px), Image.NEAREST)
    return ImageReader(im)

# ---------------------------------------------------------------- レイアウト

@dataclass
class Sticker:
    tag_id: int
    title: str      # 例: 大1・面3
    sub: str        # 例: ID 14
    tag_mm: float
    margin_mm: float

    @property
    def w(self) -> float:
        return self.tag_mm + self.margin_mm * 2

    @property
    def h(self) -> float:
        return self.w

    @property
    def h_used(self) -> float:  # 枠外ラベル込みの占有高さ
        return self.h + LABEL_STRIP_MM


class SheetWriter:
    def __init__(self, path: Path):
        pdfmetrics.registerFont(UnicodeCIDFont(FONT))
        self.c = canvas.Canvas(str(path), pagesize=A4)
        self.page_w, self.page_h = A4
        self.y = None  # 現在の書き込み位置(上から、mm座標は都度変換)
        self._new_page_started = False

    # --- 低レベル
    def _ensure(self, need_mm: float, header: str):
        if self.y is None or self.y - need_mm * mm < PAGE_MARGIN_MM * mm:
            if self.y is not None:
                self.c.showPage()
            self.y = self.page_h - PAGE_MARGIN_MM * mm
            self._page_header(header)

    def _page_header(self, title: str):
        c = self.c
        c.setFont(FONT, 10)
        c.setFillGray(0)
        c.drawString(PAGE_MARGIN_MM * mm, self.y - 4 * mm,
                     f"Hanoi Cube AprilTagシート  {title}")
        c.setFont(FONT, 7)
        c.setFillGray(0.35)
        c.drawRightString(self.page_w - PAGE_MARGIN_MM * mm, self.y - 4 * mm,
                          f"{TAG_FAMILY} / 実寸100%で印刷(拡大縮小なし)")
        # 50mmスケール確認バー
        bar_y = self.y - 9 * mm
        c.setStrokeGray(0)
        c.setLineWidth(0.6)
        c.line(PAGE_MARGIN_MM * mm, bar_y, (PAGE_MARGIN_MM + 50) * mm, bar_y)
        for t in (0, 50):
            c.line((PAGE_MARGIN_MM + t) * mm, bar_y - 1 * mm,
                   (PAGE_MARGIN_MM + t) * mm, bar_y + 1 * mm)
        c.setFont(FONT, 6)
        c.drawString((PAGE_MARGIN_MM + 52) * mm, bar_y - 1 * mm,
                     "← この線が50mmなら等倍印刷OK")
        self.y = bar_y - 5 * mm

    def text_block(self, lines: list[tuple[float, str]], leading_mm: float = 5.2):
        for size, line in lines:
            self._ensure(leading_mm, "説明")
            self.c.setFont(FONT, size)
            self.c.setFillGray(0)
            self.c.drawString(PAGE_MARGIN_MM * mm, self.y - leading_mm * mm, line)
            self.y -= leading_mm * mm

    # --- シール描画
    def _draw_sticker(self, s: Sticker, x_mm: float, top_y_pt: float):
        c = self.c
        x = x_mm * mm
        y_top = top_y_pt
        w, h = s.w * mm, s.h * mm
        y = y_top - h
        # カットライン(破線)
        c.setStrokeGray(0.55)
        c.setLineWidth(0.3)
        c.setDash(2, 2)
        c.rect(x, y, w, h)
        c.setDash()
        # タグ本体(上余白margin_mmを空けて中央)
        tx = x + s.margin_mm * mm
        ty = y_top - (s.margin_mm + s.tag_mm) * mm
        c.drawImage(tag_image_reader(s.tag_id), tx, ty,
                    s.tag_mm * mm, s.tag_mm * mm)
        # 枠内右上: 薄く小さなID(切り離し後の識別用。判定を妨げない濃度・サイズ)
        c.setFont(FONT, 3.6)
        c.setFillGray(0.75)
        c.drawRightString(x + w - 0.9 * mm, y_top - 1.6 * mm, str(s.tag_id))
        # 貼付先ラベル(枠線の外・下)
        c.setFont(FONT, 5.5)
        c.setFillGray(0.25)
        c.drawCentredString(x + w / 2, y - 2.6 * mm, f"{s.title}  {s.sub}")

    def sticker_panel(self, panel_title: str, stickers: list[Sticker],
                      cols: int, page_title: str):
        rows = -(-len(stickers) // cols)
        s0 = stickers[0]
        panel_h = 7 + rows * (s0.h_used + GAP_MM)
        self._ensure(panel_h, page_title)
        c = self.c
        c.setFont(FONT, 8.5)
        c.setFillGray(0)
        c.drawString(PAGE_MARGIN_MM * mm, self.y - 4.5 * mm, panel_title)
        self.y -= 7 * mm
        for i, s in enumerate(stickers):
            col, row = i % cols, i // cols
            x_mm = PAGE_MARGIN_MM + col * (s.w + GAP_MM)
            top = self.y - row * (s.h_used + GAP_MM) * mm
            self._draw_sticker(s, x_mm, top)
        self.y -= rows * (s0.h_used + GAP_MM) * mm

    def id_table(self, rows: list[tuple[str, str, str]], n_cols: int = 3):
        """(ID, 貼付先, 位置) の対応表を複数列で描く。"""
        per_col = -(-len(rows) // n_cols)
        row_h = 4.4
        need = 8 + (per_col + 1) * row_h
        self._ensure(need, "ID対応表")
        c = self.c
        c.setFont(FONT, 9)
        c.setFillGray(0)
        c.drawString(PAGE_MARGIN_MM * mm, self.y - 4.5 * mm, "▼ ID対応表")
        self.y -= 8 * mm
        col_w = (self.page_w / mm - PAGE_MARGIN_MM * 2) / n_cols
        widths = (9, 28)  # 貼付先 / 位置 の列オフセット(mm)
        top = self.y
        for ci in range(n_cols):
            x0 = PAGE_MARGIN_MM + ci * col_w
            c.setFont(FONT, 6.5)
            c.setFillGray(0.35)
            for xo, head in zip((0, *widths), ("ID", "貼付先", "位置")):
                c.drawString((x0 + xo) * mm, top - row_h * mm, head)
            c.setFillGray(0)
            for ri, (tid, dest, pos) in enumerate(
                    rows[ci * per_col:(ci + 1) * per_col]):
                yy = top - (ri + 2) * row_h * mm
                c.setFont(FONT, 6.5)
                for xo, text in zip((0, *widths), (tid, dest, pos)):
                    c.drawString((x0 + xo) * mm, yy, text)
        self.y = top - (per_col + 2) * row_h * mm

    def save(self):
        self.c.showPage()
        self.c.save()

# ---------------------------------------------------------------- 生成

def build():
    OUT_DIR.mkdir(exist_ok=True)
    pdf_path = OUT_DIR / "apriltag_sheet.pdf"
    w = SheetWriter(pdf_path)

    # --- 表紙: 印刷・貼り方の説明
    w._ensure(1, "説明")
    w.text_block([
        (13, "AprilTag 印刷・貼り付けガイド"),
        (8, ""),
        (9, "■ 印刷"),
        (8, "・必ず「実寸(100%・拡大縮小なし)」でA4印刷する。各ページの50mmバーで確認。"),
        (8, "・光沢紙は照明が反射して認識に失敗するため、マット(非光沢)のシール用紙を推奨。"),
        (8, "・破線に沿って切る。タグ周囲の白余白はクワイエットゾーンなので切り落とさない。"),
        (8, ""),
        (9, "■ 貼り付け(全箱共通)"),
        (8, "・シールのラベル(例: 大1・面3)の箱に貼る。他の箱に貼ると認識が壊れるので注意。"),
        (8, "・貼付先ラベルは枠線の外(下)に記載。切り離す前に貼付先を確認する。"),
        (8, "・切り離した後は、枠内右上の薄い小さな数字(ID)と下の対応表で貼付先を確認できる。"),
        (8, "・1つの箱に6枚(面1〜面6)。6つの面すべてに1枚ずつ貼る。"),
        (8, "・どの物理面を面1にするかは自由(貼った結果がその箱の面番号になる)。"),
        (8, "・タグの向きはラベル文字が正しく読める向きに統一する(推奨)。"),
        (8, ""),
        (9, "■ サイズ別"),
        (8, "・大(7.5cm箱): 面の右上隅に貼る。ロゴは面中央に約5cm角。"),
        (8, "・中(5cm箱): 面の右上隅に貼る。ロゴは面中央に約3cm角。"),
        (8, "・小(3cm箱): 面の中央に貼る(ほぼ全面)。ロゴなし。"),
        (8, "・マット: 四隅キャリブレーション用。マットの印刷データに組み込む場合は不要。"),
        (8, ""),
        (9, "■ 仕様"),
        (8, f"・ファミリー: {TAG_FAMILY} / ID = 箱通し番号×6 + (面番号-1)"),
        (8, "・ID 54〜107 は対角隅に2枚目を追加する場合の予約帯(未印刷)。マットはID 200〜203。"),
        (8, "・対応表は output/tag_master.json(CV認識・3Dテクスチャと共用のマスタ)。"),
    ])

    # --- ID対応表
    table_rows = []
    bi = 0
    for g in BOX_GROUPS:
        pos = "右上隅" if g.get("corner") == "top_right" else "面中央(全面)"
        for n in range(1, g["count"] + 1):
            for face in range(1, FACES_PER_BOX + 1):
                tid = bi * FACES_PER_BOX + (face - 1)
                table_rows.append((str(tid), f"{g['name']}{n}・面{face}", pos))
            bi += 1
    for i, corner in enumerate(MAT_TAGS["corners"]):
        table_rows.append((str(MAT_TAGS["id_base"] + i),
                           f"マット・{corner}", "マット四隅"))
    w.id_table(table_rows)

    # --- 箱シール
    master_tags = []
    box_index = 0
    for g in BOX_GROUPS:
        for n in range(1, g["count"] + 1):
            box_label = f"{g['name']}{n}"
            stickers = []
            for face in range(1, FACES_PER_BOX + 1):
                tag_id = box_index * FACES_PER_BOX + (face - 1)
                stickers.append(Sticker(
                    tag_id=tag_id,
                    title=f"{box_label}・面{face}",
                    sub=f"ID {tag_id}",
                    tag_mm=g["tag_mm"],
                    margin_mm=g["margin_mm"],
                ))
                master_tags.append(dict(
                    id=tag_id,
                    box=f"{g['key']}-{n}",
                    box_label=box_label,
                    size=g["key"],
                    box_mm=g["box_mm"],
                    face=face,
                    tag_mm=g["tag_mm"],
                    black_mm=round(g["tag_mm"] * BLACK_RATIO, 1),
                    placement=g.get("corner", "center"),
                ))
            w.sticker_panel(
                f"▼ {box_label}({g['box_mm']/10:g}cm箱)  6枚: 面1〜面6 "
                f"/ タグ黒枠約{g['tag_mm'] * BLACK_RATIO:.0f}mm / {g['note']}",
                stickers, cols=3,
                page_title=f"箱シール({g['name']})",
            )
            box_index += 1

    # --- マット
    mat_stickers = []
    mat_master = []
    for i, corner in enumerate(MAT_TAGS["corners"]):
        tag_id = MAT_TAGS["id_base"] + i
        mat_stickers.append(Sticker(
            tag_id=tag_id,
            title=f"マット・{corner}",
            sub=f"ID {tag_id}",
            tag_mm=MAT_TAGS["tag_mm"],
            margin_mm=MAT_TAGS["margin_mm"],
        ))
        mat_master.append(dict(id=tag_id, corner=corner,
                               tag_mm=MAT_TAGS["tag_mm"],
                               black_mm=round(MAT_TAGS["tag_mm"] * BLACK_RATIO, 1)))
    w.sticker_panel(
        f"▼ プレイマット四隅(キャリブレーション用)/ タグ黒枠約{MAT_TAGS['tag_mm'] * BLACK_RATIO:.0f}mm "
        "/ ラベルの隅位置に貼る(タグ全体がカメラに写ること)",
        mat_stickers, cols=3, page_title="マット",
    )

    w.save()

    master = dict(
        family=TAG_FAMILY,
        faces_per_box=FACES_PER_BOX,
        id_rule="id = box_index*6 + (face-1); box order: 大1..大3,中1..中3,小1..小3",
        second_corner_reserved_ids=[SECOND_CORNER_ID_OFFSET,
                                    SECOND_CORNER_ID_OFFSET + 53],
        box_tags=master_tags,
        mat_tags=mat_master,
    )
    master_path = OUT_DIR / "tag_master.json"
    master_path.write_text(json.dumps(master, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    print(f"wrote {pdf_path}")
    print(f"wrote {master_path}")
    return pdf_path


def verify(pdf_path: Path):
    """生成したPDFを画像化し、全タグが正しいIDで検出できるか自己検証する。"""
    try:
        import fitz  # pymupdf
        import numpy as np
        from pupil_apriltags import Detector
    except ImportError as e:
        print(f"verify skipped (pip install pymupdf pupil-apriltags): {e}")
        return

    det = Detector(families=TAG_FAMILY)
    found = set()
    for page in fitz.open(pdf_path):
        pix = page.get_pixmap(dpi=200, colorspace=fitz.csGRAY)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)
        found |= {d.tag_id for d in det.detect(img)}

    n_box = sum(g["count"] for g in BOX_GROUPS) * FACES_PER_BOX
    expected = set(range(n_box)) | {
        MAT_TAGS["id_base"] + i for i in range(len(MAT_TAGS["corners"]))
    }
    missing, extra = expected - found, found - expected
    if missing or extra:
        raise SystemExit(
            f"verify FAILED: missing={sorted(missing)} unexpected={sorted(extra)}")
    print(f"verify OK: {len(expected)}/{len(expected)} tags detected")


if __name__ == "__main__":
    verify(build())
