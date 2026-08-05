"""タグID→(箱, サイズ, 面)の解決(正: output/tag_master.json)。

tag_master.json は scripts/generate_tag_sheet.py が印刷シートと同時に生成する
(gitignore下)。実CVの受理条件「tag_id がマスタに存在」はこのモジュールで引く。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.cv.interface import BOX_IDS, BoxId, BoxSize
from app.cv.layout import MAT_TAG_BLACK_MM, MAT_TAG_IDS

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TAG_MASTER_PATH = _REPO_ROOT / "output" / "tag_master.json"


@dataclass(frozen=True)
class TagSpec:
    """箱に貼られた1タグの諸元。"""

    tag_id: int
    box_id: BoxId
    size: BoxSize
    face: int  # 1..6
    black_mm: float  # 黒枠正方形の実寸(姿勢推定のスケール)


@dataclass(frozen=True)
class TagMaster:
    """既知タグの台帳。box_tags は箱タグのみ(マット四隅は含まない)。"""

    box_tags: dict[int, TagSpec]

    @property
    def known_ids(self) -> frozenset[int]:
        return frozenset(self.box_tags) | MAT_TAG_IDS

    def black_mm(self, tag_id: int) -> float:
        if tag_id in MAT_TAG_IDS:
            return MAT_TAG_BLACK_MM
        return self.box_tags[tag_id].black_mm


def tag_master_path() -> Path:
    """環境変数 HANOI_TAG_MASTER で差し替え可能(テスト・複数セット運用)。"""
    env = os.environ.get("HANOI_TAG_MASTER")
    return Path(env) if env else DEFAULT_TAG_MASTER_PATH


def load_tag_master(path: Path | None = None) -> TagMaster:
    """マスタを読む。実CVはマスタ無しでは受理条件を満たせないため欠落は例外にする。"""
    path = path or tag_master_path()
    if not path.exists():
        raise FileNotFoundError(
            f"{path} が無い。scripts/generate_tag_sheet.py を実行して生成すること"
            "(実CVの受理条件はマスタ照合を含むため必須)"
        )
    data = json.loads(path.read_text())
    box_ids = set(BOX_IDS)
    tags: dict[int, TagSpec] = {}
    for t in data["box_tags"]:
        box_id = t["box"]
        if box_id not in box_ids:
            raise ValueError(f"tag_master.json に未知の箱ID: {box_id!r}")
        tags[t["id"]] = TagSpec(
            tag_id=t["id"],
            box_id=box_id,
            size=t["size"],
            face=t["face"],
            black_mm=float(t["black_mm"]),
        )
    return TagMaster(box_tags=tags)
