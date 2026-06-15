# -*- coding: utf-8 -*-
"""应用管理 mixin —— start / stop / restart / get_current / clear_app。"""
from typing import Optional

from ha4t.utils.log_utils import cost_time


class AppMixin:
    @cost_time
    def start_app(self, app_name: Optional[str] = None,
                  activity: Optional[str] = None) -> None:
        """启动应用。``app_name`` / ``activity`` 为 None 时从 config 取默认值。"""
        _app = app_name or self.config.resolve_app_name()
        _act = activity or self.config.android_activity_name
        if not _app:
            raise ValueError("app_name 必须提供或在 connect() 时通过 config 设置")
        self.driver.app_start(_app, _act or None)

    @cost_time
    def stop_app(self, app_name: Optional[str] = None) -> None:
        _app = app_name or self.config.resolve_app_name()
        self.driver.app_stop(_app)

    def restart_app(self, app_name: Optional[str] = None,
                    activity: Optional[str] = None) -> None:
        self.stop_app(app_name)
        self.start_app(app_name, activity)

    def get_current_app(self) -> str:
        return self.driver.app_current()

    def clear_app(self, app_name: Optional[str] = None) -> None:
        """清除应用数据（仅 Android）。"""
        _app = app_name or self.config.resolve_app_name()
        self.driver.app_clear(_app)
