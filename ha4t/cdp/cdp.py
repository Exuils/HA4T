# -*- coding: utf-8 -*-
# @时间       : 2024/8/21 10:02
# @作者       : caishilong
# @文件名      : cdp.py
# @Software   : PyCharm
"""
CDPClient 类用于与 Chrome DevTools Protocol (CDP) 进行通信。它通过 WebSocket 连接到浏览器的调试端口，并发送 CDP 命令以控制浏览器。

该模块提供了与浏览器进行交互的功能，包括发送命令、接收响应、获取页面元素等。

**使用示例：**

1. 创建 WS_CDP 实例并连接到浏览器：
   ```python
   client = WS_CDP("ws://localhost:9222/devtools/browser/<id>")
   await client.connect()
   ```

2. 发送命令并获取响应：
   ```python
   response = await client.send_command("Page.navigate", {"url": "https://www.example.com"})
   ```

3. 使用 Page 类与浏览器窗口交互：
   ```python
   page = Page(client.ws_endpoint)
   title = page.get_title()
   ```

4. 获取元素并进行操作：
   ```python
   element = page.get_element(("css selector", "#element_id"))
   Element.click()
   ```

5. 截图：
   ```python
   img = page.screenshot("screenshot.png")
   ```

"""
import asyncio
import base64
import io
import json
import queue
import threading
import time
from typing import Any

import PIL.Image
import requests
import websockets

from ha4t.cdp.jsCode import Jscript
from ha4t.config import Config as CF
from ha4t.utils.log_utils import log_out, cost_time

# js 获取及拼接工具类
JS = Jscript()


class _WS_CDP:
    def __init__(self, url):
        self.ws_endpoint = url
        self.ws = None

    async def connect(self):
        """
        建立与浏览器的 WebSocket 连接。
        """
        self.ws = await websockets.connect(self.ws_endpoint)
        log_out(f"ws_endpoint: {self.ws_endpoint} connected!")

    async def send_command(self, method, params=None):
        """
        发送 CDP 命令到浏览器，并等待响应。

        :param method: CDP 方法名
        :param params: 方法参数，默认为 None
        :return: 响应结果
        :raises ValueError: 如果连接未打开
        """
        if not self.ws or not self.ws.open:
            raise ValueError("Connection is not open.")

        # 构建命令
        command_id = self._next_command_id()
        command = {
            "id": command_id,
            "method": method,
            "params": params or {}
        }

        # 发送命令
        await self.ws.send(json.dumps(command))
        return await self._wait_for_response(command_id)

    async def _wait_for_response(self, command_id, timeout=5):
        """
        等待具有指定 ID 的响应。

        :param command_id: 命令 ID
        :param timeout: 超时时间，默认为 5 秒
        :return: 响应结果
        :raises ValueError: 如果超时
        """
        t1 = time.time()
        while True:
            response = await self.ws.recv()
            response = json.loads(response)
            if response.get("id") == command_id:
                return response
            if time.time() - t1 > timeout:
                raise ValueError(f"Command {command_id} timed out.")

    @staticmethod
    def _next_command_id():
        """
        生成下一个命令 ID。

        :return: 下一个命令 ID
        """
        # 这里简单返回一个固定值，实际使用时可能需要更复杂的逻辑来确保唯一性
        return 1

    async def close(self):
        """
        关闭 WebSocket 连接。
        """
        if self.ws:
            await self.ws.close()


def _worker(url, task_queue, result_queue, timeout=10):
    """
    工作线程，用于处理任务队列中的命令。

    :param url: WebSocket 地址
    :param task_queue: 任务队列
    :param result_queue: 结果队列
    :param timeout: 超时时间，默认为 10 秒
    """
    async def main():
        client = _WS_CDP(url)
        try:
            await client.connect()
        except Exception as e:
            result_queue.put(e)
        while True:
            try:
                task = task_queue.get(block=True)
                if task is None:
                    break
                method, params = task
                result = await asyncio.wait_for(client.send_command(method, params), timeout=timeout)
                result_queue.put(result)
            except Exception as e:
                result_queue.put(e)
                break
        await client.close()

    asyncio.run(main())

