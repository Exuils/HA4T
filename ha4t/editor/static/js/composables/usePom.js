import {
  pomListPages, pomGetPage, pomSavePage, pomDeletePage,
  pomGetMeta, pomSaveMeta, pomInstallSkill,
  getImage, saveImage,
} from '../api.js';
import { selectorFromNode } from './useTask.js';

const { ref } = Vue;

// usePom — POM (Page Object Model) capture state + persistence.
// Pages are stored as one .py per page under <tasks_dir>/pom/.
// Global meta (APP package, cross-page VARS) lives in pom/_meta.py.
export function usePom() {
  // Page index (lightweight — desc/triggers/element_count only)
  const pages              = ref([]);
  // Currently selected page
  const currentFile        = ref('');
  const page               = ref('');
  const desc               = ref('');
  const triggers           = ref('');
  const elements           = ref({});
  // Global meta
  const metaVars           = ref({});
  // Capture state
  const captureMode        = ref(false);
  const nameDialogVisible  = ref(false);
  const pendingSelector    = ref(null);
  const pendingName        = ref('');
  // Image element thumbnails — keyed by image filename, value is "data:..." URL
  // populated by selectPage() (which fetches each referenced image once) and
  // beginImageCapture() (which seeds it with the freshly captured screenshot).
  const imageCache         = ref({});

  function _msgError(msg, m) { (msg && msg.error) ? msg.error(m) : console.error(m); }

  async function loadPages() {
    try {
      const res = await pomListPages();
      if (res.success) pages.value = res.data || [];
    } catch (e) { /* tolerate transient errors */ }
  }

  async function selectPage(filename, msg) {
    if (!filename) {
      currentFile.value = '';
      page.value = ''; desc.value = ''; triggers.value = '';
      elements.value = {};
      imageCache.value = {};
      return;
    }
    try {
      const res = await pomGetPage(filename);
      if (!res.success) { _msgError(msg, res.message || '加载页面失败'); return; }
      currentFile.value = res.data.filename;
      page.value     = res.data.page || '';
      desc.value     = res.data.desc || '';
      triggers.value = res.data.triggers || '';
      elements.value = res.data.elements || {};
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
    } catch (e) { _msgError(msg, '加载页面错误: ' + e.message); }
  }

  async function createPage(pageName, descText, msg) {
    // 详细校验由后端做（要求是合法 Python 标识符，允许中文）；前端只挡空字符串。
    if (!pageName || !pageName.trim()) {
      _msgError(msg, '请输入 Page 名');
      return false;
    }
    try {
      const res = await pomSavePage({
        page: pageName, desc: descText || '', triggers: '', elements: {}, vars: {},
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
    nameDialogVisible.value = true;
  }

  // Image capture entry: useCanvas calls this from onCaptureMouseUp when pom
  // is the active capture target. `dataUrl` is the cropped PNG; `filename`
  // has been written to <images_dir>/ already so reloading the page renders it.
  function beginImageCapture(filename, dataUrl) {
    imageCache.value = { ...imageCache.value, [filename]: dataUrl };
    pendingSelector.value = { image: filename };
    pendingName.value = '';   // 图像元素无现成名字来源，用户必填
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
    elements.value = { ...elements.value, [name]: selector };
    saveCurrentPage();
    nameDialogVisible.value = false;
    pendingSelector.value = null;
    pendingName.value = '';
    msg && msg.success && msg.success(`已采集元素: ${name}`);
  }

  // Update an existing element's name and/or selector. Returns true on success.
  function updateElement(oldName, newName, newSelector, msg) {
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
    // Preserve insertion order: if name unchanged, mutate in place; otherwise
    // rebuild dict so the renamed entry stays at its original position.
    const next = {};
    for (const [k, v] of Object.entries(elements.value)) {
      next[k === oldName ? nn : k] = (k === oldName) ? cleaned : v;
    }
    elements.value = next;
    saveCurrentPage();
    // 验证模式下改了 selector → 立刻重扫，让用户看到新的定位结果
    if (window._pomVerifyOnHierarchy) window._pomVerifyOnHierarchy();
    return true;
  }

  function removeElement(name) {
    const next = { ...elements.value };
    delete next[name];
    elements.value = next;
    saveCurrentPage();
    // 验证模式下删了元素 → 重扫刷新计数与高亮
    if (window._pomVerifyOnHierarchy) window._pomVerifyOnHierarchy();
  }

  async function installSkill(msg) {
    try {
      const res = await pomInstallSkill();
      if (!res.success) { _msgError(msg, res.message || '安装失败'); return; }
      msg && msg.success && msg.success(`Skill 已安装: ${res.data.path}`);
    } catch (e) { _msgError(msg, '安装错误: ' + e.message); }
  }

  return {
    // state
    pages, currentFile, page, desc, triggers, elements,
    metaVars,
    captureMode, nameDialogVisible, pendingSelector, pendingName,
    imageCache,
    // methods
    loadPages, selectPage, createPage, deletePage, saveCurrentPage,
    loadMeta, saveMeta,
    beginCapture, beginImageCapture, setPendingSelectorField, confirmCapture,
    updateElement, removeElement, installSkill,
  };
}
