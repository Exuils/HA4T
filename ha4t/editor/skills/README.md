# HA4T 用例工作区

本目录由 HA4T 编辑器初始化，作为测试用例的独立工程；HA4T 作为依赖库使用。

## 安装依赖
```
uv sync          # 或：pip install -U ha4t
```

## 目录
- `pom/`         Page Object 元素库（编辑器「POM 采集」维护，勿手改 `__init__.py`）
- `images/`      模板图片（`dev.click(image="x.png")` 按裸名解析到此目录）
- `screenshots/` POM 图像元素裁剪源
- `testcases/`   测试用例（.py，编辑器新建用例落在此目录）

## 用例写法
```python
from ha4t import connect
from pom import 登录页, VARS          # 只 import 用到的 page + 全局 VARS

LOCAL_VARS = {"username": "tester"}   # 本用例特有常量（编辑器自动识别渲染）

dev = connect(platform="android", device_serial="")
dev.start_app(VARS["package"])
dev.click(登录页.ELEMENTS["登录按钮"])   # 注意：传 Selector 对象，不带 **
```
- ELEMENTS 值是 Selector 对象，自带跨平台分桶（android/ios/harmony） + image
- 直接 dev.click(ELEMENTS["x"])（不带 **），平台由 connect() 决定
- 全局常量 → POM 编辑器「全局 VARS」（写入 `pom/_meta.py`，代码 `VARS["key"]`）
- 用例常量 → 顶层 `LOCAL_VARS = {...}`（代码 `LOCAL_VARS["key"]`）

详见项目根目录 `AGENTS.md`。
