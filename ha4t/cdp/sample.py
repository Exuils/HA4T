# -*- coding: utf-8 -*-
# @时间       : 2024/10/10 17:33
# @作者       : caishilong
# @文件名      : sample.py
# @项目名      : HA4T
# @Software   : PyCharm
from typing import Optional, Union, Tuple, List, Any
from .cdp import CDP, Page, Element
from .server import CdpServer
window: Optional[Page] = None
cdp: Optional[CDP] = None

# if CF.USE_CDP:
#     cdp_server = CdpServer(ignore_exist_port=CF.IGNORE_EXIST_PORT)
#
#     if CF.PLATFORM == "ios":
#         driver: wda.Client
#         if driver.app_state(CF.APP_NAME)["value"] == 1:
#             driver.app_start(CF.APP_NAME)
#
#         cdp_server.start_server_for_ios_app(port=CF.CDP_IOS_PORT)
#     else:
#         driver: u2.Device
#         if CF.APP_NAME not in driver.app_list_running():
#             driver.app_start(CF.APP_NAME)
#         cdp_server.start_server_for_android_app(port=CF.CDP_ANDROID_PORT, adb=device.adb)
#     cdp = CDP(cdp_server.ws_endpoint)
#     window = cdp.get_page(ws_title=["homePage", "editPage"])