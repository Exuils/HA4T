# -*- coding: utf-8 -*-
# @时间       : 2024/8/21 10:02
# @作者       : caishilong
# @文件名      : cdp.py
# @Software   : PyCharm
"""
CDPClient 类用于与 Chrome DevTools Protocol (CDP) 进行通信。它通过 WebSocket 连接到浏览器的调试端口，并发送 CDP 命令以控制浏览器。
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


class WS_CDP:
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
        """
        # 这里简单返回一个固定值，实际使用时可能需要更复杂的逻辑来确保唯一性
        return 1

    async def close(self):
        """
        关闭 WebSocket 连接。
        """
        if self.ws:
            await self.ws.close()


def worker(url, task_queue, result_queue, timeout=10):
    async def main():
        client = WS_CDP(url)
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
        :param ws: pages 的 CDP WebSocket 地址。 可--remote-debugging-port=9222 启动浏览器时获取。
        """
        self.ws = ws
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.thread = threading.Thread(target=worker, args=(self.ws, self.task_queue, self.result_queue))
        self.thread.daemon = True
        self.thread.start()

    def restart(self):
        self.close()
        self.__init__(self.ws)

    def send(self, method, params=None, timeout=10):
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
        rs = self.send("Runtime.evaluate", {"expression": script, "returnByValue": True})
        try:
            rs = rs["result"]["result"]["value"]
        except:
            pass
        return rs

    def get_element(self, locator: tuple, timeout=CF.FIND_TIMEOUT):
        """ 获取元素 """
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
        return self.execute_script("document.title")

    def exist(self, locator: tuple):
        """ 判断元素是否存在 """
        script = JS.element_exists(locator=locator)
        return self.execute_script(script)

    def wait(self, locator: tuple, timeout=CF.FIND_TIMEOUT):
        """ 等待元素出现 """
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
        截图
        """
        data = self.send("Page.captureScreenshot")  # png
        data = base64.b64decode(data["result"]["data"])
        img = PIL.Image.open(io.BytesIO(data))
        if path:
            img.save(path)
        return img

    @cost_time
    def click(self, locator: tuple, timeout=CF.FIND_TIMEOUT):
        """ 点击元素 """
        self.wait(locator, timeout)
        script = JS.add_click(element_var_name=JS.TEMP_VAR_NAME)
        self.execute_script(script)

    # def send_text(self, locator: tuple, text, timeout=10):
    #     """ 输入文本 """
    #     if self.wait_element(locator, timeout):
    #         script = f"{self.__locator_to_script(locator)}.value='{text}'"
    #         self.execute_script(script)
    @staticmethod
    def command(method, params=None):
        return method, params

    def close(self):
        self.task_queue.put(None)
        self.thread.join()


class CDP:
    def __init__(self, url="http://localhost:9222"):
        """
        CDP 类，用于与浏览器进行交互。
        :param url: 浏览器调试地址，默认为 http://localhost:9222
        """
        self.ws_url = url

    def get_page(self, ws_title: str | list[str] = None, timeout=10) -> Page:
        """ 获取页面实例
            ws_title: 页面标题
            timeout: 超时时间
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
            except:
                pass
            if time.time() - t1 > timeout:
                raise ValueError(f"获取页面超时")

    def get_page_list(self) -> list:
        return requests.get(f"{self.ws_url}/json").json()


class Element:
    def __init__(self, cdp: Page, element_id):
        self.cdp = cdp
        self.id = element_id

    @cost_time
    def click(self):
        self.cdp.execute_script(JS.add_click(self.id))

    def exists(self):
        return self.cdp.execute_script(f"{self.id}!= null")

    def is_displayed(self):
        return self.cdp.execute_script(f"{self.id}.style.display!='none'")

    def is_enabled(self):
        return self.cdp.execute_script(f"{self.id}.disabled == false")

    def wait_util_enabled(self, timeout=10):
        t1 = time.time()
        while True:
            if self.is_enabled():
                break
            if time.time() - t1 > timeout:
                raise ValueError(f"元素未启用：{self.id}")
            time.sleep(0.1)

    def is_selected(self):
        return self.cdp.execute_script(f"{self.id}.selected == true")

    def get_text(self):
        return self.cdp.execute_script(f"{self.id}.innerText")

    def set_text(self, text):
        self.cdp.execute_script(f"{self.id}.value='{text}'")

    def get_attribute(self, attribute):
        return self.cdp.execute_script(f"{self.id}.{attribute}")

    def set_attribute(self, attribute, value):
        self.cdp.execute_script(f"{self.id}.{attribute}='{value}'")

    def get_property(self, prop):
        return self.cdp.execute_script(f"{self.id}.{prop}")

    def set_property(self, prop, value):
        self.cdp.execute_script(f"{self.id}.{prop}='{value}'")

    def get_value(self):
        return self.cdp.execute_script(f"{self.id}.value")

    def set_value(self, value):
        self.cdp.execute_script(f"{self.id}.value='{value}'")


if __name__ == '__main__':
    pass
