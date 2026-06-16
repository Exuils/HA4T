import {
  pomListPages, pomGetPage, pomSavePage, pomDeletePage,
  pomGetMeta, pomSaveMeta,
  getImage, saveImage,
} from '../api.js';
import { selectorFromNode } from './useTask.js';
import { saveToLocalStorage, getFromLocalStorage } from '../utils.js';

const { ref, computed } = Vue;

// usePom — POM (Page Object Model) capture state + persistence.
// Pages are stored as one .py per page under <tasks_dir>/pom/.
// Global meta (APP package, cross-page VARS) lives in pom/_meta.py.
export function usePom() {
  // Page index (lightweight — desc/triggers/element_count only)
  const pages              = ref([]);
  // Currently selected page
  const currentFile        = ref(getFromLocalStorage('currentPomFile', ''));
  const page               = ref('');
  const desc               = ref('');
  const triggers           = ref('');
  // 元素表 —— 现在是 ElementShape：{ name: { platforms:{android:{},ios:{},harmony:{}}, image, _parent, _doc } }
  // 前端按 currentPlatform 渲染显示，AI 读 pom/<page>.py 看到的是 Selector(...) 字面量。
  const elements           = ref({});
  // 当前显示用平台：默认从 device.platform localStorage 跟随，未连时退到 'android'。
  // 切换不改 elements 数据，只换显示。POM tab 顶上有 platform tab 让用户独立切换
  // 跨平台元素采集（一边连着 Android 设备但也想看 / 补 iOS 分桶）。
  const currentPlatform    = ref(getFromLocalStorage('platform', 'android'));
  // 兼容入口：UI 多个地方仍用扁平 docs / parents map（树渲染 / KvRow 标签等）
  // 这两个 ref 跟 elements ShapeData 派生同步 —— 修改时都从 elements 派生。
  const elementDocs        = ref({});
  const elementParents     = ref({});
  const metaVars           = ref({});
  // Capture / edit state
  const captureMode        = ref(false);
  const nameDialogVisible  = ref(false);
  const pendingSelector    = ref(null);
  const pendingName        = ref('');
  const pendingDoc         = ref('');
  const pendingParent      = ref('');
  // 「补全模式」：用户在某条 *已存在* 的元素行点了「采集」按钮 → 下一次画布选/框
  // 不弹命名弹框，直接替换该元素当前平台的 selector。null 表示非补全模式。
  const pendingFillName    = ref('');
  const imageCache         = ref({});

  // 取当前平台（或指定平台）的 native kwargs；不存在返回 null。
  // image 元素直接返回 {image: '...'}（image 跨平台共享）。
  function selectorView(name, platform) {
    const el = elements.value[name];
    if (!el) return null;
    if (el.image) return { image: el.image };
    const p = platform || currentPlatform.value;
    return (el.platforms && el.platforms[p]) || null;
  }

  function hasSelectorOn(name, platform) {
    const el = elements.value[name];
    if (!el) return false;
    if (el.image) return true;
    const p = platform || currentPlatform.value;
    return !!(el.platforms && el.platforms[p] && Object.keys(el.platforms[p]).length);
  }

  // 把 ElementShape map 同步派生出独立 docs / parents map（兼容老 UI 用法）。
  function _syncDerivedMaps() {
    const d = {}, p = {};
    for (const [k, el] of Object.entries(elements.value)) {
      if (el._doc) d[k] = el._doc;
      if (el._parent) p[k] = el._parent;
    }
    elementDocs.value = d;
    elementParents.value = p;
  }
  function _msgError(msg, m) { (msg && msg.error) ? msg.error(m) : console.error(m); }

  async function loadPages() {
    try {
      const res = await pomListPages();
      if (res.success) pages.value = res.data || [];
    } catch (e) { /* tolerate transient errors */ }
  }

  // 清掉所有 page 级状态——失败 / 显式取消选择时都用，避免残留误导。
  function _clearPageState() {
    currentFile.value = '';
    page.value = ''; desc.value = ''; triggers.value = '';
    elements.value = {};
    elementDocs.value = {};
    elementParents.value = {};
    imageCache.value = {};
    saveToLocalStorage('currentPomFile', '');
  }
  async function selectPage(filename, msg) {
    if (!filename) { _clearPageState(); return; }
    try {
      const res = await pomGetPage(filename);
      if (!res.success) {
        // 文件不存在 / 损坏 / 后端报错 —— 清残留 + 提示，避免下次刷新仍然卡在这个文件
        _msgError(msg, `加载页面失败: ${res.message || filename}`);
        _clearPageState();
        return;
      }
      currentFile.value = res.data.filename;
      page.value     = res.data.page || '';
      desc.value     = res.data.desc || '';
      triggers.value = res.data.triggers || '';
      elements.value = res.data.elements || {};
      elementDocs.value = res.data.docs || {};
      elementParents.value = res.data.parents || {};
      _syncDerivedMaps();
      // 拉取页面里所有 image 元素的缩略图 — fire-and-forget per file，单张失败不阻塞
      const wanted = new Set();
      for (const sel of Object.values(elements.value)) {
        if (sel && sel.image) wanted.add(sel.image);
      }
      const nextCache = {};
      await Promise.all([...wanted].map(async (fn) => {
        try {
          const imgRes = await getImage(fn);
          if (imgRes.success && imgRes.data && imgRes.data.data) {
            nextCache[fn] = 'data:image/png;base64,' + imgRes.data.data;
          }
        } catch (e) { /* 单图失败留空，UI 显示占位 */ }
      }));
      imageCache.value = nextCache;
    } catch (e) {
      _msgError(msg, '加载页面错误: ' + (e.message || e));
      _clearPageState();
    }
  }

  async function createPage(pageName, descText, msg) {
    // 详细校验由后端做（要求是合法 Python 标识符，允许中文）；前端只挡空字符串。
    if (!pageName || !pageName.trim()) {
      _msgError(msg, '请输入 Page 名');
      return false;
    }
    try {
      const res = await pomSavePage({
        page: pageName, desc: descText || '', triggers: '', elements: {}, docs: {}, vars: {},
      });
      if (!res.success) { _msgError(msg, res.message || '创建失败'); return false; }
      await loadPages();
      await selectPage(res.data.filename, msg);
      msg && msg.success && msg.success(`已创建 ${pageName}`);
      return true;
    } catch (e) { _msgError(msg, '创建错误: ' + e.message); return false; }
  }

  async function deletePage(filename, msg) {
    if (!filename) return;
    try {
      const res = await pomDeletePage(filename);
      if (!res.success) { _msgError(msg, res.message || '删除失败'); return; }
      if (currentFile.value === filename) await selectPage('');
      await loadPages();
      msg && msg.success && msg.success('已删除');
    } catch (e) { _msgError(msg, '删除错误: ' + e.message); }
  }

  // Fire-and-forget save — mirrors useTask._dirtyStep style (silent failure).
  function saveCurrentPage() {
    if (!page.value) return;
    pomSavePage({
      page: page.value,
      desc: desc.value || '',
      triggers: triggers.value || '',
      elements: elements.value,
      docs: elementDocs.value,
      parents: elementParents.value,
    }).catch(() => {});
  }

  async function loadMeta() {
    try {
      const res = await pomGetMeta();
      if (res.success) {
        metaVars.value = res.data.vars || {};
      }
    } catch (e) { /* tolerate */ }
  }

  function saveMeta() {
    pomSaveMeta({ vars: metaVars.value }).catch(() => {});
  }

  // ── Capture flow ───────────────────────────────────────────────────────
  function beginCapture(node) {
    pendingSelector.value = selectorFromNode(node);
    // 弹框「元素名」预填建议：优先级 text > description > resourceId 尾段。
    // - text         : 可见文案，语义最强（含中文直接保留，不做大小写归一化）
    // - description  : Android content-desc / iOS accessibility label —— 图标按钮
    //                  常无 text 但有这个（如「返回」「搜索」「更多」）
    // - resourceId   : 兜底；只取冒号/斜杠后最末段，避免完整 com.x.y:id/ 包名噪声
    let suggested = '';
    if (node.text) {
      suggested = String(node.text);
    } else if (node.description) {
      suggested = String(node.description);
    } else {
      const rid = node.resourceId || '';
      if (rid) suggested = rid.split(/[:/]/).pop() || '';
    }
    // 清理：与 _validName 对齐 —— 只剥掉控制字符 / 换行 / 制表符与首尾空白；
    // 中文标点 / 括号 / 空格中部一律保留，让用户能按原文识别。
    pendingName.value = (suggested || '')
      .replace(/[\x00-\x1f\x7f\u2028\u2029]+/g, ' ')   // 控制字符压成普通空格
      .replace(/\s+/g, ' ')                            // 连续空白压一个，去掉换行
      .trim();
    pendingDoc.value = '';
    pendingParent.value = '';
    nameDialogVisible.value = true;
  }

  // Image capture entry: useCanvas calls this from onCaptureMouseUp when pom
  // is the active capture target. `dataUrl` is the cropped PNG; `filename`
  // has been written to <images_dir>/ already so reloading the page renders it.
  function beginImageCapture(filename, dataUrl) {
    imageCache.value = { ...imageCache.value, [filename]: dataUrl };
    pendingSelector.value = { image: filename };
    pendingName.value = '';   // 图像元素无现成名字来源，用户必填
    pendingDoc.value = '';
    pendingParent.value = '';
    nameDialogVisible.value = true;
  }

  // Mutate one field of the pending selector inside the capture dialog.
  // Empty/null values are stored and stripped when the user confirms — keeps
  // the form responsive while typing without forcing key reordering.
  function setPendingSelectorField(key, value) {
    pendingSelector.value = { ...(pendingSelector.value || {}), [key]: value };
  }

  function _normalizeSelector(sel) {
    // Drop empty strings / null / undefined. Numbers (e.g. index = 0) are kept.
    const out = {};
    if (!sel) return out;
    for (const [k, v] of Object.entries(sel)) {
      if (v === null || v === undefined) continue;
      if (typeof v === 'string' && v.trim() === '') continue;
      out[k] = v;
    }
    return out;
  }

  // 元素名校验 —— 元素名最终落在 pom/<page>.py 里 ELEMENTS dict 的 string key
  // （`{k!r}: {v!r}` 自动转义任何字符），不参与 Python 标识符匹配，**不会引发代码语法错误**。
  // 因此校验目的只在 UX：不允许会导致"看不见/不能粘贴回去/格式错乱"的内容。
  //
  // 允许：中文/字母/数字/下划线、空格、中英文标点、引号、括号、emoji 等任意可见 Unicode；
  //       数字开头也允许（dict key 没有标识符限制）。
  // 禁止：空字符串、全空白、首尾留白（自动 trim 后判）、控制字符、换行、制表符 ——
  //       这些字面合法但会破坏 ELEMENTS 列表的视觉对齐 / repr 难读 / 不可见字符引发"找不到 key"。
  function _validName(name) {
    if (!name || typeof name !== 'string') return false;
    if (name.trim() !== name) return false;          // 首尾空白
    if (!name.length) return false;                  // 全空
    return !/[\x00-\x1f\x7f\u2028\u2029]/.test(name); // 控制字符 / 换行 / 制表 / U+2028/2029
  }

  function confirmCapture(msg) {
    const name = (pendingName.value || '').trim();
    if (!_validName(name)) {
      _msgError(msg, '元素名不能为空，且不可包含换行、制表符或其它控制字符');
      return;
    }
    if (Object.prototype.hasOwnProperty.call(elements.value, name)) {
      _msgError(msg, '名称已存在');
      return;
    }
    const selector = _normalizeSelector(pendingSelector.value);
    if (Object.keys(selector).length === 0) {
      _msgError(msg, 'selector 不能为空 — 至少保留一个字段');
      return;
    }
    // 包成 ElementShape：image 元素跨平台共享，其它进 currentPlatform 分桶
    const par = (pendingParent.value || '').trim();
    const doc = (pendingDoc.value || '').trim();
    let element;
    if (selector.image) {
      element = { platforms: {}, image: selector.image, _parent: par, _doc: doc };
    } else {
      const platform = currentPlatform.value || 'android';
      element = {
        platforms: { [platform]: selector },
        image: null,
        _parent: (par && Object.prototype.hasOwnProperty.call(elements.value, par)) ? par : '',
        _doc: doc,
      };
    }
    elements.value = { ...elements.value, [name]: element };
    _syncDerivedMaps();
    saveCurrentPage();
    nameDialogVisible.value = false;
    pendingSelector.value = null;
    pendingName.value = '';
    pendingDoc.value = '';
    pendingParent.value = '';
    msg && msg.success && msg.success(`已采集元素: ${name}`);
  }

  // Update an existing element's name / selector / doc / parent. Returns true on success.
  function updateElement(oldName, newName, newSelector, newDoc, newParent, msg) {
    const nn = (newName || '').trim();
    if (!_validName(nn)) {
      _msgError(msg, '元素名不能为空，且不可包含换行、制表符或其它控制字符');
      return false;
    }
    if (nn !== oldName && Object.prototype.hasOwnProperty.call(elements.value, nn)) {
      _msgError(msg, '名称已存在');
      return false;
    }
    const cleaned = _normalizeSelector(newSelector);
    if (Object.keys(cleaned).length === 0) {
      _msgError(msg, 'selector 不能为空 — 至少保留一个字段');
      return false;
    }
    // 父元素校验：禁止指向自己 / 不存在的元素 / 循环引用（自己的后代）。
    const desiredParent = (newParent === undefined || newParent === null)
      ? (elementParents.value[oldName] || '')
      : String(newParent).trim();
    if (desiredParent) {
      if (desiredParent === nn || desiredParent === oldName) {
        _msgError(msg, '父元素不能是自己');
        return false;
      }
      if (!Object.prototype.hasOwnProperty.call(elements.value, desiredParent)) {
        _msgError(msg, `父元素不存在: ${desiredParent}`);
        return false;
      }
      // 循环检测：沿 desiredParent 往上爬，不能撞到 oldName/nn 自己
      let cursor = desiredParent, hops = 0;
      const seen = new Set();
      while (cursor && !seen.has(cursor) && hops++ < 1000) {
        if (cursor === oldName || cursor === nn) {
          _msgError(msg, '父元素链产生循环引用');
          return false;
        }
        seen.add(cursor);
        cursor = elementParents.value[cursor] || '';
      }
    }

    // 写入：保留其它平台分桶不动，只更新 currentPlatform；image 元素直接替换 image 字段。
    const prevEl = elements.value[oldName] || { platforms: {}, image: null, _parent: '', _doc: '' };
    let nextEl;
    if (cleaned.image) {
      nextEl = {
        platforms: {},                       // image 元素跨平台共享，分桶清空
        image: cleaned.image,
        _parent: desiredParent || '',
        _doc: (newDoc === undefined || newDoc === null) ? (prevEl._doc || '') : String(newDoc).trim(),
      };
    } else {
      const platform = currentPlatform.value || 'android';
      const nextPlatforms = { ...(prevEl.platforms || {}) };
      nextPlatforms[platform] = cleaned;
      nextEl = {
        platforms: nextPlatforms,
        image: null,
        _parent: desiredParent || '',
        _doc: (newDoc === undefined || newDoc === null) ? (prevEl._doc || '') : String(newDoc).trim(),
      };
    }

    // Preserve insertion order：rename 时整体重组，保持位置。
    const next = {};
    for (const [k, v] of Object.entries(elements.value)) {
      next[k === oldName ? nn : k] = (k === oldName) ? nextEl : v;
    }
    // 其它元素的 _parent 指向 oldName 的 → 改成 nn
    if (nn !== oldName) {
      for (const [k, v] of Object.entries(next)) {
        if (v && v._parent === oldName) next[k] = { ...v, _parent: nn };
      }
    }
    elements.value = next;
    _syncDerivedMaps();

    saveCurrentPage();
    if (window._pomVerifyRevalidate) window._pomVerifyRevalidate(nn);
    return true;
  }
  // 删元素：子节点上升一级（变成它原祖父的子；祖父不在则升到顶层），
  // 不递归删除。selector 独立工作，子元素的查找语义不受影响。
  function removeElement(name) {
    const grandparent = (elements.value[name] && elements.value[name]._parent) || '';
    const next = {};
    for (const [k, v] of Object.entries(elements.value)) {
      if (k === name) continue;
      if (v && v._parent === name) {
        next[k] = { ...v, _parent: grandparent };
      } else {
        next[k] = v;
      }
    }
    elements.value = next;
    _syncDerivedMaps();
    saveCurrentPage();
    if (window._pomVerifyRevalidate) window._pomVerifyRevalidate(name);
  }

  // 扁平 elements + parents map → 元素树。给 el-tree :data 用。
  // 节点结构：{ name, sel, doc, status?, children: [...] }
  // 顶级顺序、同父下子节点顺序：按 elements 字典插入顺序（Object.entries 保序）。
  // 异常处理：
  //  - parent 指向不存在的元素 → 该 child 当顶层渲染（容错）
  //  - 循环引用（A→B→A）→ 起点会被认为顶层，避免栈溢出
  const elementTree = computed(() => {
    const all = Object.keys(elements.value);
    const valid = new Set(all);
    // pre-compute children
    const childrenMap = {};
    const orphans = [];   // 顶层 + 异常情况兜底
    for (const name of all) {
      const p = elementParents.value[name];
      if (p && valid.has(p)) {
        (childrenMap[p] = childrenMap[p] || []).push(name);
      } else {
        orphans.push(name);
      }
    }
    const build = (name, seen) => {
      if (seen.has(name)) return null;       // 防循环
      seen.add(name);
      const el = elements.value[name] || { platforms: {}, image: null, _parent: '', _doc: '' };
      // sel —— 兼容老 template：image 元素 {image:...}，其它取当前平台 native（可能为 null）
      const view = el.image ? { image: el.image } : ((el.platforms && el.platforms[currentPlatform.value]) || null);
      return {
        name,
        sel: view,                   // 当前平台 selector view（null = 未在该平台采集）
        element: el,                 // 完整 ElementShape，UI 需要切平台时用
        doc: el._doc || '',
        captured: hasSelectorOn(name),
        children: (childrenMap[name] || []).map(c => build(c, seen)).filter(Boolean),
      };
    };
    return orphans.map(n => build(n, new Set())).filter(Boolean);
  });

  // 拖拽后改父：el-tree node-drop 调用。drop=null 表示升到顶层。
  // 只改 _parent，不碰 selector，因此只传当前平台 view（或 image），不是整个 ElementShape。
  function setElementParent(name, newParent, msg) {
    if (!Object.prototype.hasOwnProperty.call(elements.value, name)) return false;
    const el = elements.value[name];
    const sel = el && el.image ? { image: el.image } : (el.platforms || {})[currentPlatform.value];
    if (!sel) { _msgError(msg, '该元素在当前平台未采集，无法设置父元素'); return false; }
    return updateElement(
      name, name, sel, elementDocs.value[name] || null, newParent || '',
      msg,
    );
  }

  return {
    // state
    pages, currentFile, page, desc, triggers, elements, elementDocs, elementParents,
    elementTree,
    metaVars,
    captureMode, nameDialogVisible, pendingSelector, pendingName, pendingDoc, pendingParent,
    pendingFillName,
    currentPlatform,
    imageCache,
    // methods
    loadPages, selectPage, createPage, deletePage, saveCurrentPage,
    loadMeta, saveMeta,
    beginCapture, beginImageCapture, setPendingSelectorField, confirmCapture,
    updateElement, removeElement, setElementParent,
    selectorView, hasSelectorOn,
  };
}
