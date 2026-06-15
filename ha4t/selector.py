# -*- coding: utf-8 -*-
"""
Selector —— 跨平台元素定位器（不可变值对象）。

为什么需要这个类
-----------------
POM 元素同一个名字（"登录按钮"）在不同平台上 native 字段不同：
- Android (uiautomator2)：text / resourceId / className / description / ...
- iOS (wda)：label / name / className / ...
- Harmony (hmdriver2)：保留扩展位

直接把扁平 `{text: "登录"}` 字典塞给所有 driver 会在 iOS 报错（WDA 不认 text）。
让 POM 文件按平台分桶存，调用时 `Device` 按自己的 `platform` 取对应分桶 → 调用代
码零变化（`dev.click(ELEMENTS["登录按钮"])`），跨平台自动适配。

数据模型
-----------------
Selector 三类字段（构造时严格分类）：

1. **平台分桶**（dict）—— `android` / `ios` / `harmony`：各平台的 native kwargs
2. **跨平台属性**：
   - `image: str` —— 图像模板（跨平台同一张图）；**与平台分桶互斥**
3. **meta**（`_` 前缀）：
   - `_parent: str` —— 父元素名（同 page 内）
   - `_doc: str`    —— 元素自由文本说明
   未来可加 `_owner` / `_tags` 等，统一 `_` 前缀，driver 入口剥除

构造时未知字段（既不是平台名、image、也不是 `_` 前缀）→ 拒绝并提示"是否漏了
android={...} 包装"，避免静默丢字段。

不可变性
-----------------
Selector 实例所有变换方法（`format` / `with_platform` / `override` 等）都返回**新对象**，
原对象不动。这样多 dev 实例共享同一个 ELEMENTS 表、跨平台并行测试都安全。
`repr(s)` 输出可执行 Python 表达式（`eval(repr(s)) == s`），POM 文件后端直接落盘。
"""
from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, Optional

__all__ = ["Selector", "SelectorNotAvailableError", "to_native"]


# 平台名集合 —— 集中一处，未来加 web 等只改这里
_PLATFORMS: FrozenSet[str] = frozenset({"android", "ios", "harmony"})


class SelectorNotAvailableError(LookupError):
    """当前 Selector 在指定平台没有可用定位信息（既没采集 native selector，也没 image）。"""


# ── Canonical → native 映射 ─────────────────────────────────────────
#
# 用户也可以走「raw kwargs 路径」：`dev.click(text="登录")`。此时 text 是 canonical
# 字段名，需要按当前平台翻译成 native kwargs。
#
# 映射策略：**保守**。只翻译几个最高频字段；未知字段透传（让 driver 自己报"未知
# kwarg" 比悄悄改字段更安全 —— 静默改字段会让用户调试时摸不着头脑）。
#
# canonical 字段（小写驼峰）：
#   text         可见文本内容
#   resourceId   平台内的稳定 id（Android resourceId / iOS accessibilityIdentifier）
#   label        可读标签（Android contentDescription / iOS label）
#   description  辅助说明（同上，跟 label 重叠时取首选 label）
#   className    控件类型
#   xpath        XPath 表达式
#   index        同类兄弟内位置（0-based）

_CANONICAL_FIELDS = {"text", "resourceId", "label", "description", "className", "xpath", "index"}


def to_android(canonical: Dict[str, Any]) -> Dict[str, Any]:
    """canonical → uiautomator2 接受的 kwargs。

    映射规则（仅高频字段，未知字段透传）：
      text         → text                  （u2 直接接受）
      resourceId   → resourceId            （u2 直接接受）
      label        → description           （Android 没 label 概念，用 content-desc 兜）
      description  → description
      className    → className
      xpath        → xpath
      index        → index
    """
    out: Dict[str, Any] = {}
    for k, v in canonical.items():
        if v is None or v == "":
            continue
        if k == "label":
            out.setdefault("description", v)
        elif k in _CANONICAL_FIELDS:
            out[k] = v
        else:
            out[k] = v  # 透传（保守）
    return out


def to_ios(canonical: Dict[str, Any]) -> Dict[str, Any]:
    """canonical → WDA 接受的 kwargs。

    映射规则：
      text         → label                 （WDA 用 label 表示可见文本）
      label        → label
      description  → label                 （description 偏 a11y 含义，靠 label 兜）
      resourceId   → name                  （iOS accessibilityIdentifier 对应 name）
      className    → className
      xpath        → xpath
      index        不映射（iOS 索引语义跟 Android 差异大，强制用户写 xpath 表达）
    """
    out: Dict[str, Any] = {}
    for k, v in canonical.items():
        if v is None or v == "":
            continue
        if k == "text":
            out.setdefault("label", v)
        elif k == "description":
            out.setdefault("label", v)
        elif k == "resourceId":
            out.setdefault("name", v)
        elif k == "index":
            continue   # 不映射，避免误导
        elif k in _CANONICAL_FIELDS:
            out[k] = v
        else:
            out[k] = v
    return out


