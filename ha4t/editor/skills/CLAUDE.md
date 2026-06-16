# HA4T 测试工作区 — AI 行为规则

语言：中文

本文件是工作区内 AI 行为的唯一规则来源。

## 测试用例生成

### POM 元素定位

POM 元素是 `Selector` 对象，定义在 `pom/<page>.py` 的 `ELEMENTS` dict 中：

```python
from ha4t import Selector

ELEMENTS = {
    # 平台分桶：同一元素在不同平台 native 字段不同时分别记录
    "登录按钮": Selector(
        android={"resourceId": "com.x:id/login", "text": "登录"},
        ios={"label": "Login"},
    ),
    # 跨平台共享图像：image 字段（与平台分桶互斥）
    "登录图标": Selector(image="login_icon.png"),
}
```

字段含义：
- `android={...}` / `ios={...}` / `harmony={...}`：平台 native kwargs，**只有当前 `connect(platform=...)` 的分桶生效**
- `image="..."`：跨平台共享图像模板（与平台分桶互斥）
- `_parent="父元素名"`、`_doc="说明"`：仅给 AI / 人读，driver 拿不到

### 用例文件格式

用例是**纯 Python 脚本**，放在 `testcases/` 目录。可自由使用 Python 标准库（`time` / `json` / `csv` / `for` / `while` / `if` / `list` / `dict` / `set`……）与下方 Device API 组合。

```python
# name: <用例中文名>
# platform: <android|ios|harmony>
import os, time
os.environ["FLAGS_use_mkldnn"] = "0"
from ha4t import connect, include
from pom import 首页, 登录页, VARS

LOCAL_VARS = {"username": "tester"}

dev = connect(platform="android", device_serial="")

# --step-- 启动应用
dev.start_app(VARS["package"])

# --step-- 登录
dev.click(登录页.ELEMENTS["用户名输入框"])
dev.click(登录页.ELEMENTS["密码输入框"])
dev.click(登录页.ELEMENTS["登录按钮"])
dev.wait(首页.ELEMENTS["首页加载完成"], timeout=10)
```

关键约定：
- 每个 `# --step--` 标记一个逻辑步骤，标记后可以是任意复杂的 Python 代码
- 元素一律 `dev.click(Page.ELEMENTS["name"])`，**不要复制 locator 字面量**
- 全局变量 → `VARS["key"]`；用例特有 → `LOCAL_VARS["key"]`
- 复用用例 → `include("other_case.py")`
- 参数化元素 → `dev.click(ELEMENTS["商品项"].format(index=2))`

### 不可违反的规则

1. **禁止新建、修改或删除 `pom/` 目录下的任何文件**（包括 `.py` 和 `_meta.py`）。POM 只由编辑器采集生成
2. **只能引用 `ELEMENTS` 中已存在的元素**，唯一可调的是 `index` 参数
3. **禁止猜测 resourceId / text / xpath 等 locator 值**——只有编辑器采集才能拿到真实值
4. 缺失元素只能在回复末尾输出缺失清单，**不要编造 locator，不要用临时定位绕过**
5. 临时定位（已知的临时元素，如用户明确说的某段文字）有限允许：`dev.click(Selector(android={"text": "确定"}))` 或 `dev.click(text="确定")`——但**不是常规手段**

### 可用 Device API

每个 API 接受 `Selector` 对象（首选）或 raw canonical kwargs（quick path）。

| API | 说明 |
|-----|------|
| `dev.click(selector)` / `dev.click(text=..)` | 点击 |
| `dev.click((0.5, 0.3))` | 比例坐标点击 |
| `dev.double_click(selector, interval=0.05)` | 双击 |
| `dev.long_press(selector, duration=1.0)` | 长按 |
| `dev.drag(selector, dx=0, dy=0, duration=0.5)` | 拖拽偏移 |
| `dev.swipe((x1,y1), (x2,y2))` | 滑动（像素或 0-1 比例） |
| `dev.swipe_up()` / `swipe_down()` / `swipe_left()` / `swipe_right()` | 方向滑动 |
| `dev.key("back")` / `dev.home()` | 按键 |
| `dev.exists(selector)` | 元素是否存在（返回 bool，不抛错） |
| `dev.wait(selector, timeout=10, reverse=False)` | 等待元素出现/消失 |
| `dev.get_text(selector)` | 取元素文本 |
| `dev.assert_element(selector, operator="eq", expected=..., extract="text")` | 断言 |
| `dev.start_app(pkg)` / `stop_app(pkg)` / `restart_app(pkg)` / `clear_app(pkg)` | 应用管理 |
| `sleep(seconds)` | 等待 |
| `include("case.py")` | 内联执行另一个用例 |

### 平台缺失元素的处理

若某元素在当前 `platform` 上无 selector 或 image：

1. 输出缺失清单，每项格式：`{page名} | {建议元素名} | {用途} | {需要平台}`
2. 引导用户到编辑器采集，话术模板：
   - *"请在 HA4T 编辑器中打开「{page}」页面，使用左上角手柄的采集模式，在屏幕上框选对应的元素，保存后告诉我重试。"*
   - *"如果只是缺少 {platform} 平台的分桶，请切换到该设备后重新采集。"*
3. 不要用临时定位绕过。输出清单和引导后停止，等用户补采后重试

### 工作流程

1. **读页面索引**：列出 `pom/` 下所有非 `_` 开头的 `.py` 文件，只读头部注释（`# page:` / `# desc:` / `# triggers:`）。**不读 ELEMENTS 内容**
2. **选页**：根据用户描述匹配 desc/triggers，只读相关 page 的完整 ELEMENTS
3. **读全局**：读 `pom/_meta.py` 获取 `VARS`
4. **生成用例**：写出 `.py` 文件到 `testcases/`
5. **缺失元素**：输出缺失清单 + 用户引导，停止
