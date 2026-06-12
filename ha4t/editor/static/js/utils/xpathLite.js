// xpathLite.js — JS 端最短稳定 xpath 生成器（前后端同算法）。
//
// 真值源：本文件。Python 镜像在 ha4t/editor/parser/xpath_lite.py，给 /parser/xpath-lite
// 端点与离线工具用；两份必须保持输出完全等价 —— 改一份一定同步另一份，并跑
// tests/test_xpath_lite.py 对齐验收。
//
// 算法五层候选（短→长，第一个唯一就返回）：
//   1. 单属性     //*[@resource-id="X"]
//   2. type+单属  //android.widget.Button[@text="X"]
//   3. 双属性     //*[@resource-id="X" and @text="Y"]
//   4. 祖先锚定   //*[@resource-id="P"]//Class[@text="X"]   ← 目标有属性 → // 后代轴
//                 //*[@resource-id="P"]/Type[i]/.../Type[j] ← 目标无属性 → / 子轴 + 每段 [idx]
//   5. 全路径兜底 //Root[1]/.../View[1]                      ← / 子轴 + 每段 [idx]
//
// 关键 trick：anchor 之下，**只要目标有属性就用 `//` 后代轴**（中间多/少 wrapper 不影响匹配，
// 反脆弱）；**目标无任何属性**时改走 anchor → 目标的 `/` 子轴绝对路径、每段强制带 sibling
// 索引 —— `//Type[idx]` 在 `//` 后是 position 过滤（跨分支歧义匹配），必须避免。
// Tier 5 同理：全段都带 [idx]（同类唯一也补 [1]），让 XPath 引擎一致定位。
//
// 时间复杂度：build O(N) 一次，query O(K) 候选数 + O(1) 哈希查找。

const PRIORITY = {
  android: ['resourceId', 'text', 'description'],
  ios:     ['id', 'name', 'label'],
  harmony: ['id', 'text', 'description'],
};

const ATTR_NAME = {
  resourceId:  'resource-id',
  text:        'text',
  description: 'content-desc',
  id:          'id',
  name:        'name',
  label:       'label',
};

// XPath 字面量转义：含 " 改用 ' 包；二者皆含则 concat() 拼接。
function escape(value) {
  if (!value.includes('"')) return `"${value}"`;
  if (!value.includes("'")) return `'${value}'`;
  const parts = value.split('"');
  return 'concat(' + parts.map(p => `"${p}"`).join(", '\"', ") + ')';
}

export class XPathLiteGenerator {
  constructor(platform, tree) {
    this.priority = PRIORITY[platform] || PRIORITY.android;
    this.nodeMap = new Map();
    this.attrIndex = {};
    for (const a of this.priority) this.attrIndex[a] = new Map();
    this._scan(tree, '');
  }

  _scan(node, parentId) {
    if (!node || typeof node !== 'object') return;
    const nid = node._id;
    if (nid) this.nodeMap.set(nid, node);
    for (const attr of this.priority) {
      const v = node[attr];
      if (v) {
        const bucket = this.attrIndex[attr].get(v) || [];
        bucket.push(node);
        this.attrIndex[attr].set(v, bucket);
      }
    }
    for (const c of node.children || []) this._scan(c, nid);
  }

  _isUnique(attr, value) {
    return (this.attrIndex[attr].get(value) || []).length === 1;
  }

  _matchesCount(predicates) {
    if (!predicates.length) return 0;
    // 先按"最稀有属性"取候选集，再 in-memory filter — 比全树扫快。
    let seed = predicates[0];
    let seedSize = (this.attrIndex[seed[0]].get(seed[1]) || []).length;
    for (let i = 1; i < predicates.length; i++) {
      const [a, v] = predicates[i];
      const sz = (this.attrIndex[a].get(v) || []).length;
      if (sz < seedSize) { seed = predicates[i]; seedSize = sz; }
    }
    const candidates = this.attrIndex[seed[0]].get(seed[1]) || [];
    return candidates.filter(n => predicates.every(([a, v]) => n[a] === v)).length;
  }

  _expr(type, predicates) {
    const head = type || '*';
    if (!predicates.length) return `//${head}`;
    const preds = predicates.map(([a, v]) => `@${ATTR_NAME[a]}=${escape(v)}`).join(' and ');
    return `//${head}[${preds}]`;
  }

  _siblingIndex(node) {
    const parent = this.nodeMap.get(node._parentId || '');
    if (!parent) return null;
    const sameType = (parent.children || []).filter(s => s._type === node._type);
    const i = sameType.indexOf(node);
    return i < 0 ? null : i + 1;
  }

