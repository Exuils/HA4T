# -*- coding: utf-8 -*-
# @时间       : 2024/8/21 10:02
# @作者       : caishilong
# @文件名      : orc.py
# @项目名      : xcs-mobile-ui-testing
# @Software   : PyCharm
"""orc识别文字 获取文字位置 """
import time

import PIL.Image
import numpy as np
from paddleocr import PaddleOCR

from ha4t.config import Config as CF
from ha4t.utils.log_utils import log_out


class OCR:
    def __init__(self, use_angle_cls=True, lang="ch",show_log=False,**kwargs):
        """
        :param use_angle_cls: 是否使用方向分类器
        :param lang: 识别语言
        :param kwargs: 其他参数
        """
        log_out("正在加载orc识别模块")
        self.ocr = PaddleOCR(use_angle_cls=use_angle_cls, lang=lang,show_log=show_log, **kwargs)
        log_out("orc识别模块加载完成")

    @staticmethod
    def get_pos(data):
        """矩形转换为坐标"""
        img = (int((data[0][0] + data[1][0]) / 2), int((data[0][1] + data[3][1]) / 2))
        return img

    def to_list(self, data, scale=None):
        obj = []
        for i in data[0]:
            obj.append(
                {
                    "text": i[1][0].lower(),
                    "pos": self.get_pos(i[0]),
                    "confidence": i[1][1]
                }
            )
        return obj

    def get_page_text(self, record_func) -> str:
        """
        将ocr识别结果转换为文本
        :param record_func: 截图函数
        """
        img = record_func()
        if isinstance(img, PIL.Image.Image):
            img = np.array(img)
        result = self.ocr.ocr(img, cls=True)
        res_str = ""
        for i in result[0]:
            res_str += i[1][0]
        return res_str

    def get_text_pos(self, text: str, record_func, index=0, timeout=10, scale=None) -> tuple:
        """
        反复获取截图，直到获取目标文字位置
        :param text: 目标文字
        :param record_func: 截图函数
        :param index: 匹配第几个目标文字
        :param timeout: 超时时间
        """
        t1 = time.time()
        cost = index
        while True:
            img = record_func().resize((CF.SCREEN_WIDTH, CF.SCREEN_HEIGHT))
            if isinstance(img, PIL.Image.Image):
                img = np.array(img)
            result = self.to_list(self.ocr.ocr(img, cls=True), scale=scale)
            for i in range(len(result)):
                # 返回匹配的位置，可根据index参数指定第几个匹配的位置
                # 可接受多出匹配长度为3
                if len(result[i]["text"]) - len(text) <= 3:
                    if text.lower() in result[i]["text"]:
                        if cost == 0:
                            return result[i]["pos"]
                        else:
                            cost -= 1
            if time.time() - t1 > timeout:
                raise "ocr查找文字超时"


if __name__ == '__main__':
    print(3000 / 1)


