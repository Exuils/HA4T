# -*- coding: utf-8 -*-
"""
配置模块

- DeviceConfig: 每个 Device 实例持有一份，存放设备级运行时状态（平台、序列号、
  屏幕尺寸、应用包名等）。
- GlobalConfig: 进程级单例（``global_config``），存放与具体设备无关的全局配置
  （图像识别阈值、查找超时、日志、图像资源基准路径等）。
"""
import os


class DeviceConfig:
    """设备级运行时状态，每个 Device 实例持有一份独立拷贝。"""

    def __init__(self):
        self.platform: str = 'android'          # ios / android / harmony
        self.device_serial: str = ''
        self.screen_width: int = 0
        self.screen_height: int = 0
        self.app_name: str = ''
        self.android_package_name: str = ''
        self.android_activity_name: str = ''
        self.ios_bundle_id: str = ''
        self.device_name: str = ''

    @property
    def screen_size(self):
        return (self.screen_width, self.screen_height)

    @screen_size.setter
    def screen_size(self, value):
        self.screen_width, self.screen_height = value

    def resolve_app_name(self) -> str:
        """返回有效的 app 标识：优先 app_name，其次按平台回退。"""
        if self.app_name:
            return self.app_name
        if self.platform == 'android':
            return self.android_package_name
        return self.ios_bundle_id


class GlobalConfig:
    """进程级全局配置，与具体设备无关。"""

    def __init__(self):
        self.cv_threshold: float = 0.6      # 图像识别阈值
        self.find_timeout: int = 5          # 查找元素超时（秒）
        self.save_log: bool = False
        self.log_path: str = 'log'
        self.current_path: str = os.getcwd()   # 图像资源基准路径


# 进程级单例
global_config = GlobalConfig()

