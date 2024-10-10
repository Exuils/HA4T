from ha4t import connect

connect(platform="android")
from ha4t.api import *

start_app(app_name="com.makeblock.xcs",activity="com.makeblock.xcs.MainActivity")
click("Add")