HA4T
=======

**HA4T 是一个跨平台的 UI 自动化框架，支持 Android、iOS 和 HarmonyOS NEXT，并能高效处理 WebView。该框架提供面向对象的简洁 API，帮助开发者快速实现跨平台自动化测试目标。**

特性
---------------
*   **跨平台支持：** 适用于 Android、iOS、HarmonyOS NEXT 以及 WebView
*   **多种定位方式：** OCR 文字识别、图像/模板匹配、原生控件属性、XPath、WebView(CDP) 定位
*   **面向对象 API：** ``connect()`` 返回 ``Device`` 实例，统一封装点击、滑动、输入、断言等操作
*   **多设备并行：** 每个 ``Device`` 持有独立配置，天然支持多线程并行测试

安装
------------
可以通过 pip 安装

.. code:: shell

    pip install -U ha4t

也可以从 Git 仓库安装：

.. code:: shell

    pip install -U git+https://github.com/Exuils/HA4T.git

快速开始
------------
``connect()`` 连接设备并返回一个 ``Device`` 实例，所有 UI 操作都通过该实例调用。

.. code-block:: python

    from ha4t import connect
    from ha4t.aircv.cv import Template

    # 连接设备，返回 Device 实例
    dev = connect(platform="android", device_serial="emulator-5554",
                  android_package_name="com.xxx.xxx",
                  android_activity_name="com.xxx.xxx.MainActivity")

    # 启动应用（app_name / activity 为空时取 connect 时的默认值）
    dev.start_app()

    # 等待 OCR 文字出现
    dev.wait("添加新项目", timeout=30)

    # OCR 文字识别定位点击
    dev.click("添加新项目")

    # 图像匹配定位点击
    dev.click(image="./添加新项目.png")
    dev.click(Template("./添加新项目.png"))

    # u2/wda 原生属性定位
    dev.click(text="添加新项目")

    # 坐标点击（支持绝对像素或 0-1 比例）
    dev.click((0.5, 0.5))

    # 滑动
    dev.swipe_up()
    dev.swipe((0.2, 0.5), (0.8, 0.5), duration=0.5)

    # 断言
    dev.assert_element(text="登录成功", operator="exists_true", extract="exists")

平台
------------
``connect(platform=...)`` 支持三个平台标识：

*   ``android`` —— 基于 uiautomator2
*   ``ios`` —— 基于 facebook-wda
*   ``harmony`` —— HarmonyOS NEXT

WebView 操作
------------
对于混合型 App，可通过 CDP 协议操作 WebView：

.. code-block:: python

    from ha4t.cdp.cdp import CDP
    from ha4t.cdp.server import CdpServer
    from ha4t.cdp.by import By

    cdp_server = CdpServer()
    cdp_server.start_server_for_android_app(dev.driver.adb_device)
    cdp = CDP(cdp_server.ws_endpoint)

    window = cdp.get_page(["homePage"])
    window.click((By.TEXT, "新建项目"))

多设备并行
------------
每个 ``Device`` 实例持有独立配置，可在多线程中并行运行：

.. code-block:: python

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

用例步骤复用
------------
``include()`` 在当前进程内执行另一个用例 ``.py`` 文件，复用其步骤，
并自动剥离重复的 ``import`` / ``connect()`` 等样板代码，从而复用调用者
已建立的 ``dev`` 连接：

.. code-block:: python

    from ha4t import connect, include

    dev = connect(platform="android")
    include("login.py")     # 复用登录步骤
    dev.click("我的")
