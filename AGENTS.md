# Repository Guidelines

## Project Overview

HA4T (Hybrid App For Testing Tool) — 跨平台 UI 自动化测试框架，支持 **Android**、**iOS**、**HarmonyOS NEXT** 和 **Web (CDP)**。基于 uiautomator2、facebook-wda、hmdriver2、PaddleOCR 和 OpenCV 构建。支持图像识别、OCR 文字识别、原生控件定位和 WebView 调试四种定位方式。

发布在 PyPI 上，包名 `ha4t`，当前版本 0.1.6。参见 `pyproject.toml`。

## Architecture & Data Flow

### 分层架构

```
┌────────────────────────────────────────────┐
│  Public API   (ha4t/__init__.py)             │
│  connect() → Device  |  include()  | Selector│
└──────────────────┬─────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  Device  (ha4t/device/)                       │
│  InteractionMixin  QueryMixin  AppMixin      │
│  FileMixin  CaptureMixin  DeviceBase (state) │
│  _resolve_selector → to_android/to_ios/etc.  │
│  _find_pos_*  → matchers                     │
└──────┬────────────────────┬──────────────────┘
       │                    │
┌──────▼──────┐  ┌─────────▼──────────────────┐
│ Drivers     │  │ Matchers (driver-agnostic)  │
│ BaseDriver  │  │ find_pos_by_image           │
│ Android     │  │ find_pos_by_ocr             │
│ iOS         │  │ click_inside_template       │
│ Harmony     │  └─────────┬──────────────────┘
└─────────────┘       ┌────┴──────┐
                 ┌────▼───┐ ┌────▼────┐
                 │ aircv   │ │ OCR     │
                 │ cv.py   │ │PaddleOCR│
                 └─────────┘ └─────────┘
┌──────────────────────────────────────────────┐
│ CDP Subsystem  (ha4t/cdp/)                     │
│ CdpServer → Page → Element (WebView via WS)   │
└──────────────────────────────────────────────┘
```

### 数据流

1. **connect(platform, ...)** → 构建 `BaseDriver` 子类 → 包装为 `Device`（Mixin 多重继承）
2. **dev.click(Selector)** → `DeviceBase._resolve_selector()` → 按平台提取原生 kwargs → 按 args[0] 类型分派到 OCR/图像/原生驱动
3. **dev.click(text="登录")** → `_resolve_selector()` 调用 `to_native(kwargs, platform)` 做跨平台字段映射 → 驱动层 `find(**kwargs)`
4. **dev.wait(text, ...)** → 轮询 `_exists()` → OCR 或驱动查找 → 超时抛 `ElementWaitTimeoutError`
5. **POM 文件读写**：`pom/<page>.py` (Python 源码) → `_parse_pom_py()` (ast + tokenize) → `ElementShape` dict → `_render_pom_py()` → 确定性 Python 源码（git-diff 稳定）

### 重要设计模式

- **Mixin 组合 Device**：`Device` 无自身逻辑，纯粹由 5 个 Mixin + DeviceBase 通过 MRO 装配
- **Selector 不可变值对象**：`__slots__` + `__setattr__` 禁止修改，所有转换方法返回新实例；`repr()` eval-safe 支持 POM 文件往返
- **screenshot_fn 依赖注入**：Matchers 接收 `screenshot_fn: Callable`（driver.screenshot 的绑定方法），与驱动完全解耦
- **惰性 OCR 加载**：`matchers/ocr.py` `_ocr = None` + `_get_ocr()` 首次调用才导入 PaddleOCR（避免慢导入）
- **@cost_time 横切装饰器**：剥离 `_` 前缀元 kwargs、记录耗时、包装 allure.step、失败时截图
- **CDP 异步隔离**：`cdp/cdp.py` 在守护线程中运行 async WebSocket 循环，公共 `Page` API 全同步

## Key Directories

