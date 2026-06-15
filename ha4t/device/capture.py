# -*- coding: utf-8 -*-
"""截图 mixin。"""
from typing import Optional

import PIL.Image
import numpy as np


class CaptureMixin:
    def screenshot(self, filename: Optional[str] = None) -> PIL.Image.Image:
        """截图并可选保存到本地。"""
        img = self.driver.screenshot()
        img = PIL.Image.fromarray(img) if isinstance(img, np.ndarray) else img
        if filename:
            img.save(filename)
        return img
