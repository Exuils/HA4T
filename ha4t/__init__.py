# -*- coding: utf-8 -*-
__version__ = "0.1.6"
__all__ = ["__version__", "Device", "connect", "include", "Selector", "SelectorNotAvailableError"]

import os
import time
from typing import Optional, Tuple, Union, List

import PIL.Image
import numpy as np

from ha4t.config import DeviceConfig, global_config
from ha4t.drivers import DRIVERS
from ha4t.exceptions import DeviceConnectionError
from ha4t.selector import Selector, SelectorNotAvailableError, to_native
from ha4t.utils.log_utils import log_out, cost_time

# ── OCR 懒加载 ────────────────────────────────────────────────────────────────

_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        from ha4t.orc import OCR
        _ocr = OCR()
    return _ocr


# ── Device 核心对象 ───────────────────────────────────────────────────────────

class Device:
    """持有 config + driver，暴露所有 UI 自动化操作方法。"""

    def __init__(self, driver=None, config: Optional[DeviceConfig] = None):
        self.driver = driver
        self.config: DeviceConfig = config or DeviceConfig()
        self.device_info: str = ""

    @property
    def platform(self) -> str:
        """当前连接的平台名（android / ios / harmony）。"""
        return (self.config.platform or "").lower()

    # ── Selector 解析：跨平台元素入口 ─────────────────────────────────────────
    def _resolve_selector(self, args, kwargs):
        """所有元素操作入口（click/wait/exists/...）的预处理。

        归一化两条路径：
          (1) `dev.click(SelectorObj, ...)` —— 第一个位置参数是 Selector 实例 →
              `for_platform(self.platform)` 解出 native kwargs，**合并进 kwargs**，
              并把 Selector 从 args 弹出。
          (2) `dev.click(text="登录")` —— 走 canonical 映射，按当前平台翻译成 native
              kwargs。已经是 native 字段的也会保守透传不动。

        坐标 tuple、字符串 OCR 文字、Template 等其它 args[0] 形态原样保留 ——
        Selector 解析只针对 Selector 实例触发。

        SelectorNotAvailableError 由 for_platform 抛，cost_time 装饰器会包成可读
        错误信息（包含函数名）。
        """
        if args and isinstance(args[0], Selector):
            sel = args[0]
            native = sel.for_platform(self.platform)
            # Selector 提供的字段不该被 caller 的 kwargs 覆盖（caller 显式传了 Selector
            # 就是想用元素 selector）；caller 的 kwargs 里 timeout / threshold 等动作参数仍保留
            merged = {**kwargs, **native}
            return args[1:], merged
        # 路径 (2)：raw kwargs 走 canonical → native 映射
        # 排除动作参数（timeout / threshold / interval / duration / dx / dy / rgb / ...）—— 这些
        # 不是 selector 字段，映射函数不动它们就行（to_* 透传未知字段）
        if kwargs and self.platform:
            kwargs = to_native(kwargs, self.platform)
        return args, kwargs

    # ── 截图 ──────────────────────────────────────────────────────────────────

    def screenshot(self, filename: Optional[str] = None) -> PIL.Image.Image:
        """截图并可选保存到本地。"""
        img = self.driver.screenshot()
        img = PIL.Image.fromarray(img) if isinstance(img, np.ndarray) else img
        if filename:
            img.save(filename)
        return img

    # ── 内部：坐标计算 ────────────────────────────────────────────────────────

    def _to_abs(self, p) -> Tuple[int, int]:
        """将比例坐标或绝对坐标统一转为绝对像素坐标。"""
        if isinstance(p[0], float):
            return (int(p[0] * self.config.screen_width),
                    int(p[1] * self.config.screen_height))
        return p

    def _perform_tap(self, x: int, y: int, duration: float = 0.1) -> None:
        self.driver.tap(x, y, duration)

    # ── 内部：元素定位 ────────────────────────────────────────────────────────

    def _find_pos_by_ocr(self, text: str, index: int = 0, timeout: float = 10) -> Tuple[int, int]:
        return _get_ocr().get_text_pos(
            text, self.driver.screenshot, index=index, timeout=timeout,
            screen_size=self.config.screen_size
        )

    def _find_pos_by_image(self, path: str, timeout: float = 10,
                           threshold: float = 0.8) -> Tuple[int, int]:
        from ha4t.aircv.cv import match_loop
        return match_loop(
            screenshot_func=self.driver.screenshot,
            template=path,
            timeout=timeout,
            threshold=threshold,
            screen_size=self.config.screen_size,
        )

    def _get_element_center(self, **kwargs) -> Tuple[int, int]:
        return self.driver.get_element_center(**kwargs)

    # ── 点击 ──────────────────────────────────────────────────────────────────

    @cost_time
    def click(self, *args, duration: float = 0.1, **kwargs) -> None:
        """
        点击操作，支持多种定位方式：

        - click(SelectorObj)         # 跨平台 Selector 对象（推荐 — POM 写法）
        - click((x, y))              # 绝对或比例坐标
        - click("文字")               # OCR 定位
        - click(Template(...))       # 图像匹配
        - click(text="xxx")          # canonical kwargs → 当前平台自动翻译
        - click(image="img.png")     # 图像路径
        """
        args, kwargs = self._resolve_selector(args, kwargs)
        if args:
            arg0 = args[0]
            if isinstance(arg0, tuple):
                if not arg0:
                    raise ValueError("坐标不能是空元组")
                if isinstance(arg0[0], int):
                    self._perform_tap(*self._to_abs(arg0), duration)
                elif isinstance(arg0[0], str):
                    raise NotImplementedError("webview 点击暂不支持")
            elif isinstance(arg0, str):
                pos = self._find_pos_by_ocr(arg0, index=args[1] if len(args) > 1 else 0)
                self._perform_tap(*pos, duration)
                self._perform_tap(*pos, duration)
            elif hasattr(arg0, 'filepath'):
                # Template 对象
                pos = self._find_pos_by_image(
                    arg0.filepath,
                    timeout=kwargs.get("timeout", 10),
                    threshold=kwargs.get("threshold", 0.8),
                )
                self._perform_tap(*pos, duration)
            elif isinstance(arg0, dict):
                self.driver.find(**arg0, **kwargs).tap(duration=duration) \
                    if hasattr(self.driver.find(**arg0), 'tap') \
                    else self._perform_tap(*self._get_element_center(**arg0), duration)
        elif kwargs.get("image"):
            path = os.path.join(global_config.current_path, kwargs["image"])
            grid = kwargs.pop("grid", None)
            splits = kwargs.pop("splits", None)
            if grid and splits:
                import cv2
                from ha4t.aircv.cv import Template
                source_image = self.driver.screenshot()
                source_image = np.array(
                    source_image.resize((self.config.screen_width, self.config.screen_height))
                )
                tpl = Template(
                    path,
                    threshold=kwargs.get("threshold", 0.8),
                    rgb=kwargs.get("rgb", False),
                    scale_max=kwargs.get("scale_max", 800),
                    scale_step=kwargs.get("scale_step", 0.005),
                )
                result = tpl._cv_match(source_image)
                if not result:
                    raise TimeoutError(f"图片匹配失败: {path}")
                rect = result["rectangle"]
                x1, y1 = rect[0]
                x3, y3 = rect[2]
                cell_w = (x3 - x1) / splits[0]
                cell_h = (y3 - y1) / splits[1]
                pos = (int(x1 + cell_w * (grid[0] + 0.5)),
                       int(y1 + cell_h * (grid[1] + 0.5)))
            else:
                pos = self._find_pos_by_image(
                    path,
                    timeout=kwargs.get("timeout", 10),
                    threshold=kwargs.get("threshold", 0.8),
                )
            self._perform_tap(*pos, duration)
        else:
            timeout = kwargs.pop("timeout", 3)
            xpath = kwargs.pop("xpath", None)
            if xpath:
                self.driver.find_xpath(xpath).click(timeout=timeout)
            else:
                el = self.driver.find(**kwargs)
                # u2: .click(timeout=) / wda: .tap_hold() / harmony: .click()
                if hasattr(el, 'click'):
                    el.click(timeout=timeout)
                else:
                    el.tap_hold(duration=duration)

    @cost_time
    def double_click(self, *args, interval: float = 0.05, **kwargs) -> None:
        """双击元素。"""
        self.click(*args, **kwargs)
        time.sleep(interval)
        self.click(*args, **kwargs)

    @cost_time
    def long_press(self, *args, duration: float = 1.0, **kwargs) -> None:
        """长按元素。"""
        self.click(*args, duration=duration, **kwargs)

    # ── 滑动 ──────────────────────────────────────────────────────────────────

    @cost_time
    def swipe(self, p1, p2, duration=None, steps=None) -> None:
        """滑动，坐标支持绝对像素或 0-1 比例。"""
        pos1 = self._to_abs(p1)
        pos2 = self._to_abs(p2)
        self.driver.swipe(*pos1, *pos2, duration=duration, steps=steps)

    @cost_time
    def swipe_up(self, duration: float = 0.2, steps: Optional[int] = None) -> None:
        self.swipe((0.5, 0.8), (0.5, 0.3), duration, steps)

    @cost_time
    def swipe_down(self, duration: float = 0.2, steps: Optional[int] = None) -> None:
        self.swipe((0.5, 0.3), (0.5, 0.8), duration, steps)

    @cost_time
    def swipe_left(self, duration: float = 0.1, steps: Optional[int] = None) -> None:
        self.swipe((0.8, 0.5), (0.2, 0.5), duration, steps)

    @cost_time
    def swipe_right(self, duration: float = 0.1, steps: Optional[int] = None) -> None:
        self.swipe((0.2, 0.5), (0.8, 0.5), duration, steps)

    @cost_time
    def popup_apps(self) -> None:
        """呼出多任务界面。"""
        self.swipe((0.5, 0.999), (0.5, 0.6), 0.1)

    @cost_time
    def drag(self, *args, dx: int = 0, dy: int = 0, duration: float = 0.5, **kwargs) -> None:
        """拖拽元素（偏移 dx/dy 像素）。支持 Selector 对象 / canonical kwargs。"""
        args, kwargs = self._resolve_selector(args, kwargs)
        if not args and not kwargs:
            raise ValueError("drag() 需要元素定位参数")
        center = self._get_element_center(**kwargs)
        self.driver.swipe(center[0], center[1],
                          center[0] + dx, center[1] + dy,
                          duration=duration)

    # ── 系统按键 ──────────────────────────────────────────────────────────────

    @cost_time
    def key(self, key_name: str) -> None:
        self.driver.press(key_name)

    @cost_time
    def home(self) -> None:
        self.driver.press("home")

    # ── 存在 / 等待 ───────────────────────────────────────────────────────────

    def _exists(self, *args, **kwargs) -> bool:
        args, kwargs = self._resolve_selector(args, kwargs)
        if args:
            arg0 = args[0]
            if isinstance(arg0, tuple):
                if isinstance(arg0[0], int):
                    return True
                raise NotImplementedError("webview 点击暂不支持")
            elif isinstance(arg0, str):
                try:
                    self._find_pos_by_ocr(arg0, index=args[1] if len(args) > 1 else 0, timeout=1)
                    return True
                except Exception:
                    return False
            elif isinstance(arg0, dict):
                path = os.path.join(global_config.current_path, arg0["image"])
                try:
                    self._find_pos_by_image(path, timeout=kwargs.get("timeout", 10),
                                            threshold=kwargs.get("threshold", 0.8))
                    return True
                except Exception:
                    return False
            elif hasattr(arg0, 'filepath'):
                try:
                    self._find_pos_by_image(arg0.filepath,
                                            timeout=kwargs.get("timeout", 10),
                                            threshold=kwargs.get("threshold", 0.8))
                    return True
                except Exception:
                    return False
        else:
            if kwargs.get("image"):
                path = os.path.join(global_config.current_path, kwargs["image"])
                try:
                    pos = self._find_pos_by_image(path,
                                                  timeout=kwargs.get("timeout", 10),
                                                  threshold=kwargs.get("threshold", 0.8))
                    return bool(pos)
                except Exception:
                    return False
            else:
                return bool(self.driver.find(**kwargs).exists)
        return False

    @cost_time
    def exists(self, *args, **kwargs) -> bool:
        return self._exists(*args, **kwargs)

    @cost_time
    def wait(self, *args, timeout: Optional[float] = None,
             reverse: bool = False, raise_error: bool = True,
             use_in_text: bool = False, **kwargs):
        """等待元素出现/消失。timeout 默认读取 global_config.find_timeout。支持 Selector 对象 / canonical kwargs。"""
        args, kwargs = self._resolve_selector(args, kwargs)
        _timeout = timeout if timeout is not None else global_config.find_timeout
        start = time.time()
        if use_in_text and args and isinstance(args[0], str):
            while True:
                page_text = self.get_page_text()
                if reverse:
                    if args[0] not in page_text:
                        return True
                else:
                    if args[0] in page_text:
                        return True
                if time.time() - start > _timeout:
                    if raise_error:
                        raise TimeoutError(f"等待OCR识别到指定文字[{args[0]}]超时")
                    return False
        while True:
            if reverse:
                if not self._exists(*args, **kwargs):
                    return True
            else:
                if self._exists(*args, **kwargs):
                    return True
            if time.time() - start > _timeout:
                if raise_error:
                    raise TimeoutError(f"等待元素超时：{args}, {kwargs}")
                return False

    # ── OCR / 文字 ────────────────────────────────────────────────────────────

    def get_page_text(self) -> str:
        """OCR 识别页面全部文字并拼接返回。"""
        return _get_ocr().get_page_text(self.driver.screenshot)

    @cost_time
    def get_text(self, *args, **kwargs) -> str:
        """获取元素的文本内容。支持 Selector 对象 / canonical kwargs。"""
        args, kwargs = self._resolve_selector(args, kwargs)
        if kwargs:
            try:
                el = self.driver.find(**kwargs)
                if hasattr(el, 'get_text'):
                    return el.get_text(timeout=3) or ""
                return getattr(el, 'text', None) or getattr(el, 'value', None) or ""
            except Exception:
                return ""
        elif args and isinstance(args[0], str):
            return args[0]
        return ""

    @cost_time
    def assert_element(self, *args, operator: str = 'eq', expected=None,
                       extract: str = 'text', raise_error: bool = True, **kwargs) -> bool:
        """元素断言，支持 eq/ne/contains/not_contains/empty/not_empty/regex/exists。支持 Selector 对象。"""
        args, kwargs = self._resolve_selector(args, kwargs)
        import re
        if extract == 'exists':
            exists_result = self._exists(*args, **kwargs)
            if operator == 'exists_true':
                result = exists_result
            elif operator == 'exists_false':
                result = not exists_result
            else:
                result = exists_result if operator == 'eq' else not exists_result
        else:
            actual = self.get_text(*args, **kwargs)
            if operator == 'eq':
                result = actual == expected
            elif operator == 'ne':
                result = actual != expected
            elif operator == 'contains':
                result = expected in actual
            elif operator == 'not_contains':
                result = expected not in actual
            elif operator == 'empty':
                result = not actual
            elif operator == 'not_empty':
                result = bool(actual)
            elif operator == 'regex':
                result = bool(re.search(expected, actual))
            else:
                raise ValueError(f"不支持的断言算子: {operator}")

        if not result and raise_error:
            detail = (self.get_text(*args, **kwargs) if extract == 'text'
                      else f"exists={self._exists(*args, **kwargs)}")
            raise AssertionError(
                f"断言失败: operator={operator}, expected={expected}, actual={detail}"
            )
        return result

    # ── 应用管理 ──────────────────────────────────────────────────────────────

    @cost_time
    def start_app(self, app_name: Optional[str] = None,
                  activity: Optional[str] = None) -> None:
        """启动应用。app_name/activity 为 None 时从 config 取默认值。"""
        _app = app_name or self.config.resolve_app_name()
        _act = activity or self.config.android_activity_name
        if not _app:
            raise ValueError("app_name 不能为空")
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

    # ── 文件传输 ──────────────────────────────────────────────────────────────

    @cost_time
    def pull_file(self, src_path: Union[List[str], str], filename: str) -> None:
        """从设备拉取文件到本地。"""
        remote = "/".join(src_path) if isinstance(src_path, list) else src_path
        log_out(f"从设备路径 {remote} 下载文件 {filename}")
        self.driver.pull_file(remote, filename)

    @cost_time
    def upload_files(self, src_path: str) -> None:
        """上传文件或文件夹到设备。"""
        import os as _os
        if _os.path.isdir(src_path):
            from ha4t.utils.files_operat import get_file_list as _gfl
            for f in _gfl(src_path):
                self.driver.push_file(f, f"/sdcard/{_os.path.basename(f)}")
        else:
            self.driver.push_file(src_path, f"/sdcard/{_os.path.basename(src_path)}")
        log_out(f"文件 {src_path} 上传成功")

    @cost_time
    def delete_file(self, file_path: Union[List[str], str]) -> None:
        """删除设备上的文件。"""
        remote = "/".join(file_path) if isinstance(file_path, list) else file_path
        self.driver.delete_file(remote)
        log_out(f"设备文件 {remote} 删除成功")

    def clear_app(self, app_name: Optional[str] = None) -> None:
        """清除应用数据（仅 Android）。"""
        _app = app_name or self.config.resolve_app_name()
        self.driver.app_clear(_app)


