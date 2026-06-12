# -*- coding: utf-8 -*-
r"""
Editor configuration manager — 工作区（workspace）模型。

config.json schema::

    {
        "current_workspace": "<absolute path or empty string>",
        "recent_workspaces": ["<absolute path>", ...]
    }

只有「单一工作区」这一个概念：选定后所有用例 / pom / 图片 / 截图都落在
该目录树下。首启或工作区不存在 → `workspace()` 返回 ``None``，前端 gate
负责让用户选目录或初始化新工作区。
"""
import json
from pathlib import Path
from typing import Optional


_CONFIG_DIR = Path.home() / ".ha4t"
# 模块级常量：测试通过 patch 这里把配置文件指向 tmp。
CONFIG_FILE = _CONFIG_DIR / "config.json"

_RECENT_LIMIT = 10


class EditorConfig:
    """Singleton-like config accessor."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ── persistence ────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not CONFIG_FILE.exists():
            return {}
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── workspace ──────────────────────────────────────────────────────

    def workspace(self) -> Optional[Path]:
        """当前工作区目录；未设或目录不存在 → None。"""
        data = self._load()
        cur = data.get("current_workspace") or ""
        if not cur:
            return None
        p = Path(cur)
        return p if p.is_dir() else None

    def set_workspace(self, path: str) -> Path:
        """切换工作区。目录必须已存在；自动加入 recent_workspaces。

        :raises ValueError: 目录不存在。
        """
        p = Path(path).expanduser().resolve()
        if not p.is_dir():
            raise ValueError("目录不存在")
        data = self._load()
        recent = [r for r in data.get("recent_workspaces", []) if isinstance(r, str)]
        ps = str(p)
        # 去重前插，保留仍存在的，限长。
        recent = [ps] + [r for r in recent if r != ps and Path(r).is_dir()]
        recent = recent[:_RECENT_LIMIT]
        data["current_workspace"] = ps
        data["recent_workspaces"] = recent
        self._save(data)
        return p

    def recent(self) -> list:
        """最近工作区列表（过滤掉已删除的）。"""
        data = self._load()
        out = []
        for r in data.get("recent_workspaces", []):
            if isinstance(r, str) and Path(r).is_dir():
                out.append(r)
        return out


# ── module-level helpers ───────────────────────────────────────────────


def get_workspace() -> Optional[Path]:
    return EditorConfig().workspace()


def get_tasks_dir() -> Path:
    """工作区根目录。**未设工作区时抛错**——调用方应先用 `get_workspace()` 判空。"""
    ws = get_workspace()
    if ws is None:
        raise RuntimeError("workspace not set")
    return ws


def get_testcases_dir() -> Path:
    """工作区下 testcases/，存放用例 .py，惰性创建。"""
    ws = get_tasks_dir()
    p = ws / "testcases"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_images_dir() -> Path:
    """工作区下 images/，惰性创建。"""
    ws = get_tasks_dir()
    p = ws / "images"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_screenshots_dir() -> Path:
    """工作区下 screenshots/，惰性创建。"""
    ws = get_tasks_dir()
    p = ws / "screenshots"
    p.mkdir(parents=True, exist_ok=True)
    return p
