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
from ha4t.utils.paths import BASIC_DIR
from ha4t.utils.files_operat import get_file_list
from ha4t.utils.log_utils import log_out, cost_time
from ha4t.config import Config as CF
from ha4t.orc import OCR
from ha4t.aircv.cv import match_loop

logreset.reset_logging()  # paddleocr 会污染 logging
orc = OCR()


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
            CF.DEVICE_SERIAL = device_id or wda.list_devices()[0].serial
            self.driver: wda.Client = wda.USBClient(udid=CF.DEVICE_SERIAL, port=port)
        else:
            self.driver: u2.Device = u2.connect(serial=device_id)
            self.adb = self.driver.adb_device
            CF.DEVICE_SERIAL = self.adb.serial
        # self.driver.app_start(CF.APP_NAME)
        self.device_info = json.dumps(self.driver.info, ensure_ascii=False, indent=4)
        log_out(f"设备信息：{self.device_info}")


device = Device(CF.PLATFORM, device_id=CF.DEVICE_SERIAL)
driver: Union[u2.Device, wda.Client] = device.driver
screen_size: Tuple[int, int] = driver.window_size()
CF.SCREEN_WIDTH = screen_size[0]
CF.SCREEN_HEIGHT = screen_size[1]


def perform_click(x, y, duration):
    """
    执行点击操作，根据平台选择不同的点击方式
    :param x: x坐标
    :param y: y坐标
    :param duration: 点击持续时间
    """
    if CF.PLATFORM == "ios":
        driver.tap_hold(x, y, duration=duration)
    else:
        driver.long_click(x, y, duration=duration)


@cost_time
def click(*args, duration: float = 0.1, **kwargs) -> None:
    """
    点击操作，支持多种定位方式
    用法：
    1. click((x,y))  # 坐标点击
    2. click("TEXT")  # 文字点击,orc 识别
    3. web定位
    4. uiautomator2/wda的点击（适合原生app，速度快，非H5应用建议使用）
    :param args: 可变参数，用于不同的定位方式
    :param duration: 点击持续时间，默认为0.1秒
    :param kwargs: 关键字参数，用于uiautomator2/wda的定位
    """
    if args:
        if isinstance(args[0], tuple):
            if isinstance(args[0][0], int):
                perform_click(*args[0], duration)
            elif isinstance(args[0][0], str):
                raise NotImplementedError("webview点击暂不支持")
        elif isinstance(args[0], str):
            pos = orc.get_text_pos(args[0], driver.screenshot, index=args[1] if len(args) > 1 else 0)
            perform_click(*pos, duration)
        elif isinstance(args[0], dict):
            path = os.path.join(CF.CURRENT_PATH, args[0]["image"])
            pos = match_loop(screenshot_func=driver.screenshot, template=path, timeout=kwargs.get("timeout", 10),
                             threshold=kwargs.get("threshold", 0.8))
            perform_click(*pos, duration)
    else:
        if kwargs.get("image"):
            path = os.path.join(CF.CURRENT_PATH, kwargs["image"])
            pos = match_loop(screenshot_func=driver.screenshot, template=path, timeout=kwargs.get("timeout", 10),
                             threshold=kwargs.get("threshold", 0.8))
            perform_click(*pos, duration)
        else:
            driver(**kwargs).tap_hold(duration=duration) if CF.PLATFORM == "ios" else driver(**kwargs).long_click(
                duration=duration)


