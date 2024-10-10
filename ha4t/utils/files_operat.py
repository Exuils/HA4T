# -*- coding: utf-8 -*-
# @时间       : 2024/8/22 16:24
# @作者       : caishilong
# @文件名      : files_operat.py
# @项目名      : xcs-mobile-ui-testing
# @Software   : PyCharm
import os
from typing import Union

from .paths import BASIC_DIR


def get_file_list(path: Union[list, str]) -> list:
    """
    获取指定目录下的所有文件列表
    :param path: 目录路径，可以是相对路径字符串或基于 BASIC_DIR 的路径列表
    :return: 文件列表
    """
    if isinstance(path, list):
        # 如果 path 是列表，将其与 BASIC_DIR 结合
        path = os.path.join(BASIC_DIR, *path)
    elif isinstance(path, str):
        # 如果 path 是字符串，确保它是绝对路径
        path = os.path.abspath(path) if not os.path.isabs(path) else path
    print(f"Getting file list from {path}")
    # 初始化文件列表
    file_list = []

    # 遍历目录
    try:
        for root, dirs, files in os.walk(path):
            for file in files:
                file_list.append(os.path.join(root, file))
    except Exception as e:
        print(f"Error occurred while walking the path {path}: {e}")

    return file_list
