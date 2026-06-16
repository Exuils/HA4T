# HA4T API 参考

自动从源码 docstring 生成。覆盖 Device 全部接口、工具函数与异常定义。

## 目录

- [交互操作](#交互操作)
- [查询与断言](#查询与断言)
- [应用管理](#应用管理)
- [文件操作](#文件操作)
- [工具函数](#工具函数)
- [Selector 类](#Selector 类)
- [异常定义](#异常定义)

<a name="交互操作"></a>
## 交互操作

来源：`InteractionMixin` @ `ha4t/device/interaction.py`

### `click(*args, **kwargs)`

→ `None`

点击操作，支持多种定位方式：

- ``click(SelectorObj)``         跨平台 Selector 对象（POM 写法）
- ``click((x, y))``              绝对或比例坐标
- ``click("文字")``              OCR 定位
- ``click(Template(...))``       图像匹配（``filepath`` 属性）
- ``click(text="xxx")``          canonical kwargs → 当前平台自动翻译
- ``click(image="img.png")``     图像路径（支持 ``grid``/``splits`` 网格拆分）

### `double_click(*args, **kwargs)`

→ `None`

双击元素。

### `long_press(*args, **kwargs)`

→ `None`

长按元素。

### `swipe(p1, p2, duration, steps=None)`

→ `None`

滑动，坐标支持绝对像素或 0-1 比例。

### `swipe_up(duration: float, steps=0.2)`

→ `None`

### `swipe_down(duration: float, steps=0.2)`

→ `None`

### `swipe_left(duration: float, steps=0.1)`

→ `None`

### `swipe_right(duration: float, steps=0.1)`

→ `None`

### `popup_apps()`

→ `None`

呼出多任务界面。

### `drag(*args, **kwargs)`

→ `None`

拖拽元素（偏移 dx/dy 像素）。支持 Selector 对象 / canonical kwargs。

### `key(key_name: str)`

→ `None`

### `home()`

→ `None`

---

<a name="查询与断言"></a>
## 查询与断言

来源：`QueryMixin` @ `ha4t/device/queries.py`

### `exists(*args, **kwargs)`

→ `bool`

### `wait(*args, **kwargs)`

等待元素出现/消失。timeout 默认读取 global_config.find_timeout。

### `get_page_text()`

→ `str`

OCR 识别页面全部文字并拼接返回。

### `get_text(*args, **kwargs)`

→ `str`

获取元素的文本内容。

### `assert_element(*args, **kwargs)`

→ `bool`

元素断言。operator: eq/ne/contains/not_contains/empty/not_empty/regex/exists_true/exists_false。

---

<a name="应用管理"></a>
## 应用管理

来源：`AppMixin` @ `ha4t/device/apps.py`

### `start_app(app_name: Optional[str], activity=None)`

→ `None`

启动应用。``app_name`` / ``activity`` 为 None 时从 config 取默认值。

### `stop_app(app_name: Optional[str])`

→ `None`

### `restart_app(app_name: Optional[str], activity=None)`

→ `None`

### `get_current_app()`

→ `str`

### `clear_app(app_name: Optional[str])`

→ `None`

清除应用数据（仅 Android）。

---

<a name="文件操作"></a>
## 文件操作

来源：`FileMixin` @ `ha4t/device/files.py`

### `pull_file(src_path: Union[List[str], str], filename: str)`

→ `None`

从设备拉取文件到本地。

### `upload_files(src_path: str, remote_dir: str)`

→ `None`

上传文件或文件夹到设备。

| 参数 | 类型 | 说明 |
|------|------|------|
| `src_path` | `` | 本地文件或文件夹路径 |
| `remote_dir` | `` | 设备目标子目录（相对 /sdcard/），如 "Download" → /sdcard/Download/。 |
| 默认 "" 即 /sdcard/ 根目录。 | | |

### `delete_file(file_path: Union[List[str], str])`

→ `None`

删除设备上的文件。

---

<a name="工具函数"></a>
## 工具函数

来源：`ha4t/__init__.py`

### `connect(platform='android', device_serial=None, android_package_name=None, android_activity_name=None, **driver_kwargs)`

→ `Device`

连接设备，返回 ``Device``。

:param platform: 平台标识 ``android`` / ``ios`` / ``harmony``
:param device_serial: 设备序列号；为 ``None`` 时取系统第一个可用设备
:param android_package_name: Android 包名（写进 ``DeviceConfig``，``start_app`` 默认值）
:param android_activity_name: Android 启动 Activity（同上）
:param driver_kwargs: 透传给底层 driver.connect() 的额外关键字

### `include(path: str)`

→ `None`

在当前进程内执行另一个用例 .py 文件，复用其步骤。

被引用文件中的 ``import os / os.environ / from ha4t import ... /
from time import sleep / dev = connect(...)`` 这些样板代码会被剥离，
其余源码在调用者的全局命名空间中 ``exec``——这样被引用文件可以直接
使用调用者已经建立的 ``dev`` 连接 / ``sleep`` 等符号，无需重新连接设备。

路径解析顺序：调用者所在目录 → 调用者所在目录下的 testcases/（编辑器工作区模式）→
当前工作目录下的 testcases/ → 当前工作目录 → 字面路径。
通过 ``_INCLUDE_STACK`` 防止循环引用。

---

<a name="Selector 类"></a>
## Selector 类

来源：`Selector` @ `ha4t/selector.py`

### `parent()`

→ `Optional[str]`

父元素名；无父返回 None。

### `doc()`

→ `Optional[str]`

元素自由文本说明；无返回 None。

### `image()`

→ `Optional[str]`

图像模板文件名；非图像元素返回 None。

### `platforms()`

→ `FrozenSet[str]`

有 native selector 的平台名集合（不含 image 元素）。

### `for_platform(platform: str)`

→ `Dict[str, Any]`

返回该平台的 native kwargs，可以 ** 解包传给 driver.find。

优先级：平台分桶 > image fallback > raise。
meta 字段（`_parent`/`_doc`）从来不在输出里。

### `supports(platform: str)`

→ `bool`

该平台是否有可用定位（含 image fallback）。

### `with_platform(platform: str, **kwargs: Any)`

→ `'Selector'`

返回新 Selector，覆盖某平台分桶的字段（不动其它平台 / meta / image）。

### `without_platform(platform: str)`

→ `'Selector'`

返回新 Selector，移除某平台分桶（清除当前平台 selector 用）。

### `format(**kwargs: Any)`

→ `'Selector'`

按平台分桶逐字段 `str.format(**kwargs)`，返回新 Selector。

用于参数化元素（列表项第 N 个、模板文本含变量等）：

"商品项": Selector(
        android={"xpath": "//*[@resource-id='list']/View[{index}]"},
        ios={"xpath": "//XCUIElementTypeCell[{index}]"},
    )

dev.click(ELEMENTS["商品项"].format(index=2))

非字符串字段（index、image）原样保留。

### `everywhere(cls, **kwargs: Any)`

→ `'Selector'`

所有平台用同一份 native kwargs 的工厂方法。

"取消": Selector.everywhere(text="取消")
    # 等价 Selector(android={"text":"取消"}, ios={"text":"取消"}, harmony={"text":"取消"})

注意：本工厂走的是 **canonical 同名** 假设——`text="取消"` 在所有平台都用 `text`
字段。这适用于真正所有平台都同样写法的场景；如果各平台字段不同，仍要写完整的
分桶 Selector(android=..., ios=...)。

---
