HA4T
=======

**HA4T是一个跨平台的UI自动化框架，支持Android、iOS和Web应用，能够有效地处理webview。该框架旨在为开发者提供灵活、强大的自动化测试解决方案，帮助用户快速实现自动化测试的目标。**

快速开始
---------------
*   **跨平台支持：**适用于iOS、Android和Web应用**
*   **多种定位方式：**支持图像识别、OCR文字识别、原生控件定位等**
*   **灵活的操作API：**提供点击、滑动、输入等常用操作**

安装
------------
可以通过pip安装

.. code:: shell

    pip install -U ha4t

You can also install it from Git repository.

.. code:: shell

    pip install -U git+https://github.com/1103837067/ha4t.git

简单示例:
------------
.. code-block:: python

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