#!/usr/bin/env python
# -*- coding:utf-8 -*-
# @FileName :server.py
# @Time :2024/8/26 下午10:01
# @Author :CAISHILONG
"""
用于启动 app ，并开启cdp服务，支持pc，android，ios
"""
import os
import socket
import subprocess
import time
import adbutils
import requests
from ..utils.log_utils import log_out


class Server:
    """
    window系统进程管理类，主要用于管理服务进程
    """
    def kill_dead_servers(self, port):
        if pid := self.get_port_exists(port):
            log_out(f"正在结束本机进程 {port}, pid {pid}")
            cmd = f"taskkill /f /pid {self.get_pid_by_port(port)}"
            subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            while self.pid_exists(pid):
                time.sleep(0.1)
            log_out(f"进程 {port} 已结束, pid {pid}")

    @staticmethod
    def get_pid_by_port(port):
        cmd = f"netstat -ano | findstr :{port} | findstr LISTENING"
        lines = subprocess.check_output(cmd, shell=True).decode().strip().splitlines()
        for line in lines:
            pid = line.split(" ")[-1]
            if pid != 0:
                return pid

    @classmethod
    def get_pid(cls, process) -> str:
        return process.pid if process else None

    @staticmethod
    def pid_exists(pid) -> bool:
        try:
            subprocess.check_output(f"ps -p {pid}", shell=True, stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            return False

    @classmethod
    def get_port_exists(cls, port) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0


class CdpServer(Server):
    def __init__(self, ignore_exist_port=True):
        """
        开启H5应用cdp服务,支持pc，android，ios
        :param ignore_exist_port: 是否忽略已存在的端口，关闭后每次都会先结束已存在的端口
        """
        self.ws_endpoint = None
        self.ignore_exist_port = ignore_exist_port

    @staticmethod
    def check_port_connection(port, timeout=10):
        try:
            requests.get(f"http://localhost:{port}/json", timeout=timeout)
            return True
        except requests.RequestException:
            return False

    def can_start_server(self, port):
        if self.check_port_connection(port):
            log_out(f"端口{port}已存在")
            if self.ignore_exist_port:
                log_out(f"忽略端口{port}，继续测试")
                return False
            else:
                log_out(f"查询启动端口{port}，如需要忽略已存在端口，请设置ignore_exist_port=True")
                self.kill_dead_servers(port)
                return True
        log_out(f"开始{port}CDP端口转发...")
        return True

    def start_server_for_android_app(self, adb: adbutils.AdbDevice, port=9222, timeout=10):
        """
        开启android app cdp服务
        :param adb: adb设备
        :param port: 端口
        :param timeout: 超时时间
        """
        can_start = self.can_start_server(port)
        if can_start:
            rs: str = adb.shell(['grep', '-a', 'webview_devtools_remote', '/proc/net/unix'])
            end = rs.split("@")[-1]
            log_out(f"app webview 进程 {end} 已存在，尝试端口转发")
            server = adb.forward(local=f"tcp:{port}", remote=f"localabstract:{end}")
            requests.get(f"http://localhost:{port}/json", timeout=timeout)
            self.ws_endpoint = f"http://localhost:{port}"
            log_out(f"CDP端口转发成功，端口：{port}")
            return server
        self.ws_endpoint = f"http://localhost:{port}"
        return None

    def start_server_for_ios_app(self, port=9222, timeout=10):
        """
        开启ios app cdp服务
        :param port: 端口
        :param timeout: 超时时间
        """
        can_start = self.can_start_server(port)
        if can_start:
            server = subprocess.Popen(["remotedebug_ios_webkit_adapter", f"--port={str(port)}"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,shell=True)
            requests.get(f"http://localhost:{port}/json", timeout=timeout)
            self.ws_endpoint = f"http://localhost:{port}"
            log_out(f"CDP端口转发成功，端口：{port}")
            return server
        self.ws_endpoint = f"http://localhost:{port}"
        return None

    def start_server_for_windows_app(self, app_path: str, port=9222, reset=False, user_data_dir=None, timeout=10, lang="zh-CN"):
        """
        开启windows app cdp服务
        :param app_path: 应用路径
        :param port: 端口
        :param reset: 是否重置用户数据
        :param user_data_dir: 用户数据目录
        :param timeout: 超时时间
        :param lang: 语言
        """
        can_start = self.can_start_server(port=port)
        if can_start:
            start_app_args = [app_path, f"--remote-debugging-port={port}"]
            print(reset)
            if reset:
                if user_data_dir is None:
                    user_data_dir = os.path.join(os.path.dirname(__file__), 'app_user_data')
                if os.path.exists(user_data_dir):
                    try:
                        os.remove(user_data_dir)
                        print(f"已成功删除用户数据目录: {user_data_dir}")
                    except PermissionError as e:
                        print(f"没有权限删除 {user_data_dir}. 错误信息: {e}")
                    except FileNotFoundError as e:
                        print(f"找不到文件或目录: {e}")
                    except Exception as e:
                        print(f"删除 {user_data_dir} 时发生未知错误: {e}")
                start_app_args.append(f"--user-data-dir={user_data_dir}")
            start_app_args.append("--no-sandbox")
            start_app_args.append(f"--lang={lang}")
            log_out(f"启动命令：{start_app_args}")
            app_server = subprocess.Popen(start_app_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            requests.get(f"http://localhost:{port}/json", timeout=timeout)
            log_out(f"CDP端口转发成功，端口：{port}")
            self.ws_endpoint = f"http://localhost:{port}"
            return app_server
        self.ws_endpoint = f"http://localhost:{port}"
        return None

    def start_server_for_mac_app(self, file_path: str, port=9222):
        # 这里需要根据macOS的具体情况实现
        """
        TODO: 这里需要根据macOS的具体情况实现
        :param file_path:
        :param port:
        :return:
        """
        pass
