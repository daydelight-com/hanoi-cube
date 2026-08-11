"""H/A/N/O/I カスタムマーカー(7×7、cv2.aruco カスタムDictionary)。

本番CV(server/app/cv/)の tag36h11 とは独立した自己完結PoC。
ビット規約: 1 = 白, 0 = 黒。
"""

from src.dictionary import LABELS, create_hanoi_dictionary
from src.detector import detect_letters
from src.generator import generate_marker_image
from src.marker_patterns import BASE_PATTERNS, get_patterns

__all__ = [
    "LABELS",
    "create_hanoi_dictionary",
    "detect_letters",
    "generate_marker_image",
    "BASE_PATTERNS",
    "get_patterns",
]
