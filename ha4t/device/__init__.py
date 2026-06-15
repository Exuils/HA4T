# -*- coding: utf-8 -*-
"""``Device`` 类装配：用多继承把所有 mixin 拼到一起。

子类划分：
- ``DeviceBase`` —— ``__init__`` / platform property / Selector 解析 / 私有找点 helper
- ``CaptureMixin`` —— screenshot
- ``InteractionMixin`` —— click / swipe / drag / key / home / popup_apps
- ``QueryMixin`` —— exists / wait / get_text / assert_element
- ``AppMixin`` —— start_app / stop_app / restart_app / clear_app / get_current_app
- ``FileMixin`` —— pull / upload / delete file

每个 mixin 都是纯方法集合（无 ``__init__``），通过 ``DeviceBase`` 的状态
（``self.driver`` / ``self.config`` / 解析 helper）协作。多继承顺序：
``DeviceBase`` 最后，因为它持有 ``__init__``，按 Python MRO 规则放在最右
意味着其它 mixin 的方法优先（实际我们没有覆盖，但保持一致）。
"""
from ha4t.device._base import DeviceBase
from ha4t.device.apps import AppMixin
from ha4t.device.capture import CaptureMixin
from ha4t.device.files import FileMixin
from ha4t.device.interaction import InteractionMixin
from ha4t.device.queries import QueryMixin


class Device(
    InteractionMixin,
    QueryMixin,
    AppMixin,
    FileMixin,
    CaptureMixin,
    DeviceBase,
):
    """跨平台 UI 自动化设备入口。

    持有 ``config`` + ``driver``，把所有 UI 操作统一暴露在 ``self`` 上。
    平台差异由 ``driver`` 隔离，selector 跨平台语义由 ``self._resolve_selector``
    + ``Selector`` 类承担，``Device`` 自身只负责 *动作分发*。
    """


__all__ = ["Device"]
