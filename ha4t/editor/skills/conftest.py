# -*- coding: utf-8 -*-
import os
import sys
from ha4t.config import global_config

# 工作区根入 sys.path —— 用例在 testcases/ 下仍可 `from pom import ...`
_WS_ROOT = os.path.dirname(os.path.abspath(__file__))
if _WS_ROOT not in sys.path:
    sys.path.insert(0, _WS_ROOT)


def pytest_configure(config):
    global_config.current_path = os.path.join(_WS_ROOT, "images")
