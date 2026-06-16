# -*- coding: utf-8 -*-
"""工作区端点测试：/fs/list + /workspace + /workspace/init + 守卫。"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ha4t.editor import _config as cfg_module
from ha4t.editor.routers import api as api_module
from ha4t.editor.routers.api import router


class _WsTestBase(unittest.TestCase):
    """所有 workspace 测试都需要把 CONFIG_FILE 隔离到 tmp，避免污染 ~/.ha4t/config.json。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ha4t_ws_test_")
        self.cfg_file = Path(self.tmp) / "_config.json"
        self._cfg_patcher = patch.object(cfg_module, "CONFIG_FILE", self.cfg_file)
        self._cfg_patcher.start()
        # EditorConfig 是单例，需要清缓存（虽然其本身已无 _data 缓存）。
        cfg_module.EditorConfig._instance = None

        # 把模块级路径也清零 → 模拟「未选工作区」初始态。
        self._tasks_dir_before = api_module.TASKS_DIR
        self._images_dir_before = api_module.IMAGES_DIR
        api_module.TASKS_DIR = None
        api_module.IMAGES_DIR = None

        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)

    def tearDown(self):
        self._cfg_patcher.stop()
        cfg_module.EditorConfig._instance = None
        api_module.TASKS_DIR = self._tasks_dir_before
        api_module.IMAGES_DIR = self._images_dir_before
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _ok(self, resp):
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"], body.get("message"))
        return body["data"]


class TestFsList(_WsTestBase):
    def test_fs_list_root(self):
        data = self._ok(self.client.get("/fs/list"))
        self.assertEqual(data["path"], "")
        self.assertIsNone(data["parent"])
        self.assertGreaterEqual(len(data["entries"]), 1)
        # 必定有 HOME。
        home_str = str(Path.home())
        self.assertTrue(any(e["path"] == home_str for e in data["entries"]))

    def test_fs_list_subdir(self):
        os.makedirs(Path(self.tmp) / "a")
        os.makedirs(Path(self.tmp) / "b")
        os.makedirs(Path(self.tmp) / ".hidden")
        data = self._ok(self.client.get(f"/fs/list?path={self.tmp}"))
        names = {e["name"] for e in data["entries"]}
        self.assertEqual(names, {"a", "b"})  # 隐藏目录被排除
        # parent 正确（Windows: 自带盘符；POSIX: /tmp）。
        self.assertEqual(data["parent"], str(Path(self.tmp).parent))

    def test_fs_list_not_dir(self):
        resp = self.client.get("/fs/list?path=/this/path/should/not/exist/xyz123")
        body = resp.json()
        self.assertFalse(body["success"])


