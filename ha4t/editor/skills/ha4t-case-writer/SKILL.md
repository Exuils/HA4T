---
name: ha4t-case-writer
description: 根据自然语言描述与 HA4T 编辑器采集的 POM 元素库，生成可在 HA4T 编辑器中直接运行的 UI 自动化测试用例。当用户要求"写测试用例/生成用例/把这段流程变成用例"且项目中存在 pom/ 目录时使用。
---

# HA4T 测试用例生成

## 工作流程（必须按序）

用例放在工作区的 `testcases/` 目录；运行时工作目录为工作区根，`from pom import` 与 `dev.click(Selector(image=...))` 自动解析。

1. **读页面索引**：列出 `pom/` 下所有非 `_` 开头的 `.py` 文件，只读每个文件头部注释（`# page:` / `# desc:` / `# triggers:`）。不在这一步读 ELEMENTS 内容。
2. **选页**：根据用户自然语言描述，从 desc/triggers 判断本流程涉及哪些 page。只把这些 page 文件完整读入。
3. **读全局**：读 `pom/_meta.py` 获取全局 `VARS`（包名 / 基础 URL / 测试账号等跨用例常量）。
4. **生成用例**：按下方格式示意写出 `.py` 文件，保存到 `testcases/`。可自由组合 Python 标准库与 Device API 实现复杂场景。用例顶部建议声明 `LOCAL_VARS = {...}` 字典存放本用例特有的常量。
5. **缺失元素**：若流程需要的元素在 ELEMENTS 中不存在（或当前平台分桶为空）→ **禁止编造 locator**。在回复末尾输出"缺失元素清单"（page 名 + 建议元素名 + 用途 + 哪些平台需要），让用户回编辑器采集后重试。

## POM 元素：`Selector` 对象

每个 page 的 `ELEMENTS` 是 `{ name → Selector(...) }`。Selector 是**跨平台元素定位器**：

```python
from ha4t import Selector

ELEMENTS = {
    # 平台分桶：同一元素在 Android/iOS native 字段不同时分别记录
    "登录按钮": Selector(
        android={"resourceId": "com.x:id/login", "text": "登录"},
        ios={"label": "Login"},
    ),
    # 跨平台共享图像：image 字段（不分平台，与平台分桶互斥）
    "登录图标": Selector(image="login_icon.png"),
    # 带 meta：_parent 父元素名（UI 树语义） / _doc 元素说明
    "返回按钮": Selector(
        _parent="顶部导航",
        _doc="退回到上一页",
        android={"text": "返回"},
        ios={"label": "Back"},
    ),
}
```

**字段分类**：
- `android={...}` / `ios={...}` / `harmony={...}`：平台 native kwargs，**只有当前 `connect(platform=...)` 的那个分桶生效**
- `image="..."`：跨平台共享图像模板（与平台分桶互斥）
- `_parent="父元素名"`、`_doc="说明"`：meta，driver 拿不到，仅给 AI / 人读

## 用例文件格式（示意，非限制）
  
用例是一个 Python 脚本，可以自由组合 Python 标准库 + 下方 Device API。以下仅作格式示意，**实际生成的用例可以远复杂于此**（循环 / 计时 / 数据收集 / 条件分支……）。
  
```python
# name: <用例中文名>
# platform: <android|ios|harmony>
import os, time, json
os.environ["FLAGS_use_mkldnn"] = "0"
from ha4t import connect, include
from pom import 首页, 登录页, VARS

LOCAL_VARS = {
    "username": "tester",
}

dev = connect(platform="android", device_serial="")

# --step-- 启动应用
dev.start_app(VARS["package"])

# --step-- 登录
dev.click(登录页.ELEMENTS["用户名输入框"])
dev.click(登录页.ELEMENTS["密码输入框"])
dev.click(登录页.ELEMENTS["登录按钮"])
dev.wait(首页.ELEMENTS["首页加载完成"], timeout=10)
```

**关键变化（vs 旧 API）**：
- ✅ `dev.click(登录页.ELEMENTS["登录按钮"])` —— 直接传 Selector 对象（**没有 `**`**）
- ❌ 不再写 `dev.click(**登录页.ELEMENTS["登录按钮"])`（Selector 不是 dict）
- ✅ 平台分桶由 `connect(platform=...)` 决定，**用例代码切平台零变化**
- ✅ image 元素同样用 `dev.click(ELEMENTS["x"])` —— Selector 内部按规则解析

## 规则
  
