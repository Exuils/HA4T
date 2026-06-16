# -*- coding: utf-8 -*-
"""HA4T —— 跨平台 UI 自动化测试框架。

核心抽象：
- ``connect(platform=...)`` 返回 ``Device``，所有平台同一套 API：
    ``dev.click(...)`` / ``dev.swipe(...)`` / ``dev.wait(...)`` / ``dev.assert_element(...)`` ...
- ``Selector`` 类承载跨平台元素定位器：::

    from ha4t import connect, Selector
    LOGIN = Selector(android={"text": "登录"}, ios={"label": "Login"})
    dev = connect(platform="android")
    dev.click(LOGIN)                       # 平台分桶自动选 android 分支

- 临时定位也接受 canonical kwargs，自动按当前平台翻译：::

    dev.click(text="登录")                 # iOS 上自动用 label='登录'

模块结构：
- ``ha4t.selector``  —— Selector / canonical→native 映射
- ``ha4t.device``    —— Device 类（用 mixin 装配出来）
- ``ha4t.matchers``  —— OCR / 图像找点（与 Device 解耦的找点策略）
- ``ha4t.drivers``   —— Android / iOS / Harmony 平台 driver

POM 工程化用法见工作区根目录 ``CLAUDE.md``（编辑器初始化时自动生成）。
"""
import os
from typing import List, Optional

from ha4t.config import DeviceConfig
from ha4t.device import Device
from ha4t.drivers import DRIVERS
from ha4t.exceptions import DeviceConnectionError
from ha4t.selector import Selector, SelectorNotAvailableError
from ha4t.utils.log_utils import log_out

__version__ = "0.1.6"
__all__ = [
    "__version__", "Device", "connect", "include",
    "Selector", "SelectorNotAvailableError",
]


def connect(
    platform: str = "android",
    device_serial: Optional[str] = None,
    android_package_name: Optional[str] = None,
    android_activity_name: Optional[str] = None,
    **driver_kwargs,
) -> Device:
    """连接设备，返回 ``Device``。

    :param platform: 平台标识 ``android`` / ``ios`` / ``harmony``
    :param device_serial: 设备序列号；为 ``None`` 时取系统第一个可用设备
    :param android_package_name: Android 包名（写进 ``DeviceConfig``，``start_app`` 默认值）
    :param android_activity_name: Android 启动 Activity（同上）
    :param driver_kwargs: 透传给底层 driver.connect() 的额外关键字
    """
    _platform = platform.lower()
    if _platform not in DRIVERS:
        raise DeviceConnectionError(
            f"不支持的平台：{_platform}，请使用 android / ios / harmony"
        )

    driver_cls = DRIVERS[_platform]
    driver = driver_cls()
    actual_serial = driver.connect(device_serial, **driver_kwargs)

    cfg = DeviceConfig()
    cfg.platform = _platform
    cfg.device_serial = actual_serial or device_serial or ''
    if android_package_name:
        cfg.android_package_name = android_package_name
        cfg.app_name = android_package_name
    if android_activity_name:
        cfg.android_activity_name = android_activity_name
    cfg.screen_size = driver.screen_size()

    dev = Device(driver=driver, config=cfg)
    dev.device_info = str(driver.get_device_info())
    log_out(f"设备信息：{dev.device_info}")
    return dev


# ── 用例引用 ────────────────────────────────────────────────────────────────

_INCLUDE_STACK: List[str] = []


def include(path: str) -> None:
    """在当前进程内执行另一个用例 .py 文件，复用其步骤。

    被引用文件中的 ``import os / os.environ / from ha4t import ... /
    from time import sleep / dev = connect(...)`` 这些样板代码会被剥离，
    其余源码在调用者的全局命名空间中 ``exec``——这样被引用文件可以直接
    使用调用者已经建立的 ``dev`` 连接 / ``sleep`` 等符号，无需重新连接设备。

    路径解析顺序：调用者所在目录 → 调用者所在目录下的 testcases/（编辑器工作区模式）→
    当前工作目录下的 testcases/ → 当前工作目录 → 字面路径。
    通过 ``_INCLUDE_STACK`` 防止循环引用。
    """
    import inspect

    frame = inspect.stack()[1].frame
    caller_file = frame.f_globals.get("__file__")
    candidates: List[str] = []
    if caller_file:
        caller_dir = os.path.dirname(os.path.abspath(caller_file))
        candidates.append(os.path.join(caller_dir, path))
        candidates.append(os.path.join(caller_dir, "testcases", path))
    candidates.append(os.path.join(os.getcwd(), "testcases", path))
    candidates.append(os.path.join(os.getcwd(), path))
    candidates.append(path)

    resolved = next((p for p in candidates if os.path.isfile(p)), None)
    if resolved is None:
        raise FileNotFoundError(
            f"include: 找不到用例文件 '{path}' (已尝试: {candidates})"
        )
    resolved = os.path.abspath(resolved)
    if resolved in _INCLUDE_STACK:
        chain = " -> ".join(_INCLUDE_STACK + [resolved])
        raise RuntimeError(f"include: 循环引用：{chain}")

    with open(resolved, encoding="utf-8") as f:
        src = f.read()

    # 剥离样板：避免被引用文件重新 connect 设备 / 重复导入。
    skip_prefixes = (
        "from ha4t import",
        "import ha4t",
        "from time import sleep",
        "import os",
        "os.environ[",
    )
    cleaned_lines: List[str] = []
    for line in src.split("\n"):
        stripped = line.lstrip()
        if any(stripped.startswith(p) for p in skip_prefixes):
            continue
        # dev = connect(...) / dev=connect(...)
        if stripped.split("=", 1)[0].strip().isidentifier() and "=" in stripped:
            _, _, rhs = stripped.partition("=")
            if rhs.lstrip().startswith("connect("):
                continue
        cleaned_lines.append(line)
    cleaned_src = "\n".join(cleaned_lines)

    # 把调用者的 locals 也合并进 exec globals —— 这样被引用文件能看到调用者
    # 函数内定义的符号（不止 module-level）；编辑器跑用例时 dev 就在 module
    # top-level，但这个 fallback 让 include 在任何调用栈深度都可用。
    exec_globals = dict(frame.f_globals)
    exec_globals.update(frame.f_locals)

    _INCLUDE_STACK.append(resolved)
    try:
        code_obj = compile(cleaned_src, resolved, "exec")
        exec(code_obj, exec_globals)  # noqa: S102 — intentional script include
    finally:
        _INCLUDE_STACK.pop()
