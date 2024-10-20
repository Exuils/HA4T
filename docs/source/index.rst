.. HA4T 文档主文件，由
   sphinx-quickstart 于 2023 年 10 月 12 日创建。
   您可以根据自己的需要完全自定义此文件，但至少应包含根 `toctree` 指令。

欢迎使用 HA4T 文档!
================================

HA4T 是一个强大的 UI 自动化测试框架，支持 Android 和 iOS 平台。它提供了简单易用的 API，让您能够快速编写和执行自动化测试脚本。

主要特性:

- 支持 Android 和 iOS 平台
- 提供直观的元素定位和操作 API  
- 内置 OCR 文字识别功能
- 支持图像识别和模板匹配
- 集成 CDP 调试功能，支持 Web 应用测试
- 丰富的辅助功能，如截图、日志记录等

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
   :caption: 配置

   modules/ha4t.config

================================

.. toctree::
   :maxdepth: 2
   :caption: 原生元素操作

   modules/ha4t.api

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
