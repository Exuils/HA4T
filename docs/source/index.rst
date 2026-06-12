.. HA4T 文档主文件，由
   sphinx-quickstart 于 2023 年 10 月 12 日创建。
   您可以根据自己的需要完全自定义此文件，但至少应包含根 `toctree` 指令。

欢迎使用 HA4T 文档!
================================

HA4T (Hybrid App For Testing Tool) 是一个跨平台的 UI 自动化测试框架，支持 Android、iOS 和 HarmonyOS NEXT，同时擅长处理混合型 App 中的 WebView。它提供面向对象的简洁 API，让您能够快速编写并执行自动化测试脚本。

主要特性:

- 跨平台支持：Android、iOS、HarmonyOS NEXT 以及 WebView
- 多种定位方式：OCR 文字识别、图像/模板匹配、原生控件属性、XPath、WebView(CDP) 定位
- 面向对象 API：``connect()`` 返回 ``Device`` 实例，统一封装点击、滑动、输入、断言等操作
- 内置 OCR 文字识别（飞桨 PaddleOCR，懒加载）
- 多设备并行：每个 ``Device`` 持有独立配置，天然支持多线程并行测试
- 用例步骤复用：``include()`` 在同一进程内复用其他用例文件
- 丰富的辅助功能：截图、文件传输、日志记录等

快速开始
---------

安装 HA4T:

.. code-block:: bash

   pip install ha4t

================================

.. toctree::
   :maxdepth: 4
   :caption: 快速开始

   README_MORE.rst

================================

.. toctree::
   :maxdepth: 4
   :caption: 核心 API

   modules/ha4t
   modules/ha4t.config
   modules/ha4t.exceptions

================================

.. toctree::
   :maxdepth: 4
   :caption: 设备驱动

   modules/ha4t.drivers

================================

.. toctree::
   :maxdepth: 2
   :caption: Webview 操作

   modules/ha4t.cdp.cdp
   modules/ha4t.cdp.server
   modules/ha4t.cdp.by

================================

.. toctree::
   :maxdepth: 2
   :caption: 工具模块

   modules/ha4t.utils.log_utils

================================

.. toctree::
   :maxdepth: 2
   :caption: 所有模块

   modules/modules

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
