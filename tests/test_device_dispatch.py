# -*- coding: utf-8 -*-
"""Device 入口 Selector / canonical kwargs 路由测试 —— 用 fake driver 隔离真机。

验证 `dev._resolve_selector` 的两条路径：
  1. SelectorObj 位置参数 → for_platform(self.platform) → native kwargs
  2. raw kwargs → to_native(kwargs, self.platform) canonical → native 翻译

外加 image fallback、平台缺失 raise、cost_time 剥 `_` 前缀 meta 的兜底。
"""
import unittest
from unittest.mock import MagicMock

from ha4t import Device, Selector, SelectorNotAvailableError
from ha4t.config import DeviceConfig


def _make_dev(platform: str) -> Device:
    """构造一个挂着 MagicMock driver 的 Device，避免真机依赖。"""
    cfg = DeviceConfig()
    cfg.platform = platform
    cfg.screen_size = (1080, 2400)
    cfg.screen_width = 1080
    cfg.screen_height = 2400
    drv = MagicMock(name=f"{platform}-driver")
    drv.find.return_value = MagicMock(exists=True, info={"bounds": {"left": 0, "top": 0, "right": 10, "bottom": 10}})
    return Device(driver=drv, config=cfg)


class TestResolveSelectorObject(unittest.TestCase):
    """传入 Selector 对象时正确解出当前平台 native kwargs。"""

    def test_android_picks_android_bucket(self):
        dev = _make_dev("android")
        sel = Selector(android={"text": "登录"}, ios={"label": "Login"})
        args, kwargs = dev._resolve_selector((sel,), {})
        self.assertEqual(args, ())
        self.assertEqual(kwargs, {"text": "登录"})

    def test_ios_picks_ios_bucket(self):
        dev = _make_dev("ios")
        sel = Selector(android={"text": "登录"}, ios={"label": "Login"})
        args, kwargs = dev._resolve_selector((sel,), {})
        self.assertEqual(kwargs, {"label": "Login"})

    def test_missing_platform_raises(self):
        dev = _make_dev("harmony")
        sel = Selector(android={"text": "X"})
        with self.assertRaises(SelectorNotAvailableError):
            dev._resolve_selector((sel,), {})

    def test_image_fallback_when_platform_bucket_missing(self):
        dev = _make_dev("ios")
        sel = Selector(image="login.png")   # 跨平台共享图像
        args, kwargs = dev._resolve_selector((sel,), {})
        self.assertEqual(kwargs, {"image": "login.png"})

    def test_caller_kwargs_preserved_alongside_selector(self):
        """timeout 等动作参数仍随 Selector 路径透传给底层。"""
        dev = _make_dev("android")
        sel = Selector(android={"text": "X"})
        args, kwargs = dev._resolve_selector((sel,), {"timeout": 5})
        self.assertEqual(kwargs, {"timeout": 5, "text": "X"})

    def test_meta_fields_not_in_native_kwargs(self):
        """`_parent`/`_doc` 永远不到 driver。"""
        dev = _make_dev("android")
        sel = Selector(_parent="顶部", _doc="说明", android={"text": "X"})
        _, kwargs = dev._resolve_selector((sel,), {})
        self.assertNotIn("_parent", kwargs)
        self.assertNotIn("_doc", kwargs)


class TestRawKwargsCanonicalMapping(unittest.TestCase):
    """raw kwargs 路径自动按当前平台翻译 canonical 字段。"""

    def test_text_passthrough_on_android(self):
        dev = _make_dev("android")
        _, kwargs = dev._resolve_selector((), {"text": "登录"})
        self.assertEqual(kwargs, {"text": "登录"})

    def test_text_maps_to_label_on_ios(self):
        """关键点：`dev.click(text=...)` 在 iOS 自动转 `label=`，不报"未知 kwarg"。"""
        dev = _make_dev("ios")
        _, kwargs = dev._resolve_selector((), {"text": "登录"})
        self.assertEqual(kwargs, {"label": "登录"})

    def test_label_maps_to_description_on_android(self):
        dev = _make_dev("android")
        _, kwargs = dev._resolve_selector((), {"label": "Back"})
        self.assertEqual(kwargs, {"description": "Back"})

    def test_resource_id_maps_to_name_on_ios(self):
        dev = _make_dev("ios")
        _, kwargs = dev._resolve_selector((), {"resourceId": "loginBtn"})
        self.assertEqual(kwargs, {"name": "loginBtn"})

    def test_no_platform_no_mapping(self):
        """没连接设备（platform 为空）时不做映射，等同原 raw kwargs 透传。"""
        cfg = DeviceConfig()
        cfg.platform = ""
        dev = Device(driver=MagicMock(), config=cfg)
        _, kwargs = dev._resolve_selector((), {"text": "X"})
        self.assertEqual(kwargs, {"text": "X"})


class TestOtherArgFormsUntouched(unittest.TestCase):
    """元组坐标、字符串 OCR、Template 等非 Selector args 不被 _resolve_selector 修改。"""

    def test_tuple_coords_preserved(self):
        dev = _make_dev("android")
        args, kwargs = dev._resolve_selector(((100, 200),), {})
        self.assertEqual(args, ((100, 200),))
        self.assertEqual(kwargs, {})

    def test_string_ocr_preserved(self):
        dev = _make_dev("android")
        args, kwargs = dev._resolve_selector(("文字",), {})
        self.assertEqual(args, ("文字",))

    def test_template_object_preserved(self):
        dev = _make_dev("android")
        tmpl = MagicMock()
        tmpl.filepath = "x.png"
        args, _ = dev._resolve_selector((tmpl,), {})
        self.assertIs(args[0], tmpl)


if __name__ == "__main__":
    unittest.main()
