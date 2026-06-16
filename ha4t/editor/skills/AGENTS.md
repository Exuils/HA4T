# HA4T 测试工作区 — AI 行为规则

语言：中文

## 核心约束

1. **禁止新建、修改或删除 `pom/` 下任何文件**（包括 `_meta.py`）。POM 只由编辑器采集生成，你不知道真实页面上 resourceId / text / xpath 的值
2. **只能引用 `ELEMENTS` 中已存在的元素**，唯一可调的是 `index` 参数：`dev.click(ELEMENTS["商品项"].format(index=2))`
3. **禁止猜测复杂 locator 值**。复杂元素（含 xpath / resourceId / className 组合的）只能在缺失清单输出引导采集
4. 临时定位：页面上的可见文案（text / description）或根据现有 POM 模式推导的简单 selector 可以直接在用例内联——不修改 pom/ 文件，仅当前用例有效

## 用例生成

用例是**纯 Python 脚本**，放在 `testcases/` 目录。可自由组合 Python 标准库（time / json / csv / for / while / list / dict……）与 HA4T Device API。

```python
# name: <用例中文名>
# platform: <android|ios|harmony>
from ha4t import connect
from pom import 首页, 登录页, VARS
LOCAL_VARS = {"username": "tester"}
dev = connect(platform="android", device_serial="")
# --step-- 启动应用
dev.start_app(VARS["package"])
# --step-- 登录
dev.click(登录页.ELEMENTS["登录按钮"])
dev.wait(首页.ELEMENTS["首页加载完成"], timeout=10)
```

关键约定：
- `# --step--` 标记一个逻辑步骤，标记后可以是任意复杂代码
- 已采集的元素 → `dev.click(Page.ELEMENTS["name"])`，**优先使用**
- 可在用例内基于 POM 已有元素推导：`ELEMENTS["商品项"].format(index=i)` 配合 `for` 循环轮询
- 简单临时定位（页面可见文案 / 根据现有 POM 模式推导的简单定位）可直接内联
- 临时定位**不修改 pom/ 文件**，仅当前用例有效
- 全局变量 → `VARS["key"]`；用例特有 → `LOCAL_VARS["key"]`
- 复用用例 → `include("other_case.py")`

## Device 对象结构

`connect()` 返回的 `dev` 是一个多继承组合对象。了解它的骨架就能知道还有什么方法可用：

```
Device  ← 站在 dev 上直接调用的方法来自各个 Mixin
 ├── InteractionMixin   → click / double_click / long_press / swipe / drag / key / home
 ├── QueryMixin         → exists / wait / get_page_text / get_text / assert_element
 ├── AppMixin           → start_app / stop_app / restart_app / get_current_app / clear_app
 ├── FileMixin          → pull_file / upload_files(, remote_dir="") / delete_file
 ├── CaptureMixin       → screenshot
 └── DeviceBase         → driver (底层平台句柄)
```

**关键 escape hatch**：`dev.driver` 是底层平台 driver 对象（Android 是 uiautomator2、iOS 是 wda、Harmony 是 hmdriver）。它有 HA4T Mixin 没包装的平台原生方法：

```python
dev.driver.push_file(local, remote)       # 推到任意设备路径（不限于 /sdcard/）
dev.driver.pull_file(remote, local)       # 从任意路径拉
dev.driver.app_current()                  # 当前前台应用
dev.driver.press("home")                   # 系统按键
```

用 `help(type(dev.driver))` 或 `print([m for m in dir(dev.driver) if not m.startswith("_")])` 在用例里自查。

## HA4T Device API 速查