| 目录 | 用途 |
|---|---|
| `ha4t/` | 核心框架包 |
| `ha4t/device/` | Device 类（Mixin 装配）— interaction, queries, apps, files, capture |
| `ha4t/drivers/` | 平台驱动 — base.py (ABC), android.py, ios.py, harmony.py |
| `ha4t/matchers/` | 找点策略 — image.py (OpenCV), ocr.py (PaddleOCR) |
| `ha4t/selector.py` | Selector 类 + 跨平台字段映射 (to_android/to_ios/to_harmony) |
| `ha4t/cdp/` | WebView CDP 自动化 — cdp.py, server.py, by.py |
| `ha4t/config.py` | DeviceConfig + GlobalConfig 单例 |
| `ha4t/exceptions.py` | 异常层次 (HA4TError → 9 个子类) |
| `ha4t/orc.py` | PaddleOCR 封装 |
| `ha4t/aircv/` | 基于 OpenCV 的图像匹配（forked from airtest） |
| `ha4t/editor/` | FastAPI + Vue 3 UI 编辑器（本地开发服务器） |
| `ha4t/editor/skills/` | AI 助手技能包（ha4t-case-writer） |
| `tests/` | 测试套件（unittest.TestCase，75 个测试） |
| `docs/` | Sphinx 文档 (sphinx_rtd_theme, zh_CN) |
| `.github/workflows/` | CI — publish (PyPI), docs-and-deploy, test (stale), welcome |

## Development Commands

```bash
# 安装依赖
uv sync

# 运行测试
uv run pytest tests/ -v

# 启动编辑器
uv run uvicorn ha4t.editor.__main__:app --port 8765
# 或
python -m ha4t.editor [-p PORT] [-w WORKSPACE]

# 构建分发包
uv build

# 发布到 PyPI
uv publish

# 代码格式化（dev 依赖）
black ha4t/
isort ha4t/

# 代码检查
flake8 ha4t/

# 构建文档
cd docs && make html
```

## Code Conventions & Common Patterns

### 命名约定

- **模块级常量/单例**：下划线全大写（`_PLATFORMS`, `_INCLUDE_STACK`, `_ocr`）
- **私有方法/助手**：`_` 前缀（`_resolve_selector`, `_to_abs`, `_find_pos_by_*`, `_get_ocr`, `_ensure_hdc`）
- **Selector 元字段**：`_` 前缀（`_parent`, `_doc`）— `@cost_time` 自动剥离
- **规范字段名**：snake_case（`resourceId`, `className`, `xpath`）
- **驱动内部句柄**：`self._d`（AndroidDriver/IOSDriver/HarmonyDriver 统一）
- **测试类**：`Test<Concept>` PascalCase；方法 `test_<what>_<condition>` snake_case
- **用户可见日志/注释/文档**：简体中文

### 跨平台字段映射核心规则

定义在 `ha4t/selector.py`，无需在其他位置重复：

| 规范字段 | Android | iOS | Harmony |
|---|---|---|---|
| text | text | label | text |
| resourceId | resourceId | name | — |
| label | description | label | text |
| className | className | className | — |
| index | index | (dropped) | — |

### 异常层次

所有异常继承自 `HA4TError(Exception)`：
- `DeviceConnectionError`（also `ConnectionError`）
- `PlatformNotSupportedError`（also `NotImplementedError`，携带 op+platform）
- `ElementNotFoundError`
- `ElementWaitTimeoutError`（also `TimeoutError`）
- `ImageMatchError`
- `OCRTimeoutError`（also `TimeoutError`）
- `AssertionFailedError`（also `AssertionError`）
- `FileTransferError`

`PlatformNotSupportedError` 使用 `op` + `platform` 属性生成消息。

### 异步模式

- **核心框架**：全同步（线程安全不保证；多设备并行用 `threading`）
- **CDP**：内部 async websocket 隔离在守护线程中，公共 API 同步
- **Editor WebSocket**：`/ws/run` endpoint 使用 FastAPI WebSocket 异步流式推送执行结果

### 状态管理

- **Editor**：Vue 3 Options-API 无构建步骤，composables 通过 `provide/inject` 共享，无 Vuex/Pinia
- **GlobalConfig**：进程级单例（`ha4t.config.global_config`）
- **EditorConfig**：单例（`__new__` 模式），持久化到 `~/.ha4t/config.json`
- **cached_devices**：进程内 dict，重启不持久

### 依赖管理

- **uv** 运行时包管理器（`uv sync` / `uv run` / `uv add`）
- **PyPI 镜像**：Tsinghua（已在 `uv.toml` 和 `pyproject.toml` 中配置）
- **Python >= 3.10**（`.python-version` 锁定 3.13）
- **无 requirements.txt**（`docs/requirements.txt` 仅用于 Sphinx）
- **可选 dev 依赖**：flake8, black, isort, twine

## Important Files

