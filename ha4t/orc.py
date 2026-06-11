# -*- coding: utf-8 -*-
"""orc识别文字 获取文字位置 """
import os
import time

import PIL.Image
import numpy as np

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ["FLAGS_use_mkldnn"] = "0"

import paddle.inference as _pi
_original_create_predictor = _pi.create_predictor


def _patched_create_predictor(config):
    try:
        config.disable_mkldnn()
    except (AttributeError, RuntimeError):
        pass
    return _original_create_predictor(config)


_pi.create_predictor = _patched_create_predictor

from paddleocr import PaddleOCR

from ha4t.utils.log_utils import log_out


class OCR:
    def __init__(self, lang="ch", **kwargs):
        log_out("正在加载orc识别模块")
        self.ocr = PaddleOCR(lang=lang, **kwargs)
        log_out("orc识别模块加载完成")

    @staticmethod
    def get_pos(poly):
        """矩形四角坐标转中心点"""
        return (int((poly[0][0] + poly[1][0]) / 2), int((poly[0][1] + poly[3][1]) / 2))

    def _predict(self, img):
        if isinstance(img, PIL.Image.Image):
            img = np.array(img)
        return self.ocr.predict(img)

    def to_list(self, result) -> list[dict]:
        """将 predict() 返回结果转为统一格式 [{text, pos, confidence}, ...]"""
        res = result[0]
        items = []
        for poly, text, score in zip(res["dt_polys"], res["rec_texts"], res["rec_scores"]):
            items.append({
                "text": text.lower(),
                "pos": self.get_pos(poly),
                "confidence": score,
            })
        return items

    def get_page_text(self, record_func) -> str:
        """OCR识别页面全部文字并拼接返回"""
        img = record_func()
        result = self._predict(img)
        return "".join(result[0]["rec_texts"])

    def get_text_pos(self, text: str, record_func, index=0, timeout=10, scale=None, screen_size=None) -> tuple:
        """反复截图直到匹配到目标文字，返回坐标"""
        from ha4t.exceptions import OCRTimeoutError
        t1 = time.time()
        cost = index
        while True:
            raw = record_func()
            if screen_size and raw.size != screen_size:
                img = raw.resize(screen_size)
            else:
                img = raw
            items = self.to_list(self._predict(img))
            for item in items:
                if abs(len(item["text"]) - len(text)) <= 3:
                    if text.lower() in item["text"]:
                        if cost == 0:
                            return item["pos"]
                        else:
                            cost -= 1
            if time.time() - t1 > timeout:
                raise OCRTimeoutError(f"OCR 查找文字 [{text}] 超时")
