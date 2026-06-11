# -*- coding: utf-8 -*-
"""IOSDriver: 基于 facebook-wda 的 iOS 平台驱动。"""
import os
import subprocess
from typing import Optional, Tuple

import PIL.Image
import wda

from ha4t.drivers.base import BaseDriver
from ha4t.exceptions import DeviceConnectionError


class IOSDriver(BaseDriver):

    def __init__(self):
        self._d: Optional[wda.Client] = None
        self._serial: str = ''

    # ── 连接 ─────────────────────────────────────────────────────

    def connect(self, serial: Optional[str] = None, port: int = 8100, **kwargs) -> str:
        try:
            self._serial = serial or wda.list_devices()[0].serial
        except IndexError as e:
            raise DeviceConnectionError("未找到 iOS 设备，请检查 USB 连接和信任设置") from e
        try:
            self._d = wda.USBClient(udid=self._serial, port=port)
        except Exception as e:
            raise DeviceConnectionError(f"iOS 设备 {self._serial} 连接失败：{e}") from e
        return self._serial

    # ── 设备信息 ─────────────────────────────────────────────────

    def get_device_info(self) -> dict:
        info = dict(self._d.info)
        info["serial"] = self._serial
        return info

    def screen_size(self) -> Tuple[int, int]:
        return self._d.window_size()

    # ── 截图 ─────────────────────────────────────────────────────

    def screenshot(self) -> PIL.Image.Image:
        img = self._d.screenshot()
        if isinstance(img, PIL.Image.Image):
            return img
        return img

    # ── 点击 / 手势 ──────────────────────────────────────────────

    def tap(self, x: int, y: int, duration: float = 0.1) -> None:
        # iOS 用 tap_hold 实现按压
        self._d.tap_hold(x, y, duration=duration)

    def swipe(self, x1: int, y1: int, x2: int, y2: int,
              duration: Optional[float] = None, steps: Optional[int] = None) -> None:
        # wda 的 swipe 不支持 steps，忽略该参数
        self._d.swipe(x1, y1, x2, y2, duration=duration)

    def press(self, key: str) -> None:
        self._d.press(key)

    # ── 元素查找 ─────────────────────────────────────────────────

    def find(self, **kwargs):
        return self._d(**kwargs)

    def find_xpath(self, xpath: str):
        return self._d.xpath(xpath)

    def get_element_center(self, **kwargs):
        el = self._d(**kwargs)
        rect = el.bounds
        return (int(rect.origin.x + rect.size.width / 2),
                int(rect.origin.y + rect.size.height / 2))

    # ── 应用管理 ─────────────────────────────────────────────────

    def app_start(self, app_name: str, activity: Optional[str] = None) -> None:
        self._d.app_start(app_name)

    def app_stop(self, app_name: str) -> None:
        self._d.app_stop(app_name)

    def app_current(self) -> str:
        return self._d.app_current()["bundleId"]

    # ── 文件传输（tidevice / t3） ────────────────────────────────

    def push_file(self, local_path: str, remote_path: str, app_name: str = '') -> None:
        """remote_path 是 app 容器内相对路径，例如 Documents/xxx"""
        if not app_name:
            raise ValueError("iOS push_file 需要传入 app_name")
        subprocess.run(
            ["tidevice", '-u', self._serial, 'fsync', '-B', app_name,
             'push', local_path, remote_path],
            check=True
        )

    def pull_file(self, remote_path: str, local_path: str, app_name: str = '') -> None:
        """通过 t3 fsync pull 拉取 app 容器内文件。"""
        if not app_name:
            raise ValueError("iOS pull_file 需要传入 app_name")
        cmd = f"t3 fsync -B {app_name} pull {remote_path} {local_path}"
        subprocess.run(cmd, shell=True, check=True)

    def delete_file(self, remote_path: str, app_name: str = '') -> None:
        if not app_name:
            raise ValueError("iOS delete_file 需要传入 app_name")
        subprocess.run(
            ["tidevice", '-u', self._serial, 'fsync', '-B', app_name,
             'rmtree', remote_path],
            check=True
        )

    def mkdir(self, remote_path: str, app_name: str = '') -> None:
        subprocess.run(
            ["tidevice", '-u', self._serial, 'fsync', '-B', app_name,
             'mkdir', remote_path],
            check=True
        )
