import { pomVerifySelector } from '../api.js';

const { ref } = Vue;

// usePomVerify — POM 元素验证状态（不落盘，纯实时扫描）。
//
// results: { name: { status, rect, error } }
//   status ∈ 'pending' | 'found' | 'not_found' | 'unsupported'
//   - unsupported: 平台 driver 不暴露元素查找（Harmony）
// rect 与 hierarchy 同坐标系（pixel space），由 useCanvas 画到截图 overlay。
export function usePomVerify({ pom, device, msg }) {
  const verifyMode = ref(false);
  const results    = ref({});
  // 扫描代号：endVerify / 重扫会自增，使在飞的旧串行扫描结果作废，
  // 避免迟到的响应覆盖新一轮扫描或污染已退出的空状态。
  let _scanGen = 0;

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

    // 把待扫元素中尚未 found 的项置 pending；已 found / unsupported 不动。
    const next = { ...results.value };
    for (const n of names) {
      const sel = pom.elements.value[n];
      if (sel === undefined) continue;                       // 元素已被删
      if (next[n] && next[n].status === 'found') continue;   // 粘性：保留
      next[n] = { status: 'pending', rect: null, error: null };
    }
    results.value = next;

    // 串行扫 — ADB/WDA 并发查找易锁竞争。
    for (const name of names) {
      const sel = pom.elements.value[name];
      if (sel === undefined) continue;
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
    } catch (e) { /* 截图失败不阻断后续 */ }
    const all = Object.keys(pom.elements.value);
    await _scan(all);
  }

  // 重扫所有「尚未 found」的元素（not_found / pending / undefined）。
  // 在验证过程中用户点工具栏「刷新」反复调用，已 found 的永远不动。
  async function rescanPending() {
    if (!verifyMode.value) { msg.warn('未进入验证模式'); return; }
    const all = Object.keys(pom.elements.value);
    const targets = all.filter(n => {
      const r = results.value[n];
      return !r || (r.status !== 'found' && r.status !== 'unsupported');
    });
    if (!targets.length) {
      msg.success && msg.success('全部已通过');
      return;
    }
    // 每轮刷新前先截一张新图
    try {
      if (window._screenshotAndDump) await window._screenshotAndDump();
    } catch (e) { /* 截图失败不阻断后续 */ }
    await _scan(targets);
  }

  function endVerify() {
    verifyMode.value = false;
    results.value = {};
    pom.captureMode.value = true;
  }

  // 元素改名 / 改 selector / 删除时的回调：扫一次该元素，不动其它项。
  // （删除场景下 sel 已不在 pom.elements，_scan 会跳过 —— 那就只起到把它从
  // results 里抹掉的副作用，靠下面这两行 prune 显式删掉。）
  function revalidateElement(name) {
    const next = { ...results.value };
    delete next[name];
    results.value = next;
    if (!verifyMode.value) return;
    const sel = pom.elements.value[name];
    if (!sel) return;
    _scan([name]);
  }

  // ── 单元素临时高亮（持续 N 毫秒，不进入 verify 模式） ─────────────────
  // 列表行的「高亮」按钮调用：调一次后端定位 → 在 canvas overlay 上画 3s 方框，
  // 不污染 results / verifyMode。
  let _flashTimer = null;
  async function flashOne(name, sel, durationMs = 3000) {
    if (!sel) { msg.warn('元素 selector 为空'); return; }
    const platform = device.platform.value;
    const serial   = device.serial.value;
    if (!platform || !serial) { msg.warn('设备未连接'); return; }
    let r;
    try {
      const res = await pomVerifySelector({ platform, serial, selector: sel });
      if (!res.success) { msg.warn(res.message); return; }
      if (!res.data.found) { msg.warn('未找到该元素'); return; }
      r = res.data.rect;
    } catch (e) { msg.warn('查找失败: ' + e.message); return; }
    // 在全局画 overlay
    const key = '__flash__';
    const overlay = { [key]: { status: 'found', rect: r, error: null } };
    window._pomVerifyResults = overlay;
    if (window._renderHierarchyCanvas) window._renderHierarchyCanvas();
    clearTimeout(_flashTimer);
    _flashTimer = setTimeout(() => {
      if (window._pomVerifyResults === overlay) {
        window._pomVerifyResults = null;
        if (window._renderHierarchyCanvas) window._renderHierarchyCanvas();
      }
    }, durationMs);
  }

  return { verifyMode, results, beginVerify, endVerify, rescanPending, revalidateElement, flashOne };
}
