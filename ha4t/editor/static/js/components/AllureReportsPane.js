// Allure 报告 tab —— 列出 <workspace>/allure-reports/ 下所有报告，可打开 / 删除。
//
// 每个报告是 Allure 生成的静态 SPA（index.html + 内部 js/css 走相对路径自洽），
// 后端通过 GET /allure/{name}/{...} 直接 serve；点列表条目 → 新窗口打开 index.html，
// 不嵌 iframe 是因为：(1) 多个报告不便并排；(2) Allure 默认会读取 window.location，
// 嵌套在 iframe 里有时路由失常；(3) 新 tab 让用户可保留多个报告。

import { listAllureReports, deleteAllureReport } from '../api.js';

const { ref, onMounted, computed, inject } = Vue;

function _fmtTs(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const z = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}:${z(d.getSeconds())}`;
}

const TEMPLATE = `
<div class="allure-pane">
  <div class="allure-toolbar">
    <span class="allure-toolbar-title">Allure 报告</span>
    <span class="allure-toolbar-hint">{{ reports.length }} 个</span>
    <span style="flex:1"></span>
    <el-button size="small" @click="refresh" :loading="loading">
      <el-icon><Refresh /></el-icon>&nbsp;刷新
    </el-button>
  </div>

  <div v-if="loading" class="allure-empty">加载中…</div>
  <div v-else-if="error" class="allure-empty allure-error">{{ error }}</div>
  <div v-else-if="!reports.length" class="allure-empty">
    当前工作区还没有 Allure 报告。<br>
    在「用例编辑」tab 里点「运行 + Allure 报告」即可生成。
  </div>
  <div v-else class="allure-list">
    <div v-for="r in reports" :key="r.name" class="allure-card"
        :class="{ 'allure-card-pass': stateOf(r) === 'pass', 'allure-card-fail': stateOf(r) === 'fail' }">
      <div class="allure-card-head">
        <span class="allure-card-name">{{ r.name }}</span>
        <span class="allure-card-time">{{ fmtTs(r.mtime) }}</span>
      </div>
      <div class="allure-card-summary" v-if="r.summary && r.summary.total">
        <span class="allure-stat allure-stat-passed">{{ r.summary.passed || 0 }} 通过</span>
        <span class="allure-stat allure-stat-failed" v-if="r.summary.failed">{{ r.summary.failed }} 失败</span>
        <span class="allure-stat allure-stat-broken" v-if="r.summary.broken">{{ r.summary.broken }} 异常</span>
        <span class="allure-stat allure-stat-skipped" v-if="r.summary.skipped">{{ r.summary.skipped }} 跳过</span>
        <span class="allure-stat-total">共 {{ r.summary.total }}</span>
      </div>
      <div class="allure-card-actions">
        <el-button size="small" type="primary" @click="openReport(r)" plain>
          <el-icon><View /></el-icon>&nbsp;打开
        </el-button>
        <el-button size="small" @click="copyUrl(r)" plain>
          <el-icon><CopyDocument /></el-icon>&nbsp;复制链接
        </el-button>
        <el-button size="small" type="danger" @click="onDelete(r)" plain>
          <el-icon><Delete /></el-icon>&nbsp;删除
        </el-button>
      </div>
    </div>
  </div>
</div>
`;

export default {
  name: 'AllureReportsPane',
  template: TEMPLATE,

  setup() {
    const msg = inject('msg', null);
    const reports = ref([]);
    const loading = ref(false);
    const error   = ref('');

    async function refresh() {
      loading.value = true;
      error.value = '';
      try {
        const r = await listAllureReports();
        if (!r.success) {
          error.value = r.message || '加载失败';
          reports.value = [];
        } else {
          reports.value = r.data.reports || [];
        }
      } catch (e) {
        error.value = e.message || String(e);
        reports.value = [];
      } finally {
        loading.value = false;
      }
    }

    function stateOf(r) {
      const s = r.summary || {};
      if (!s.total) return 'unknown';
      return (s.failed || s.broken) ? 'fail' : 'pass';
    }

    function openReport(r) {
      // 新 tab 打开 —— Allure SPA 是相对路径自洽，URL prefix 后多个报告互不干扰
      window.open(r.url, '_blank', 'noopener');
    }

    function copyUrl(r) {
      const full = window.location.origin + r.url;
      try {
        navigator.clipboard.writeText(full);
        msg && msg.success && msg.success('已复制');
      } catch (e) {
        msg && msg.warn && msg.warn('复制失败：' + (e.message || e));
      }
    }

    async function onDelete(r) {
      if (!window.confirm(`删除报告「${r.name}」?`)) return;
      const res = await deleteAllureReport(r.name);
      if (!res.success) {
        msg && msg.error && msg.error('删除失败：' + (res.message || ''));
        return;
      }
      msg && msg.success && msg.success('已删除');
      await refresh();
    }

    onMounted(refresh);

    return { reports, loading, error, refresh, stateOf, openReport, copyUrl, onDelete, fmtTs: _fmtTs };
  },
};
