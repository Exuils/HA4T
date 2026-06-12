const { inject, ref, computed, onMounted } = Vue;

const TEMPLATE = `
<div class="ws-gate" v-if="!workspace.initialized.value">
  <div class="ws-gate-box">
    <div class="ws-gate-title">选择 HA4T 工作区</div>
    <div class="ws-gate-hint">工作区是一个独立目录，保存用例（.py）、POM 元素库（pom/）、模板图片（images/）与 skill。</div>

    <!-- 1. 绝对路径输入框 -->
    <div class="ws-gate-path">
      <div class="ws-gate-section-label">输入绝对路径</div>
      <div class="ws-gate-path-row">
        <el-input
          v-model="pathInput"
          placeholder="例：C:/Users/Me/Desktop/my_ha4t_ws"
          @keyup.enter="onOpenPath"
          size="default"
          style="flex:1"
        ></el-input>
        <el-button type="primary" @click="onOpenPath">打开</el-button>
        <el-button @click="onInitFromPath">新建</el-button>
      </div>
    </div>

    <!-- 2. 最近工作区 -->
    <div class="ws-gate-recent" v-if="workspace.recent.value.length">
      <div class="ws-gate-section-label">最近</div>
      <div class="ws-gate-recent-list">
        <div
          v-for="r in workspace.recent.value"
          :key="r"
          class="ws-gate-recent-item"
          @click="onOpenPath(null, r)"
          :title="r"
        >{{ r }}</div>
      </div>
    </div>

    <!-- 3. 目录树 -->
    <div class="ws-gate-tree">
      <div class="ws-gate-section-label">浏览目录</div>
      <div class="ws-gate-cwd">
        <el-button size="small" @click="goUp" :disabled="!treeData.parent">上一级</el-button>
        <span class="ws-gate-cwd-path" :title="treeData.path">{{ treeData.path || '/' }}</span>
      </div>
      <div class="ws-gate-tree-list">
        <div
          v-for="entry in treeData.entries"
          :key="entry.path"
          class="ws-gate-tree-item"
          @click="onEntryClick(entry)"
          :title="entry.path"
        >📁 {{ entry.name }}</div>
        <div v-if="!treeData.entries.length" class="ws-gate-tree-empty">（无可访问的子目录）</div>
      </div>
    </div>

    <!-- 4. 操作按钮（针对当前浏览路径） -->
    <div class="ws-gate-actions">
      <el-button type="primary" @click="onOpenCwd" :disabled="!treeData.path">打开此目录为工作区</el-button>
      <el-button @click="onInitInCwd" :disabled="!treeData.path">在此目录下新建…</el-button>
    </div>
  </div>
</div>
`;

function splitParentName(raw) {
  // 把一个完整路径切成 [parent, name]；末尾的 / \ 会被剥掉。
  const trimmed = (raw || '').replace(/[\\/]+$/, '');
  if (!trimmed) return ['', ''];
  const idx = Math.max(trimmed.lastIndexOf('/'), trimmed.lastIndexOf('\\'));
  if (idx <= 0) return ['', trimmed];
  return [trimmed.slice(0, idx), trimmed.slice(idx + 1)];
}

export default {
  name: 'WorkspaceGate',
  template: TEMPLATE,

  setup() {
    const workspace        = inject('workspace');
    const msg              = inject('msg');
    const onWorkspaceReady = inject('onWorkspaceReady');

    const pathInput = ref('');
    const treeData  = ref({ path: '', parent: null, entries: [] });

    async function refreshTree(path) {
      treeData.value = await workspace.browse(path || '');
    }

    async function ready() {
      // workspace open/init 成功后：让 App 重新加载工作区数据。
      if (typeof onWorkspaceReady === 'function') {
        await onWorkspaceReady();
      }
    }

    async function onOpenPath(_evt, override) {
      const p = (override !== undefined ? override : pathInput.value).trim();
      if (!p) { msg && msg.error && msg.error('请输入路径'); return; }
      if (await workspace.open(p, msg)) await ready();
    }

    async function onInitFromPath() {
      const [parent, name] = splitParentName(pathInput.value);
      if (!parent || !name) {
        msg && msg.error && msg.error('请输入完整路径，如 C:/Users/Me/Desktop/my_ws');
        return;
      }
      if (await workspace.init(parent, name, msg)) await ready();
    }

    async function onEntryClick(entry) {
      pathInput.value = entry.path;
      await refreshTree(entry.path);
    }

    async function goUp() {
      if (!treeData.value.parent && treeData.value.parent !== '') {
        // root 已是 ''
        await refreshTree('');
        return;
      }
      await refreshTree(treeData.value.parent || '');
    }

    async function onOpenCwd() {
      if (!treeData.value.path) return;
      if (await workspace.open(treeData.value.path, msg)) await ready();
    }

    async function onInitInCwd() {
      if (!treeData.value.path) return;
      const name = window.prompt('新工作区目录名（将在当前浏览目录下创建）：');
      if (!name) return;
      if (await workspace.init(treeData.value.path, name, msg)) await ready();
    }

    onMounted(async () => {
      await refreshTree('');
    });

    return {
      workspace, pathInput, treeData,
      onOpenPath, onInitFromPath, onEntryClick, goUp, onOpenCwd, onInitInCwd,
    };
  },
};
