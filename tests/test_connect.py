# -*- coding: utf-8 -*-
import json
import unittest
from unittest.mock import MagicMock, patch

from ha4t import connect, Device


class TestDeviceConnect(unittest.TestCase):
    """验证 connect() 返回正确的 Device 实例，config 字段匹配预期。"""

    @patch('ha4t.drivers.android.u2.connect')
    def test_connect_android(self, mock_u2_connect):
        mock_d = MagicMock()
        mock_d.window_size.return_value = (1080, 1920)
        mock_d.adb_device.serial = "123456"
        mock_d.info = {"serial": "123456"}
        mock_u2_connect.return_value = mock_d

        dev = connect(platform="android", device_serial="123456")

        self.assertIsInstance(dev, Device)
        self.assertEqual(dev.config.platform, "android")
        self.assertEqual(dev.config.device_serial, "123456")
        self.assertEqual(dev.config.screen_size, (1080, 1920))

    @patch('ha4t.drivers.ios.wda.USBClient')
    @patch('ha4t.drivers.ios.wda.list_devices')
    def test_connect_ios(self, mock_list_devices, mock_wda_client):
        mock_list_devices.return_value = [MagicMock(serial="ios-udid")]
        mock_d = MagicMock()
        mock_d.window_size.return_value = (375, 667)
        mock_d.info = {"productName": "iPhone"}
        mock_wda_client.return_value = mock_d

        dev = connect(platform="ios", device_serial="ios-udid")

        self.assertIsInstance(dev, Device)
        self.assertEqual(dev.config.platform, "ios")
        self.assertEqual(dev.config.device_serial, "ios-udid")
        self.assertEqual(dev.config.screen_size, (375, 667))

    @patch('ha4t.drivers.harmony.HarmonyDriver.connect')
    def test_connect_harmony(self, mock_hm_connect):
        # HarmonyDriver.connect 返回序列号
        mock_hm_connect.return_value = "hm-serial"

        # 同时 mock screen_size 和 get_device_info
        with patch('ha4t.drivers.harmony.HarmonyDriver.screen_size',
                   return_value=(1260, 2720)), \
             patch('ha4t.drivers.harmony.HarmonyDriver.get_device_info',
                   return_value={"productName": "Mate60", "serial": "hm-serial"}):
            dev = connect(platform="harmony", device_serial="hm-serial")

        self.assertIsInstance(dev, Device)
        self.assertEqual(dev.config.platform, "harmony")
        self.assertEqual(dev.config.device_serial, "hm-serial")
        self.assertEqual(dev.config.screen_size, (1260, 2720))


    @patch('ha4t.drivers.android.u2.connect')
    def test_connect_two_devices_independent(self, mock_u2_connect):
        d1, d2 = MagicMock(), MagicMock()
        d1.window_size.return_value = (1080, 1920)
        d1.adb_device.serial = "dev-A"
        d1.info = {}
        d2.window_size.return_value = (720, 1280)
        d2.adb_device.serial = "dev-B"
        d2.info = {}
        mock_u2_connect.side_effect = [d1, d2]
        a = connect(platform="android", device_serial="dev-A")
        b = connect(platform="android", device_serial="dev-B")
        self.assertIsNot(a, b)
        self.assertEqual(a.config.device_serial, "dev-A")
        self.assertEqual(b.config.device_serial, "dev-B")
        self.assertEqual(a.config.screen_size, (1080, 1920))
        self.assertEqual(b.config.screen_size, (720, 1280))

    def test_legacy_api_removed(self):
        import importlib
        with self.assertRaises(ImportError):
            importlib.import_module('ha4t.api')
        from ha4t import config as cfg_mod
        self.assertFalse(hasattr(cfg_mod, 'Config'))
        import ha4t as pkg
        self.assertFalse(hasattr(pkg, 'device'))
        self.assertFalse(hasattr(pkg, '_active_device'))

class TestDriverAbstraction(unittest.TestCase):
    """验证各平台 driver 的 tap/screen_size 分派正确。"""

    @patch('ha4t.drivers.android.u2.connect')
    def test_android_tap_calls_long_click(self, mock_u2_connect):
        mock_d = MagicMock()
        mock_u2_connect.return_value = mock_d

        from ha4t.drivers.android import AndroidDriver
        drv = AndroidDriver()
        drv._d = mock_d
        drv.tap(100, 200, 0.1)

        mock_d.long_click.assert_called_once_with(100, 200, duration=0.1)

    def test_ios_tap_calls_tap_hold(self):
        from ha4t.drivers.ios import IOSDriver
        mock_d = MagicMock()
        drv = IOSDriver()
        drv._d = mock_d
        drv.tap(50, 80, 0.2)

        mock_d.tap_hold.assert_called_once_with(50, 80, duration=0.2)

    def test_android_screen_size_delegates(self):
        from ha4t.drivers.android import AndroidDriver
        mock_d = MagicMock()
        mock_d.window_size.return_value = (1080, 2340)
        drv = AndroidDriver()
        drv._d = mock_d

        self.assertEqual(drv.screen_size(), (1080, 2340))


if __name__ == '__main__':
    unittest.main()
