import os
import sys
import setuptools
from setuptools import find_packages
import re

with open("./ha4t/__init__.py", 'r') as f:
    content = f.read()
    # from https://www.py4u.net/discuss/139845
    version = re.search(r'__version__\s*=\s*[\'"]([^\'"]*)[\'"]', content).group(1)
    
with open("README.md", "r") as fh:
    long_description = fh.read()

def is_docker():
    if os.path.exists('/proc/self/cgroup'):
        with open('/proc/self/cgroup', 'rt') as ifh:
            return 'docker' in ifh.read()
    return False

def parse_requirements(filename):
    """ load requirements from a pip requirements file. (replacing from pip.req import parse_requirements)"""
    lineiter = (line.strip() for line in open(filename))
    reqs = [line for line in lineiter if line and not line.startswith("#")]
    if sys.platform == "win32":
        reqs.append('pywin32')
    # if py<=3.6 add dataclasses
    if sys.version_info.major == 3 and sys.version_info.minor <= 6:
        reqs.append("dataclasses")
    if sys.version_info.major == 3 and sys.version_info.minor <= 7:
        reqs.remove("facebook-wda>=1.3.3")
        reqs.append("facebook-wda<1.4.8")
    if is_docker():
        reqs.remove("opencv-contrib-python>=4.4.0.46, <=4.6.0.66")
        reqs.append("opencv-contrib-python-headless==4.5.5.64")
    return reqs


setuptools.setup(
    name="HA4T",
    version=version,
    author="caishilong",
    author_email="1103837067@qq.com",
    description="跨平台的UI自动化框架，适用于混合型app",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license='Apache License 2.0',
    url="https://github.com/1103837067/HA4T",
    install_requires=parse_requirements('requirements.txt'),
    packages=find_packages(exclude=("tests",)),
    keywords=['automation', 'automated-test', 'game', 'android', 'ios',"hybird-app"],
    extras_require={
        "dev": ["flake8", "black==22.3.0", "isort", "twine", "pytest", "wheel"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)
