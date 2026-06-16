# -*- coding: utf-8 -*-
"""POM API helpers + endpoint round-trip tests.

设计要点：
- 用 unittest.mock.patch.object 替换 api 模块的 TASKS_DIR 全局，
  这样 _pom_dir() 在 handler 内拿到隔离的 tmpdir。
- TestClient(FastAPI() + include_router(router)) 真实跑路由，不依赖 server.py。
- 顺便测一遍：pom/__init__.py 生成的别名可以 `from pom import LoginPage`。
"""
import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ha4t.editor.routers import api as api_module
from ha4t.editor.routers.api import (
    _page_filename,
    _parse_pom_py,
    _render_pom_meta,
    _render_pom_py,
    router,
)


class TestPomHelpers(unittest.TestCase):
    """Pure-function helpers — no filesystem."""

    def test_page_filename_camelcase(self):
        self.assertEqual(_page_filename("LoginPage"), "login_page.py")
        self.assertEqual(_page_filename("HomePage"), "home_page.py")
        # 连续大写：每个大写前都插下划线（计划已记录此行为）
        self.assertEqual(_page_filename("POMHome"), "p_o_m_home.py")
        # 单字符大写
        self.assertEqual(_page_filename("A"), "a.py")

    def test_page_filename_non_ascii_and_snake(self):
        # 中文 page → 直接 <page>.py
        self.assertEqual(_page_filename("登录页"), "登录页.py")
        self.assertEqual(_page_filename("首页"), "首页.py")
        # 已经是 snake_case → 原样
        self.assertEqual(_page_filename("login_page"), "login_page.py")
        # 混合中英文
        self.assertEqual(_page_filename("登录Page"), "登录Page.py")

    def test_render_then_parse_roundtrip(self):
        """渲染 → 解析 → ElementShape 完全保留（page 文件不再有 VARS）。"""
        elements = {
            "btn_a": {"text": "登录", "resourceId": "com.x:id/login"},
            "with_quote": {"text": "say \"hi\""},
            "tricky": {"xpath": '//*[@text="hi"]/parent::*[contains(@id,\'x\')]'},
            "with_index": {"className": "Button", "index": 3},
        }
        py = _render_pom_py("LoginPage", "登录页", "登录,login", elements)
        parsed = _parse_pom_py(py)
        self.assertEqual(parsed["meta"]["page"], "LoginPage")
        self.assertEqual(parsed["meta"]["desc"], "登录页")
        self.assertEqual(parsed["meta"]["triggers"], "登录,login")
        # 老 flat dict 入参 → 自动迁移成 ElementShape 进 android 分桶
        self.assertEqual(parsed["elements"]["btn_a"]["platforms"], {"android": {"text": "登录", "resourceId": "com.x:id/login"}})
        self.assertEqual(parsed["elements"]["with_index"]["platforms"]["android"]["index"], 3)
        self.assertEqual(parsed["elements"]["tricky"]["platforms"]["android"]["xpath"], elements["tricky"]["xpath"])
        self.assertEqual(parsed["vars"], {})

    def test_render_then_parse_chinese_keys(self):
        """元素 key 允许中文，repr/literal_eval 应保留原字符。"""
        elements = {
            "登录按钮": {"text": "登录", "resourceId": "com.x:id/login"},
            "用户名输入框": {"className": "EditText", "index": 0},
            "tab_home": {"text": "首页"},
        }
        py = _render_pom_py("登录页", "登录页面", "登录,login", elements)
        self.assertIn("登录按钮", py)
        self.assertIn("用户名输入框", py)
        parsed = _parse_pom_py(py)
        self.assertEqual(parsed["meta"]["page"], "登录页")
        self.assertEqual(parsed["elements"]["登录按钮"]["platforms"]["android"], elements["登录按钮"])
        self.assertEqual(parsed["elements"]["tab_home"]["platforms"]["android"]["text"], "首页")

    def test_render_meta_roundtrip(self):
        vars_ = {"package": "com.example.app", "base_url": "https://x.test", "timeout": 10}
        py = _render_pom_meta(vars_)
        parsed = _parse_pom_py(py)
        self.assertEqual(parsed["vars"], vars_)

    def test_parse_handles_syntax_error(self):
        """损坏文件 → 返回空 dict，不抛异常。"""
        broken = "# page: Foo\nELEMENTS = {this is not python\n"
        parsed = _parse_pom_py(broken)
        # meta 仍可从注释行读出（注释行级解析独立于 ast）
        self.assertEqual(parsed["meta"]["page"], "Foo")
        self.assertEqual(parsed["elements"], {})
        self.assertEqual(parsed["vars"], {})

    def test_parse_meta_only(self):
        """只有头注释、没有任何 ELEMENTS 时不应报错。"""
        parsed = _parse_pom_py("# page: P\n# desc: D\n")
        self.assertEqual(parsed["meta"]["page"], "P")
        self.assertEqual(parsed["meta"]["desc"], "D")
        self.assertEqual(parsed["elements"], {})

    def test_render_then_parse_docs_roundtrip(self):
        """docs 写入 Selector(_doc=...) 字段，解析时回填到 docs 字典 + ElementShape._doc。"""
        elements = {
            "登录按钮": {"text": "登录"},
            "商品项":   {"xpath": "//*[@id='list']/View"},
        }
        docs = {
            "登录按钮": "顶部主按钮，点击进入登录态",
            "商品项":   "列表项模板。用例调用时追加 [index] 选第几个（1-based）。\nindex 由测试数据决定。",
        }
        py = _render_pom_py("商品页", "", "", elements, docs)
        # 渲染输出每条 doc 进 Selector(_doc=...) 字段
        self.assertIn("_doc='顶部主按钮，点击进入登录态'", py)
        # 多行 doc 用 \n 字面量保留在 _doc 字段里
        self.assertIn("index 由测试数据决定", py)

        parsed = _parse_pom_py(py)
        self.assertEqual(parsed["docs"], docs)

    def test_parse_preserves_handwritten_comment(self):
        """用户手工在 pom/<page>.py 里写注释 → GET 时被读回，编辑器后续 save 保留。

        老格式（无 Selector），doc 走顶上 `#` 注释；新格式 Selector(_doc=...)
        优先生效。这条测试覆盖老兼容。
        """
        py = (
            "# -*- coding: utf-8 -*-\n"
            "# kind: pom\n"
            "# page: LoginPage\n"
            "\n"
            "ELEMENTS = {\n"
            "    # 人写的注释\n"
            "    '登录按钮': {'text': '登录'},\n"
            "}\n"
        )
        parsed = _parse_pom_py(py)
        self.assertEqual(parsed["docs"], {"登录按钮": "人写的注释"})

    def test_parse_blank_line_truncates_doc(self):
        """老格式：元素与注释之间有空行 → 注释不属于该元素。"""
        py = (
            "ELEMENTS = {\n"
            "    # 这是模块说明\n"
            "\n"
            "    '按钮': {'text': 'go'},\n"
            "}\n"
        )
        parsed = _parse_pom_py(py)
        self.assertEqual(parsed["docs"], {})

    def test_render_no_docs_unchanged(self):
        """docs 为空 / 某 key 没 doc → 不写 _doc 字段。保持简洁。"""
        py = _render_pom_py("P", "", "", {"a": {"text": "x"}}, None)
        self.assertNotIn("_doc=", py)
        py2 = _render_pom_py("P", "", "", {"a": {"text": "x"}}, {})
        self.assertEqual(py, py2)

    def test_parent_roundtrip(self):
        """`_parent` 字段：render 进 Selector(_parent=...)；parse 拆到 parents map。"""
        elements = {
            "顶部导航": {"resourceId": "com.x:id/top"},
            "返回按钮": {"text": "返回"},
            "标题":     {"resourceId": "com.x:id/title"},
            "登录按钮": {"text": "登录"},
        }
        parents = {"返回按钮": "顶部导航", "标题": "顶部导航"}
        py = _render_pom_py("登录页", "", "", elements, None, parents)
        # selector 不再嵌 _parent —— 它现在是 Selector 顶层 kwarg
        self.assertIn("_parent='顶部导航'", py)
        # 顶层元素没塞 _parent
        self.assertNotIn("'登录按钮': Selector(_parent=", py)

        parsed = _parse_pom_py(py)
        self.assertEqual(parsed["parents"], parents)
        # elements 是 ElementShape；返回按钮的 _parent 在 shape 里
        self.assertEqual(parsed["elements"]["返回按钮"]["_parent"], "顶部导航")
        self.assertEqual(parsed["elements"]["顶部导航"]["_parent"], "")
        self.assertEqual(parsed["elements"]["顶部导航"]["platforms"]["android"], {"resourceId": "com.x:id/top"})

    def test_no_parent_emits_empty_map(self):
        py = _render_pom_py("P", "", "", {"a": {"text": "x"}})
        parsed = _parse_pom_py(py)
        self.assertEqual(parsed["parents"], {})

    def test_selector_literal_roundtrip(self):
        """直接传新 ElementShape（含多平台分桶 + _parent + _doc）→ 渲染 → 解析回来一致。"""
        elements = {
            "顶部导航": {
                "platforms": {"android": {"resourceId": "com.x:id/top"}, "ios": {"label": "Header"}},
                "image": None, "_parent": "", "_doc": "顶部容器",
            },
            "返回按钮": {
                "platforms": {"android": {"text": "返回"}, "ios": {"label": "Back"}},
                "image": None, "_parent": "顶部导航", "_doc": "",
            },
            "登录图标": {
                "platforms": {}, "image": "login_icon.png",
                "_parent": "", "_doc": "跨平台共享图像",
            },
        }
        py = _render_pom_py("LoginPage", "登录页", "", elements)
        # 输出格式
        self.assertIn("from ha4t import Selector", py)
        self.assertIn("Selector(_doc='顶部容器'", py)
        self.assertIn("ios={'label': 'Back'}", py)
        self.assertIn("Selector(_doc='跨平台共享图像', image='login_icon.png')", py)

        parsed = _parse_pom_py(py)
        self.assertEqual(parsed["elements"]["顶部导航"]["platforms"]["android"], {"resourceId": "com.x:id/top"})
        self.assertEqual(parsed["elements"]["顶部导航"]["platforms"]["ios"], {"label": "Header"})
        self.assertEqual(parsed["elements"]["返回按钮"]["_parent"], "顶部导航")
        self.assertEqual(parsed["elements"]["登录图标"]["image"], "login_icon.png")
        self.assertEqual(parsed["elements"]["登录图标"]["platforms"], {})
        # docs / parents 并列字典
        self.assertEqual(parsed["docs"]["顶部导航"], "顶部容器")
        self.assertEqual(parsed["parents"]["返回按钮"], "顶部导航")

