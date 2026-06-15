# -*- coding: utf-8 -*-
"""图像模板匹配定位 —— 包装 ``ha4t.aircv``。"""
from typing import Callable, Tuple

import numpy as np


def find_pos_by_image(
    template_path: str,
    screenshot_fn: Callable,
    screen_size: Tuple[int, int],
    timeout: float = 10,
    threshold: float = 0.8,
) -> Tuple[int, int]:
    """模板匹配定位 —— 返回 (x, y) 中心坐标。匹配失败抛 TimeoutError。"""
    from ha4t.aircv.cv import match_loop
    return match_loop(
        screenshot_func=screenshot_fn,
        template=template_path,
        timeout=timeout,
        threshold=threshold,
        screen_size=screen_size,
    )


def click_inside_template(
    template_path: str,
    screenshot_fn: Callable,
    screen_size: Tuple[int, int],
    grid: Tuple[int, int],
    splits: Tuple[int, int],
    threshold: float = 0.8,
    rgb: bool = False,
    scale_max: int = 800,
    scale_step: float = 0.005,
) -> Tuple[int, int]:
    """在匹配到的模板矩形内，按 ``splits`` 网格划分，返回 ``grid`` 那格的中心坐标。

    用例（POM 图像元素拼接定位）：模板是一张大背景图，里面有 N×M 个相同样式的
    单元格（如九宫格按钮 / 数字键盘），用户只想点其中第 (i, j) 格。这种比"先
    定位整个模板再算偏移"更稳。
    """
    from ha4t.aircv.cv import Template
    source = screenshot_fn()
    source = np.array(source.resize(screen_size)) if hasattr(source, 'resize') else np.array(source)
    tpl = Template(
        template_path,
        threshold=threshold,
        rgb=rgb,
        scale_max=scale_max,
        scale_step=scale_step,
    )
    result = tpl._cv_match(source)
    if not result:
        raise TimeoutError(f"图片匹配失败: {template_path}")
    rect = result["rectangle"]
    x1, y1 = rect[0]
    x3, y3 = rect[2]
    cell_w = (x3 - x1) / splits[0]
    cell_h = (y3 - y1) / splits[1]
    return (
        int(x1 + cell_w * (grid[0] + 0.5)),
        int(y1 + cell_h * (grid[1] + 0.5)),
    )
