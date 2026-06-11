# -*- coding: utf-8 -*-
"""
BaseDriver: 所有平台驱动的抽象基类。
每个平台实现此接口，Device 层统一通过 BaseDriver 方法调用，
消灭 api.py / __init__.py 中散落的 if platform == 判断。
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import PIL.Image


class BaseDriver(ABC):

    # ── 连接 / 断开 ──────────────────────────────────────────────

    @abstractmethod
    def connect(self, serial: Optional[str] = None, **kwargs) -> str:
        """
        连接设备，返回实际使用的序列号。
        :raises DeviceConnectionError: 连接失败
        """

    # ── 设备信息 ─────────────────────────────────────────────────

    @abstractmethod
    def get_device_info(self) -> dict:
        """返回设备基本信息字典（productName/model/serial 等）。"""

    @abstractmethod
    def screen_size(self) -> Tuple[int, int]:
        """返回屏幕分辨率 (width, height)。"""

    # ── 截图 ─────────────────────────────────────────────────────

    @abstractmethod
    def screenshot(self) -> PIL.Image.Image:
        """截图并返回 PIL.Image.Image 对象。"""

    # ── 点击 / 手势 ──────────────────────────────────────────────

    @abstractmethod
    def tap(self, x: int, y: int, duration: float = 0.1) -> None:
        """单击坐标点，duration 为按压时长（秒）。"""

    @abstractmethod
    def swipe(self, x1: int, y1: int, x2: int, y2: int,
              duration: Optional[float] = None, steps: Optional[int] = None) -> None:
        """从 (x1,y1) 滑动到 (x2,y2)。"""

    @abstractmethod
    def press(self, key: str) -> None:
        """模拟系统按键，如 home / back / menu。"""

    # ── 原生元素查找（u2/wda 属性定位） ──────────────────────────

    @abstractmethod
    def find(self, **kwargs):
        """
        根据 u2/wda/hmdriver2 属性定位元素，返回平台原生元素对象。
        上层通过此方法拿到元素后自行调用 .click() / .exists 等。
        """

    @abstractmethod
    def find_xpath(self, xpath: str):
        """通过 xpath 定位元素，返回平台原生元素对象。"""

    # ── 应用管理 ─────────────────────────────────────────────────

    @abstractmethod
    def app_start(self, app_name: str, activity: Optional[str] = None) -> None:
        """启动应用。"""

    @abstractmethod
    def app_stop(self, app_name: str) -> None:
        """停止应用。"""

    @abstractmethod
    def app_current(self) -> str:
        """返回当前前台应用的包名/bundleId。"""

    def app_clear(self, app_name: str) -> None:
        """清除应用数据（默认不支持，子类按需覆写）。"""
        raise NotImplementedError(f"{self.__class__.__name__} 不支持 app_clear")

    # ── 文件传输 ─────────────────────────────────────────────────

    def push_file(self, local_path: str, remote_path: str) -> None:
        """上传文件到设备（默认不支持，子类按需覆写）。"""
        raise NotImplementedError(f"{self.__class__.__name__} 不支持 push_file")

    def pull_file(self, remote_path: str, local_path: str) -> None:
        """从设备下载文件（默认不支持，子类按需覆写）。"""
        raise NotImplementedError(f"{self.__class__.__name__} 不支持 pull_file")

    def delete_file(self, remote_path: str) -> None:
        """删除设备上的文件（默认不支持，子类按需覆写）。"""
        raise NotImplementedError(f"{self.__class__.__name__} 不支持 delete_file")