- 用例是**纯 Python 脚本**。除下方 Device API 外，可自由使用 Python 标准库（`time` / `json` / `csv` / `math` / `dataclasses` / `collections` / `datetime`……）、控制流（`for` / `while` / `if`）、数据结构（`list` / `dict` / `set` / 推导式 / 生成器）——没有功能限制
- 每个 `# --step--` 标记一个逻辑步骤。标记后可以是一行、一个 `for` 循环、一个函数调用——任意复杂度都行。pytest 以 step 为单位拆分输出到 Allure 报告
- 元素一律 `dev.click(Page.ELEMENTS["name"])` 形式，**不要复制 locator 字面量**
- Page 名与元素名都允许中文。按 pom 文件里实际 key 原样写
- 临时定位（不进 POM）有两种写法：
  - `dev.click(Selector(android={"text": "确定"}, ios={"label": "OK"}))` 显式 Selector
  - `dev.click(text="确定")` —— canonical kwargs，HA4T 内部按当前平台翻译
- 全局变量：`VARS["key"]`（pom/_meta.py 维护）；用例特有：`LOCAL_VARS["key"]`（顶层 dict，命名固定）
- 复用用例：`include("other_case.py")`（被引用文件同在 `testcases/`）
- 参数化元素：`dev.click(商品页.ELEMENTS["商品项"].format(index=2))`。Selector `.format(**kwargs)` 按平台分桶逐字段做 `str.format`

## 平台缺失元素的处理

若某元素 `Selector(android={...})` 只采集了 Android 但用例运行在 iOS：

```python
# 运行时会抛 SelectorNotAvailableError
# Selector 在 'ios' 上无定位信息；已采集平台: ['android'] / image: None
```

**生成用例时**：检查每个引用的元素是否在目标 `platform` 上有 selector 或 image。缺失则进缺失清单输出，**不要生成会运行时报错的代码**。

## 可用 Device API（可自由组合 Python 标准库）

每个 API 都接受 `Selector` 对象（首选）或 raw canonical kwargs（quick path）。

| API | 说明 |
|-----|------|
| `dev.click(SelectorObj)` / `dev.click(text=..)` | 点击 |
| `dev.click((0.5, 0.3))` | 按比例坐标点击 |
| `dev.double_click(SelectorObj, interval=0.05)` | 双击 |
| `dev.long_press(SelectorObj, duration=1.0)` | 长按 |
| `dev.drag(SelectorObj, dx=0, dy=0, duration=0.5)` | 拖拽偏移 |
| `dev.swipe((x1,y1), (x2,y2))` | 滑动（绝对像素或 0-1 比例） |
| `dev.swipe_up()` / `swipe_down()` / `swipe_left()` / `swipe_right()` | 方向滑动 |
| `dev.key("back")` / `dev.home()` | 按键 |
| `dev.exists(SelectorObj)` | 元素是否存在（返回 bool，不抛错） |
| `dev.wait(SelectorObj, timeout=10, reverse=False)` | 等待元素出现/消失 |
| `dev.get_text(SelectorObj)` | 取元素文本 |
| `dev.assert_element(SelectorObj, operator="eq", expected=..., extract="text")` | 断言。operator: eq/ne/contains/not_contains/empty/not_empty/regex/exists |
| `dev.start_app(pkg)` / `stop_app(pkg)` / `restart_app(pkg)` / `clear_app(pkg)` | 应用管理 |
| `sleep(seconds)` | 等待 |
| `include("case.py")` | 内联执行另一个用例（共享 dev） |

## Canonical 字段映射（raw kwargs 路径）

`dev.click(text="登录")` 这种 raw kwargs 走 canonical 翻译表：

| canonical | Android (u2) | iOS (WDA) |
|---|---|---|
| `text` | `text` | `label` |
| `resourceId` | `resourceId` | `name` |
| `label` | `description` | `label` |
| `description` | `description` | `label` |
| `className` | `className` | `className` |
| `xpath` | `xpath` | `xpath` |
| `index` | `index` | (不映射) |

## 调试提示
  
在 HA4T 编辑器「POM 采集」模式点工具栏「验证」按钮，可一键扫描当前 page 当前平台所有 selector 元素是否在当前设备屏幕上能定位到。验证模式下 found 状态粘性保留，切页面后点「刷新未找到」补扫；image 元素需手工逐个验证。验证结果不落盘。
  
## 示例
  
用户输入："我写个冷启动性能测试，记录5次启动耗时并输出最大值最小值平均值"
  
1. 读 pom/ 索引 → desc 匹配出 HomePage 等
2. 读相关 page 文件 + _meta.py
3. 若流程需要的 POM 元素已采集 → 生成 `test_cold_start.py`：用 `for` 循环执行 5 轮 stop+start，`time.time()` 收集耗时，末尾算 max/min/avg 并 `print()` 输出表格
4. 若元素缺失 → 输出缺失清单，等用户补采后重试
