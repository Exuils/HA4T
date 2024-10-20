__version__ = "0.0.5"
__all__ = ["__version__", "connect", "device", "driver", "Device", "screen_size"]

import json
from typing import Optional, Any, Union, Tuple
import wda
from ha4t.utils.log_utils import log_out
import uiautomator2 as u2
from ha4t.config import Config as _CF

class Device:
    def __init__(self):
        self.driver = None

    def connect(self, platform: str, device_serial: Optional[str] = None, port: int = 8100):
        self.adb: Optional[Any] = None
        if platform == "ios":
            try:
                _CF.DEVICE_SERIAL = device_serial or wda.list_devices()[0].serial
            except IndexError:
                raise IndexError("未找到设备，请检查连接")
            self.driver: wda.Client = wda.USBClient(udid=_CF.DEVICE_SERIAL, port=port)
        else:
            self.driver: u2.Device = u2.connect(serial=device_serial)
            self.adb = self.driver.adb_device
            _CF.DEVICE_SERIAL = self.adb.serial
        self.device_info = json.dumps(self.driver.info, ensure_ascii=False, indent=4)
        log_out(f"设备信息：{self.device_info}")

device: Device = Device()
screen_size: Tuple[int, int] = (0, 0)

def connect(device_serial=_CF.DEVICE_SERIAL, android_package_name=_CF.ANDROID_PACKAGE_NAME, android_activity_name=_CF.ANDROID_ACTIVITY_NAME, platform=_CF.PLATFORM):
    """
    连接设备
    """
    global device, driver, screen_size
    _CF.PLATFORM = platform
    _CF.DEVICE_SERIAL = device_serial
    device.connect(platform, device_serial)
    screen_size = device.driver.window_size()
    _CF.SCREEN_WIDTH, _CF.SCREEN_HEIGHT = screen_size
    _CF.ANDROID_PACKAGE_NAME = android_package_name
    _CF.ANDROID_ACTIVITY_NAME = android_activity_name
    _CF.DEVICE_SERIAL = device.driver.serial

