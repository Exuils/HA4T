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
from ha4t.editor._models import Platform, BaseHierarchy, CurrentApp
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

    def current_app(self) -> Optional[CurrentApp]:
        """返回当前前台应用 {package, activity?}；失败/不支持返回 None。

        默认实现 None；子类按平台覆盖。dump_hierarchy 内会调一次填入 BaseHierarchy.currentApp，
        UI header 用来显示「当前页面：xxx」。app_current 抛错时一律吞掉返 None —— 显示功能
        不能拖累 hierarchy 主流程。
        """
        return None

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
            currentApp=self.current_app(),
        )

    def current_app(self) -> Optional[CurrentApp]:
        try:
            # hmdriver2 HdcWrapper.current_app() → (bundle, ability) or (None, None)
            pkg, page = self.hdc.current_app()
        except Exception:
            return None
        if not pkg:
            return None
        return CurrentApp(package=pkg, activity=page or None)

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
        # hierarchy dump 走 uiautomator2 jsonrpc，current_app 走 adb shell dumpsys，
        # 是两条独立通道，IO 并行能省下 current_app 那 ~100-300ms（不阻塞主路径）。
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f_hier = ex.submit(self.d.dump_hierarchy)
            f_app  = ex.submit(self.current_app)
            page_xml = f_hier.result()
            current = f_app.result()
        page_json = android_hierarchy.convert_android_hierarchy(page_xml)
        return BaseHierarchy(
            jsonHierarchy=page_json,
            windowSize=self._window_size,
            scale=1,
            currentApp=current,
        )

    # 缓存正则：第一条是 Android 焦点窗口的标准格式，第二条是 mFocusedApp 兜底
    # （某些 OEM ROM 上 mCurrentFocus 偶尔会改写但 mFocusedApp 一直在）。
    _RE_FOCUS_PATTERNS = None

    def current_app(self) -> Optional[CurrentApp]:
        """单次 `dumpsys window` 抽 mCurrentFocus / mFocusedApp 拿当前焦点窗口。

        实测对比这台 Moto API 34 设备：
          - u2.app_current()              ~10000ms（最坏 3 次 dumpsys fallback）
          - dumpsys window                ~100ms，含 mCurrentFocus  ← 用这个
          - dumpsys window windows        ~75ms 但不含 mCurrentFocus（OEM 差异）

        失败 / 解析不出来 → 返 None，UI 隐藏「当前页面」标签即可，不影响主流程。
        """
        import re
        if AndroidDevice._RE_FOCUS_PATTERNS is None:
            AndroidDevice._RE_FOCUS_PATTERNS = [
                # mCurrentFocus=Window{<hash> u0 com.x.y/.MainActivity}
                re.compile(r"mCurrentFocus=Window\{[^}]*\s(?P<package>[^\s/]+)/(?P<activity>[^\s}]+)\}"),
                # mFocusedApp=ActivityRecord{<hash> u0 com.x.y/.MainActivity t<task>}
                re.compile(r"mFocusedApp=ActivityRecord\{[^}]*\s(?P<package>[^\s/]+)/(?P<activity>[^\s}]+)\s"),
            ]
        try:
            out = self.d.shell(["dumpsys", "window"]).output
        except Exception:
            return None
        for pat in AndroidDevice._RE_FOCUS_PATTERNS:
            m = pat.search(out or "")
            if m:
                pkg = m.group("package")
                act = m.group("activity")
                if pkg:
                    return CurrentApp(package=pkg, activity=act or None)
        return None

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
            currentApp=self.current_app(),
        )

    def current_app(self) -> Optional[CurrentApp]:
        try:
            # wda → {'pid', 'name', 'bundleId', 'processArguments'}；name 是 VC 标题（可能空）
            info = self.client.app_current()
        except Exception:
            return None
        if not info:
            return None
        return CurrentApp(
            package=info.get('bundleId') or None,
            activity=info.get('name') or None,   # iOS 用 VC name 作 activity 槽位
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