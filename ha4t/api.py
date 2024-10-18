# -*- coding: utf-8 -*-
# @时间       : 2024/8/23 15:24
# @作者       : caishilong
# @文件名      : api.py
# @项目名      : Uimax
# @Software   : PyCharm
"""
ui 自动化操作接口
提供操作如：点击、滑动、输入、ocr识别等
"""
import json
import os
import subprocess
import time
from typing import Optional, Union, Tuple, List, Any

import PIL.Image
import logreset
import numpy as np
import uiautomator2 as u2
import wda

from ha4t.aircv.cv import match_loop, Template
from ha4t.config import Config as _CF
from ha4t.orc import OCR
from ha4t.utils.files_operat import get_file_list as _get_file_list
from ha4t.utils.log_utils import log_out, cost_time

logreset.reset_logging()  # paddleocr 会污染 logging
ocr = OCR()


class Device:
    def __init__(self, platform: str, device_id: Optional[str] = None, port: int = 8100):
        """
        连接手机,原生操作
        :param platform: 平台类型，'ios' 或 'android'
        :param device_id: 设备ID，如果为None则自动获取
        :param port: 端口号，默认为8100
        """
        self.adb: Optional[Any] = None
        if platform == "ios":
            try:
                _CF.DEVICE_SERIAL = device_id or wda.list_devices()[0].serial
            except IndexError:
                raise IndexError("未找到设备，请检查连接")
            self.driver: wda.Client = wda.USBClient(udid=_CF.DEVICE_SERIAL, port=port)
        else:
            self.driver: u2.Device = u2.connect(serial=device_id)
            self.adb = self.driver.adb_device
            _CF.DEVICE_SERIAL = self.adb.serial
        # self.driver.app_start(CF.APP_NAME)
        self.device_info = json.dumps(self.driver.info, ensure_ascii=False, indent=4)
        log_out(f"设备信息：{self.device_info}")


device = Device(_CF.PLATFORM, device_id=_CF.DEVICE_SERIAL)
driver: Union[u2.Device, wda.Client] = device.driver
screen_size: Tuple[int, int] = driver.window_size()
_CF.SCREEN_WIDTH, _CF.SCREEN_HEIGHT = screen_size


@cost_time
def click(*args, duration: float = 0.1, **kwargs) -> None:
    """
    点击操作，支持多种定位方式
    用法：
    1. click((x,y))  # 坐标点击
    2. click("TEXT")  # 文字点击,OCR识别
    3. click(image="path/to/image.png")  # 图像匹配点击
    4. click(**kwargs)  # uiautomator2/wda的点击（适合原生app，速度快，非H5应用建议使用）
    """

    def perform_click(x, y, duration):
        """
        执行点击操作，根据平台选择不同的点击方式
        :param x: x坐标
        :param y: y坐标
        :param duration: 点击持续时间
        """
        if _CF.PLATFORM == "ios":
            driver.tap_hold(x, y, duration=duration)
        else:
            driver.long_click(x, y, duration=duration)

    if args:
        if isinstance(args[0], tuple):
            if isinstance(args[0][0], int):
                perform_click(*args[0], duration)
            elif isinstance(args[0][0], str):
                raise NotImplementedError("webview点击暂不支持")
        elif isinstance(args[0], str):
            pos = ocr.get_text_pos(args[0], driver.screenshot, index=args[1] if len(args) > 1 else 0)
            perform_click(*pos, duration)
        elif isinstance(args[0], dict):
            path = os.path.join(_CF.CURRENT_PATH, args[0]["image"])
            pos = match_loop(screenshot_func=driver.screenshot, template=path, timeout=kwargs.get("timeout", 10),
                             threshold=kwargs.get("threshold", 0.8))
            perform_click(*pos, duration)
        elif isinstance(args[0], Template):
            pos = match_loop(screenshot_func=driver.screenshot, template=args[0].filepath,
                             timeout=kwargs.get("timeout", 10), threshold=kwargs.get("threshold", 0.8))
            perform_click(*pos, duration)
    elif kwargs.get("image"):
        path = os.path.join(_CF.CURRENT_PATH, kwargs["image"])
        pos = match_loop(screenshot_func=driver.screenshot, template=path, timeout=kwargs.get("timeout", 10),
                         threshold=kwargs.get("threshold", 0.8))
        perform_click(*pos, duration)
    else:
        if _CF.PLATFORM == "ios":
            driver(**kwargs).tap_hold(duration=duration)
        else:
            driver(**kwargs).long_click(duration=duration)


