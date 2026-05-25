# name: Demo EufyMake
# desc: Launch eufymake app on Android
# platform: android
import os
os.environ["FLAGS_use_mkldnn"] = "0"

from ha4t import connect
from ha4t.api import *

connect(platform="android")

# --step--
start_app("com.oceanwing.eufymake.cn", activity="com.oceanwing.FDMPrint.main.StartActivity")

# --step--
click(text="打印照片")
