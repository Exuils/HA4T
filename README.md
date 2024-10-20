# HA4T 🐍

[![PyPI version](https://badge.fury.io/py/ha4t.svg)](https://badge.fury.io/py/ha4t)
[![Documentation Status](https://img.shields.io/badge/docs-latest-brightgreen)](https://exuils.github.io/HA4T/)

HA4T (Hybrid App For Testing Tool)
是一个跨平台的UI自动化框架，适用于混合型app、web和原生app等。该框架基于airtest、飞浆OCR、WS、uiautomator2和facebook_wda进行开发。

## 特性

- 跨平台支持：适用于iOS、Android和Web应用
- 多种定位方式：支持图像识别、OCR文字识别、webview定位、原生控件定位等
- 灵活的操作API：提供点击、滑动、输入等常用操作

## 安装

使用pip安装HA4T：

```bash
pip install ha4t
```

## 快速开始

以下是一个简单的示例，展示如何使用HA4T进行基本操作：

```python

# 原生定位
from ha4t import connect
from ha4t.api import *

connect(platform="android")

# 启动应用
start_app(activity="com.xxx.xxx.MainActivity",app_name="com.xxx.xxx")

# 等待
wait(text="添加新项目",timeout=30)

# orc 文字识别定位 中/英
click("添加新项目")
# 图像匹配定位
click(image = "./添加新项目.png")
from ha4t.aircv.cv import Template
click(Template("./添加新项目.png"))
# u2 元素定位
click(text="添加新项目")


# webview 定位
from ha4t.cdp.cdp import CDP
from ha4t.cdp.server import CdpServer
from ha4t.cdp.by import By

cdp_server = CdpServer()
cdp_server.start_server_for_android_app(device.driver.adb_device)
cdp = CDP(cdp_server.ws_endpoint)


window = cdp.get_page(["homePage"])
time.sleep(3)
window.click((By.TEXT, "新建项目"))
```

## 详细文档(未完善)

查看我们的[详细文档](https://exuils.github.io/HA4T/)以获取更多信息，包括：

- 完整的API参考
- 高级用法指南
- 最佳实践和技巧


## 问题和支持

如果您遇到任何问题或需要支持，请[提交一个issue](https://github.com/Exuils/HA4T/issues)。

## 许可证

本项目采用MIT许可证。详情请见[LICENSE](LICENSE)文件。

## 致谢

HA4T 的开发得益于以下开源项目：

- [airtest](https://github.com/NetEase/airtest)
- [uiautomator2](https://github.com/openatx/uiautomator2)
- [facebook-wda](https://github.com/openatx/facebook-wda)
- [paddleocr](https://github.com/PaddlePaddle/PaddleOCR)
- [ios-webkit-debug-proxy](https://github.com/google/ios-webkit-debug-proxy)

感谢这些项目的贡献者们！
如果您觉得HA4T对您有帮助，请考虑给我们一个星标 ⭐️
