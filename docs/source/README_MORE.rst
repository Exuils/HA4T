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

   from ha4t.api import *
   
   # 连接设备  
   device = Device("android")
   
   # 启动应用
   start_app("com.example.app")
   
   # 点击元素
   click("登录")
   
   # 输入文本
   input("用户名", "testuser")
   
   # 等待元素出现
   wait("登录成功")
   
   # 断言文本存在
   assert "欢迎回来" in get_page_text()