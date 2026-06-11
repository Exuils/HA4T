# -*- coding: utf-8 -*-
"""
HA4T 异常体系
所有自定义异常的统一定义。
"""


class HA4TError(Exception):
    """HA4T 基础异常"""


class DeviceConnectionError(HA4TError, ConnectionError):
    """设备连接失败"""


class PlatformNotSupportedError(HA4TError, NotImplementedError):
    """平台不支持当前操作"""

    def __init__(self, op: str, platform: str):
        super().__init__(f"操作 [{op}] 在平台 [{platform}] 上不被支持")
        self.op = op
        self.platform = platform


class ElementNotFoundError(HA4TError):
    """元素未找到"""


class ElementWaitTimeoutError(HA4TError, TimeoutError):
    """等待元素超时"""


class ImageMatchError(HA4TError):
    """图像匹配失败"""


class OCRTimeoutError(HA4TError, TimeoutError):
    """OCR 文字识别超时"""


class AssertionFailedError(HA4TError, AssertionError):
    """业务断言失败"""


class FileTransferError(HA4TError):
    """设备文件传输失败"""