def _exists(*args, **kwargs) -> bool:
    """
        判断元素是否存在
        :param args: 可变参数，用于不同的定位方式
        :param kwargs: 关键字参数，用于uiautomator2/wda的定位
        :return: 元素是否存在
        """
    if args:
        if isinstance(args[0], tuple):
            if isinstance(args[0][0], int):
                return True
            elif isinstance(args[0][0], str):
                raise NotImplementedError("webview点击暂不支持")
        elif isinstance(args[0], str):
            try:
                pos = ocr.get_text_pos(args[0], driver.screenshot, index=args[1] if len(args) > 1 else 0, timeout=1)
                return True
            except:
                return False

        elif isinstance(args[0], dict):
            path = os.path.join(_CF.CURRENT_PATH, args[0]["image"])
            try:
                match_loop(screenshot_func=driver.screenshot, template=path, timeout=kwargs.get("timeout", 10),
                           threshold=kwargs.get("threshold", 0.8))
                return True
            except:
                return False
        elif isinstance(args[0], Template):
            try:
                match_loop(screenshot_func=driver.screenshot, template=args[0].filepath,
                           timeout=kwargs.get("timeout", 10),
                           threshold=kwargs.get("threshold", 0.8))
                return True
            except:
                return False
    else:
        if kwargs.get("image"):
            path = os.path.join(_CF.CURRENT_PATH, kwargs["image"])
            pos = match_loop(screenshot_func=driver.screenshot, template=path, timeout=kwargs.get("timeout", 10),
                             threshold=kwargs.get("threshold", 0.8))
            if pos:
                return True
            else:
                return False
        else:
            return driver(**kwargs).exists


@cost_time
def exists(*args, **kwargs) -> bool:
    """
    判断元素是否存在
    :param args: 可变参数，用于不同的定位方式
    :param kwargs: 关键字参数，用于uiautomator2/wda的定位
    :return: 元素是否存在
    """
    return _exists(*args, **kwargs)


@cost_time
def wait(*args, timeout: float = _CF.FIND_TIMEOUT, reverse: bool = False, raise_error: bool = True,
         use_in_text: bool = False, **kwargs):
    """
    等待元素出现，支持多种定位方式
    用法：
    2. wait("TEXT")  # 文字等待,orc 识别
    3. web等待
    4. uiautomator2/wda的等待（适合原生app，速度快，非H5应用建议使用）
    :param use_in_text:
    :param raise_error:
    :param reverse:
    :param args: 可变参数，用于不同的定位方式
    :param timeout: 等待超时时间，默认为CF.FIND_TIMEOUT
    :param kwargs: 关键字参数，用于uiautomator2/wda的定位
    :return: 元素是否出现
    """
    start_time = time.time()
    if use_in_text:
        if isinstance(args[0], str):
            while True:
                if reverse:
                    if args[0] not in get_page_text():
                        return True
                else:
                    if args[0] in get_page_text():
                        return True
                    if time.time() - start_time > timeout:
                        if raise_error:
                            raise TimeoutError(f"等待ocr识别到指定文字[{args[0]}]超时")
                        else:
                            return False
    while True:
        if reverse:
            if not _exists(*args, **kwargs):
                return True
        else:
            if _exists(*args, **kwargs):
                return True
        if time.time() - start_time > timeout:
            if raise_error:
                raise TimeoutError(f"等待元素超时：{args}, {kwargs}")
            else:
                return False


@cost_time
def swipe(p1, p2, duration=None, steps=None):
    """
    uiautomator2/wda的滑动操作
    :param p1: 起始位置，(x, y)坐标或比例
    :param p2: 结束位置，(x, y)坐标或比例
    :param duration: 滑动持续时间
    :param steps: 滑动步数，1步约5ms，如果设置则忽略duration
    """

    def calculate_position(p):
        return (int(p[0] * screen_size[0]), int(p[1] * screen_size[1])) if isinstance(p[0], float) else p

    pos1 = calculate_position(p1)
    pos2 = calculate_position(p2)
    driver.swipe(*pos1, *pos2, duration=duration, steps=steps)


