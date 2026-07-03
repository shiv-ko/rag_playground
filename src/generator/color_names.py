"""RGB16進数コードを基本色名に変換する。"""
from __future__ import annotations

_BASIC_PALETTE: dict[str, tuple[int, int, int]] = {
    "red": (255, 0, 0),
    "orange": (255, 165, 0),
    "yellow": (255, 255, 0),
    "green": (0, 128, 0),
    "cyan": (0, 255, 255),
    "blue": (0, 0, 255),
    "purple": (128, 0, 128),
    "pink": (255, 192, 203),
    "brown": (139, 69, 19),
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "gray": (128, 128, 128),
}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def nearest_basic_color_name(hex_color: str | None) -> str:
    if not hex_color or len(hex_color.lstrip("#")) < 6:
        return "none"
    try:
        r, g, b = _hex_to_rgb(hex_color)
    except ValueError:
        return "none"

    if r >= 100 and r > g * 1.8 and r > b * 1.8:
        return "red"

    best_name = "none"
    best_dist = float("inf")
    for name, (pr, pg, pb) in _BASIC_PALETTE.items():
        dist = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name
