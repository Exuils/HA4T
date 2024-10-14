# -*- coding: utf-8 -*-
# @时间       : 2024/8/5 17:56
# @作者       : caishilong
# @文件名      : decorator_utils.py
# @Software   : PyCharm
import threading
import time
from functools import wraps


def useTread(func):
    """
     装饰器，使用线程运行, 防止阻塞
    :param func:
    :return:
    """

    def wrapper(*args, **kwargs):
        t = threading.Thread(target=func, args=args, kwargs=kwargs)
        t.start()

    return wrapper


def retry(retries=3, delay=1, exceptions=Exception):
    """失败重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt < retries:
                        time.sleep(delay)
                    else:
                        raise
        return wrapper
    return decorator