def connect(platform: str = "android",
            device_serial: Optional[str] = None,
            android_package_name: Optional[str] = None,
            android_activity_name: Optional[str] = None,
            **driver_kwargs) -> Device:
    """
    连接设备，支持 android / ios / harmony 三平台。

    :param platform: 平台标识 android / ios / harmony
    :param device_serial: 设备序列号
    :param android_package_name: Android 包名
    :param android_activity_name: Android 启动 Activity
    :returns: 已连接的 Device 实例
    """
    _platform = platform.lower()

    if _platform not in DRIVERS:
        raise DeviceConnectionError(
            f"不支持的平台：{_platform}，请使用 android / ios / harmony"
        )

    driver_cls = DRIVERS[_platform]
    driver = driver_cls()

    # connect() 返回实际使用的序列号
    actual_serial = driver.connect(device_serial, **driver_kwargs)

    # 组装 DeviceConfig
    cfg = DeviceConfig()
    cfg.platform = _platform
    cfg.device_serial = actual_serial or device_serial or ''

    if android_package_name:
        cfg.android_package_name = android_package_name
        cfg.app_name = android_package_name
    if android_activity_name:
        cfg.android_activity_name = android_activity_name

    # 查询屏幕尺寸
    cfg.screen_size = driver.screen_size()

    dev = Device(driver=driver, config=cfg)
    dev.device_info = str(driver.get_device_info())

    log_out(f"设备信息：{dev.device_info}")

    return dev

