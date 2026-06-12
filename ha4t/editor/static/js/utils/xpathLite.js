// xpathLite.js — JS 端最短稳定 xpath 生成器（与后端 ha4t/editor/parser/xpath_lite.py 等价）。
//
// 算法五层候选（短→长，第一个唯一就返回）：
//   1. 单属性     //*[@resource-id="X"]
//   2. type+单属  //android.widget.Button[@text="X"]
//   3. 双属性     //*[@resource-id="X" and @text="Y"]
//   4. 祖先锚定   //*[@resource-id="P"]//Class[@text="X"]   ← // 后代轴，跳过中间任意 wrapper
//   5. 全路径兜底 //Layout/.../View[3]                       ← / 子轴
//
// 关键 trick：层级拼接用 `//` 后代轴而不是 `/` 子轴，UI 增删 wrapper view 不影响匹配。
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

  _tailForAnchor(node, ownAttrs, ownType) {
    if (ownAttrs.length) {
      const [attr, value] = ownAttrs[0];
      const head = ownType || '*';
      return `//${head}[@${ATTR_NAME[attr]}=${escape(value)}]`;
    }
    const idx = this._siblingIndex(node);
    const head = ownType || '*';
    return idx == null ? `//${head}` : `//${head}[${idx}]`;
  }

  _buildFromRoot(node) {
    const segments = [];
    let cur = node;
    while (cur) {
      const parent = this.nodeMap.get(cur._parentId || '');
      if (!parent) break;
      const sameType = (parent.children || []).filter(s => s._type === cur._type);
      const head = cur._type || '*';
      segments.push(sameType.length <= 1 ? head : `${head}[${sameType.indexOf(cur) + 1}]`);
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
          return this._expr(null, [[attr, value]]) + this._tailForAnchor(node, ownAttrs, ownType);
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