| 方法 | 说明 | 关键参数 |
|------|------|---------|
| `dev.click(sel)` | 点击元素 | `sel`: Selector / canonical kwargs / 比例坐标 `(0.5, 0.5)` |
| `dev.double_click(sel)` | 双击 | `interval`: 0.05 |
| `dev.long_press(sel)` | 长按 | `duration`: 1.0 |
| `dev.swipe(p1, p2)` | 滑动（像素或比例） | 可选 `duration`/`steps` |
| `dev.swipe_up/down/left/right()` | 方向滑动 | 可选 `duration`/`steps` |
| `dev.drag(sel, dx, dy)` | 拖拽偏移 | `dx/dy`: 像素值 |
| `dev.key(key_name)` | 系统按键 | `"back"`, `"home"`, `"menu"` 等 |
| `dev.home()` | Home 键 | — |
| `dev.exists(sel)` | 元素是否存在 | 返回 `bool`，不抛错 |
| `dev.wait(sel, timeout)` | 等待元素出现/消失 | `reverse=True` 等消失 |
| `dev.get_text(sel)` | 取元素文本 | — |
| `dev.get_page_text()` | OCR 识别全页文字 | — |
| `dev.assert_element(sel, op, expected)` | 断言 | `operator`: eq/ne/contains/regex/exists_true… |
| `dev.start_app(pkg)` | 启动应用 | 可选 `activity` |
| `dev.stop_app(pkg)` | 停止应用 | — |
| `dev.restart_app(pkg)` | 重启应用 | — |
| `dev.get_current_app()` | 当前前台包名 | — |
| `dev.clear_app(pkg)` | 清除数据（仅 Android） | — |
| `dev.pull_file(src, dst)` | 从设备拉文件 | — |
| `dev.upload_files(local, remote_dir='')` | 上传文件/夹 | `remote_dir` 如 `"Download"`→`/sdcard/Download/` |
| `dev.delete_file(path)` | 删除设备文件 | — |
| `dev.driver.push_file(local, remote)` | 推到任意设备路径（不限于 /sdcard） | 底层 driver 能力 |
| `time.sleep(secs)` | 等待 | Python 标准库 |
| `include("case.py")` | 内联执行另一个用例 | — |
| `dir(dev)` / `help(dev.method)` | 运行时自查 | 不依赖文档 |

完整签名、参数说明、返回类型见同目录下的 `API_REFERENCE.md`。

## API 调用优先级

```
1. dev.xxx()              ← HA4T Device Mixin 方法（优先）
2. dev.driver.xxx()       ← 底层平台 driver（Mixin 没包装时用）
3. subprocess/adb 等      ← 环境工具（框架/底层都不够用时降级）
```

例：上传文件到 Download 目录 → `dev.upload_files(local, "Download")`（优先）。
如果不存在该方法（旧版）→ `dev.driver.push_file(local, "/sdcard/Download/f.png")`。
只在上述都不可行时再调 `adb push`。

## 缺失元素时的交互

缺失清单每项格式 `{page名} | {建议元素名} | {用途} | {需要平台}`，并引导用户：

- *"请在 HA4T 编辑器中打开「{page}」页面，使用左上角手柄的采集模式，在屏幕上框选对应元素，保存后告诉我重试。"*
- *"如果只是缺少 {platform} 平台的分桶，请切换到该设备后重新采集。"*

输出清单和引导后停止，等用户补采后重试。

## 工作流程

1. 读 `pom/` 索引（头部注释，不读 ELEMENTS）
2. 匹配后读相关 page 完整 ELEMENTS + `pom/_meta.py`
3. 写出 `.py` 到 `testcases/`
4. 缺失元素 → 输出清单 + 引导，停止

## API 发现方式（别去读源码）

HA4T API 的签名和行为只靠以下来源，**不要去读 `ha4t/` 源码目录**：

1. **上方 Device 对象结构图** → 理解 dev 由哪些 Mixin 拼成，知道有哪些方法类别
2. **上方 API 速查表** → 快速知道有什么方法
3. **`API_REFERENCE.md`** → 完整签名、参数说明、返回类型（编辑器初始化时自动生成）
4. **Python 运行时自查** → 在用例里调 `dir(dev)` 或 `help(dev.method)` 查看
5. **`dev.driver`** → 底层平台 driver 的额外方法，`help(type(dev.driver))` 可查

只有需要**给 HA4T 框架本身加新功能**时，才去碰源码仓库。

## 环境辅助调试

当用例运行异常或框架层面无法处理时（如文件管理、文件传输、网络状态、权限弹窗、系统设置、页面结构探查、日志排查等），可以直接使用当前环境中的工具链辅助调试。

**原则**：按 API 调用优先级逐级降级。辅助手段只用于问题排查和系统层操作，不替代测试用例的主体逻辑。
## 问题排查流程

当 API 不够用时，按这个顺序处理，**别跳步骤**：

1. **查已安装的 API** —— `dir(dev)` 列方法、`help(dev.method)` 看签名和 docstring、读 `API_REFERENCE.md`
2. **找现有模式** —— workspace 里已有的测试用例有没有类似的（`testcases/*.py`、`pom/`）
3. **用 workaround 绕过缺口** —— `dev.driver.push_file()` 走底层、或 `subprocess` 调 adb。workaround 只写在该用例里，不改 pom/ 或框架
4. **报告缺口** —— 在回复末尾输出：什么操作、缺什么能力、当前 workaround 是什么。等用户决定要不要改框架
5. **只有用户明确要求扩展框架时**，才能去读 `ha4t/` 源码并提 PR。禁止自作主张去读源码来分析现有 API

