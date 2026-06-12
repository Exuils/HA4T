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

  async function _scanOnce() {
    if (!verifyMode.value) return;
    const gen = ++_scanGen;
    const platform = device.platform.value;
    const serial   = device.serial.value;
    if (!platform || !serial) { msg.warn('设备未连接'); return; }
    const entries = Object.entries(pom.elements.value);
    const next = {};
    // 先全量铺底：image → manual，selector → pending
    for (const [name, sel] of entries) {
      next[name] = _isManualOnly(sel)
        ? { status: 'manual',  rect: null, error: null }
        : { status: 'pending', rect: null, error: null };
    }
    results.value = next;
    // 串行扫 selector 元素 — ADB/WDA 并发查找易锁竞争，先按串行交付
    for (const [name, sel] of entries) {
      if (next[name].status === 'manual') continue;
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

  function beginVerify() {
    if (!pom.currentFile.value) { msg.warn('请先选择 Page'); return; }
    if (!device.isConnected.value) { msg.warn('设备未连接'); return; }
    pom.captureMode.value = false;   // 采集 / 验证互斥
    verifyMode.value = true;
    _scanOnce();
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

  return { verifyMode, results, beginVerify, endVerify, onHierarchyUpdated };
}
