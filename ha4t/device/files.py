# -*- coding: utf-8 -*-
"""文件传输 mixin —— pull / upload / delete。"""
import os
from typing import List, Union

from ha4t.utils.log_utils import cost_time, log_out


class FileMixin:
    @cost_time
    def pull_file(self, src_path: Union[List[str], str], filename: str) -> None:
        """从设备拉取文件到本地。"""
        remote = "/".join(src_path) if isinstance(src_path, list) else src_path
        log_out(f"从设备路径 {remote} 下载文件 {filename}")
        self.driver.pull_file(remote, filename)

    @cost_time
    def upload_files(self, src_path: str) -> None:
        """上传文件或文件夹到设备 ``/sdcard/`` 根目录下。"""
        if os.path.isdir(src_path):
            from ha4t.utils.files_operat import get_file_list as _gfl
            for f in _gfl(src_path):
                self.driver.push_file(f, f"/sdcard/{os.path.basename(f)}")
        else:
            self.driver.push_file(src_path, f"/sdcard/{os.path.basename(src_path)}")
        log_out(f"文件 {src_path} 上传成功")

    @cost_time
    def delete_file(self, file_path: Union[List[str], str]) -> None:
        """删除设备上的文件。"""
        remote = "/".join(file_path) if isinstance(file_path, list) else file_path
        self.driver.delete_file(remote)
        log_out(f"设备文件 {remote} 删除成功")
