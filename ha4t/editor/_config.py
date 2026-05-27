# -*- coding: utf-8 -*-
r"""
Editor configuration manager.
Config file: ~/.ha4t/config.json (or %USERPROFILE%\.ha4t\config.json on Windows)
"""
import json
import os
from pathlib import Path


_CONFIG_DIR = Path.home() / ".ha4t"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

_DEFAULTS = {
    "tasks_dir": str(Path.home() / "Documents" / "HA4T" / "tasks" if os.name == "nt" else Path.home() / "ha4t" / "tasks"),
    "images_dir": str(Path.home() / "Documents" / "HA4T" / "images" if os.name == "nt" else Path.home() / "ha4t" / "images"),
    "screenshots_dir": str(Path.home() / "Documents" / "HA4T" / "screenshots" if os.name == "nt" else Path.home() / "ha4t" / "screenshots"),
}


class EditorConfig:
    """Singleton-like config accessor."""

    _instance = None
    _data = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        if _CONFIG_FILE.exists():
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # Merge with defaults to ensure all keys exist
                self._data = {**_DEFAULTS, **loaded}
            except Exception:
                self._data = _DEFAULTS.copy()
        else:
            self._data = _DEFAULTS.copy()
            self._save()

    def _save(self):
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value
        self._save()

    def path(self, key: str) -> Path:
        """Return the configured path as a Path object (expanding ~)."""
        p = self.get(key, _DEFAULTS.get(key))
        return Path(p).expanduser()


# Convenience functions for direct import
_cfg = EditorConfig()

def get_tasks_dir() -> Path:
    p = _cfg.path("tasks_dir")
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_images_dir() -> Path:
    p = _cfg.path("images_dir")
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_screenshots_dir() -> Path:
    p = _cfg.path("screenshots_dir")
    p.mkdir(parents=True, exist_ok=True)
    return p
