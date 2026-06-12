# -*- coding: utf-8 -*-

"""XPathLite — 最短稳定 xpath 生成器。

算法目标：在保证**唯一匹配**的前提下输出最短表达式，并尽量避开脆弱的父子路径。

策略（按短→长枚举候选，第一个唯一的就返回）：
  1. 单属性    : //*[@resource-id="X"]
  2. type+单属 : //android.widget.Button[@text="X"]
  3. 双属性    : //*[@resource-id="X" and @text="Y"]
  4. 祖先锚定  : //*[@resource-id="P"]//Class[@text="X"]      ← // 后代轴
  5. 全路径兜 : //Root/Layout[1]/.../View[3]                 ← / 子轴（最后才用）

关键 trick：层级拼接用 `//` 而不是 `/`，中间多/少一层 wrapper view 都不影响匹配，
这是避免"脆弱路径"的核心 —— 旧实现一律用 `/` 子轴，UI 改一行 padding wrapper
就整条失效。

时间复杂度：O(N) 建索引（仅 __init__ 一次），单次 get_xpathLite 查询 O(K)
（K=候选属性数，恒定小常数）+ 索引 O(1) 哈希查找；实际 ~1ms 量级。
"""

from typing import Dict, List, Optional


# 平台 → 候选属性优先级（短/稳）
_PRIORITY = {
    'android': ['resourceId', 'text', 'description'],
    'ios':     ['id', 'name', 'label'],
    'harmony': ['id', 'text', 'description'],
}

# 属性字段名 → xpath @属性名（参照 uiautomator2 / WDA / hdc 暴露的实际 attr）
_ATTR_NAME = {
    'resourceId':  'resource-id',
    'text':        'text',
    'description': 'content-desc',
    'id':          'id',
    'name':        'name',
    'label':       'label',
}


def _xpath_escape(value: str) -> str:
    """XPath 字面量转义 — 含 " 时改用 ' 包，二者都含时用 concat()。"""
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    parts = value.split('"')
    return 'concat(' + ', \'"\', '.join(f'"{p}"' for p in parts) + ')'