| 文件 | 角色 |
|---|---|
| `ha4t/__init__.py` | 公共 API — connect(), include(), Selector, Device |
| `ha4t/selector.py` | Selector 类 + 跨平台字段映射 |
| `ha4t/config.py` | DeviceConfig + GlobalConfig 单例 |
| `ha4t/exceptions.py` | 异常层次 |
| `ha4t/device/__init__.py` | Device 多重继承装配 |
| `ha4t/device/_base.py` | DeviceBase — 资源选择、坐标转换、OCR/图像查找 |
| `ha4t/drivers/__init__.py` | DRIVERS 工厂 dict |
| `ha4t/drivers/base.py` | BaseDriver ABC |
| `ha4t/editor/__main__.py` | FastAPI 服务器入口 + CLI 解析 |
| `ha4t/editor/routers/api.py` | 全部 34+ REST 端点 + 1 WebSocket |
| `ha4t/editor/conftest.py` | pytest 插件 — # --step-- 文件收集器 |
| `pyproject.toml` | 构建配置、依赖、入口点、pytest 选项 |
| `.python-version` | Python 版本锁定（3.13） |
| `uv.toml` | uv 源镜像配置 |

## Runtime/Tooling Preferences

- **包管理器**：**uv**（不要用 pip）。命令：`uv sync`, `uv run <cmd>`, `uv add <pkg>`
- **Python 版本**：>= 3.10（正式版本 3.13）
- **测试运行器**：**pytest**（内部类使用 unittest.TestCase，但通过 pytest 发现执行）
- **构建工具**：setuptools + wheel（传统打包，`uv build` 调用）
- **前端编辑器**：Vue 3 Options-API + Element Plus，**无构建步骤**，CDN 依赖已 vendored 在 `static/cdn/`。改完 .js 直接刷新浏览器
- **文档**：Sphinx（sphinx_rtd_theme），中文语言
- **无 CI 自动格式化**：`test.yml` workflow 已失效（目标 Python 3.7-3.9，现在需要 3.10+）
- **无 pre-commit hook**

## Testing & QA

### 测试框架

- **测试框架**：`unittest.TestCase`（全部 8 个测试文件使用，无原生 pytest 函数）
- **发现方式**：pytest 自动发现（`pyproject.toml`: `python_files = ["*.py"]`, `testpaths = []`）
- **Mock 策略**：`unittest.mock`（`@patch` / `patch.object` / `patch.dict` / `MagicMock`）
- **总测试数**：75 个（通过 `uv run pytest tests/ -v` 运行）

### 测试覆盖类型

| 层次 | 对应文件 | 说明 |
|---|---|---|
| **纯单元（无 I/O）** | test_canonical_mapping.py, test_selector.py, test_xpath_lite.py | 代数/逻辑测试，无 mock |
| **单元（mock 外部）** | test_connect.py, test_device_dispatch.py | mock 驱动层 |
| **集成（HTTP）** | test_pom_api.py, test_workspace.py | FastAPI TestClient + 真实临时文件 |
| **集成（exec）** | test_include.py | 真实 exec() Python 源码 |

### Test Suite 结构模式

```python
# 统一模式
class Test<Concept>(unittest.TestCase):
    def setUp(self): ...       # 构造对象 / patch 全局 / 创建临时目录
    def tearDown(self): ...    # 停止 patcher / 清理 / 恢复 sys.modules
    def test_<behavior>(self):
        # Arrange（安排）
        # Act（执行）
        # Assert（断言）
```

- **Helper 函数**：模块级 `_<name>()` 工厂（`_make_dev()`、`_node()`、`_write()`）
- **Base 类**：下划线前缀防止 pytest 收集（`_WsTestBase`、`_ok()` HTTP 检查助手）
- **单例重置**：`EditorConfig._instance = None` 测试间重置；`del sys.modules['pom.*']` 确保重新导入
- **参数化**：不使用 `@pytest.mark.parametrize`，用循环内联

### QA 注意事项

- **无 conftest.py** 在 `tests/` 目录（`ha4t/editor/conftest.py` 是 pytest 插件，非测试配置）
- **`test.yml` CI 已失效**（Python 3.7-3.9 矩阵，项目实际需要 3.10+）
- **`allure-pytest`** 在依赖中但测试未使用 `@allure.*` 装饰器
- 自定义 markers `smoke`/`login` 已定义但未使用
