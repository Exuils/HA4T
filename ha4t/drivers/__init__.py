# -*- coding: utf-8 -*-
"""
drivers 工厂模块。

用法：
    from ha4t.drivers import DRIVERS
    driver = DRIVERS["android"]()
    serial = driver.connect("emulator-5554")
"""
from ha4t.drivers.base import BaseDriver
from ha4t.drivers.android import AndroidDriver
from ha4t.drivers.ios import IOSDriver
from ha4t.drivers.harmony import HarmonyDriver

DRIVERS: dict[str, type[BaseDriver]] = {
    "android": AndroidDriver,
    "ios": IOSDriver,
    "harmony": HarmonyDriver,
}

__all__ = ["BaseDriver", "AndroidDriver", "IOSDriver", "HarmonyDriver", "DRIVERS"]
