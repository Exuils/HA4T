# HA4T 测试工作区 — AI 行为规则

语言：中文

## 核心约束

1. **禁止新建、修改或删除 `pom/` 下任何文件**（包括 `_meta.py`）。POM 只由编辑器采集生成，你不知道真实页面上 resourceId / text / xpath 的值
2. **只能引用 `ELEMENTS` 中已存在的元素**，唯一可调的是 `index` 参数：`dev.click(ELEMENTS["商品项"].format(index=2))`
3. **禁止猜测 locator 值**。缺失元素只能在回复末尾输出缺失清单并引导采集，不得用临时定位绕过
4. 临时定位有限允许（用户明确说的一段文字）：`dev.click(Selector(android={"text": "确定"}))` 或 `dev.click(text="确定")`——但**不是常规手段**

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
- 元素一律 `dev.click(Page.ELEMENTS["name"])`，不带 `**`
- 全局变量 → `VARS["key"]`；用例特有 → `LOCAL_VARS["key"]`
- 复用用例 → `include("other_case.py")`

可用 Device API 见 `ha4t/__init__.py` 模块文档或 `from ha4t import Device` 类型签名。

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