def to_harmony(canonical: Dict[str, Any]) -> Dict[str, Any]:
    """canonical → hmdriver2 接受的 kwargs。

    Harmony 元素查找 SDK 支持仍在演进，目前只透传 text / xpath；其它字段忽略。
    需要更多字段时按需扩展。
    """
    out: Dict[str, Any] = {}
    for k, v in canonical.items():
        if v is None or v == "":
            continue
        if k in ("text", "xpath"):
            out[k] = v
        # 其它字段在 Harmony 上语义不明，先丢弃避免误用
    return out


_PLATFORM_TO_NATIVE_FN = {
    "android": to_android,
    "ios":     to_ios,
    "harmony": to_harmony,
}


def to_native(canonical: Dict[str, Any], platform: str) -> Dict[str, Any]:
    """canonical kwargs → 指定平台的 native kwargs。未识别平台直接透传。"""
    fn = _PLATFORM_TO_NATIVE_FN.get(platform)
    return fn(canonical) if fn else dict(canonical)


# ── Selector 类 ─────────────────────────────────────────────────────


class Selector:
    """跨平台元素定位器（不可变值对象）。

    示例：

        # 平台 native selector 分别采集
        LOGIN_BTN = Selector(
            android={"resourceId": "com.x:id/login", "text": "登录"},
            ios={"label": "Login"},
        )

        # 跨平台共享图像
        LOGIN_ICON = Selector(image="login_icon.png")

        # 带 meta（_parent 父子关系、_doc 给 AI 看的注释）
        BACK_BTN = Selector(
            _parent="顶部导航",
            _doc="点击退回上一页",
            android={"text": "返回"},
            ios={"label": "Back"},
        )

    解析顺序（`for_platform(p)`）：
      1. 该平台分桶里有 native selector → 返回之
      2. 平台分桶为空 → 落回 `image`（如有），返回 `{"image": ...}`
      3. 都没 → raise SelectorNotAvailableError
    """

    # 构造时已校验过的字段集合
    __slots__ = ("_platforms", "_image", "_meta")

    def __init__(self, *, image: Optional[str] = None, **kwargs: Any) -> None:
        platforms: Dict[str, Dict[str, Any]] = {}
        meta: Dict[str, Any] = {}

        for key, value in kwargs.items():
            if key in _PLATFORMS:
                if not isinstance(value, dict):
                    raise TypeError(f"Selector 平台分桶必须是 dict，got {type(value).__name__}: {key}={value!r}")
                platforms[key] = dict(value)  # 浅 copy 防外部修改
            elif key.startswith("_"):
                meta[key] = value
            else:
                # 未知字段 —— 大概率是用户漏了 android={...} 包装。明确报错而非静默接受。
                raise TypeError(
                    f"Selector 未知字段 {key!r}: "
                    f"平台 native 字段必须放在 android={{...}} / ios={{...}} / harmony={{...}} 里；"
                    f"meta 字段需 _ 前缀；image 放最外层；其它字段不允许"
                )

        # image 与平台分桶互斥（产品决策：图像元素就是图像元素，不混杂 native）
        if image is not None:
            if not isinstance(image, str) or not image:
                raise TypeError(f"Selector image 必须是非空字符串，got {image!r}")
            if platforms:
                raise TypeError("Selector image 与平台分桶互斥 —— 图像元素不要同时写 android/ios/harmony")

        # 至少要有一个数据载体（image 或任一平台分桶），否则空 Selector 无意义
        if image is None and not platforms:
            raise ValueError("Selector 至少需要 image= 或 android/ios/harmony 任一字段")

        # 写入 __slots__，之后通过 __setattr__ 拒绝修改实现不可变
        object.__setattr__(self, "_platforms", platforms)
        object.__setattr__(self, "_image", image)
        object.__setattr__(self, "_meta", meta)

    # ── 不可变：阻止外部修改 __slots__ 属性 ─────────────────────────
    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"Selector 是不可变对象，不能修改 {name!r}；请用 .with_platform()/.format() 等返回新实例的方法")

    # ── 访问器 ─────────────────────────────────────────────────────
    @property
    def parent(self) -> Optional[str]:
        """父元素名；无父返回 None。"""
        return self._meta.get("_parent") or None

    @property
    def doc(self) -> Optional[str]:
        """元素自由文本说明；无返回 None。"""
        return self._meta.get("_doc") or None

    @property
    def image(self) -> Optional[str]:
        """图像模板文件名；非图像元素返回 None。"""
        return self._image

    def platforms(self) -> FrozenSet[str]:
        """有 native selector 的平台名集合（不含 image 元素）。"""
        return frozenset(self._platforms.keys())

    # ── 解析为当前平台 native kwargs ─────────────────────────────────
    def for_platform(self, platform: str) -> Dict[str, Any]:
        """返回该平台的 native kwargs，可以 ** 解包传给 driver.find。

        优先级：平台分桶 > image fallback > raise。
        meta 字段（`_parent`/`_doc`）从来不在输出里。
        """
        if platform in self._platforms and self._platforms[platform]:
            return dict(self._platforms[platform])
        if self._image:
            return {"image": self._image}
        raise SelectorNotAvailableError(
            f"Selector 在 {platform!r} 上无定位信息；"
            f"已采集平台：{sorted(self._platforms)} / image: {self._image!r}"
        )

    def supports(self, platform: str) -> bool:
        """该平台是否有可用定位（含 image fallback）。"""
        return bool(self._platforms.get(platform)) or bool(self._image)

    # ── 不可变变换 ─────────────────────────────────────────────────
    def with_platform(self, platform: str, **kwargs: Any) -> "Selector":
        """返回新 Selector，覆盖某平台分桶的字段（不动其它平台 / meta / image）。"""
        if platform not in _PLATFORMS:
            raise ValueError(f"未知平台 {platform!r}；允许 {sorted(_PLATFORMS)}")
        new_kwargs: Dict[str, Any] = {p: dict(d) for p, d in self._platforms.items()}
        new_kwargs[platform] = dict(kwargs)
        new_kwargs.update(self._meta)
        return Selector(image=self._image, **new_kwargs)

    def without_platform(self, platform: str) -> "Selector":
        """返回新 Selector，移除某平台分桶（清除当前平台 selector 用）。"""
        new_kwargs: Dict[str, Any] = {p: dict(d) for p, d in self._platforms.items() if p != platform}
        new_kwargs.update(self._meta)
        if self._image is None and not new_kwargs:
            raise ValueError(f"移除 {platform!r} 后 Selector 没有任何定位字段了；请用 removeElement 直接删整个元素")
        return Selector(image=self._image, **new_kwargs)

    def format(self, **kwargs: Any) -> "Selector":
        """按平台分桶逐字段 `str.format(**kwargs)`，返回新 Selector。

        用于参数化元素（列表项第 N 个、模板文本含变量等）：

            "商品项": Selector(
                android={"xpath": "//*[@resource-id='list']/View[{index}]"},
                ios={"xpath": "//XCUIElementTypeCell[{index}]"},
            )

            dev.click(ELEMENTS["商品项"].format(index=2))

        非字符串字段（index、image）原样保留。
        """
        def _fmt_dict(d: Dict[str, Any]) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            for k, v in d.items():
                if isinstance(v, str) and "{" in v:
                    try:
                        out[k] = v.format(**kwargs)
                    except KeyError as e:
                        raise KeyError(f"Selector.format: 字段 {k}={v!r} 缺占位 {e}")
                else:
                    out[k] = v
            return out
        new_kwargs: Dict[str, Any] = {p: _fmt_dict(d) for p, d in self._platforms.items()}
        new_kwargs.update(self._meta)
        # image 是文件名通常不带 {} ；如果用户真在 image 路径里写了 {} 也支持
        new_image = self._image
        if new_image and "{" in new_image:
            try:
                new_image = new_image.format(**kwargs)
            except KeyError as e:
                raise KeyError(f"Selector.format: image={new_image!r} 缺占位 {e}")
        return Selector(image=new_image, **new_kwargs)

    # ── 工厂糖 ─────────────────────────────────────────────────────
    @classmethod
    def everywhere(cls, **kwargs: Any) -> "Selector":
        """所有平台用同一份 native kwargs 的工厂方法。

            "取消": Selector.everywhere(text="取消")
            # 等价 Selector(android={"text":"取消"}, ios={"text":"取消"}, harmony={"text":"取消"})

        注意：本工厂走的是 **canonical 同名** 假设——`text="取消"` 在所有平台都用 `text`
        字段。这适用于真正所有平台都同样写法的场景；如果各平台字段不同，仍要写完整的
        分桶 Selector(android=..., ios=...)。
        """
        return cls(**{p: dict(kwargs) for p in _PLATFORMS})

    # ── 比较 / hash / 表达 ─────────────────────────────────────────
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Selector):
            return NotImplemented
        return (
            self._platforms == other._platforms
            and self._image == other._image
            and self._meta == other._meta
        )

    def __hash__(self) -> int:
        # Selector 不可变，可哈希；用 repr 当 key 简单且稳
        return hash(repr(self))

    def __repr__(self) -> str:
        """可逆 repr：eval(repr(s)) == s。POM 文件 round-trip 直接用这个落盘。"""
        parts = []
        # meta 在前（_parent/_doc 紧贴元素名读起来更顺）
        for k in sorted(self._meta):
            parts.append(f"{k}={self._meta[k]!r}")
        if self._image is not None:
            parts.append(f"image={self._image!r}")
        # 平台按固定顺序输出，确保 round-trip 稳定
        for p in ("android", "ios", "harmony"):
            if p in self._platforms:
                parts.append(f"{p}={self._platforms[p]!r}")
        return f"Selector({', '.join(parts)})"
