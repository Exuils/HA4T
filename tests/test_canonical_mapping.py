# -*- coding: utf-8 -*-
"""Canonical selector kwargs → 平台 native kwargs 的映射单测。"""
import unittest

from ha4t.selector import to_android, to_ios, to_harmony, to_native


class TestToAndroid(unittest.TestCase):
    def test_passthrough_native_fields(self):
        out = to_android({"text": "X", "resourceId": "r", "className": "C"})
        self.assertEqual(out, {"text": "X", "resourceId": "r", "className": "C"})

    def test_label_maps_to_description(self):
        """Android 没有 label 概念，canonical label → content-desc。"""
        out = to_android({"label": "Back"})
        self.assertEqual(out, {"description": "Back"})

    def test_description_preserved(self):
        out = to_android({"description": "cd"})
        self.assertEqual(out, {"description": "cd"})

    def test_label_does_not_clobber_description(self):
        """同时给 description + label → description 优先。"""
        out = to_android({"description": "raw", "label": "fallback"})
        self.assertEqual(out["description"], "raw")

    def test_empty_values_filtered(self):
        out = to_android({"text": "", "resourceId": "r"})
        self.assertEqual(out, {"resourceId": "r"})

    def test_unknown_fields_passthrough(self):
        """未识别字段保守透传，让 driver 自己报错而非静默改字段。"""
        out = to_android({"customField": "X"})
        self.assertEqual(out, {"customField": "X"})


class TestToIos(unittest.TestCase):
    def test_text_maps_to_label(self):
        out = to_ios({"text": "登录"})
        self.assertEqual(out, {"label": "登录"})

    def test_resource_id_maps_to_name(self):
        out = to_ios({"resourceId": "loginBtn"})
        self.assertEqual(out, {"name": "loginBtn"})

    def test_label_passthrough(self):
        out = to_ios({"label": "Login"})
        self.assertEqual(out, {"label": "Login"})

    def test_description_maps_to_label(self):
        out = to_ios({"description": "back hint"})
        self.assertEqual(out, {"label": "back hint"})

    def test_text_does_not_clobber_label(self):
        out = to_ios({"label": "primary", "text": "fallback"})
        self.assertEqual(out["label"], "primary")

    def test_index_dropped(self):
        """iOS index 语义跟 Android 差异大，不映射避免误导。"""
        out = to_ios({"index": 2, "label": "x"})
        self.assertNotIn("index", out)
        self.assertEqual(out["label"], "x")


class TestToHarmony(unittest.TestCase):
    def test_text_xpath_only(self):
        out = to_harmony({"text": "X", "xpath": "//a", "resourceId": "r", "label": "L"})
        self.assertEqual(out, {"text": "X", "xpath": "//a"})


class TestToNative(unittest.TestCase):
    def test_dispatches_by_platform(self):
        kw = {"text": "登录"}
        self.assertEqual(to_native(kw, "android"), {"text": "登录"})
        self.assertEqual(to_native(kw, "ios"), {"label": "登录"})

    def test_unknown_platform_passthrough(self):
        """未识别 platform 全量透传 —— 至少 driver 能给出准确报错。"""
        kw = {"text": "X"}
        self.assertEqual(to_native(kw, "web"), {"text": "X"})


if __name__ == "__main__":
    unittest.main()
