# -*- coding: utf-8 -*-
# @时间       : 2023/10/26 18:18
# @作者       : caishilong
# @文件名      : logs.py
# @项目名      : pythonProject
# @Software   : PyCharm
import functools
import logging
import os
import time
from io import BytesIO

import allure
import colorlog
import PIL.Image

from ha4t.config import Config as CF

if CF.SAVE_LOG:
    path = CF.LOG_PATH if CF.LOG_PATH else os.path.join(os.path.dirname(__file__), 'log')
    logname = os.path.join(path, f"{time.strftime('%Y-%m-%d-%H-%M-%S')}.logs")
else:
    logname = None  # 不保存日志时，logname设为None

log_colors_config = {
    'DEBUG': 'white',  # cyan white
    'INFO': 'green',
    'WARNING': 'yellow',
    'ERROR': 'red',
    'CRITICAL': 'bold_red',
}


class Logger:
    def __init__(self):
        # 如果不保存日志，则不进行文件相关操作
        self.logname = logname

    def __printconsole(self, level, message):
        logger = logging.getLogger("ha4t")
        logger.setLevel(logging.DEBUG)

        # 如果需要保存日志
        if self.logname:
            fh = logging.FileHandler(self.logname, 'a', encoding='utf-8')
            fh.setLevel(logging.DEBUG)
            logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)

        console_formatter = colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
            log_colors=log_colors_config
        )
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        if self.logname:
            fh.setFormatter(formatter)
        ch.setFormatter(console_formatter)

        logger.addHandler(ch)

        # 记录日志
        if level == 'info':
            logger.info(message)
        elif level == 'debug':
            logger.debug(message)
        elif level == 'warning':
            logger.warning(message)
        elif level == 'error':
            logger.error(message)

        if self.logname:
            logger.removeHandler(fh)
            fh.close()  # 关闭文件处理器

        logger.removeHandler(ch)

    def debug(self, message):
        self.__printconsole('debug', message)

    def info(self, message):
        self.__printconsole('info', message)

    def warning(self, message):
        self.__printconsole('warning', message)

    def error(self, message):
        self.__printconsole('error', message)


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


def _attach_screenshot(name="screenshot"):
    """附加当前设备截图到 Allure step"""
    try:
        from ha4t import device
        if device and hasattr(device, 'driver') and device.driver:
            img = device.driver.screenshot()
            if img:
                if isinstance(img, PIL.Image.Image):
                    buf = BytesIO()
                    img.save(buf, format='PNG')
                    allure.attach(buf.getvalue(), name=name, attachment_type=allure.attachment_type.PNG)
                elif isinstance(img, bytes):
                    allure.attach(img, name=name, attachment_type=allure.attachment_type.PNG)
    except Exception:
        pass


def cost_time(func):
    """
    计算函数运行时间，log打印每个操作事件耗时
    :param func:
    :return:
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()  # 记录开始时间
        try:
            with allure.step(f"动作：{func.__name__},参数：{args, *kwargs.values()}"):
                result = func(*args, **kwargs)  # 调用原始函数
            log_out(
                f"动作：【{func.__name__}】-执行成功，参数：{args, *kwargs.values()}，耗时：{round(time.time() - start_time, 3)}秒")
            return result
        except Exception as e:
            _attach_screenshot(f"{func.__name__}_失败")
            log_out(
                f"动作：【{func.__name__}】-执行失败，参数：{args, *kwargs.values()},耗时：{round(time.time() - start_time, 3)}秒 失败原因：{e}",
                level=2)
            raise e

    return wrapper


Log = Logger()
