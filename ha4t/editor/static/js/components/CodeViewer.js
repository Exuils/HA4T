// 只读源码查看器 —— 弹窗显示工作区内某个 .py 文件的原始文本，hljs python 语法高亮。
// 用例 tab / POM tab 各放一个按钮触发；只看不改，磁盘内容才是真值。
//
// hljs 通过 index.html 全局 <script> 注入，运行时挂在 window.hljs 上。

import { getFileRaw } from '../api.js';

const { ref, watch, nextTick, inject } = Vue;

const TEMPLATE = `
<el-dialog
  v-model="visible"
  :title="'查看源码 — ' + (path || '')"
  width="80%"
  top="6vh"
  :close-on-click-modal="true"
  @opened="onOpened"
>
  <div v-if="loading" class="code-viewer-loading">加载中…</div>
  <div v-else-if="error" class="code-viewer-error">{{ error }}</div>
  <div v-else class="code-viewer-wrap">
    <pre class="code-viewer-pre"><code ref="codeRef" class="language-python">{{ content }}</code></pre>
  </div>
  <template #footer>
    <span style="margin-right:auto;font-size:11px;color:var(--fg-2)">
      只读 · 修改请回到编辑器 · 文件以磁盘为准
    </span>
    <el-button size="small" @click="copyAll" :disabled="!content">复制全文</el-button>
    <el-button size="small" type="primary" @click="visible = false">关闭</el-button>
  </template>
</el-dialog>
`;

export default {
  name: 'CodeViewer',
  template: TEMPLATE,

  props: {
    modelValue: { type: Boolean, default: false },
    // 工作区相对路径（如 testcases/test_login.py / pom/login_page.py）
    path:       { type: String, default: '' },
  },
  emits: ['update:modelValue'],

  setup(props, { emit }) {
    const msg     = inject('msg', null);
    const visible = ref(props.modelValue);
    const content = ref('');
    const loading = ref(false);
    const error   = ref('');
    const codeRef = ref(null);

    // 父级 v-model 双向同步
    watch(() => props.modelValue, v => { visible.value = v; });
    watch(visible, v => { emit('update:modelValue', v); });

    // 每次打开 / 切换 path 重新拉一次 —— 磁盘即真值
    watch([visible, () => props.path], async ([open, p]) => {
      if (!open || !p) return;
      loading.value = true;
      error.value = '';
      content.value = '';
      try {
        const res = await getFileRaw(p);
        if (!res.success) {
          error.value = res.message || '加载失败';
        } else {
          content.value = res.data.content || '';
        }
      } catch (e) {
        error.value = e.message || String(e);
      } finally {
        loading.value = false;
        // 等 DOM 写入后再触发高亮 —— hljs 必须见到真实 <code> 节点
        await nextTick();
        applyHighlight();
      }
    });

    function applyHighlight() {
      const el = codeRef.value;
      if (!el || !window.hljs) return;
      // hljs 11+：先清掉 data-highlighted 才能重复 highlight 同一个节点（切换文件时）
      delete el.dataset.highlighted;
      el.className = 'language-python';   // 重置以防多次 highlight 后类名累计
      try { window.hljs.highlightElement(el); } catch (e) { /* 兜底：不高亮也能显示纯文本 */ }
    }

    // dialog @opened 在面板真正可见且过渡结束后触发 —— 避免在 display:none 时高亮没效果
    function onOpened() { applyHighlight(); }

    async function copyAll() {
      if (!content.value) return;
      try {
        await navigator.clipboard.writeText(content.value);
        msg && msg.success && msg.success('已复制');
      } catch (e) {
        msg && msg.error && msg.error('复制失败：' + (e.message || e));
      }
    }

    return { visible, content, loading, error, codeRef, onOpened, copyAll };
  },
};
