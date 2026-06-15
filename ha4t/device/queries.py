# -*- coding: utf-8 -*-
"""查询 mixin —— exists / wait / get_text / get_page_text / assert_element。"""
import os
import re
import time
from typing import Optional

from ha4t.config import global_config
from ha4t.matchers.ocr import read_page_text
from ha4t.utils.log_utils import cost_time


class QueryMixin:
    # ── 存在性 ────────────────────────────────────────────────────────────────

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

    # ── 等待 ──────────────────────────────────────────────────────────────────

    @cost_time
    def wait(self, *args, timeout: Optional[float] = None,
             reverse: bool = False, raise_error: bool = True,
             use_in_text: bool = False, **kwargs):
        """等待元素出现/消失。timeout 默认读取 global_config.find_timeout。"""
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

    # ── 文字 ──────────────────────────────────────────────────────────────────

    def get_page_text(self) -> str:
        """OCR 识别页面全部文字并拼接返回。"""
        return read_page_text(self.driver.screenshot)

    @cost_time
    def get_text(self, *args, **kwargs) -> str:
        """获取元素的文本内容。"""
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

    # ── 断言 ──────────────────────────────────────────────────────────────────

    @cost_time
    def assert_element(self, *args, operator: str = 'eq', expected=None,
                       extract: str = 'text', raise_error: bool = True, **kwargs) -> bool:
        """元素断言。operator: eq/ne/contains/not_contains/empty/not_empty/regex/exists_true/exists_false。"""
        args, kwargs = self._resolve_selector(args, kwargs)
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
