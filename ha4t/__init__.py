__version__ = "0.0.2"

from ha4t.config import Config as CF


def connect(device_serial="", android_package_name=None, android_activity_name=None, platform="android"):
    CF.PLATFORM = platform
    CF.DEVICE_SERIAL = device_serial
    CF.ANDROID_PACKAGE_NAME = android_package_name
    CF.ANDROID_ACTIVITY_NAME = android_activity_name


__all__ = ["__version__", "connect"]
