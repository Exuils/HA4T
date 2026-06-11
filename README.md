# HA4T 🐍

[![PyPI version](https://badge.fury.io/py/ha4t.svg)](https://badge.fury.io/py/ha4t)
[![Documentation Status](https://img.shields.io/badge/docs-latest-brightgreen)](https://exuils.github.io/HA4T/)

HA4T (Hybrid App For Testing Tool)
是一个跨平台的UI自动化框架，适用于混合型app、web和原生app等。该框架基于airtest
aircv模块、飞浆OCR、WS、uiautomator2和facebook_wda进行开发。
(目前仅个人开发和使用，可能存在一些问题~)

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

### 面向对象风格（推荐）

```python
from ha4t import connect
from ha4t.aircv.cv import Template

# 连接设备，返回 Device 实例
dev = connect(platform="android", device_serial="emulator-5554",
              android_package_name="com.xxx.xxx",
              android_activity_name="com.xxx.xxx.MainActivity")

# 启动应用
dev.start_app()

# 等待 OCR 文字出现
dev.wait("添加新项目", timeout=30)

# OCR 文字识别定位点击
dev.click("添加新项目")

# 图像匹配点击
dev.click(image="./添加新项目.png")
dev.click(Template("./添加新项目.png"))

# u2/wda 原生属性定位
dev.click(text="添加新项目")

# 滑动
dev.swipe_up()
dev.swipe((0.2, 0.5), (0.8, 0.5), duration=0.5)

# WebView（CDP）
from ha4t.cdp.cdp import CDP
from ha4t.cdp.server import CdpServer
from ha4t.cdp.by import By

cdp_server = CdpServer()
cdp_server.start_server_for_android_app(dev.driver.adb_device)
cdp = CDP(cdp_server.ws_endpoint)
window = cdp.get_page(["homePage"])
window.click((By.TEXT, "新建项目"))
```


### 多设备并行

```python
from ha4t import connect
import threading

dev1 = connect(platform="android", device_serial="device1")
dev2 = connect(platform="android", device_serial="device2")

def run(dev):
    dev.click("登录")
    dev.wait("首页")

t1 = threading.Thread(target=run, args=(dev1,))
t2 = threading.Thread(target=run, args=(dev2,))
t1.start(); t2.start()
t1.join(); t2.join()
```

## 详细文档(未完善)

查看[详细文档](https://exuils.github.io/HA4T/)以获取更多信息，包括：

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
- [ui-viewer](https://github.com/codematrixer/ui-viewer) (MIT License) — 编辑器模块基于此项目二次开发

如果您觉得HA4T对您有帮助，请考虑给项目一个星标 ⭐️
