import os
import re

import setuptools
from setuptools import find_packages

with open("./ha4t/__init__.py", 'r', encoding="utf-8") as f:
    content = f.read()
    version = re.search(r'__version__\s*=\s*[\'"]([^\'"]*)[\'"]', content).group(1)
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()


setuptools.setup(
    name="HA4T",
    version=version,
    author="caishilong",
    author_email="caishilong@exuils.com",
    description="跨平台的UI自动化框架，适用于混合型app",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license='Apache License 2.0',
    url="https://github.com/exuils/HA4T",
    packages=find_packages(exclude=("tests",)),
    keywords=['automation', 'automated-test', 'game', 'android', 'ios', "hybrid-app"],
    package_data={
        'ha4t': ['binaries/*'],
        'ha4t.editor': ['static/**/*'],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
)