class Page:
    def __init__(self, ws):
        """
        窗口类，用于与浏览器窗口进行交互。

        :param ws: pages 的 CDP WebSocket 地址。可通过 --remote-debugging-port=9222 启动浏览器时获取。
        :Example:
            >>> page = Page("ws://localhost:9222/devtools/page/<id>")
        """
        self.ws = ws
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.thread = threading.Thread(target=_worker, args=(self.ws, self.task_queue, self.result_queue))
        self.thread.daemon = True
        self.thread.start()

    def restart(self):
        """
        重新启动页面。
        """
        self.close()
        self.__init__(self.ws)

    def send(self, method, params=None, timeout=10):
        """
        发送命令到浏览器并获取结果。

        :param method: CDP 方法名
        :param params: 方法参数，默认为 None
        :param timeout: 超时时间，默认为 10 秒
        :return: 响应结果
        :raises ValueError: 如果超时
        :Example:
            >>> result = Page().send("Page.navigate", {"url": "https://www.example.com"})
        """
        self.task_queue.put(self.command(method, params))
        t1 = time.time()
        while True:
            try:
                result = self.result_queue.get(block=True, timeout=1)
                if isinstance(result, Exception):
                    raise result
                return result
            except queue.Empty:
                if time.time() - t1 > timeout:
                    raise ValueError(f"Command {method} timed out.")
                pass

    def execute_script(self, script) -> Any:
        """
        执行 JavaScript 脚本并返回结果。

        :param script: 要执行的 JavaScript 脚本
        :return: 执行结果
        :Example:
            >>> result = Page().execute_script("return document.title;")
        """
        rs = self.send("Runtime.evaluate", {"expression": script, "returnByValue": True})
        try:
            rs = rs["result"]["result"]["value"]
        except:
            pass
        return rs

    def get_element(self, locator: tuple, timeout=CF.FIND_TIMEOUT):
        """
        获取页面元素。

        :param locator: 元素定位器，格式为元组，例如 ("css selector", "#element_id")
        :param timeout: 超时时间，默认为配置中的 FIND_TIMEOUT
        :return: Element 实例
        :raises ValueError: 如果元素定位失败
        :Example:
            >>> element = Page().get_element(("css selector", "#element_id"))
        """
        t1 = time.time()
        while True:
            try:
                element_id = f"TEMP_{str(int(time.time()))}"
                exists = self.execute_script(
                    JS.element_exists(locator=locator, var_name=element_id))
                if not exists:
                    raise ValueError(f"元素定位失败：{locator}")
                break
            except Exception as e:
                if time.time() - t1 > timeout:
                    raise e
        return Element(self, element_id)

    def get_title(self):
        """
        获取当前页面标题。

        :return: 页面标题
        :Example:
            >>> title = Page().get_title()
        """
        return self.execute_script("document.title")

    def exist(self, locator: tuple):
        """
        判断元素是否存在。

        :param locator: 元素定位器
        :return: 如果元素存在返回 True，否则返回 False
        :Example:
            >>> exists = Page().exist(("css selector", "#element_id"))
        """
        script = JS.element_exists(locator=locator)
        return self.execute_script(script)

    def wait(self, locator: tuple, timeout=CF.FIND_TIMEOUT):
        """
        等待元素出现。

        :param locator: 元素定位器
        :param timeout: 超时时间，默认为配置中的 FIND_TIMEOUT
        :raises ValueError: 如果超时
        :Example:
            >>> Page().wait(("css selector", "#element_id"))
        """
        t1 = time.time()
        while True:
            try:
                if self.exist(locator):
                    break
                if time.time() - t1 > timeout:
                    raise ValueError(f"元素定位超时：{locator}")
                time.sleep(0.1)
            except Exception as e:
                raise e

    def screenshot(self, path=None) -> PIL.Image.Image:
        """
        截图并返回图像对象。

        :param path: 可选，保存截图的路径
        :return: PIL.Image.Image 对象
        :Example:
            >>> img = Page().screenshot("screenshot.png")
        """
        data = self.send("Page.captureScreenshot")  # png
        data = base64.b64decode(data["result"]["data"])
        img = PIL.Image.open(io.BytesIO(data))
        if path:
            img.save(path)
        return img

    @cost_time
    def click(self, locator: tuple, timeout=CF.FIND_TIMEOUT):
        """
        点击元素。

        :param locator: 元素定位器
        :param timeout: 超时时间，默认为配置中的 FIND_TIMEOUT
        :Example:
            >>> Page().click(("css selector", "#element_id"))
        """
        self.wait(locator, timeout)
        script = JS.add_click(element_var_name=JS.TEMP_VAR_NAME)
        self.execute_script(script)

    @staticmethod
    def command(method, params=None):
        """
        构建命令元组。

        :param method: CDP 方法名
        :param params: 方法参数，默认为 None
        :return: (method, params) 元组
        :Example:
            >>> cmd = Page().command("Page.navigate", {"url": "https://www.example.com"})
        """
        return method, params

    def close(self):
        """
        关闭页面并等待工作线程结束。
        :Example:
            >>> Page().close()
        """
        self.task_queue.put(None)
        self.thread.join()