def get_page_text() -> str:
    """
    OCR识别页面文字, 返回当前页面所有文字的拼接字符串
    可用于断言
    
    :return: 页面上的所有文字拼接成的字符串
    """
    return ocr.get_page_text(driver.screenshot)


@cost_time
def swipe_up(duration: float = 0.2, steps: Optional[int] = None) -> None:
    """
    向上滑动
    
    :param duration: 滑动持续时间
    :param steps: 滑动步数
    """
    swipe((0.5, 0.8), (0.5, 0.3), duration, steps)


@cost_time
def swipe_down(duration: float = 0.2, steps: Optional[int] = None) -> None:
    """
    向下滑动
    
    :param duration: 滑动持续时间
    :param steps: 滑动步数
    """
    swipe((0.5, 0.3), (0.5, 0.8), duration, steps)


@cost_time
def swipe_left(duration: float = 0.1, steps: Optional[int] = None) -> None:
    """
    向左滑动
    
    :param duration: 滑动持续时间
    :param steps: 滑动步数
    """
    swipe((0.8, 0.5), (0.2, 0.5), duration, steps)


@cost_time
def swipe_right(duration: float = 0.1, steps: Optional[int] = None) -> None:
    """
    向右滑动
    
    :param duration: 滑动持续时间
    :param steps: 滑动步数
    """
    swipe((0.2, 0.5), (0.8, 0.5), duration, steps)


def screenshot(filename: Optional[str] = None) -> PIL.Image.Image:
    """
    截图并可选保存到本地
    
    :param filename: 保存截图的文件名，如果为None则不保存
    :return: 截图的PIL.Image对象
    """
    img = driver.screenshot()
    img = PIL.Image.fromarray(img) if isinstance(img, np.ndarray) else img
    if filename:
        img.save(filename)
    return img


@cost_time
def popup_apps() -> None:
    """
    上划弹起应用列表
    注意：此方法在部分手机上可能无法使用
    """
    swipe((0.5, 0.999), (0.5, 0.6), 0.1)


@cost_time
def home() -> None:
    """返回桌面"""
    driver.press("home")


@cost_time
def pull_file(src_path: Union[List[str], str], filename: str) -> None:
    """
    从app本地路径下载文件到本地
    
    :param src_path: 路径列表或字符串，ios为Documents/xxx，android为/data/data/xxx/files/xxx
    :param filename: 本地文件名
    """
    log_out(f"从app本地路径{src_path}下载文件{filename}到本地")
    base = f"t3 fsync -B {_CF.APP_NAME} pull " if _CF.PLATFORM == "ios" else f"adb -s {_CF.DEVICE_SERIAL} pull "
    root_path = "Library" if _CF.PLATFORM == "ios" else f"/sdcard/Android/data/{_CF.APP_NAME}/files"
    root_path += "/" + ("/".join(src_path) if isinstance(src_path, list) else src_path)
    cmd = base + root_path + " " + filename

    # 执行命令
    try:
        subprocess.run(cmd, shell=True, check=True)
        log_out(f"文件{root_path}下载成功,路径：{filename}")
    except subprocess.CalledProcessError as e:
        log_out(f"文件{root_path}下载失败，原因：{e}", 2)
        raise


@cost_time
def upload_files(src_path: str) -> None:
    """
    上传文件或文件夹到设备
    
    :param src_path: 源文件或文件夹路径，可以是列表或字符串
    :raises Exception: 如果上传过程中出现错误
    """
    try:
        # elif isinstance(src_path, str):
        #     # 如果 src_path 是字符串，确保它是绝对路径
        #     src_path = os.path.abspath(src_path)
        #
        # log_out(f"开始上传文件或文件夹: {src_path}")

        if os.path.isdir(src_path):
            _upload_directory(src_path)
        else:
            _upload_file(src_path)

        log_out(
            f"文件或文件夹 {src_path} 上传成功!\n"
            f"{'安卓' if _CF.PLATFORM == 'android' else 'iOS'}路径：{'我的iPhone/' + _CF.APP_NAME if _CF.PLATFORM == 'ios' else '/sdcard'}/{os.path.basename(src_path)}"
        )
    except Exception as e:
        log_out(f"文件或文件夹 {src_path} 上传失败，原因：{e}", 2)
        raise


