# -*- coding: utf-8 -*-
"""Selector 类单测：构造校验 / 不可变 / for_platform / format / repr 可逆 / 异常路径。"""
import unittest

from ha4t.selector import Selector, SelectorNotAvailableError


class TestSelectorConstruction(unittest.TestCase):
    def test_minimal_platform_bucket(self):
        s = Selector(android={"text": "X"})
        self.assertEqual(s.for_platform("android"), {"text": "X"})

    def test_multi_platform(self):
        s = Selector(android={"text": "登录"}, ios={"label": "Login"})
        self.assertEqual(s.platforms(), frozenset({"android", "ios"}))

    def test_image_only(self):
        s = Selector(image="login.png")
        self.assertEqual(s.image, "login.png")
        self.assertEqual(s.platforms(), frozenset())

    def test_meta_doc_and_parent(self):
        s = Selector(_parent="顶部", _doc="返回按钮", android={"text": "返回"})
        self.assertEqual(s.parent, "顶部")
        self.assertEqual(s.doc, "返回按钮")

    def test_meta_not_in_for_platform_output(self):
        """`_parent`/`_doc` 不能泄漏到 driver。"""
        s = Selector(_parent="X", _doc="Y", android={"text": "a"})
        out = s.for_platform("android")
        self.assertNotIn("_parent", out)
        self.assertNotIn("_doc", out)
        self.assertEqual(out, {"text": "a"})

    def test_image_excludes_platform_buckets(self):
        """image 与平台分桶互斥 —— 简化语义，禁止混用。"""
        with self.assertRaises(TypeError):
            Selector(image="x.png", android={"text": "Y"})

    def test_unknown_top_level_field_rejected(self):
        """`text=` 直接挂在 Selector 顶层 → 拒绝，提示放进平台分桶。"""
        with self.assertRaises(TypeError) as cm:
            Selector(text="X")
        self.assertIn("android={", str(cm.exception))

    def test_empty_selector_rejected(self):
        """既无 image 也无平台分桶 → 没有意义，拒绝。"""
        with self.assertRaises(ValueError):
            Selector()

    def test_platform_bucket_must_be_dict(self):
        with self.assertRaises(TypeError):
            Selector(android="text=X")


class TestSelectorImmutability(unittest.TestCase):
    def test_cannot_set_attributes(self):
        s = Selector(android={"text": "X"})
        with self.assertRaises(AttributeError):
            s._platforms = {}

    def test_construction_deep_copies_buckets(self):
        """外部修改传入的 dict 不能影响 Selector 内部状态。"""
        d = {"text": "原"}
        s = Selector(android=d)
        d["text"] = "改"
        self.assertEqual(s.for_platform("android"), {"text": "原"})

    def test_for_platform_returns_new_dict(self):
        """返回的 dict 修改不影响 Selector。"""
        s = Selector(android={"text": "X"})
        d = s.for_platform("android")
        d["text"] = "Y"
        self.assertEqual(s.for_platform("android"), {"text": "X"})


class TestForPlatform(unittest.TestCase):
    def test_image_fallback_when_platform_missing(self):
        s = Selector(image="x.png")
        self.assertEqual(s.for_platform("android"), {"image": "x.png"})
        self.assertEqual(s.for_platform("ios"), {"image": "x.png"})

    def test_platform_bucket_takes_precedence_over_image(self):
        """互斥规则下 image 与 platform 不会同时出现；但 supports() 区分。"""
        s = Selector(android={"text": "X"})
        self.assertTrue(s.supports("android"))
        self.assertFalse(s.supports("ios"))

    def test_raises_when_no_data_for_platform(self):
        s = Selector(android={"text": "X"})
        with self.assertRaises(SelectorNotAvailableError) as cm:
            s.for_platform("ios")
        self.assertIn("ios", str(cm.exception))


class TestSelectorTransforms(unittest.TestCase):
    def test_with_platform_returns_new_selector(self):
        s = Selector(android={"text": "old"})
        s2 = s.with_platform("ios", label="New")
        self.assertEqual(s.platforms(), frozenset({"android"}))
        self.assertEqual(s2.platforms(), frozenset({"android", "ios"}))
        self.assertEqual(s2.for_platform("ios"), {"label": "New"})

    def test_without_platform(self):
        s = Selector(android={"text": "X"}, ios={"label": "Y"})
        s2 = s.without_platform("ios")
        self.assertEqual(s2.platforms(), frozenset({"android"}))

    def test_without_last_platform_keeps_image_or_raises(self):
        s = Selector(android={"text": "X"})
        with self.assertRaises(ValueError):
            s.without_platform("android")

    def test_format_substitutes_placeholders(self):
        s = Selector(
            android={"xpath": "//View[{idx}]"},
            ios={"xpath": "//Cell[{idx}]"},
        )
        s2 = s.format(idx=3)
        self.assertEqual(s2.for_platform("android"), {"xpath": "//View[3]"})
        self.assertEqual(s2.for_platform("ios"), {"xpath": "//Cell[3]"})

    def test_format_preserves_non_string_fields(self):
        s = Selector(android={"index": 2, "text": "X"})
        s2 = s.format()
        self.assertEqual(s2.for_platform("android"), {"index": 2, "text": "X"})

    def test_format_missing_placeholder_raises(self):
        s = Selector(android={"xpath": "//View[{idx}]"})
        with self.assertRaises(KeyError):
            s.format()


class TestEverywhere(unittest.TestCase):
    def test_everywhere_fills_all_platforms(self):
        s = Selector.everywhere(text="取消")
        self.assertEqual(s.platforms(), frozenset({"android", "ios", "harmony"}))
        for p in ("android", "ios", "harmony"):
            self.assertEqual(s.for_platform(p), {"text": "取消"})


class TestRepr(unittest.TestCase):
    def test_repr_roundtrips_for_full_selector(self):
        s = Selector(
            _parent="顶部", _doc="返回按钮",
            android={"text": "返回"},
            ios={"label": "Back"},
        )
        s2 = eval(repr(s), {"Selector": Selector})
        self.assertEqual(s, s2)

    def test_repr_roundtrips_image(self):
        s = Selector(image="x.png")
        s2 = eval(repr(s), {"Selector": Selector})
        self.assertEqual(s, s2)

    def test_repr_has_stable_platform_order(self):
        """同样的 Selector 重新构造应得到相同 repr —— git diff 友好。"""
        s1 = Selector(ios={"label": "B"}, android={"text": "A"})
        s2 = Selector(android={"text": "A"}, ios={"label": "B"})
        self.assertEqual(repr(s1), repr(s2))

    def test_equality_and_hash(self):
        s1 = Selector(android={"text": "X"})
        s2 = Selector(android={"text": "X"})
        s3 = Selector(android={"text": "Y"})
        self.assertEqual(s1, s2)
        self.assertNotEqual(s1, s3)
        self.assertEqual(hash(s1), hash(s2))


if __name__ == "__main__":
    unittest.main()
