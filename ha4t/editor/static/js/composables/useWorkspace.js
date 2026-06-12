import { getWorkspace, openWorkspace, initWorkspace, fsList } from '../api.js';

const { ref } = Vue;

/**
 * 工作区状态 — current/recent/initialized + 增删改用回调。
 * 所有数据端点都在「未选工作区」时返回 doError，前端只需用 initialized 控制 gate 显隐。
 */
export function useWorkspace() {
  const current     = ref('');      // 当前工作区绝对路径
  const recent      = ref([]);      // 最近列表（已过滤不存在的）
  const initialized = ref(false);   // 工作区是否已选定且有效

  async function load() {
    try {
      const r = await getWorkspace();
      if (r.success) {
        current.value     = r.data.current || '';
        recent.value      = r.data.recent || [];
        initialized.value = !!r.data.initialized;
      } else {
        initialized.value = false;
      }
    } catch (e) {
      initialized.value = false;
    }
  }

  async function open(path, msg) {
    const r = await openWorkspace(path);
    if (!r.success) {
      if (msg && msg.error) msg.error(r.message || '打开失败');
      return false;
    }
    current.value     = r.data.path;
    initialized.value = true;
    await load();
    return true;
  }

  async function init(parent, name, msg) {
    const r = await initWorkspace(parent, name);
    if (!r.success) {
      if (msg && msg.error) msg.error(r.message || '初始化失败');
      return false;
    }
    current.value     = r.data.path;
    initialized.value = true;
    await load();
    return true;
  }

  async function browse(path) {
    const r = await fsList(path);
    return r.success ? r.data : { path: '', parent: null, entries: [] };
  }

  return { current, recent, initialized, load, open, init, browse };
}
