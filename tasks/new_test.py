# name: New Test
# platform: android
import os
os.environ["FLAGS_use_mkldnn"] = "0"
from ha4t import connect
from ha4t.api import *
connect(platform="android")


# --step--
start_app("com.atomform.threedprinter.tech")