class TestWorkspaceLifecycle(_WsTestBase):
    def test_initial_status_no_workspace(self):
        data = self._ok(self.client.get("/workspace"))
        self.assertEqual(data["current"], "")
        self.assertEqual(data["recent"], [])
        self.assertFalse(data["initialized"])

    def test_workspace_init_creates_skeleton(self):
        data = self._ok(self.client.post("/workspace/init", json={
            "parent": self.tmp, "name": "ws1",
        }))
        ws_path = Path(data["path"])
        self.assertEqual(ws_path.name, "ws1")

        # 骨架文件全部存在
        self.assertTrue((ws_path / "pom" / "__init__.py").exists())
        self.assertTrue((ws_path / "pom" / "_meta.py").exists())
        self.assertTrue((ws_path / "images").is_dir())
        self.assertTrue((ws_path / "screenshots").is_dir())
        self.assertTrue((ws_path / "CLAUDE.md").exists())
        self.assertTrue((ws_path / "conftest.py").exists())
        self.assertTrue((ws_path / "pyproject.toml").exists())
        self.assertTrue((ws_path / "README.md").exists())

        # pyproject.toml 含 ha4t 依赖
        toml_text = (ws_path / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('"ha4t"', toml_text)

        # /workspace 反映出选定状态
        data2 = self._ok(self.client.get("/workspace"))
        self.assertEqual(Path(data2["current"]), ws_path)
        self.assertTrue(data2["initialized"])
        # recent 已加入
        self.assertIn(str(ws_path), data2["recent"])

    def test_workspace_init_rejects_nonempty(self):
        target = Path(self.tmp) / "ws1"
        target.mkdir()
        (target / "x.txt").write_text("x", encoding="utf-8")
        resp = self.client.post("/workspace/init", json={
            "parent": self.tmp, "name": "ws1",
        })
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertIn("非空", body["message"])

    def test_workspace_init_rejects_bad_name(self):
        for bad in ["", "  ", "x/y", "a*b", "with:colon"]:
            resp = self.client.post("/workspace/init", json={
                "parent": self.tmp, "name": bad,
            })
            body = resp.json()
            self.assertFalse(body["success"], f"应拒绝 {bad!r}")

    def test_workspace_init_rejects_missing_parent(self):
        resp = self.client.post("/workspace/init", json={
            "parent": str(Path(self.tmp) / "nope"), "name": "x",
        })
        body = resp.json()
        self.assertFalse(body["success"])

    def test_workspace_open_creates_skeleton_in_empty_dir(self):
        """打开一个全新的空目录 → 应当幂等铺出工作区骨架（skill / conftest / pyproject / pom 等）。"""
        target = Path(self.tmp) / "fresh_dir"
        target.mkdir()
        data = self._ok(self.client.post("/workspace/open", json={"path": str(target)}))
        self.assertEqual(Path(data["path"]), target.resolve())
        # 切换成功
        self.assertTrue(self._ok(self.client.get("/workspace"))["initialized"])
        # 骨架文件全部就位（不区分顺序）
        for rel in (
            "pom/__init__.py", "pom/_meta.py",
            "images/.gitkeep", "screenshots/.gitkeep",
            "CLAUDE.md",
            "conftest.py", "pyproject.toml", "README.md",
        ):
            self.assertTrue((target / rel).exists(), f"missing: {rel}")
        # 响应里报告了创建清单
        self.assertIn("pyproject.toml", data["created"])

    def test_workspace_open_is_idempotent_and_preserves_user_files(self):
        """打开一个已是工作区的目录 → 用户已有的 pyproject/conftest 等不应被覆盖。"""
        target = Path(self.tmp) / "existing_ws"
        target.mkdir()
        # 用户自己写的 pyproject —— 跟模板不同
        user_pyproject = '[project]\nname = "my-custom"\nversion = "9.9.9"\n'
        (target / "pyproject.toml").write_text(user_pyproject, encoding="utf-8")

        data = self._ok(self.client.post("/workspace/open", json={"path": str(target)}))
        # 用户文件原封不动
        self.assertEqual((target / "pyproject.toml").read_text(encoding="utf-8"), user_pyproject)
        # 但缺失的骨架（conftest / pom / skill）被补齐了
        self.assertTrue((target / "conftest.py").exists())
        self.assertTrue((target / "pom" / "_meta.py").exists())
        # created 列表不应包含已存在的 pyproject
        self.assertNotIn("pyproject.toml", data["created"])
        self.assertIn("conftest.py", data["created"])

        # 再次 open —— created 应为空（全部已存在）
        data2 = self._ok(self.client.post("/workspace/open", json={"path": str(target)}))
        self.assertEqual(data2["created"], [])

    def test_workspace_open_invalid(self):
        resp = self.client.post("/workspace/open", json={
            "path": str(Path(self.tmp) / "does_not_exist"),
        })
        body = resp.json()
        self.assertFalse(body["success"])


class TestNoWorkspaceGuard(_WsTestBase):
    """模块级 TASKS_DIR=None 时，所有数据端点必须返回 doError('未选择工作区')。"""

    def _err(self, resp, expected="未选择工作区"):
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["message"], expected)

    def test_list_tasks_guarded(self):
        self._err(self.client.get("/tasks"))

    def test_load_task_guarded(self):
        self._err(self.client.get("/tasks/x.py"))

    def test_save_task_guarded(self):
        self._err(self.client.post("/tasks/x.py", json={"content": ""}))

    def test_get_image_guarded(self):
        self._err(self.client.get("/images/x.png"))

    def test_save_image_guarded(self):
        self._err(self.client.post("/images/x.png", json={"data": ""}))

    def test_pom_list_guarded(self):
        self._err(self.client.get("/pom/pages"))

    def test_pom_get_meta_guarded(self):
        self._err(self.client.get("/pom/meta"))

    def test_open_folder_guarded(self):
        self._err(self.client.post("/tasks/open-folder"))


class TestFilesRaw(_WsTestBase):
    """`/files/raw` 用于「查看源码」弹窗 —— 工作区内文本文件只读访问。"""

    def setUp(self):
        super().setUp()
        # 启用工作区：直接戳模块级路径，等价 init 但绕过 EditorConfig 持久化
        ws = Path(self.tmp) / "ws"
        ws.mkdir()
        (ws / "testcases").mkdir()
        (ws / "pom").mkdir()
        (ws / "testcases" / "foo.py").write_text("print('hi')\n", encoding="utf-8")
        (ws / "pom" / "login.py").write_text("ELEMENTS = {}\n", encoding="utf-8")
        api_module.TASKS_DIR = ws
        api_module.IMAGES_DIR = ws / "images"

    def test_read_case_source(self):
        data = self._ok(self.client.get("/files/raw?path=testcases/foo.py"))
        self.assertEqual(data["content"], "print('hi')\n")
        self.assertEqual(data["path"], "testcases/foo.py")

    def test_read_pom_source(self):
        data = self._ok(self.client.get("/files/raw?path=pom/login.py"))
        self.assertEqual(data["content"], "ELEMENTS = {}\n")

    def test_reject_path_traversal(self):
        # 试图 escape 工作区根
        resp = self.client.get("/files/raw?path=../etc/passwd")
        body = resp.json()
        self.assertFalse(body["success"])

    def test_reject_unsupported_extension(self):
        (api_module.TASKS_DIR / "a.exe").write_bytes(b"\x00")
        body = self.client.get("/files/raw?path=a.exe").json()
        self.assertFalse(body["success"])
        self.assertIn("不支持", body["message"])

    def test_missing_file(self):
        body = self.client.get("/files/raw?path=testcases/nope.py").json()
        self.assertFalse(body["success"])

    def test_missing_path_param(self):
        body = self.client.get("/files/raw?path=").json()
        self.assertFalse(body["success"])


if __name__ == "__main__":
    unittest.main()
