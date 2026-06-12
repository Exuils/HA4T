# -*- coding: utf-8 -*-

import abc
import os
import traceback
import tempfile
from typing import List, Dict, Optional, Union, Tuple
from functools import cached_property  # python3.8+

from PIL import Image
from requests import request
import tidevice
import adbutils
import wda
import uiautomator2 as u2
from hmdriver2 import hdc
from fastapi import HTTPException

from ha4t.editor._logger import logger
from ha4t.editor._utils import file2base64, image2base64
from ha4t.editor._models import Platform, BaseHierarchy
from ha4t.editor.parser import android_hierarchy, ios_hierarchy, harmony_hierarchy


def list_serials(platform: str) -> List[str]:
    devices = []
    if platform == Platform.ANDROID:
        raws = adbutils.AdbClient().device_list()
        devices = [item.serial for item in raws]
    elif platform == Platform.IOS:
        raw = tidevice.Usbmux().device_list()
        devices = [d.udid for d in raw]
    else:
        try:
            devices = hdc.list_devices()
        except Exception:
            pass

    return devices


class DeviceMeta(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def take_screenshot(self) -> str:
        pass

    def dump_hierarchy(self) -> Dict:
        pass

    @abc.abstractmethod
    def find_element_rect(self, selector: Dict) -> Optional[Dict]:
        """根据 selector dict 在当前设备上查找元素。

        返回 {'x': int, 'y': int, 'width': int, 'height': int} 或 None。
        selector 含 'image' key 由调用方拦截，本方法不应被调用到 image 元素。
        """


class HarmonyDevice(DeviceMeta):
    def __init__(self, serial: str):
        self.serial = serial
        self.hdc = hdc.HdcWrapper(serial)

    @cached_property
    def _display_size(self) -> Tuple:
        return self.hdc.display_size()

    def take_screenshot(self) -> str:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        try:
            # adapt windows
            temp_file.close()
            path = temp_file.name
            self.hdc.screenshot(path)
            return file2base64(path)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def dump_hierarchy(self) -> BaseHierarchy:
        raw: Dict = self.hdc.dump_hierarchy()
        hierarchy: Dict = harmony_hierarchy.convert_harmony_hierarchy(raw)
        return BaseHierarchy(
            jsonHierarchy=hierarchy,
            windowSize=self._display_size,
            scale=1,
        )

    def find_element_rect(self, selector: Dict) -> Optional[Dict]:
        # HdcWrapper 不暴露元素查找；返回 None 让前端标记为「不支持」
        return None


class AndroidDevice(DeviceMeta):
    def __init__(self, serial: str):
        self.serial = serial
        self.d: u2.Device = u2.connect(serial)

    @cached_property
    def _window_size(self) -> Tuple:
        return self.d.window_size()

    def take_screenshot(self) -> str:
        img: Image.Image = self.d.screenshot()
        return image2base64(img)

    def dump_hierarchy(self) -> BaseHierarchy:
        page_xml = self.d.dump_hierarchy()
        page_json = android_hierarchy.convert_android_hierarchy(page_xml)
        return BaseHierarchy(
            jsonHierarchy=page_json,
            windowSize=self._window_size,
            scale=1,
        )

    def find_element_rect(self, selector: Dict) -> Optional[Dict]:
        kw = {k: v for k, v in selector.items() if k in
              ('text', 'resourceId', 'className', 'description', 'index')}
        xpath = selector.get('xpath')
        try:
            if xpath:
                el = self.d.xpath(xpath)
                if not el.exists:
                    return None
                info = el.info
            else:
                if not kw:
                    return None
                el = self.d(**kw)
                if not el.exists:
                    return None
                info = el.info
        except Exception:
            return None
        b = info.get('bounds') or {}
        # u2 element.info['bounds'] 形如 {'left':,'top':,'right':,'bottom':}
        if not b or 'left' not in b:
            return None
        return {'x': b['left'], 'y': b['top'],
                'width': b['right'] - b['left'],
                'height': b['bottom'] - b['top']}


class IosDevice(DeviceMeta):
    def __init__(self, udid: str, wda_url: str, max_depth: int) -> None:
        self.udid = udid
        self.wda_url = wda_url
        self._max_depth = max_depth
        self.client = wda.Client(wda_url)

    @property
    def max_depth(self) -> int:
        return int(self._max_depth) if self._max_depth else 30

    @cached_property
    def scale(self) -> int:
        return self.client.scale

    @cached_property
    def _window_size(self) -> Tuple:
        return self.client.window_size()

    def _check_wda_health(self) -> bool:
        resp = request("GET", f"{self.wda_url}/status", timeout=5).json()
        state = resp.get("value", {}).get("state")
        return state == "success"

    def take_screenshot(self) -> str:
        img: Image.Image = self.client.screenshot()
        return image2base64(img)

    def dump_hierarchy(self) -> BaseHierarchy:
        self.client.appium_settings({"snapshotMaxDepth": self.max_depth})
        data: Dict = self.client.source(format="json")
        hierarchy: Dict = ios_hierarchy.convert_ios_hierarchy(data, self.scale)
        return BaseHierarchy(
            jsonHierarchy=hierarchy,
            windowSize=self._window_size,
            scale=self.scale,
        )

    def find_element_rect(self, selector: Dict) -> Optional[Dict]:
        # iOS WDA 不支持 resourceId；按 best-effort 映射到 wda 查询参数
        kw = {}
        if selector.get('text'):
            kw['label'] = selector['text']
        if selector.get('className'):
            kw['className'] = selector['className']
        if selector.get('description'):
            kw['name'] = selector['description']
        xpath = selector.get('xpath')
        try:
            if xpath:
                el = self.client.xpath(xpath)
            else:
                if not kw:
                    return None
                el = self.client(**kw)
            if not el.exists:
                return None
            bounds = el.bounds  # wda Rect：x, y, width, height（point space）
        except Exception:
            return None
        # 乘 scale 转 pixel space（与 hierarchy rect 同坐标系）
        s = self.scale or 1
        return {'x': int(bounds.x * s), 'y': int(bounds.y * s),
                'width': int(bounds.width * s), 'height': int(bounds.height * s)}


def get_device(platform: str, serial: str, wda_url: str, max_depth: int) -> Union[HarmonyDevice, AndroidDevice, IosDevice]:
    if platform == Platform.HARMONY:
        return HarmonyDevice(serial)
    elif platform == Platform.ANDROID:
        return AndroidDevice(serial)
    else:
        return IosDevice(serial, wda_url, max_depth)


# Global cache for devices
cached_devices = {}


def init_device(platform: str, serial: str, wda_url: str, max_depth: int):

    if serial not in list_serials(platform):
        logger.error(f"Device<{serial}> not found")
        raise HTTPException(status_code=500, detail=f"Device<{serial}> not found")

    try:
        device: Union[HarmonyDevice, AndroidDevice] = get_device(platform, serial, wda_url, max_depth)
        cached_devices[(platform, serial)] = device

        if isinstance(device, IosDevice):
            return device._check_wda_health()
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

    return True