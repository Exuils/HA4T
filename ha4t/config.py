# -*- coding: utf-8 -*-
# @时间       : 2024/10/10 16:54
# @作者       : caishilong
# @文件名      : config.py
# @项目名      : HA4T
# @Software   : PyCharm
"""
配置文件,用于存放全局变量
"""


class Config:
    """全局变量"""
    """手动配置项"""
    # 测试
    AUTHER = 'caishilong'
    # 执行平台（ios/android）
    PLATFORM = 'android'
    # 指定设备序列号，默认不选，多设备时可指定
    DEVICE_SERIAL = None
    # 缩放比例# 缩放比例# 缩放比例# 缩放比例
    SCREEN_WIDTH = 1
    SCREEN_HEIGHT = 1
    # Android包名
    ANDROID_PACKAGE_NAME = ''
    # Android活动名
    ANDROID_ACTIVITY_NAME = ''
    # iOS包名
    IOS_BUNDLE_ID = ''
    # 图像识别阈值
    CV_THRESHOLD = 0.6
    # 查找图片超时时间
    FIND_TIMEOUT = 5

    SAVE_LOG = False
    LOG_PATH = 'log'

    """动态配置, 由代码自动生成"""
    # 设备名称
    DEVICE_NAME = ''
    # 应用名(动态
    APP_NAME = ANDROID_PACKAGE_NAME if PLATFORM.lower() == 'android' else IOS_BUNDLE_ID
    # 动态路径引用，用于图像识别切换路径(动态
    CURRENT_PATH = ""
