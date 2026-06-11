# -*- coding: utf-8 -*-
"""HarmonyDriver: 基于 hmdriver2 的鸿蒙平台驱动。"""
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Tuple

import PIL.Image

from ha4t.drivers.base import BaseDriver
from ha4t.exceptions import DeviceConnectionError


def _setup_builtin_hdc():
    """将内置 HDC 二进制目录加入 PATH（仅在首次调用时生效）。"""
    base_path = os.path.dirname(os.path.dirname(__file__))  # ha4t/
    if sys.platform == "win32":
        hdc_dir = os.path.join(base_path, "binaries", "hdc", "windows")
    elif sys.platform == "darwin":
        hdc_dir = os.path.join(base_path, "binaries", "hdc", "darwin")
    else:
        hdc_dir = os.path.join(base_path, "binaries", "hdc", "linux")

    if os.path.exists(hdc_dir) and hdc_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = hdc_dir + os.pathsep + os.environ.get("PATH", "")


def _ensure_hdc():
    """确保 hdc 可用，尝试通过 hdc-installer 自动安装。"""
    _setup_builtin_hdc()
    if shutil.which("hdc"):
        return
    from ha4t.utils.log_utils import log_out
    log_out("未检测到 HDC，尝试通过 hdc-installer 自动修复环境...")
    try:
        subprocess.run([sys.executable, "-m", "hdc_installer"], check=True)
        if shutil.which("hdc"):
            log_out("HDC 环境修复成功！")
            return
    except (ImportError, subprocess.CalledProcessError) as e:
        log_out(f"自动修复失败: {e}，请手动安装：pip install hdc-installer && hdc-install", 2)


class HarmonyDriver(BaseDriver):

    def __init__(self):
        self._d = None
        self._serial: str = ''

    # ── 连接 ─────────────────────────────────────────────────────

    def connect(self, serial: Optional[str] = None, **kwargs) -> str:
        _ensure_hdc()
        try:
            from hmdriver2.driver import Driver as HmDriver
            from hmdriver2 import hdc
        except ImportError as e:
            raise DeviceConnectionError(
                "缺少 hmdriver2 依赖，请安装：pip install hmdriver2"
            ) from e

        if not serial:
            try:
                devices = hdc.list_devices()
            except Exception as e:
                raise DeviceConnectionError(
                    f"HDC 设备扫描失败（请确保已通过 hdc-install 下载驱动）：{e}"
                ) from e
            if not devices:
                raise DeviceConnectionError("未找到 HarmonyOS 设备，请检查 HDC 连接及授权")
            serial = devices[0]

        self._serial = serial
        try:
            self._d = HmDriver(serial)
        except Exception as e:
            raise DeviceConnectionError(
                f"HarmonyOS 设备 {serial} 连接失败：{e}"
            ) from e
        return self._serial

    # ── 设备信息 ─────────────────────────────────────────────────

    def get_device_info(self) -> dict:
        info = self._d.device_info
        return {
            "productName": info.productName,
            "model": info.model,
            "sdkVersion": info.sdkVersion,
            "cpuAbi": info.cpuAbi,
            "serial": self._serial,
        }

    def screen_size(self) -> Tuple[int, int]:
        return self._d.display_size

    # ── 截图 ─────────────────────────────────────────────────────

    def screenshot(self) -> PIL.Image.Image:
        """hmdriver2 截图保存为临时文件，再读取为 PIL.Image 返回。"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp_path = tmp.name
        try:
            self._d.screenshot(tmp_path)
            return PIL.Image.open(tmp_path).copy()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ── 点击 / 手势 ──────────────────────────────────────────────

    def tap(self, x: int, y: int, duration: float = 0.1) -> None:
        self._d.long_click(x, y, duration=duration)

    def swipe(self, x1: int, y1: int, x2: int, y2: int,
              duration: Optional[float] = None, steps: Optional[int] = None) -> None:
        self._d.swipe(x1, y1, x2, y2, duration=duration)

    def press(self, key: str) -> None:
        self._d.press_key(key)

    # ── 元素查找 ─────────────────────────────────────────────────

    def find(self, **kwargs):
        return self._d(**kwargs)

    def find_xpath(self, xpath: str):
        return self._d.find_element(xpath=xpath)

    def get_element_center(self, **kwargs):
        raise NotImplementedError("Harmony 暂不支持元素坐标定位")

    # ── 应用管理 ─────────────────────────────────────────────────

    def app_start(self, app_name: str, activity: Optional[str] = None) -> None:
        self._d.start_app(app_name, activity)

    def app_stop(self, app_name: str) -> None:
        self._d.stop_app(app_name)

    def app_current(self) -> str:
        return self._d.get_current_app()