def _upload_directory(dir_path: str) -> None:
    """
    上传文件夹到设备
    
    :param dir_path: 文件夹路径
    """
    if _CF.PLATFORM == "ios":
        dir_name = os.path.basename(dir_path)
        subprocess.run(
            ["tidevice", '-u', _CF.DEVICE_SERIAL, 'fsync', "-B", _CF.APP_NAME, 'mkdir', f"Documents/{dir_name}"],
            check=True)
        for file in _get_file_list(dir_path):
            subprocess.run(["tidevice", '-u', _CF.DEVICE_SERIAL, 'fsync', "-B", _CF.APP_NAME, 'push', file,
                            f"Documents/{dir_name}/{os.path.basename(file)}"], check=True)
    else:
        subprocess.run(f"adb -s {_CF.DEVICE_SERIAL} push {dir_path} /sdcard/", shell=True, check=True)


def _upload_file(file_path: str) -> None:
    """
    上传单个文件到设备
    
    :param file_path: 文件路径
    """
    if _CF.PLATFORM == "ios":
        subprocess.run(["tidevice", '-u', _CF.DEVICE_SERIAL, 'fsync', "-B", _CF.APP_NAME, 'push', file_path,
                        f"Documents/{os.path.basename(file_path)}"], check=True)
    else:
        subprocess.run(f"adb -s {_CF.DEVICE_SERIAL} push {file_path} /sdcard/", shell=True, check=True)


@cost_time
def delete_file(file_path: Union[List[str], str]) -> None:
    """
    删除设备上的文件或文件夹
    
    :param file_path: 要删除的文件或文件夹路径，可以是列表或字符串
    :raises Exception: 如果删除过程中出现错误
    """

    def directory_exists(file_path1):
        """检查设备上的目录是否存在"""
        result = subprocess.run(
            ["tidevice", "-u", _CF.DEVICE_SERIAL, "fsync", "-B", _CF.APP_NAME, "ls", f"Documents/{file_path}"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0

    try:
        file_path = '/'.join(file_path) if isinstance(file_path, list) else file_path

        if not directory_exists(file_path):
            log_out(f"Directory {file_path} does not exist.")
            return

        if _CF.PLATFORM == "ios":
            subprocess.run(
                ["tidevice", "-u", _CF.DEVICE_SERIAL, "fsync", "-B", _CF.APP_NAME, "rmtree", f"Documents/{file_path}"],
                check=True
            )
        else:
            subprocess.run(f"adb -s {_CF.DEVICE_SERIAL} shell rm -r /sdcard/{file_path}", shell=True, check=True)

        log_out(f"设备上的文件或文件夹 {file_path} 删除成功")
    except subprocess.CalledProcessError as e:
        log_out(f"设备上的文件或文件夹 {file_path} 删除失败，原因：{e}", 2)
        raise


@cost_time
def start_app(app_name: Optional[str] = None, activity: Optional[str] = None) -> None:
    """
    启动应用程序
    
    :param app_name: 应用程序名称，如果为None则使用配置中的默认值
    :param activity: Android应用的活动名称，如果为None则使用配置中的默认值
    :raises ValueError: 如果是Android平台且activity为None
    """
    app_name = app_name or _CF.APP_NAME

    if _CF.PLATFORM == "ios":
        driver.app_start(app_name)
    else:
        activity = activity or _CF.ANDROID_ACTIVITY_NAME
        if activity is None:
            raise ValueError("Android平台必须提供activity参数")
        driver.adb_device.app_start(app_name, activity)


def restart_app(app_name: Optional[str] = None, activity: Optional[str] = None) -> None:
    """
    重启应用程序并更新CDP连接
    """
    driver.app_stop(app_name)
    start_app(app_name, activity)


if __name__ == '__main__':
    pass