class XPathLiteGenerator:
    def __init__(self, platform: str, treedata: Dict):
        self.platform = platform
        self.tree = treedata
        self._priority: List[str] = _PRIORITY.get(platform, _PRIORITY['android'])
        # node_id → node
        self._node_map: Dict[str, Dict] = {}
        # attr → {value → [node, ...]}
        self._attr_index: Dict[str, Dict[str, List[Dict]]] = {a: {} for a in self._priority}
        self._scan(treedata, '')

    # ── 索引构建 ──────────────────────────────────────────────────────
    def _scan(self, node, parent_id: str):
        if not isinstance(node, dict):
            return
        nid = node.get('_id')
        if nid:
            self._node_map[nid] = node
        for attr in self._priority:
            v = node.get(attr)
            if v:  # 空字符串/None 跳过
                self._attr_index[attr].setdefault(v, []).append(node)
        for child in node.get('children', []) or []:
            self._scan(child, nid)

    # ── 唯一性辅助 ────────────────────────────────────────────────────
    def _is_unique(self, attr: str, value: str) -> bool:
        return len(self._attr_index.get(attr, {}).get(value, [])) == 1

    def _matches_count(self, predicates: List) -> int:
        """predicates = [(attr, value), ...]；返回同时满足所有谓词的节点数。
        先用最稀有那个属性命中候选集，再 in-memory filter — 比全树扫快。"""
        if not predicates:
            return 0
        seed_attr, seed_val = min(
            predicates,
            key=lambda p: len(self._attr_index.get(p[0], {}).get(p[1], [])),
        )
        candidates = self._attr_index.get(seed_attr, {}).get(seed_val, [])
        cnt = 0
        for n in candidates:
            if all(n.get(a) == v for a, v in predicates):
                cnt += 1
        return cnt

    # ── 表达式构造 ────────────────────────────────────────────────────
    def _expr(self, _type: Optional[str], predicates: List) -> str:
        """构造 //{type}[@a="x" and @b="y" ...]；type 缺省用 *。"""
        head = _type if _type else '*'
        if not predicates:
            return f'//{head}'
        preds = ' and '.join(f'@{_ATTR_NAME[a]}={_xpath_escape(v)}' for a, v in predicates)
        return f'//{head}[{preds}]'

    # ── 主入口 ────────────────────────────────────────────────────────
    def get_xpathLite(self, target_id: str) -> str:
        node = self._node_map.get(target_id)
        if not node:
            return ''

        own_attrs = [(a, node[a]) for a in self._priority if node.get(a)]
        own_type = node.get('_type') or ''

        # Tier 1 — 单属性唯一：//*[@x="v"]
        for attr, value in own_attrs:
            if self._is_unique(attr, value):
                return self._expr(None, [(attr, value)])

        # Tier 2 — type + 单属性唯一：//Class[@x="v"]
        if own_type:
            for attr, value in own_attrs:
                bucket = self._attr_index[attr].get(value, [])
                if sum(1 for n in bucket if n.get('_type') == own_type) == 1:
                    return self._expr(own_type, [(attr, value)])

        # Tier 3 — 双属性组合唯一：//*[@a="v1" and @b="v2"]
        for i in range(len(own_attrs)):
            for j in range(i + 1, len(own_attrs)):
                preds = [own_attrs[i], own_attrs[j]]
                if self._matches_count(preds) == 1:
                    return self._expr(None, preds)

        # Tier 4 — 锚定到"有唯一属性"的最近祖先 + 用 `//` 后代轴拼到目标。
        # 这是关键的反脆弱手段：中间多几层 wrapper view 也不影响匹配。
        ancestor = self._node_map.get(node.get('_parentId') or '')
        while ancestor:
            anc_attrs = [(a, ancestor[a]) for a in self._priority if ancestor.get(a)]
            for attr, value in anc_attrs:
                if not self._is_unique(attr, value):
                    continue
                # 祖先锚定后，目标自己用最强属性 / type 表达即可（不必再保证全局唯一）
                tail_expr = self._tail_for_anchor(node, own_attrs, own_type)
                return self._expr(None, [(attr, value)]) + tail_expr
            ancestor = self._node_map.get(ancestor.get('_parentId') or '')

        # Tier 5 — 兜底：从根开始的 / 子轴绝对路径（脆弱，仅在前 4 层都拿不到时使用）
        return self._build_from_root(node)

    def _tail_for_anchor(self, node: Dict, own_attrs: List, own_type: str) -> str:
        """祖先已经唯一后，自己用属性 + // 拼接 — 后代轴对中间层数不敏感。"""
        if own_attrs:
            # type + 第一个属性就够稳了，不再叠多个谓词（短优先）
            attr, value = own_attrs[0]
            head = own_type if own_type else '*'
            return f'//{head}[@{_ATTR_NAME[attr]}={_xpath_escape(value)}]'
        # 完全无属性的节点：fallback 到 type + 同类兄弟 index
        idx = self._sibling_index(node)
        head = own_type or '*'
        if idx is None:
            return f'//{head}'
        return f'//{head}[{idx}]'

    def _sibling_index(self, node: Dict) -> Optional[int]:
        """在 parent.children 中按 _type 同类排第几（1-based）；无父返回 None。"""
        parent = self._node_map.get(node.get('_parentId') or '')
        if not parent:
            return None
        same_type = [s for s in parent.get('children', []) if s.get('_type') == node.get('_type')]
        try:
            return same_type.index(node) + 1
        except ValueError:
            return None

    def _build_from_root(self, node: Dict) -> str:
        """全路径兜底 — 同类兄弟唯一时省 [index]。"""
        segments = []
        cur = node
        while cur is not None:
            parent = self._node_map.get(cur.get('_parentId') or '')
            if parent is None:
                break
            same_type = [s for s in parent.get('children', []) if s.get('_type') == cur.get('_type')]
            head = cur.get('_type') or '*'
            if len(same_type) <= 1:
                segments.append(head)
            else:
                segments.append(f'{head}[{same_type.index(cur) + 1}]')
            cur = parent
        segments.reverse()
        return '//' + '/'.join(segments) if segments else ''
