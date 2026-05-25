import os
os.environ["FLAGS_use_mkldnn"] = "0"

from ha4t import connect
from ha4t.api import start_app, click

connect(platform="android")
start_app("com.oceanwing.eufymake.cn", activity="com.oceanwing.FDMPrint.main.StartActivity")

click(description="打印照片")
