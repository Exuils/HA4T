# -*- coding: utf-8 -*-
"""位置定位器：把截图 + 模板/文字 → 坐标。

这两个模块（`ocr` / `image`）是平台无关的图像/OCR 找点逻辑，从 ``Device``
分出来好处：
1. ``Device.__init__`` 不再因为找点逻辑而臃肿；
2. 找点的策略（OCR vs 图像匹配 vs 模板裁剪）日后可以独立演进；
3. 写单元测试可以 mock screenshot 函数，不需要真 driver。
"""
from ha4t.matchers.image import find_pos_by_image, click_inside_template
from ha4t.matchers.ocr import find_pos_by_ocr, read_page_text

__all__ = [
    "find_pos_by_image",
    "click_inside_template",
    "find_pos_by_ocr",
    "read_page_text",
]