class TestPomEndpoints(unittest.TestCase):
    """端点循环：create → list → get → save(更新) → delete + __init__ 验证。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ha4t_pom_test_")
        self._patcher = patch.object(api_module, "TASKS_DIR", Path(self.tmp))
        self._patcher.start()
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def tearDown(self):
        self._patcher.stop()
        # 清理可能被 import 的 pom 模块
        for name in list(sys.modules):
            if name == "pom" or name.startswith("pom."):
                del sys.modules[name]
        if self.tmp in sys.path:
            sys.path.remove(self.tmp)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ok(self, resp):
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"], body.get("message"))
        return body["data"]

    def test_full_lifecycle(self):
        # 起点：empty list
        data = self._ok(self.client.get("/pom/pages"))
        self.assertEqual(data, [])

        # create LoginPage
        data = self._ok(self.client.post("/pom/pages", json={
            "page": "LoginPage", "desc": "登录页", "triggers": "登录",
            "elements": {},
        }))
        self.assertEqual(data["filename"], "login_page.py")

        # create HomePage
        self._ok(self.client.post("/pom/pages", json={
            "page": "HomePage", "desc": "首页", "triggers": "首页",
            "elements": {},
        }))

        # list — 2 pages
        items = self._ok(self.client.get("/pom/pages"))
        names = sorted(i["page"] for i in items)
        self.assertEqual(names, ["HomePage", "LoginPage"])

        # get LoginPage
        data = self._ok(self.client.get("/pom/pages/login_page.py"))
        self.assertEqual(data["page"], "LoginPage")
        self.assertEqual(data["desc"], "登录页")
        self.assertEqual(data["elements"], {})

        # update LoginPage with elements (老 flat dict 入参 — 后端 lazy migrate 进 android 分桶)
        new_elements = {"login_button": {"resourceId": "com.x:id/login", "text": "登录"}}
        self._ok(self.client.post("/pom/pages", json={
            "page": "LoginPage", "desc": "登录页", "triggers": "登录,login",
            "elements": new_elements,
        }))

        data = self._ok(self.client.get("/pom/pages/login_page.py"))
        # 响应是 ElementShape：扁平 dict 自动进 android 分桶
        self.assertEqual(data["elements"]["login_button"]["platforms"]["android"], new_elements["login_button"])
        self.assertEqual(data["triggers"], "登录,login")

        # __init__.py 应含 alias
        init_path = Path(self.tmp) / "pom" / "__init__.py"
        init_text = init_path.read_text(encoding="utf-8")
        self.assertIn("from . import login_page as LoginPage", init_text)
        self.assertIn("from . import home_page as HomePage", init_text)

        # delete HomePage
        self._ok(self.client.delete("/pom/pages/home_page.py"))
        items = self._ok(self.client.get("/pom/pages"))
        self.assertEqual([i["page"] for i in items], ["LoginPage"])
        init_text = init_path.read_text(encoding="utf-8")
        self.assertNotIn("HomePage", init_text)

        # delete nonexistent → error
        resp = self.client.delete("/pom/pages/ghost.py")
        body = resp.json()
        self.assertFalse(body["success"])

    def test_element_edit_rename_and_update(self):
        """模拟编辑器二次编辑：重命名 + 改 selector 字段 + 整 page 保存覆盖。
        因为后端接口是 *整个 elements dict* 覆盖式保存，所以前端的 updateElement
        最终也是通过同一 POST /pom/pages 落盘。这里在端点层验证：
        - 旧 key 不再存在
        - 新 key 含修改后的 selector
        - 其他元素位置/顺序不变
        """
        # 初始：三个元素，按插入顺序排列
        elems = {
            "btn_a": {"text": "A", "resourceId": "x:id/a"},
            "btn_b": {"text": "B"},
            "btn_c": {"text": "C"},
        }
        self._ok(self.client.post("/pom/pages", json={
            "page": "TestPage", "desc": "", "triggers": "",
            "elements": elems,
        }))

        # 编辑：把 btn_b → 确认按钮，文本改成「确定」，去掉 resourceId（已不在）
        edited = {
            "btn_a": {"text": "A", "resourceId": "x:id/a"},
            "确认按钮": {"text": "确定", "xpath": "//Button[@text='确定']"},
            "btn_c": {"text": "C"},
        }
        self._ok(self.client.post("/pom/pages", json={
            "page": "TestPage", "desc": "", "triggers": "",
            "elements": edited,
        }))

        data = self._ok(self.client.get("/pom/pages/test_page.py"))
        self.assertEqual(list(data["elements"].keys()), ["btn_a", "确认按钮", "btn_c"])
        confirm = data["elements"]["确认按钮"]["platforms"]["android"]
        self.assertEqual(confirm["text"], "确定")
        self.assertEqual(confirm["xpath"], "//Button[@text='确定']")
        self.assertNotIn("resourceId", confirm)
        # 未编辑的相邻元素保持不变
        self.assertEqual(data["elements"]["btn_a"]["platforms"]["android"], {"text": "A", "resourceId": "x:id/a"})
        self.assertEqual(data["elements"]["btn_c"]["platforms"]["android"], {"text": "C"})

        # 仅改 selector 字段（不重命名）：去掉一个字段，新增一个字段
        edited2 = dict(edited)
        edited2["btn_a"] = {"description": "首字母 A 的按钮"}  # 完全替换 selector
        self._ok(self.client.post("/pom/pages", json={
            "page": "TestPage", "desc": "", "triggers": "",
            "elements": edited2,
        }))
        data = self._ok(self.client.get("/pom/pages/test_page.py"))
        self.assertEqual(data["elements"]["btn_a"]["platforms"]["android"], {"description": "首字母 A 的按钮"})

    def test_image_element_lifecycle(self):
        """图像元素：{'image': 'fname.png'} 与 selector 元素同源存储，
        可在 import 后通过 ELEMENTS['x']['image'] 取出文件名，供 dev.click(**...) 解包。"""
        mixed = {
            "登录按钮": {"text": "登录", "resourceId": "x:id/login"},  # selector 类型
            "游戏开始按钮": {"image": "pom_GamePage_1700000000.png"},     # image 类型
        }
        self._ok(self.client.post("/pom/pages", json={
            "page": "GamePage", "desc": "游戏页", "triggers": "",
            "elements": mixed,
        }))
        data = self._ok(self.client.get("/pom/pages/game_page.py"))
        self.assertEqual(data["elements"]["登录按钮"]["platforms"]["android"]["text"], "登录")
        # image 元素：image 字段非空，platforms 为空
        img = data["elements"]["游戏开始按钮"]
        self.assertEqual(img["image"], "pom_GamePage_1700000000.png")
        self.assertEqual(img["platforms"], {})

        # 磁盘文件包含 image 文件名字面量
        page_text = (Path(self.tmp) / "pom" / "game_page.py").read_text(encoding="utf-8")
        self.assertIn("'pom_GamePage_1700000000.png'", page_text)

        # import 后能拿到 image 字段
        sys.path.insert(0, self.tmp)
        for name in list(sys.modules):
            if name == "pom" or name.startswith("pom."):
                del sys.modules[name]
        pom_pkg = importlib.import_module("pom")
        # 新格式：image 元素是 Selector 实例，.image 拿文件名，.for_platform 拿 kwargs
        img_sel = pom_pkg.GamePage.ELEMENTS["游戏开始按钮"]
        self.assertEqual(img_sel.image, "pom_GamePage_1700000000.png")
        # 任何平台 for_platform 都返回 {'image': ...}（image 元素跨平台一致）
        for plat in ("android", "ios", "harmony"):
            self.assertEqual(img_sel.for_platform(plat), {"image": "pom_GamePage_1700000000.png"})

    def test_invalid_page_name(self):
        # 数字开头：非法标识符
        for bad in ["1Page", "has space", "with-dash", "", "class"]:
            resp = self.client.post("/pom/pages", json={
                "page": bad, "desc": "", "triggers": "",
                "elements": {},
            })
            body = resp.json()
            self.assertFalse(body["success"], f"应拒绝非法名 {bad!r}")
            self.assertIn("Python 标识符", body["message"])

    def test_chinese_page_lifecycle(self):
        """中文 page 名：保存→读回→删除 + import 正常。"""
        # element key 也用中文：这是用户希望的真实工作流
        elements = {
            "登录按钮": {"text": "登录", "resourceId": "com.x:id/login"},
            "用户名输入框": {"className": "EditText"},
        }
        data = self._ok(self.client.post("/pom/pages", json={
            "page": "登录页", "desc": "登录页面", "triggers": "登录,login",
            "elements": elements,
        }))
        self.assertEqual(data["filename"], "登录页.py")

        items = self._ok(self.client.get("/pom/pages"))
        self.assertEqual([i["page"] for i in items], ["登录页"])
        # element_count 应包含中文 key
        self.assertEqual(items[0]["element_count"], 2)

        data = self._ok(self.client.get("/pom/pages/登录页.py"))
        self.assertEqual(data["page"], "登录页")
        # 响应是 ElementShape：原 flat dict → android 分桶
        self.assertEqual(data["elements"]["登录按钮"]["platforms"]["android"], elements["登录按钮"])
        self.assertEqual(data["elements"]["用户名输入框"]["platforms"]["android"], elements["用户名输入框"])

        # __init__.py 应包含中文 alias
        init_text = (Path(self.tmp) / "pom" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("from . import 登录页 as 登录页", init_text)

        # 磁盘文件里中文 key 不被 escape，直接以 UTF-8 字符出现
        page_text = (Path(self.tmp) / "pom" / "登录页.py").read_text(encoding="utf-8")
        self.assertIn("'登录按钮'", page_text)
        self.assertIn("'用户名输入框'", page_text)

        # 可被 import，且能按中文 key 取 Selector 实例
        sys.path.insert(0, self.tmp)
        for name in list(sys.modules):
            if name == "pom" or name.startswith("pom."):
                del sys.modules[name]
        pom_pkg = importlib.import_module("pom")
        page = getattr(pom_pkg, "登录页")
        self.assertEqual(page.ELEMENTS["登录按钮"].for_platform("android"), elements["登录按钮"])
        self.assertEqual(page.ELEMENTS["用户名输入框"].for_platform("android"), elements["用户名输入框"])

    def test_meta_get_creates_default(self):
        """meta.py 不存在时 GET 自动创建并返回空 vars。"""
        meta_f = Path(self.tmp) / "pom" / "_meta.py"
        self.assertFalse(meta_f.exists())
        data = self._ok(self.client.get("/pom/meta"))
        self.assertIn("vars", data)
        self.assertEqual(data["vars"], {})
        self.assertTrue(meta_f.exists())

    def test_meta_save(self):
        self._ok(self.client.post("/pom/meta", json={
            "vars": {"package": "com.x.app", "base_url": "https://x.test"},
        }))
        data = self._ok(self.client.get("/pom/meta"))
        self.assertEqual(data["vars"]["package"], "com.x.app")
        self.assertEqual(data["vars"]["base_url"], "https://x.test")

    def test_generated_pom_is_importable(self):
        """端到端：编辑器写出的 pom/ 包可被 `from pom import LoginPage` 直接消费。"""
        self._ok(self.client.post("/pom/pages", json={
            "page": "LoginPage", "desc": "登录页", "triggers": "",
            "elements": {"login_button": {"text": "登录"}},
        }))
        self._ok(self.client.post("/pom/pages", json={
            "page": "HomePage", "desc": "首页", "triggers": "",
            "elements": {"search": {"resourceId": "x:id/s"}},
        }))
        self._ok(self.client.post("/pom/meta", json={
            "vars": {"package": "com.x", "g": 1},
        }))
        sys.path.insert(0, self.tmp)
        # 确保 import 拿到的是新写的包，而不是其他地方缓存的
        for name in list(sys.modules):
            if name == "pom" or name.startswith("pom."):
                del sys.modules[name]
        pom_pkg = importlib.import_module("pom")
        self.assertTrue(hasattr(pom_pkg, "LoginPage"))
        self.assertTrue(hasattr(pom_pkg, "HomePage"))
        self.assertTrue(hasattr(pom_pkg, "VARS"))
        self.assertIsInstance(pom_pkg.LoginPage.ELEMENTS, dict)
        # 新格式：ELEMENTS 值是 Selector 实例，用 .for_platform('android') 拿 native kwargs
        login_sel = pom_pkg.LoginPage.ELEMENTS["login_button"]
        self.assertEqual(login_sel.for_platform("android"), {"text": "登录"})
        # search 元素同理
        search_sel = pom_pkg.HomePage.ELEMENTS["search"]
        self.assertEqual(search_sel.for_platform("android"), {"resourceId": "x:id/s"})
        self.assertEqual(pom_pkg.VARS["package"], "com.x")
        self.assertEqual(pom_pkg.VARS["g"], 1)

class TestPomVerifySelector(unittest.TestCase):
    """verify-selector 端点：image 拦截、空 selector、设备缺失、mock 设备命中/未命中。

    cached_devices 是 _device.py 的模块级 dict，api 模块 import 的是同一对象 ——
    patch.dict(api_module.cached_devices, ...) 即可注入伪设备并在 teardown 还原。
    """

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def _post(self, payload):
        resp = self.client.post("/pom/verify-selector", json=payload)
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_verify_selector_device_not_connected(self):
        with patch.dict(api_module.cached_devices, {}, clear=True):
            body = self._post({
                "platform": "android", "serial": "NOPE",
                "selector": {"text": "登录"},
            })
        self.assertFalse(body["success"])
        self.assertIn("设备未连接", body["message"])

    def test_verify_selector_image_element_no_template(self):
        """image 元素不再拒绝，而是走模板匹配。没模板文件时报 '图片模板不存在'。"""
        from unittest.mock import MagicMock
        from ha4t.editor._device import AndroidDevice
        mock_dev = MagicMock(spec=AndroidDevice)
        mock_dev.take_screenshot.return_value = ""
        with patch.dict(api_module.cached_devices, {("android", "S1"): mock_dev}, clear=True):
            body = self._post({
                "platform": "android", "serial": "S1",
                "selector": {"image": "x.png"},
            })
        self.assertFalse(body["success"])
        self.assertIn("图片模板不存在", body["message"])

    def test_verify_selector_rejects_empty(self):
        body = self._post({
            "platform": "android", "serial": "S1", "selector": {},
        })
        self.assertFalse(body["success"])

    def test_verify_selector_with_mock_device(self):
        from unittest.mock import MagicMock
        from ha4t.editor._device import AndroidDevice

        mock_dev = MagicMock(spec=AndroidDevice)
        rect = {"x": 10, "y": 20, "width": 30, "height": 40}
        mock_dev.find_element_rect.return_value = rect
        with patch.dict(api_module.cached_devices, {("android", "S1"): mock_dev}, clear=True):
            # 命中：found + rect 原样返回 + Android 平台 supported
            body = self._post({
                "platform": "android", "serial": "S1",
                "selector": {"text": "登录"},
            })
            self.assertTrue(body["success"], body.get("message"))
            self.assertTrue(body["data"]["found"])
            self.assertEqual(body["data"]["rect"], rect)
            self.assertTrue(body["data"]["platform_supported"])
            mock_dev.find_element_rect.assert_called_once_with({"text": "登录"})

            # 未命中：found=False, rect=None — 正常 success，不是错误
            mock_dev.find_element_rect.return_value = None
            body = self._post({
                "platform": "android", "serial": "S1",
                "selector": {"text": "不存在的"},
            })
            self.assertTrue(body["success"])
            self.assertFalse(body["data"]["found"])
            self.assertIsNone(body["data"]["rect"])

            # driver 抛异常 → doError 且 message 带异常类型，不向上冒 500
            mock_dev.find_element_rect.side_effect = RuntimeError("adb died")
            body = self._post({
                "platform": "android", "serial": "S1",
                "selector": {"text": "登录"},
            })
            self.assertFalse(body["success"])
            self.assertIn("RuntimeError", body["message"])

    def test_verify_selector_harmony_unsupported(self):
        from unittest.mock import MagicMock
        from ha4t.editor._device import HarmonyDevice

        mock_dev = MagicMock(spec=HarmonyDevice)
        mock_dev.find_element_rect.return_value = None
        with patch.dict(api_module.cached_devices, {("harmony", "H1"): mock_dev}, clear=True):
            body = self._post({
                "platform": "harmony", "serial": "H1",
                "selector": {"text": "登录"},
            })
        self.assertTrue(body["success"])
        self.assertFalse(body["data"]["found"])
        self.assertFalse(body["data"]["platform_supported"])


if __name__ == "__main__":
    unittest.main()
