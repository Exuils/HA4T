---
name: ha4t-case-writer
description: 根据自然语言描述与 HA4T 编辑器采集的 POM 元素库，生成可在 HA4T 编辑器中直接运行的 UI 自动化测试用例。当用户要求"写测试用例/生成用例/把这段流程变成用例"且项目中存在 pom/ 目录时使用。
---

# HA4T 测试用例生成

## 工作流程（必须按序）

1. **读页面索引**：列出 `pom/` 下所有非 `_` 开头的 `.py` 文件，只读每个文件的头部注释（`# page:` / `# desc:` / `# triggers:`）。不要在这一步读取 ELEMENTS 内容。
2. **选页**：根据用户的自然语言描述，从 desc/triggers 判断本流程涉及哪些 page。只把这些 page 文件完整读入。
3. **读全局**：读 `pom/_meta.py` 获取全局 `VARS`（包名 / 基础 URL / 测试账号等跨用例常量）。
4. **生成用例**：按下方"用例文件格式"写出 `.py` 文件，保存到 pom/ 的上级目录（tasks 根目录）。用例文件顶部必须声明 `LOCAL_VARS = {...}` 字典存放本用例特有的常量（如本用例的测试账号、固定文案、时间戳种子），编辑器据此自动渲染出可视化变量编辑器。
5. **缺失元素**：若流程需要的元素在已选 page 的 ELEMENTS 中不存在，**禁止编造 locator**。在回复末尾输出"缺失元素清单"（page 名 + 建议元素名 + 用途），让用户回编辑器采集后重试。

## 用例文件格式

```python
# name: <用例中文名>
# platform: <android|ios|harmony，取自 _meta 或用户指定>
import os
os.environ["FLAGS_use_mkldnn"] = "0"
from ha4t import connect, include
from time import sleep
from pom import 登录页, HomePage, VARS  # 只 import 用到的 page；page/element 名可中文

# 本用例特有的常量；编辑器自动检测顶层 LOCAL_VARS = {...} 并渲染为可视化 kv 编辑区。
# 跨用例共享的常量请放进 POM 编辑器的「全局 VARS」（pom/_meta.py 的 VARS）。
LOCAL_VARS = {
    "username": "tester",
    "password": "p@ss",
}

dev = connect(platform="android", device_serial="")

# --step-- 启动应用
dev.start_app(VARS["package"])

# --step-- 点击登录按钮
dev.click(**登录页.ELEMENTS["登录按钮"])
```

规则：
- 每个步骤一个 `# --step--` 标记 + 一行（或几行）代码；标记后的文字是步骤备注。
- 元素一律 `dev.click(**Page.ELEMENTS["name"])` 形式引用，不要把 locator 字面量复制进用例。
- Page 名与元素名都允许中文（如 `登录页.ELEMENTS["登录按钮"]`），用户采集时常用中文以表达语义——按 pom 文件里的实际 key 原样写，不要自行翻译或转写为拼音/英文。
- 元素有两种类型，都用同一种 `dev.click(**...)` 语法：
  - **selector 类型**：`{"text": "登录", "resourceId": "..."}` → 走层级匹配
  - **image 类型**：`{"image": "btn_a1b2.png"}` → 走截图模板匹配（用户在画面上框选了图像区域，文件已存在 `<images_dir>/` 下）
  不需要写不同代码，`**` 解包后 HA4T 内部自动选定位方式。NEVER 替换 image 类型的字面量为 selector 字段——这是用户明确放弃层级定位的标记。
- 变量用法 — 全局 `VARS["key"]`（POM 编辑器维护，写入 `pom/_meta.py`）/ 本用例特有 `LOCAL_VARS["key"]`（顶层字典声明）。LOCAL_VARS 命名固定，编辑器靠它识别；不要换其它变量名。
- 复用已有整个用例：`include("other_case.py")`（文件在 tasks 根目录）。

## 可用 Device API（仅限以下，不存在文本输入 API）

| API | 说明 |
|-----|------|
| `dev.click(**selector)` / `dev.click(text=..)` | 点击。selector 键：text / resourceId / className / xpath / description / index |
| `dev.click((0.5, 0.3))` | 按比例坐标点击 |
| `dev.double_click(**selector, interval=0.05)` | 双击 |
| `dev.long_press(**selector, duration=1.0)` | 长按 |
| `dev.drag(**selector, dx=0, dy=0, duration=0.5)` | 拖拽偏移 |
| `dev.swipe((x1,y1), (x2,y2))` | 滑动（绝对像素或 0-1 比例） |
| `dev.swipe_up()` / `swipe_down()` / `swipe_left()` / `swipe_right()` | 方向滑动 |
| `dev.key("back")` / `dev.home()` | 按键 |
| `dev.exists(**selector)` | 元素是否存在（返回 bool，不抛错） |
| `dev.wait(**selector, timeout=10, reverse=False)` | 等待元素出现/消失 |
| `dev.get_text(**selector)` | 取元素文本 |
| `dev.assert_element(**selector, operator="eq", expected=..., extract="text")` | 断言。operator: eq/ne/contains/not_contains/empty/not_empty/regex/exists |
| `dev.start_app(pkg)` / `stop_app(pkg)` / `restart_app(pkg)` / `clear_app(pkg)` | 应用管理 |
| `sleep(seconds)` | 等待 |
| `include("case.py")` | 内联执行另一个用例（共享 dev） |

## 调试提示

在 HA4T 编辑器「POM 采集」模式点底部「验证元素」按钮可以一键扫描当前 page 所有 selector 元素是否在当前设备屏幕上能定位到；image 元素需手工逐个验证。验证结果不会落盘。

## 示例

用户输入："打开 app 登录后进入搜索页搜火锅"

1. 读 pom/ 索引 → desc 匹配出 LoginPage、HomePage、SearchPage
2. 读这三个文件 + _meta.py
3. 生成 `test_search_hotpot.py`，缺 `SearchPage.ELEMENTS["search_input"]` 时停下输出缺失清单。
