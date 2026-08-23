"""pytest 共通設定: `app.core`(../server)と pyxel_app 直下のモジュールを import 可能にする。"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = APP_DIR.parent / "server"

for path in (APP_DIR, SERVER_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