  _tailForAnchor(node, ownAttrs, ownType, ancestor) {
    // 目标自己有属性 → 单属性 + // 后代轴；属性已经做了 in-tree 唯一性判定（tier 4
    // 的 anchor 已唯一，对其后代再加属性绝大多数场景命中即唯一）。短而稳。
    if (ownAttrs.length) {
      const [attr, value] = ownAttrs[0];
      const head = ownType || '*';
      return `//${head}[@${ATTR_NAME[attr]}=${escape(value)}]`;
    }
    // 目标无任何属性 —— 不能用 `//Type[idx]`，因为 `[idx]` 在 `//` 后是过滤式
    // (`position()=idx`)，会匹配多个分支里"在各自父级中是第 idx 个"的所有节点。
    // 改走 anchor → target 的 `/` 子轴绝对路径，每段必带 sibling 索引（含同类
    // 唯一也保留 [1]，避免 anchor 多次匹配后路径在不同子树中表现不一致）。
    return this._childPathFromAncestorTo(ancestor, node);
  }

  // 沿 _parentId 从 node 回溯到 ancestor（不含 ancestor），构造 /-子轴绝对路径段。
  _childPathFromAncestorTo(ancestor, node) {
    const segments = [];
    let cur = node;
    while (cur && cur !== ancestor) {
      const parent = this.nodeMap.get(cur._parentId || '');
      if (!parent) break;
      const sameType = (parent.children || []).filter(s => s._type === cur._type);
      const head = cur._type || '*';
      const idx = sameType.indexOf(cur) + 1;
      // 每段都加 index —— 即便同类仅 1 个，明确索引也比 ambig 更稳（XPath 引擎差异）。
      segments.push(`${head}[${idx > 0 ? idx : 1}]`);
      cur = parent;
    }
    if (!segments.length) return '';
    segments.reverse();
    return '/' + segments.join('/');   // 单 `/` 子轴
  }

  _buildFromRoot(node) {
    // 全路径兜底：从顶（无父）开始，向下逐段 `/Type[idx]/Type[idx]/...`。每段都强制带 index
    // —— 即使同类只有一个，明确 index 也避免 XPath 引擎在 `//Type` 起点歧义匹配。
    const segments = [];
    let cur = node;
    while (cur) {
      const parent = this.nodeMap.get(cur._parentId || '');
      if (!parent) break;
      const sameType = (parent.children || []).filter(s => s._type === cur._type);
      const head = cur._type || '*';
      const idx = Math.max(sameType.indexOf(cur) + 1, 1);
      segments.push(`${head}[${idx}]`);
      cur = parent;
    }
    segments.reverse();
    return segments.length ? '//' + segments.join('/') : '';
  }

  get(targetId) {
    const node = this.nodeMap.get(targetId);
    if (!node) return '';

    const ownAttrs = this.priority
      .filter(a => node[a])
      .map(a => [a, node[a]]);
    const ownType = node._type || '';

    // Tier 1 — 单属性唯一
    for (const [attr, value] of ownAttrs) {
      if (this._isUnique(attr, value)) {
        return this._expr(null, [[attr, value]]);
      }
    }

    // Tier 2 — type + 单属性唯一
    if (ownType) {
      for (const [attr, value] of ownAttrs) {
        const bucket = this.attrIndex[attr].get(value) || [];
        if (bucket.filter(n => n._type === ownType).length === 1) {
          return this._expr(ownType, [[attr, value]]);
        }
      }
    }

    // Tier 3 — 双属性组合唯一
    for (let i = 0; i < ownAttrs.length; i++) {
      for (let j = i + 1; j < ownAttrs.length; j++) {
        const preds = [ownAttrs[i], ownAttrs[j]];
        if (this._matchesCount(preds) === 1) {
          return this._expr(null, preds);
        }
      }
    }

    // Tier 4 — 锚定最近"有唯一属性"的祖先 + // 后代轴拼到目标（反脆弱）
    let ancestor = this.nodeMap.get(node._parentId || '');
    while (ancestor) {
      const ancAttrs = this.priority.filter(a => ancestor[a]).map(a => [a, ancestor[a]]);
      for (const [attr, value] of ancAttrs) {
        if (this._isUnique(attr, value)) {
          return this._expr(null, [[attr, value]]) + this._tailForAnchor(node, ownAttrs, ownType, ancestor);
        }
      }
      ancestor = this.nodeMap.get(ancestor._parentId || '');
    }

    // Tier 5 — 全路径兜底
    return this._buildFromRoot(node);
  }
}

// 便捷函数：buildXPath(platform, tree, nodeId) — 一次性使用，不复用 generator。
export function buildXPath(platform, tree, nodeId) {
  return new XPathLiteGenerator(platform, tree).get(nodeId);
}
