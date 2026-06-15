# -*- coding: utf-8 -*-
# @时间       : 2023/10/26 18:18
# @作者       : caishilong
# @文件名      : log_utils.py
# @项目名      : HA4T
# @Software   : PyCharm
import functools
import logging
import os
import time
from io import BytesIO
from typing import Optional

import allure
import colorlog
import PIL.Image

from ha4t.config import global_config

# 颜色配置
log_colors_config = {
    'DEBUG': 'white',
    'INFO': 'green',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'CRITICAL': 'bold_red',
}


class Logger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.logger = logging.getLogger("ha4t")
        self.logger.setLevel(logging.DEBUG)
        
        # 避免重复添加 handler
        if not self.logger.handlers:
            # 控制台处理器
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            console_formatter = colorlog.ColoredFormatter(
                '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
                log_colors=log_colors_config
            )
            ch.setFormatter(console_formatter)
            self.logger.addHandler(ch)

            # 文件处理器 (如果配置开启)
            if global_config.save_log:
                path = global_config.log_path if global_config.log_path else os.path.join(os.getcwd(), 'log')
                if not os.path.exists(path):
                    os.makedirs(path)
                log_file = os.path.join(path, f"{time.strftime('%Y-%m-%d')}.log")
                fh = logging.FileHandler(log_file, 'a', encoding='utf-8')
                fh.setLevel(logging.DEBUG)
                file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
                fh.setFormatter(file_formatter)
                self.logger.addHandler(fh)

        self._initialized = True

    def debug(self, message):
        self.logger.debug(message)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)


# 全局单例对象
Log = Logger()


def log_out(msg, level=1):
    """
    打印日志
    :param msg: 日志信息
    :param level: 日志级别，1：info，2：error
    """
    if level == 1:
        Log.info(msg)
    elif level == 2:
        Log.error(msg)


def _attach_screenshot(name="screenshot", device=None):
    """附加当前设备截图到 Allure step"""
    try:
        if device is None or device.driver is None:
            return
        img = device.driver.screenshot()
        if img:
            from io import BytesIO
            buf = BytesIO()
            if isinstance(img, bytes):
                allure.attach(img, name=name, attachment_type=allure.attachment_type.PNG)
            else:
                img.save(buf, format='PNG')
                allure.attach(buf.getvalue(), name=name, attachment_type=allure.attachment_type.PNG)
    except Exception as e:
        Log.warning(f"附加截图失败: {e}")


def cost_time(func):
    """
    计算函数运行时间，log 打印每个操作事件耗时。

    顺便剥掉 selector kwargs 里所有 `_` 开头的 meta 字段（如 `_doc`/`_parent`
    —— POM 元素自带的注释 / 父子关系，给 AI 和编辑器 UI 用，driver 不该看到）。
    `**ELEMENTS[name]` 把整个 selector dict 解包传进来时，未列出的 meta 字段
    会被底层 driver 当未知 kwarg 拒绝（u2 的 _selector.__setitem__ 直接 raise）。
    在这里统一过滤，POM 文件就能干净存储这些元数据而不污染调用方代码。
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # 剥 `_` 前缀 meta —— `**ELEMENTS[name]` 调用时携带的 doc/parent 等
        kwargs = {k: v for k, v in kwargs.items() if not k.startswith('_')}
        start_time = time.time()
        args_str = str(args)[:100] + "..." if len(str(args)) > 100 else str(args)
        kwargs_str = str(kwargs)[:100] + "..." if len(str(kwargs)) > 100 else str(kwargs)

        try:
            with allure.step(f"动作：{func.__name__}, 参数：{args_str}, {kwargs_str}"):
                result = func(*args, **kwargs)
            log_out(
                f"动作：【{func.__name__}】-执行成功，耗时：{round(time.time() - start_time, 3)}秒")
            return result
        except Exception as e:
            dev = args[0] if args and hasattr(args[0], "driver") else None
            _attach_screenshot(f"{func.__name__}_失败", dev)
            log_out(
                f"动作：【{func.__name__}】-执行失败，耗时：{round(time.time() - start_time, 3)}秒，原因：{e}",
                level=2)
            raise e

    return wrapper