class CDP:
    def __init__(self, url="http://localhost:9222"):
        """
        CDP 类，用于与浏览器进行交互。

        :param url: 浏览器调试地址，默认为 http://localhost:9222
        :Example:
            >>> cdp = CDP("http://localhost:9222")
        """
        self.ws_url = url

    def get_page(self, ws_title: str | list[str] = None, timeout=10) -> Page:
        """
        获取页面实例。

        :param ws_title: 页面标题，可以是字符串或字符串列表
        :param timeout: 超时时间，默认为 10 秒
        :return: Page 实例
        :raises ValueError: 如果获取页面超时
        :Example:
            >>> page = CDP().get_page("页面标题")
        """
        t1 = time.time()
        while True:
            try:
                ws_list = self.get_page_list()
                if ws_title:
                    for ws in ws_list:
                        if isinstance(ws_title, list):
                            for ws_title_item in ws_title:
                                if ws["title"] == ws_title_item:
                                    return Page(ws["webSocketDebuggerUrl"])
                        elif isinstance(ws_title, str):
                            if ws["title"] == ws_title:
                                return Page(ws["webSocketDebuggerUrl"])
                else:
                    return Page(ws_list[0]["webSocketDebuggerUrl"])
            # 请求错误
            except requests.exceptions.RequestException as e:
                raise e
            except Exception:
                pass
            if time.time() - t1 > timeout:
                raise ValueError(f"获取页面超时")

    def get_page_list(self) -> list:
        """
        获取当前打开的页面列表。

        :return: 页面列表
        :Example:
            >>> pages = CDP.get_page_list()
        """
        return requests.get(f"{self.ws_url}/json").json()


class Element:
    def __init__(self, cdp: Page, element_id):
        """
        元素类，用于与页面元素进行交互。

        :param cdp: Page 实例
        :param element_id: 元素 ID
        :Example:
            >>> element = Element(Page(), "element_id")
        """
        self.cdp = cdp
        self.id = element_id

    @cost_time
    def click(self):
        """
        点击元素。
        :Example:
            >>> Element.click()
        """
        self.cdp.execute_script(JS.add_click(self.id))

    def exists(self) -> bool:
        """
        判断元素是否存在。

        :return: 如果元素存在返回 True，否则返回 False
        :Example:
            >>> is_exist = Element.exists()
        """
        return self.cdp.execute_script(f"{self.id} != null")

    def is_displayed(self) -> bool:
        """
        判断元素是否可见。

        :return: 如果元素可见返回 True，否则返回 False
        :Example:
            >>> visible = Element.is_displayed()
        """
        return self.cdp.execute_script(f"{self.id}.style.display != 'none'")

    def is_enabled(self) -> bool:
        """
        判断元素是否可用。

        :return: 如果元素可用返回 True，否则返回 False
        :Example:
            >>> enabled = Element.is_enabled()
        """
        return self.cdp.execute_script(f"{self.id}.disabled == false")

    def wait_util_enabled(self, timeout=10):
        """
        等待元素可用。

        :param timeout: 超时时间，默认为 10 秒
        :raises ValueError: 如果超时
        :Example:
            >>> Element.wait_util_enabled()
        """
        t1 = time.time()
        while True:
            if self.is_enabled():
                break
            if time.time() - t1 > timeout:
                raise ValueError(f"元素未启用：{self.id}")
            time.sleep(0.1)

    def is_selected(self) -> bool:
        """
        判断元素是否被选中。

        :return: 如果元素被选中返回 True，否则返回 False
        :Example:
            >>> selected = Element.is_selected()
        """
        return self.cdp.execute_script(f"{self.id}.selected == true")

    def get_text(self) -> str:
        """
        获取元素文本。

        :return: 元素文本
        :Example:
            >>> text = Element.get_text()
        """
        return self.cdp.execute_script(f"{self.id}.innerText")

    def set_text(self, text: str):
        """
        设置元素文本。

        :param text: 要设置的文本
        :Example:
            >>> Element.set_text("新文本")
        """
        self.cdp.execute_script(f"{self.id}.value='{text}'")

    def get_attribute(self, attribute: str) -> Any:
        """
        获取元素属性。

        :param attribute: 属性名
        :return: 属性值
        :Example:
            >>> value = Element.get_attribute("class")
        """
        return self.cdp.execute_script(f"{self.id}.{attribute}")

    def set_attribute(self, attribute: str, value: Any):
        """
        设置元素属性。

        :param attribute: 属性名
        :param value: 属性值
        :Example:
            >>> Element.set_attribute("class", "new-class")
        """
        self.cdp.execute_script(f"{self.id}.{attribute}='{value}'")

    def get_property(self, prop: str) -> Any:
        """
        获取元素属性值。

        :param prop: 属性名
        :return: 属性值
        :Example:
            >>> value = Element.get_property("value")
        """
        return self.cdp.execute_script(f"{self.id}.{prop}")

    def set_property(self, prop: str, value: Any):
        """
        设置元素属性值。

        :param prop: 属性名
        :param value: 属性值
        :Example:
            >>> Element.set_property("value", "新值")
        """
        self.cdp.execute_script(f"{self.id}.{prop}='{value}'")

    def get_value(self) -> Any:
        """
        获取元素值。

        :return: 元素值
        :Example:
            >>> value = Element.get_value()
        """
        return self.cdp.execute_script(f"{self.id}.value")

    def set_value(self, value: Any):
        """
        设置元素值。

        :param value: 要设置的值
        :Example:
            >>> Element.set_value("新值")
        """
        self.cdp.execute_script(f"{self.id}.value='{value}'")

if __name__ == '__main__':
    pass
