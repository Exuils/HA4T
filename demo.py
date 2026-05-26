import os
os.environ["FLAGS_use_mkldnn"] = "0"

from ha4t import connect
from ha4t.api import *

connect(platform="android")
start_app("com.oceanwing.eufymake.cn", activity="com.oceanwing.FDMPrint.main.StartActivity")

# --step--
click(description="打印照片")
