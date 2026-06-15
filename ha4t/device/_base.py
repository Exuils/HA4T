# -*- coding: utf-8 -*-
"""Device 基础混入：``__init__`` / 平台属性 / Selector 解析 / 坐标计算 / 找点 helper。

所有其它 mixin 都假设 ``self`` 上有：
- ``self.driver`` —— 底层平台 driver（u2 / wda / hdc 之一）
- ``self.config`` —— ``DeviceConfig`` 实例
- ``self.platform`` —— 当前平台名小写
- ``self._resolve_selector(args, kwargs)`` —— Selector 对象 / canonical kwargs 归一化
- ``self._to_abs(p)`` —— 比例坐标 → 绝对像素
- ``self._perform_tap(x, y, duration)`` —— 单击底层
- ``self._find_pos_by_ocr(text, index, timeout)`` —— OCR 找点
- ``self._find_pos_by_image(path, timeout, threshold)`` —— 图像找点
- ``self._get_element_center(**kwargs)`` —— 通过 driver 拿元素中心
"""
from typing import Optional, Tuple

from ha4t.config import DeviceConfig
from ha4t.matchers import find_pos_by_image, find_pos_by_ocr
from ha4t.selector import Selector, to_native


class DeviceBase:
    """共享状态 + 跨平台 Selector 解析层 + 私有 helper。"""

    def __init__(self, driver=None, config: Optional[DeviceConfig] = None):
        self.driver = driver
        self.config: DeviceConfig = config or DeviceConfig()
        self.device_info: str = ""

    @property
    def platform(self) -> str:
        """当前连接的平台名（android / ios / harmony）。"""
        return (self.config.platform or "").lower()

    # ── Selector 解析 ────────────────────────────────────────────────────────

    def _resolve_selector(self, args, kwargs):
        """所有元素操作入口（click/wait/exists/...）的预处理。

        归一化两条路径：
          (1) ``dev.click(SelectorObj, ...)`` —— 第一个位置参数是 Selector 实例，
              ``for_platform(self.platform)`` 解出 native kwargs，**合并进 kwargs**，
              并把 Selector 从 args 弹出。
          (2) ``dev.click(text="登录")`` —— 走 canonical 映射，按当前平台翻译成
              native kwargs。已经是 native 字段的也会保守透传不动。

        坐标 tuple、字符串 OCR 文字、Template 等其它 args[0] 形态原样保留 ——
        Selector 解析只针对 Selector 实例触发。
        """
        if args and isinstance(args[0], Selector):
            sel = args[0]
            native = sel.for_platform(self.platform)
            # caller 的 kwargs（timeout/threshold/动作参数等）保留；Selector 字段优先
            merged = {**kwargs, **native}
            return args[1:], merged
        if kwargs and self.platform:
            kwargs = to_native(kwargs, self.platform)
        return args, kwargs

    # ── 坐标 / 点击底层 ─────────────────────────────────────────────────────

    def _to_abs(self, p) -> Tuple[int, int]:
        """比例坐标 (float, float) → 绝对像素；已是 int 则不变。"""
        if isinstance(p[0], float):
            return (
                int(p[0] * self.config.screen_width),
                int(p[1] * self.config.screen_height),
            )
        return p

    def _perform_tap(self, x: int, y: int, duration: float = 0.1) -> None:
        self.driver.tap(x, y, duration)

    # ── 找点 helper —— 包装 matchers ─────────────────────────────────────────

    def _find_pos_by_ocr(self, text: str, index: int = 0, timeout: float = 10) -> Tuple[int, int]:
        return find_pos_by_ocr(
            text,
            self.driver.screenshot,
            self.config.screen_size,
            index=index,
            timeout=timeout,
        )

    def _find_pos_by_image(self, path: str, timeout: float = 10,
                           threshold: float = 0.8) -> Tuple[int, int]:
        return find_pos_by_image(
            path,
            self.driver.screenshot,
            self.config.screen_size,
            timeout=timeout,
            threshold=threshold,
        )

    def _get_element_center(self, **kwargs) -> Tuple[int, int]:
        return self.driver.get_element_center(**kwargs)
