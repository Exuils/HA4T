# -*- coding: utf-8 -*-
"""交互 mixin —— click / double_click / long_press / swipe(_*) / drag / popup_apps / key / home。"""
import os
import time

from ha4t.config import global_config
from ha4t.matchers.image import click_inside_template
from ha4t.utils.log_utils import cost_time


class InteractionMixin:
    """所有动作类操作。selector 形态由 ``_resolve_selector`` 归一化后分发到具体 driver。"""

    @cost_time
    def click(self, *args, duration: float = 0.1, **kwargs) -> None:
        """
        点击操作，支持多种定位方式：

        - ``click(SelectorObj)``         跨平台 Selector 对象（POM 写法）
        - ``click((x, y))``              绝对或比例坐标
        - ``click("文字")``              OCR 定位
        - ``click(Template(...))``       图像匹配（``filepath`` 属性）
        - ``click(text="xxx")``          canonical kwargs → 当前平台自动翻译
        - ``click(image="img.png")``     图像路径（支持 ``grid``/``splits`` 网格拆分）
        """
        args, kwargs = self._resolve_selector(args, kwargs)
        if args:
            arg0 = args[0]
            if isinstance(arg0, tuple):
                if not arg0:
                    raise ValueError("坐标不能是空元组")
                if isinstance(arg0[0], int):
                    self._perform_tap(*self._to_abs(arg0), duration)
                elif isinstance(arg0[0], str):
                    raise NotImplementedError("webview 点击暂不支持")
            elif isinstance(arg0, str):
                pos = self._find_pos_by_ocr(arg0, index=args[1] if len(args) > 1 else 0)
                self._perform_tap(*pos, duration)
                self._perform_tap(*pos, duration)
            elif hasattr(arg0, 'filepath'):
                pos = self._find_pos_by_image(
                    arg0.filepath,
                    timeout=kwargs.get("timeout", 10),
                    threshold=kwargs.get("threshold", 0.8),
                )
                self._perform_tap(*pos, duration)
            elif isinstance(arg0, dict):
                self.driver.find(**arg0, **kwargs).tap(duration=duration) \
                    if hasattr(self.driver.find(**arg0), 'tap') \
                    else self._perform_tap(*self._get_element_center(**arg0), duration)
        elif kwargs.get("image"):
            path = os.path.join(global_config.current_path, kwargs["image"])
            grid = kwargs.pop("grid", None)
            splits = kwargs.pop("splits", None)
            if grid and splits:
                pos = click_inside_template(
                    path,
                    self.driver.screenshot,
                    (self.config.screen_width, self.config.screen_height),
                    grid=grid,
                    splits=splits,
                    threshold=kwargs.get("threshold", 0.8),
                    rgb=kwargs.get("rgb", False),
                    scale_max=kwargs.get("scale_max", 800),
                    scale_step=kwargs.get("scale_step", 0.005),
                )
            else:
                pos = self._find_pos_by_image(
                    path,
                    timeout=kwargs.get("timeout", 10),
                    threshold=kwargs.get("threshold", 0.8),
                )
            self._perform_tap(*pos, duration)
        else:
            timeout = kwargs.pop("timeout", 3)
            xpath = kwargs.pop("xpath", None)
            if xpath:
                self.driver.find_xpath(xpath).click(timeout=timeout)
            else:
                el = self.driver.find(**kwargs)
                # u2: .click(timeout=) / wda: .tap_hold() / harmony: .click()
                if hasattr(el, 'click'):
                    el.click(timeout=timeout)
                else:
                    el.tap_hold(duration=duration)

    @cost_time
    def double_click(self, *args, interval: float = 0.05, **kwargs) -> None:
        """双击元素。"""
        self.click(*args, **kwargs)
        time.sleep(interval)
        self.click(*args, **kwargs)

    @cost_time
    def long_press(self, *args, duration: float = 1.0, **kwargs) -> None:
        """长按元素。"""
        self.click(*args, duration=duration, **kwargs)

    # ── 滑动 ──────────────────────────────────────────────────────────────────

    @cost_time
    def swipe(self, p1, p2, duration=None, steps=None) -> None:
        """滑动，坐标支持绝对像素或 0-1 比例。"""
        pos1 = self._to_abs(p1)
        pos2 = self._to_abs(p2)
        self.driver.swipe(pos1[0], pos1[1], pos2[0], pos2[1],
                          duration=duration, steps=steps)

    @cost_time
    def swipe_up(self, duration: float = 0.2, steps=None) -> None:
        self.swipe((0.5, 0.8), (0.5, 0.3), duration, steps)

    @cost_time
    def swipe_down(self, duration: float = 0.2, steps=None) -> None:
        self.swipe((0.5, 0.3), (0.5, 0.8), duration, steps)

    @cost_time
    def swipe_left(self, duration: float = 0.1, steps=None) -> None:
        self.swipe((0.8, 0.5), (0.2, 0.5), duration, steps)

    @cost_time
    def swipe_right(self, duration: float = 0.1, steps=None) -> None:
        self.swipe((0.2, 0.5), (0.8, 0.5), duration, steps)

    @cost_time
    def popup_apps(self) -> None:
        """呼出多任务界面。"""
        self.swipe((0.5, 0.999), (0.5, 0.6), 0.1)

    @cost_time
    def drag(self, *args, dx: int = 0, dy: int = 0, duration: float = 0.5, **kwargs) -> None:
        """拖拽元素（偏移 dx/dy 像素）。支持 Selector 对象 / canonical kwargs。"""
        args, kwargs = self._resolve_selector(args, kwargs)
        if not args and not kwargs:
            raise ValueError("drag() 需要元素定位参数")
        center = self._get_element_center(**kwargs)
        self.driver.swipe(center[0], center[1],
                          center[0] + dx, center[1] + dy,
                          duration=duration)

    # ── 系统按键 ──────────────────────────────────────────────────────────────

    @cost_time
    def key(self, key_name: str) -> None:
        self.driver.press(key_name)

    @cost_time
    def home(self) -> None:
        self.driver.press("home")
