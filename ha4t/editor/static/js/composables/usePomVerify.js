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

  // 串行扫指定一批元素；`names=null` 表示全量重扫（清空旧 results）。
  // 增量扫（names 给定）只动这批元素的 result，其它项保持不变。
  async function _scan(names = null) {
    if (!verifyMode.value) return;
    const gen = ++_scanGen;
    const platform = device.platform.value;
    const serial   = device.serial.value;
    if (!platform || !serial) { msg.warn('设备未连接'); return; }
    const allEntries = Object.entries(pom.elements.value);

    if (names === null) {
      // 全量：先把所有元素铺成 pending / manual，再串行扫
      const next = {};
      for (const [name, sel] of allEntries) {
        next[name] = _isManualOnly(sel)
          ? { status: 'manual',  rect: null, error: null }
          : { status: 'pending', rect: null, error: null };
      }
      results.value = next;
      names = allEntries.map(([n]) => n);
    } else {
      // 增量：只把待扫的几个置 pending，其它项原样保留
      const next = { ...results.value };
      for (const n of names) {
        const sel = pom.elements.value[n];
        if (sel === undefined) continue;  // 元素已删
        next[n] = _isManualOnly(sel)
          ? { status: 'manual',  rect: null, error: null }
          : { status: 'pending', rect: null, error: null };
      }
      results.value = next;
    }

    // 串行扫 selector 元素 — ADB/WDA 并发查找易锁竞争，先按串行交付
    for (const name of names) {
      const sel = pom.elements.value[name];
      if (sel === undefined) continue;
      if (_isManualOnly(sel)) continue;
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
      results.value = { ...results.value, [name]: r };
    }
  }

  // 兼容名（onHierarchyUpdated / beginVerify 等内部调用方法名不变）
  async function _scanOnce() { return _scan(null); }

  function beginVerify() {
    if (!pom.currentFile.value) { msg.warn('请先选择 Page'); return; }
    if (!device.isConnected.value) { msg.warn('设备未连接'); return; }
    pom.captureMode.value = false;   // 采集 / 验证互斥
    verifyMode.value = true;
    _scan(null);
  }

  // 重新验证「未找到」的元素 —— 用户场景：第一次验证时部分页面还没打开，
  // 切到对应页面再点这个按钮，把没命中的元素再扫一遍，已命中 / manual / unsupported
  // 一律保持原状态不动；没"未找到"项时什么也不做并提示。
  function rescanFailures() {
    if (!verifyMode.value) { msg.warn('未进入验证模式'); return; }
    const failed = Object.entries(results.value)
      .filter(([, r]) => r && r.status === 'not_found')
      .map(([n]) => n);
    if (!failed.length) { msg.success && msg.success('全部已通过，无需重扫'); return; }
    _scan(failed);
  }

  function endVerify() {
    verifyMode.value = false;
    _scanGen++;          // 作废在飞扫描
    results.value = {};
  }

  // 外部钩子：hierarchy 重新 dump 成功后（window._pomVerifyOnHierarchy）、
  // 元素编辑/删除后（usePom.updateElement / removeElement）触发重扫。
  function onHierarchyUpdated() {
    if (verifyMode.value) _scanOnce();
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

  return { verifyMode, results, beginVerify, endVerify, rescanFailures, onHierarchyUpdated, flashOne };
}
