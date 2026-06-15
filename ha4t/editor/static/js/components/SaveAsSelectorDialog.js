// 「保存为选择器」对话框 —— 把当前步骤的 selector 字段固化成一条 POM 元素，
// 写回 pom/<page>.py。提交成功后由父组件把当前 step 切到 pom_ref 模式。
//
// 弹框只负责采集 4 个字段（page / 元素名 / 说明 / 父元素），不直接调后端 ——
// 真正落盘走父组件的 saveStepAsPomSelector，保持职责单一便于测试 / 复用。

import { pomListPages, pomGetPage } from '../api.js';

const { ref, watch, computed, nextTick, inject } = Vue;

const TEMPLATE = `
<el-dialog
  v-model="visible"
  title="保存为 POM 选择器"
  width="520px"
  :close-on-click-modal="false"
  @opened="onOpened">
  <div v-if="loading" class="save-sel-loading">加载中…</div>
  <div v-else>
    <div class="prop-row" style="margin-bottom:8px">
      <label class="prop-label">Page</label>
      <el-select v-model="pageName" filterable allow-create default-first-option
                 placeholder="选择已有 page 或输入新 page 名" size="small"
                 ref="pageSelectRef" style="flex:1" @change="onPageChange">
        <el-option v-for="p in pageOptions" :key="p" :label="p" :value="p"></el-option>
      </el-select>
    </div>
    <div class="prop-row" style="margin-bottom:8px">
      <label class="prop-label">元素名</label>
      <el-input v-model="elementName" placeholder="如 登录按钮 / login_btn" size="small"
                @keyup.enter="onConfirm"
                style="flex:1"></el-input>
    </div>
    <div class="prop-row" style="margin-bottom:8px;align-items:flex-start">
      <label class="prop-label" style="padding-top:5px">说明</label>
      <el-input v-model="docText" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
                size="small"
                placeholder="可选 — 给 AI / 阅读者的元素说明"
                style="flex:1"></el-input>
    </div>
    <div class="prop-row" style="margin-bottom:8px" v-if="parentOptions.length">
      <label class="prop-label">父元素</label>
      <el-select v-model="parentName" clearable filterable size="small"
                 placeholder="（顶层 / 默认）" style="flex:1">
        <el-option v-for="opt in parentOptions" :key="opt" :label="opt" :value="opt"></el-option>
      </el-select>
    </div>
    <div v-if="error" class="save-sel-error">{{ error }}</div>
    <div class="save-sel-preview">
      <div class="save-sel-preview-title">将写入：</div>
      <pre class="save-sel-preview-code">{{ previewLine }}</pre>
    </div>
  </div>
  <template #footer>
    <el-button size="small" @click="visible = false">取消</el-button>
    <el-button size="small" type="primary" :loading="submitting"
               :disabled="!canSubmit" @click="onConfirm">保存</el-button>
  </template>
</el-dialog>
`;

export default {
  name: 'SaveAsSelectorDialog',
  template: TEMPLATE,

  props: {
    modelValue:   { type: Boolean, default: false },
    // 当前要保存的 step 数据。父组件传：{ selector: {text,...}, action: 'click', currentPlatform: 'android' }
    payload:      { type: Object, default: null },
  },
  emits: ['update:modelValue', 'confirm'],

  setup(props, { emit }) {
    const msg     = inject('msg', null);
    const visible = ref(props.modelValue);
    watch(() => props.modelValue, v => { visible.value = v; });
    watch(visible, v => { emit('update:modelValue', v); });

    const loading      = ref(false);
    const submitting   = ref(false);
    const pageOptions  = ref([]);                  // 已有 page 名列表
    const pageElementsCache = ref({});             // page 名 → 元素清单（用于父元素下拉 + 重名校验）
    const pageName     = ref('');
    const elementName  = ref('');
    const docText      = ref('');
    const parentName   = ref('');
    const error        = ref('');
    const pageSelectRef = ref(null);

    function reset() {
      pageName.value = '';
      elementName.value = '';
      docText.value = '';
      parentName.value = '';
      error.value = '';
    }

    // 进入弹框时拉 page 列表
    async function onOpened() {
      reset();
      loading.value = true;
      try {
        const r = await pomListPages();
        if (r.success) pageOptions.value = (r.data || []).map(p => p.page).filter(Boolean);
      } catch (e) { /* 容忍 — 用户也可直接输新 page 名 */ }
      loading.value = false;
      await nextTick();
      if (pageSelectRef.value) pageSelectRef.value.focus();
    }

    // 切 page 后拉该 page 的元素清单（用于父元素下拉 + 重名校验）
    const parentOptions = ref([]);
    async function onPageChange(name) {
      parentOptions.value = [];
      parentName.value = '';
      if (!name) return;
      // 已有 page：拉一次元素清单（缓存）
      if (pageOptions.value.includes(name)) {
        if (pageElementsCache.value[name]) {
          parentOptions.value = Object.keys(pageElementsCache.value[name]);
          return;
        }
        try {
          const filename = name + '.py';
          const r = await pomGetPage(filename);
          if (r.success) {
            const els = r.data.elements || {};
            pageElementsCache.value[name] = els;
            parentOptions.value = Object.keys(els);
          }
        } catch (e) { /* ignore */ }
      }
      // 新 page：父元素列表为空，OK
    }

    // 重名校验：page + name 已存在 → 不允许
    const canSubmit = computed(() => {
      if (!pageName.value.trim() || !elementName.value.trim()) return false;
      const els = pageElementsCache.value[pageName.value.trim()] || {};
      if (els[elementName.value.trim()]) return false;   // 重名拒绝
      return true;
    });

    // 预览将写入的 Python 行 —— 让用户保存前看到结果
    const previewLine = computed(() => {
      const p = props.payload || {};
      const sel = p.selector || {};
      const platform = p.currentPlatform || 'android';
      const fields = Object.entries(sel).map(([k, v]) => `'${k}': ${JSON.stringify(v)}`).join(', ');
      const docPart = docText.value.trim() ? `_doc='${docText.value.trim()}', ` : '';
      const parPart = parentName.value ? `_parent='${parentName.value}', ` : '';
      const name = elementName.value.trim() || '<元素名>';
      return `'${name}': Selector(${parPart}${docPart}${platform}={${fields}})`;
    });

    async function onConfirm() {
      if (!canSubmit.value) {
        const els = pageElementsCache.value[pageName.value.trim()] || {};
        if (els[elementName.value.trim()]) error.value = `元素名 ${elementName.value.trim()} 已存在于 ${pageName.value}`;
        else error.value = 'page / 元素名 不能为空';
        return;
      }
      submitting.value = true;
      try {
        emit('confirm', {
          page: pageName.value.trim(),
          name: elementName.value.trim(),
          doc: docText.value.trim(),
          parent: parentName.value || '',
          isNewPage: !pageOptions.value.includes(pageName.value.trim()),
        });
        // 父组件应当在 confirm 完成后关闭弹框（通过 v-model）；
        // 这里不主动关，以便父组件失败时保留输入。
      } finally {
        submitting.value = false;
      }
    }

    return {
      visible, loading, submitting, pageOptions, pageName, elementName,
      docText, parentName, parentOptions, error, previewLine, canSubmit,
      pageSelectRef, onOpened, onPageChange, onConfirm,
    };
  },
};
