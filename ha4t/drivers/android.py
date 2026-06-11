# -*- coding: utf-8 -*-
"""AndroidDriver: 基于 uiautomator2 的 Android 平台驱动。"""
import subprocess
from typing import Optional, Tuple

import PIL.Image
import uiautomator2 as u2

from ha4t.drivers.base import BaseDriver
from ha4t.exceptions import DeviceConnectionError


class AndroidDriver(BaseDriver):

    def __init__(self):
        self._d: Optional[u2.Device] = None

    # ── 连接 ─────────────────────────────────────────────────────

    def connect(self, serial: Optional[str] = None, **kwargs) -> str:
        try:
            self._d = u2.connect(serial=serial)
            return self._d.adb_device.serial
        except Exception as e:
            raise DeviceConnectionError(
                f"Android 设备 {serial or '默认设备'} 连接失败：{e}"
            ) from e

    # ── 设备信息 ─────────────────────────────────────────────────

    def get_device_info(self) -> dict:
        info = self._d.info
        info["serial"] = self._d.adb_device.serial
        return info

    def screen_size(self) -> Tuple[int, int]:
        return self._d.window_size()

    # ── 截图 ─────────────────────────────────────────────────────

    def screenshot(self) -> PIL.Image.Image:
        img = self._d.screenshot()
        if isinstance(img, PIL.Image.Image):
            return img
        import numpy as np
        return PIL.Image.fromarray(img) if hasattr(img, '__array__') else img

    # ── 点击 / 手势 ──────────────────────────────────────────────

    def tap(self, x: int, y: int, duration: float = 0.1) -> None:
        self._d.long_click(x, y, duration=duration)

    def swipe(self, x1: int, y1: int, x2: int, y2: int,
              duration: Optional[float] = None, steps: Optional[int] = None) -> None:
        self._d.swipe(x1, y1, x2, y2, duration=duration, steps=steps)

    def press(self, key: str) -> None:
        self._d.press(key)

    # ── 元素查找 ─────────────────────────────────────────────────

    def find(self, **kwargs):
        return self._d(**kwargs)

    def find_xpath(self, xpath: str):
        return self._d.xpath(xpath)

    def get_element_center(self, **kwargs):
        el = self._d(**kwargs)
        return el.center()

    # ── 应用管理 ─────────────────────────────────────────────────

    def app_start(self, app_name: str, activity: Optional[str] = None) -> None:
        self._d.adb_device.app_start(app_name, activity)

    def app_stop(self, app_name: str) -> None:
        self._d.app_stop(app_name)

    def app_current(self) -> str:
        return self._d.adb_device.app_current().package

    def app_clear(self, app_name: str) -> None:
        self._d.adb_device.app_clear(app_name)

    # ── 文件传输（adb） ──────────────────────────────────────────

    def push_file(self, local_path: str, remote_path: str) -> None:
        serial = self._d.adb_device.serial
        subprocess.run(
            f"adb -s {serial} push {local_path} {remote_path}",
            shell=True, check=True
        )

    def pull_file(self, remote_path: str, local_path: str) -> None:
        serial = self._d.adb_device.serial
        subprocess.run(
            f"adb -s {serial} pull {remote_path} {local_path}",
            shell=True, check=True
        )

    def delete_file(self, remote_path: str) -> None:
        serial = self._d.adb_device.serial
        subprocess.run(
            f"adb -s {serial} shell rm -r {remote_path}",
            shell=True, check=True
        )

    # ── 暴露底层 driver（供 cdp 等需要 adb_device 的模块使用） ──

    @property
    def adb_device(self):
        return self._d.adb_device
