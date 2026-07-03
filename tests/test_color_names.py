"""RGB16進数から基本色名への変換テスト。"""
from __future__ import annotations

from src.generator.color_names import nearest_basic_color_name


def test_pure_red_is_red() -> None:
    assert nearest_basic_color_name("FF0000") == "red"


def test_pure_yellow_is_yellow() -> None:
    assert nearest_basic_color_name("FFFF00") == "yellow"


def test_pure_black_is_black() -> None:
    assert nearest_basic_color_name("000000") == "black"


def test_pure_white_is_white() -> None:
    assert nearest_basic_color_name("FFFFFF") == "white"


def test_dark_red_maroon_is_red() -> None:
    assert nearest_basic_color_name("8B2500") == "red"


def test_none_returns_none_name() -> None:
    assert nearest_basic_color_name(None) == "none"
