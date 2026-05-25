# -*- coding: utf-8 -*-

import importlib.metadata

try:
    __version__ = importlib.metadata.version("HA4T")
except importlib.metadata.PackageNotFoundError:
    __version__ = "1.0.1"
