import { pomVerifySelector } from '../api.js';

const { ref } = Vue;

// usePomVerify — POM 元素验证状态（不落盘，纯实时扫描）。
//
// results: { name: { status, rect, error } }
//   status ∈ 'pending' | 'found' | 'not_found' | 'unsupported' | 'manual'
//   - manual:      image 元素，机器不扫，需在设备上手工验证
//   - unsupported: 平台 driver 不暴露元素查找（Harmony）
// rect 与 hierarchy 同坐标系（pixel space），由 useCanvas 画到截图 overlay。
export function usePomVerify({ pom, device, msg }) {
  const verifyMode = ref(false);
  const results    = ref({});
  // 扫描代号：endVerify / 重扫会自增，使在飞的旧串行扫描结果作废，
  // 避免迟到的响应覆盖新一轮扫描或污染已退出的空状态。
  let _scanGen = 0;

  function _isManualOnly(sel) {
    return sel && typeof sel === 'object' && 'image' in sel;
  }

  // 在验证模式下串行扫指定一批元素，**already-found 项一律保留不动**——
  // 用户语义：一旦某元素曾被定位到，就算后续切了页面找不到了也不刷掉，直到点
  // 「完成验证」(endVerify) 才清空。这让用户可以分多次切不同界面把没找到的逐
  // 个扫齐，永远不会丢已经成功过的。
  async function _scan(names) {
    if (!verifyMode.value) return;
    const gen = ++_scanGen;
    const platform = device.platform.value;
    const serial   = device.serial.value;
    if (!platform || !serial) { msg.warn('设备未连接'); return; }

    // 把待扫元素中尚未 found 的项置 pending；已 found / manual / unsupported 不动。
    const next = { ...results.value };
    for (const n of names) {
      const sel = pom.elements.value[n];
      if (sel === undefined) continue;                       // 元素已被删
      if (next[n] && next[n].status === 'found') continue;   // 粘性：保留
      next[n] = _isManualOnly(sel)
        ? { status: 'manual',  rect: null, error: null }
        : { status: 'pending', rect: null, error: null };
    }
    results.value = next;

    // 串行扫 — ADB/WDA 并发查找易锁竞争。
    for (const name of names) {
      const sel = pom.elements.value[name];
      if (sel === undefined) continue;
      if (_isManualOnly(sel)) continue;
      // 已 found 的不再发请求 —— 节省 ADB 往返。
      const cur = results.value[name];
      if (cur && cur.status === 'found') continue;

      let r;
      try {
        const res = await pomVerifySelector({ platform, serial, selector: sel });
        if (!res.success) {
          r = { status: 'not_found', rect: null, error: res.message || null };
        } else if (res.data.platform_supported === false) {
          r = { status: 'unsupported', rect: null, error: null };
        } else {
          r = { status: res.data.found ? 'found' : 'not_found', rect: res.data.rect, error: null };
        }
      } catch (e) {
        r = { status: 'not_found', rect: null, error: e.message };
      }
      if (gen !== _scanGen || !verifyMode.value) return;   // 过期扫描，丢弃
      // 二次防御：响应到达时如果已经被别的轮次刷成 found，依然保留。
      const now = results.value[name];
      if (now && now.status === 'found') continue;
      results.value = { ...results.value, [name]: r };
    }
  }

  async function beginVerify() {
    if (!pom.currentFile.value) { msg.warn('请先选择 Page'); return; }
    if (!device.isConnected.value) { msg.warn('设备未连接'); return; }
    pom.captureMode.value = false;          // 采集 / 验证互斥
    verifyMode.value = true;
    results.value = {};                      // 进入验证时清一次，进入后只增不减
    // 第一轮先取一次最新截图 + hierarchy，再扫所有元素
    try {
      if (window._screenshotAndDump) await window._screenshotAndDump();
    } catch (e) { /* 容忍：driver 内部会重试 */ }
    _scan(Object.keys(pom.elements.value));
  }

  // 重扫所有「尚未 found」的元素（not_found / pending / undefined）。
  // 在验证过程中用户点工具栏「刷新」反复调用，已 found 的永远不动。
  async function rescanPending() {
    if (!verifyMode.value) { msg.warn('未进入验证模式'); return; }
    const all = Object.keys(pom.elements.value);
    const targets = all.filter(n => {
      const r = results.value[n];
      return !r || (r.status !== 'found' && r.status !== 'manual' && r.status !== 'unsupported');
    });
    if (!targets.length) {
      msg.success && msg.success('全部已通过');
      return;
    }
    // 先重新截图 + dump hierarchy —— driver 端拿到当前界面才能准确定位；
    // 否则后端用上次的 hierarchy 查，看起来"刷新没用"。失败不阻塞扫描。
    try {
      if (window._screenshotAndDump) await window._screenshotAndDump();
    } catch (e) { /* 截图失败也继续 _scan —— driver 内部还会重试 */ }
    msg.info && msg.info(`重扫 ${targets.length} 个元素…`);
    _scan(targets);
  }


  function endVerify() {
    verifyMode.value = false;
    _scanGen++;          // 作废在飞扫描
    results.value = {};
    window._pomVerifyHover = '';
  }

  // 元素改名 / 改 selector / 删除时的回调：扫一次该元素，不动其它项。
  // （删除场景下 sel 已不在 pom.elements，_scan 会跳过 —— 那就只起到把它从
  // results 里抹掉的副作用，靠下面这两行 prune 显式删掉。）
  function revalidateElement(name) {
    if (!verifyMode.value) return;
    // 先把这一项的旧 result 清掉（特别是 sticky-found 的 selector 已变，得让它重判）
    if (results.value[name]) {
      const next = { ...results.value };
      delete next[name];
      results.value = next;
    }
    if (pom.elements.value[name] !== undefined) {
      _scan([name]);
    }
  }
  // ── 单元素临时高亮（持续 N 毫秒，不进入 verify 模式） ─────────────────
  // 列表行的「高亮」按钮调用：调一次后端定位 → 在 canvas overlay 上画 3s 方框，
  // 不污染 results / verifyMode。 image 元素后端不支持，前端直接拒绝。
  let _flashTimer = null;
  async function flashOne(name, sel, durationMs = 3000) {
    if (!sel) { msg.warn('元素 selector 为空'); return; }
    if (_isManualOnly(sel)) { msg.warn('图像元素需在设备上手工验证'); return; }
    const platform = device.platform.value;
    const serial   = device.serial.value;
    if (!platform || !serial) { msg.warn('设备未连接'); return; }

    try {
      const res = await pomVerifySelector({ platform, serial, selector: sel });
      if (!res.success) { msg.error(res.message || '定位失败'); return; }
      if (res.data.platform_supported === false) { msg.warn('当前平台不支持元素查找'); return; }
      if (!res.data.found || !res.data.rect) { msg.warn(`未找到: ${name}`); return; }

      // 直接戳 window 变量（绕过 verifyMode）—— App.js 的 watch 不会清零，因为我们
      // 没动 verify.results / verifyMode；timer 结束时按当前 verifyMode 还原。
      const overlay = { [name]: { status: 'found', rect: res.data.rect, error: null } };
      window._pomVerifyResults = overlay;
      if (window._renderHierarchyCanvas) window._renderHierarchyCanvas();

      clearTimeout(_flashTimer);
      _flashTimer = setTimeout(() => {
        window._pomVerifyResults = verifyMode.value ? results.value : null;
        if (window._renderHierarchyCanvas) window._renderHierarchyCanvas();
      }, durationMs);
    } catch (e) {
      msg.error('高亮失败: ' + (e.message || e));
    }
  }

  return { verifyMode, results, beginVerify, endVerify, rescanPending, revalidateElement, flashOne };
}