# ── 用例引用 (步骤复用) ──────────────────────────────────────────────

_INCLUDE_STACK: List[str] = []


def include(path: str) -> None:
    """在当前进程内执行另一个用例 .py 文件，复用其步骤。

    被引用文件中的 ``import os / os.environ / from ha4t import ... /
    from time import sleep / dev = connect(...)`` 这些样板代码会被剥离，
    其余源码在调用者的全局命名空间中 ``exec``——这样被引用文件可以直接
    使用调用者已经建立的 ``dev`` 连接、``sleep`` 等符号，无需重新连接设备。

    路径解析顺序：调用者所在目录 → 当前工作目录 → 字面路径。
    通过 ``_INCLUDE_STACK`` 防止循环引用。

    :param path: 被引用用例的相对/绝对 .py 路径
    """
    import inspect

    frame = inspect.stack()[1].frame
    caller_file = frame.f_globals.get("__file__")
    candidates: List[str] = []
    if caller_file:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(caller_file)), path))
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
        # dev = connect(...) / dev=connect(...) — 任何对 connect 的赋值
        if stripped.lstrip().split("=", 1)[0].strip().isidentifier() and "=" in stripped:
            lhs, _, rhs = stripped.partition("=")
            if rhs.lstrip().startswith("connect("):
                continue
        cleaned_lines.append(line)
    cleaned_src = "\n".join(cleaned_lines)

    # Merge caller locals into the exec globals so symbols defined inside a
    # function (e.g. tests, helper wrappers) are visible to the included file
    # in addition to module-level ones. This is how editor scripts always
    # populate `dev` at module top level, but the union keeps the helper
    # usable from any scope.
    exec_globals = dict(frame.f_globals)
    exec_globals.update(frame.f_locals)

    _INCLUDE_STACK.append(resolved)
    try:
        code_obj = compile(cleaned_src, resolved, "exec")
        exec(code_obj, exec_globals)  # noqa: S102 — intentional script include
    finally:
        _INCLUDE_STACK.pop()
