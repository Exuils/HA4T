# -*- coding: utf-8 -*-
"""OCR 文字定位 —— 包装 ``ha4t.orc.OCR``。"""
from typing import Callable, Tuple

# 懒加载：PaddleOCR import 重，避免 ``import ha4t`` 触发。
_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        from ha4t.orc import OCR
        _ocr = OCR()
    return _ocr


def find_pos_by_ocr(
    text: str,
    screenshot_fn: Callable,
    screen_size: Tuple[int, int],
    index: int = 0,
    timeout: float = 10,
) -> Tuple[int, int]:
    """OCR 识别截图中给定文字的位置，返回 (x, y) 中心坐标。"""
    return _get_ocr().get_text_pos(
        text, screenshot_fn, index=index, timeout=timeout, screen_size=screen_size,
    )


def read_page_text(screenshot_fn: Callable) -> str:
    """OCR 识别整页文字并拼接为字符串。"""
    return _get_ocr().get_page_text(screenshot_fn)