@cost_time
def exists(*args, **kwargs) -> bool:
    """
    判断元素是否存在
    :param args: 可变参数，用于不同的定位方式
    :param duration: 点击持续时间，默认为0.1秒
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
            pos = orc.get_text_pos(args[0], driver.screenshot, index=args[1] if len(args) > 1 else 0)
            if pos:
                return True
            else:
                return False
        elif isinstance(args[0], dict):
            path = os.path.join(CF.CURRENT_PATH, args[0]["image"])
            pos = match_loop(screenshot_func=driver.screenshot, template=path, timeout=kwargs.get("timeout", 10),
                             threshold=kwargs.get("threshold", 0.8))
            if pos:
                return True
            else:
                return False
    else:
        if kwargs.get("image"):
            path = os.path.join(CF.CURRENT_PATH, kwargs["image"])
            pos = match_loop(screenshot_func=driver.screenshot, template=path, timeout=kwargs.get("timeout", 10),
                             threshold=kwargs.get("threshold", 0.8))
            if pos:
                return True
            else:
                return False
        else:
            return driver(**kwargs).exists


@cost_time
def wait(*args, timeout: float = CF.FIND_TIMEOUT, **kwargs):
    """
    等待元素出现，支持多种定位方式
    用法：
    2. wait("TEXT")  # 文字等待,orc 识别
    3. web等待
    4. uiautomator2/wda的等待（适合原生app，速度快，非H5应用建议使用）
    :param args: 可变参数，用于不同的定位方式
    :param timeout: 等待超时时间，默认为CF.FIND_TIMEOUT
    :param kwargs: 关键字参数，用于uiautomator2/wda的定位
    :return: 元素是否出现
    """
    start_time = time.time()
    while not exists(*args, **kwargs):
        if time.time() - start_time > timeout:
            raise TimeoutError(f"等待元素超时：{args}, {kwargs}")
        time.sleep(0.1)
    return True


@cost_time
def swipe(p1, p2, duration=None, steps=None):
    """
    uiautomator2/wda的滑动操作
    :param p1: 起始位置，(x, y)坐标或比例
    :param p2: 结束位置，(x, y)坐标或比例
    :param duration: 滑动持续时间
    :param steps: 滑动步数，1步约5ms，如果设置则忽略duration
    """

    def calculate_position(p, screen_size):
        """
        计算位置，如果是比例则转换为具体坐标
        :param p: 位置，可以是坐标或比例
        :param screen_size: 屏幕尺寸
        :return: 具体坐标
        """
        return (int(p[0] * screen_size[0]), int(p[1] * screen_size[1])) if isinstance(p[0], float) else p

    pos1 = calculate_position(p1, screen_size)
    pos2 = calculate_position(p2, screen_size)
    driver.swipe(*pos1, *pos2, duration=duration, steps=steps)


def get_page_text() -> str:
    """
    OCR识别页面文字, 返回当前页面所有文字的拼接字符串
    可用于断言
    
    :return: 页面上的所有文字拼接成的字符串
    """
    return orc.get_page_text(driver.screenshot)


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

    if isinstance(img, PIL.Image.Image):
        if filename:
            img.save(filename)
        return img
    elif isinstance(img, np.ndarray):
        img = PIL.Image.fromarray(img)
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
def wait_text(text: str, timeout: float = CF.FIND_TIMEOUT, reverse: bool = False, raise_error: bool = True) -> bool:
    """
    等待OCR识别到指定文字
    
    :param text: 要等待的文字
    :param timeout: 超时时间
    :param reverse: 如果为True，则等待文字消失
    :param raise_error: 如果为True，超时时抛出异常；否则返回False
    :return: 是否成功等待到文字（或文字消失）
    """
    t1 = time.time()
    while True:
        if reverse:
            if text not in get_page_text():
                return True
        else:
            if text in get_page_text():
                return True
            if time.time() - t1 > timeout:
                if raise_error:
                    raise TimeoutError(f"等待ocr识别到指定文字[{text}]超时")
                else:
                    return False


@cost_time
def pull_file(src_path: Union[List[str], str], filename: str) -> None:
    """
    从app本地路径下载文件到本地
    
    :param src_path: 路径列表或字符串，ios为Documents/xxx，android为/data/data/xxx/files/xxx
    :param filename: 本地文件名
    """
    log_out(f"从app本地路径{src_path}下载文件{filename}到本地")
    # t3 / adb 的 pull 命令不同
    base = f"t3 fsync -B {CF.APP_NAME} pull " \
        if CF.PLATFORM == "ios" \
        else "adb -s " + CF.DEVICE_SERIAL + " pull "
    # ios 和 android 的app本地路径不同
    root_path = "Library" if CF.PLATFORM == "ios" else "/sdcard/Android/data/com.makeblock.xcs/files"
    # 拼接app内部路径
    if isinstance(src_path, list):
        for p in src_path:
            root_path += "/" + p
    else:
        root_path += "/" + src_path
    # 拼接命令
    cmd = base + root_path + " " + filename
    "t3 fsync -B com.Makeblock.XCSiPhone pull Library/task/originalData/manifest.json D://manifest.json"
    '/sdcard/Android/data/com.makeblock.xcs/files/originalData/manifest.json'

    # 执行命令
    try:
        subprocess.run(cmd, shell=True)
        log_out(f"文件{root_path}下载成功,路径：{filename}")
    except Exception as e:
        log_out(f"文件{root_path}下载失败，原因：{e}")


@cost_time
def upload_files(src_path: Union[List[str], str]) -> None:
    """
    上传文件或文件夹到设备
    
    :param src_path: 源文件或文件夹路径，可以是列表或字符串
    :raises Exception: 如果上传过程中出现错误
    """
    try:
        if isinstance(src_path, list):
            # 如果 src_path 是列表，将其与 BASIC_DIR 结合
            src_path = os.path.join(BASIC_DIR, *src_path)
        elif isinstance(src_path, str):
            # 如果 src_path 是字符串，确保它是绝对路径
            src_path = os.path.abspath(src_path)

        log_out(f"开始上传文件或文件夹: {src_path}")

        if os.path.isdir(src_path):
            _upload_directory(src_path)
        else:
            _upload_file(src_path)

        log_out(
            f"文件或文件夹 {src_path} 上传成功!\n"
            f"安卓路径：/sdcard/{os.path.basename(src_path)}\n"
            f"iOS路径：我的iPhone/{CF.APP_NAME}/{os.path.basename(src_path)}"
        )
    except Exception as e:
        log_out(f"文件或文件夹 {src_path} 上传失败，原因：{e}", 2)
        raise


def _upload_directory(dir_path: str) -> None:
    """
    上传文件夹到设备
    
    :param dir_path: 文件夹路径
    """
    if CF.PLATFORM == "ios":
        dir_name = os.path.basename(dir_path)
        subprocess.run(
            ["tidevice", '-u', CF.DEVICE_SERIAL, 'fsync', "-B", CF.APP_NAME, 'mkdir', f"Documents/{dir_name}"],
            check=True)
        for file in get_file_list(dir_path):
            subprocess.run(["tidevice", '-u', CF.DEVICE_SERIAL, 'fsync', "-B", CF.APP_NAME, 'push', file,
                            f"Documents/{dir_name}/{os.path.basename(file)}"], check=True)
    else:
        subprocess.run(f"adb -s {CF.DEVICE_SERIAL} push {dir_path} /sdcard/", shell=True, check=True)


def _upload_file(file_path: str) -> None:
    """
    上传单个文件到设备
    
    :param file_path: 文件路径
    """
    if CF.PLATFORM == "ios":
        subprocess.run(["tidevice", '-u', CF.DEVICE_SERIAL, 'fsync', "-B", CF.APP_NAME, 'push', file_path,
                        f"Documents/{os.path.basename(file_path)}"], check=True)
    else:
        subprocess.run(f"adb -s {CF.DEVICE_SERIAL} push {file_path} /sdcard/", shell=True, check=True)


def directory_exists(file_path):
    result = subprocess.run(
        ["tidevice", "-u", CF.DEVICE_SERIAL, "fsync", "-B", CF.APP_NAME, "ls", f"Documents/{file_path}"],
        capture_output=True,
        text=True
    )
    return result.returncode == 0


@cost_time
def delete_file(file_path: Union[List[str], str]) -> None:
    """
    删除设备上的文件或文件夹
    
    :param file_path: 要删除的文件或文件夹路径，可以是列表或字符串
    :raises Exception: 如果删除过程中出现错误
    """
    try:
        if isinstance(file_path, list):
            file_path = '/'.join(file_path)

        if not directory_exists(file_path):
            log_out(f"Directory {file_path} does not exist.")
            return

        if CF.PLATFORM == "ios":
            subprocess.run(
                ["tidevice", "-u", CF.DEVICE_SERIAL, "fsync", "-B", CF.APP_NAME, "rmtree", f"Documents/{file_path}"],
                check=True
            )
        else:
            subprocess.run(f"adb -s {CF.DEVICE_SERIAL} shell rm -r /sdcard/{file_path}", shell=True, check=True)

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
    app_name = app_name or CF.APP_NAME

    if CF.PLATFORM == "ios":
        driver.app_start(app_name)
    else:
        activity = activity or CF.ANDROID_ACTIVITY_NAME
        if activity is None:
            raise ValueError("Android平台必须提供activity参数")
        driver.adb_device.app_start(app_name, activity)


def restart_app() -> None:
    """
    重启应用程序并更新CDP连接
    """
    driver.app_stop(CF.APP_NAME)
    start_app()


if __name__ == '__main__':
    # pull_file(["task", "originalData", "manifest.json"], "manifest.json")
    # window.click((By.TEXT,"New project"))
    # popup_apps()
    click(image=r"D:\project\cv\img_1.png")
    # click("配置Wi-Fi")
    # click((By.TEXT, "新建项目"))
    # click((By.TEXT, "加工设置"))
    # click((By.TEXT, "材料"))
    # click((By.TEXT, "更多官方耗材"))
    # wait_text("Store", 30)
    # page2 = page_cdp.get_page("xTool Material Settings Library")
    # page2.click((By.CSS_SELECTOR, "div.search-filter"))
    # click(resourceId="com.makeblock.xcs:ID/closeIv")
    # click((By.CSS_SELECTOR, ".arrow_left"))
    # while True:
    #     click((By.TEXT, "添加新项目"))
    #     click((By.TEXT, "新建项目"))
    #     click((By.CSS_SELECTOR, ".nav-bar-back"))
    #     time.sleep(1)
    #     click((By.CSS_SELECTOR, 'div.van-popup[style="z-index: 4000;"]  >* .cancel-btn'))
