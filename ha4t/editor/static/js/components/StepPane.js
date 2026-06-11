import { reorderTask } from '../api.js';

const { inject, ref, nextTick, watch } = Vue;

const TEMPLATE = `
<div class="center">
  <!-- Editor Toolbar -->
  <div class="editor-toolbar">
    <el-select v-model="task.currentYamlFile.value" placeholder="选择用例文件" size="small"
        style="flex:1;" @change="onFileChange" clearable>
      <el-option v-for="f in task.yamlFiles.value" :key="f.filename" :label="f.name" :value="f.filename">
        <span>{{ f.name }}</span>
        <span style="float:right;color:#8492a6;font-size:11px">{{ f.step_count }} 步 | {{ f.platform }}</span>
      </el-option>
    </el-select>
    <el-tooltip content="刷新文件列表" placement="top">
      <el-button size="small" circle @click="task.refreshYamlFiles()">
        <el-icon><Refresh /></el-icon>
      </el-button>
    </el-tooltip>
    <el-tooltip content="新建用例" placement="top">
      <el-button size="small" @click="newFile">
        <el-icon><CirclePlus /></el-icon>
      </el-button>
    </el-tooltip>
    <el-tooltip content="打开文件夹" placement="top">
      <el-button size="small" @click="openFolder">
        <el-icon><Document /></el-icon>
      </el-button>
    </el-tooltip>
    <el-dropdown @command="handleRunCommand" :disabled="!device.isConnected.value || !task.steps.value.length" trigger="click">
      <el-button size="small" type="success">
        <el-icon><CircleCheck /></el-icon>
        全部运行
        <el-icon class="el-icon--right"><ArrowDown /></el-icon>
      </el-button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="run">运行</el-dropdown-item>
          <el-dropdown-item command="run-allure">运行 + Allure 报告</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
    <el-tooltip content="清理未引用图片" placement="top">
      <el-button size="small" :disabled="!task.projectId.value" @click="task.cleanupTaskImages(msg)">
        <el-icon><Delete /></el-icon>
      </el-button>
    </el-tooltip>
    <el-tooltip content="设置" placement="top">
      <el-button size="small" @click="task.settingsVisible.value = true">
        <el-icon><Setting /></el-icon>
      </el-button>
    </el-tooltip>
    <el-switch v-model="task.autoRun.value" active-text="自动运行" inactive-text="手动" size="small" style="margin-left:4px;"></el-switch>
  </div>

  <!-- Meta bar -->
  <div class="editor-meta">
    <span class="meta-item">平台: <b>{{ task.taskPlatform.value }}</b></span>
    <span class="meta-item" v-if="task.taskName.value">名称: <b>{{ task.taskName.value }}</b></span>
    <span class="meta-item">步骤: <b>{{ task.steps.value.length }}</b></span>
  </div>

  <!-- Step list -->
  <div class="step-list" ref="stepList">
    <div v-if="task.steps.value.length === 0" class="step-empty">
      在下方输入命令, 或按 <b>/</b> 选择动作
    </div>
    <div v-for="(s, i) in task.steps.value" :key="i"
        :class="['step-row',
                 s._type === 'imglocate' ? 'step-img' : '',
                 s._type === 'include' ? 'step-include' : '',
                 { 'step-selected': task.selectedStepIndex.value === i }]"
        @click="task.selectStep(i)" style="position:relative">
      <!-- Remark strip — full-width row above step content -->
      <div v-if="s.remark" class="step-remark">
        <span class="step-remark-icon">#</span>{{ s.remark }}
      </div>
      <!-- Drag handle -->
      <span class="step-drag-handle"><el-icon><Rank /></el-icon></span>

      <!-- Include step: flat layout — header items participate in step-row's flex,
           body uses flex-basis:100% so it wraps below when expanded. Collapsed
           state has no body node at all — identical height to a regular row. -->
      <template v-if="s._type === 'include'">
        <span class="step-icon" :class="task.stepIcon(s._status).cls">{{ task.stepIcon(s._status).icon }}</span>
        <span class="step-num">{{ i + 1 }}.</span>
        <span class="inc-step-badge">引用</span>
        <span class="inc-step-name" :title="s.includeFile">{{ s.includeFile }}</span>
        <span class="inc-step-count" v-if="s._includedSteps">({{ s._includedSteps.length }} 步)</span>
        <div class="step-btns">
          <button class="sb" @click.stop="toggleInclude(i)" :title="s._open ? '收起' : '展开'">{{ s._open ? '▾' : '▸' }}</button>
          <button class="sb" @click.stop="openIncludedFile(s.includeFile)" title="打开该用例编辑">E</button>
          <button class="sb sb-del" @click.stop="deleteStep(i)" title="删除">X</button>
        </div>
        <div v-if="s._open" class="inc-step-body">
          <div v-if="s._loading" class="inc-step-loading">加载中…</div>
          <div v-else-if="!s._includedSteps || !s._includedSteps.length" class="inc-step-empty">（该用例没有步骤）</div>
          <ol v-else class="inc-step-list">
            <li v-for="(c, j) in s._includedSteps" :key="j" class="inc-step-item">
              <span class="inc-sub-num">{{ j + 1 }}.</span>
              <span v-if="c.remark" class="inc-sub-remark">#{{ c.remark }}</span>
              <code class="inc-sub-code">{{ c.code }}</code>
            </li>
          </ol>
        </div>
      </template>

      <!-- Regular step -->
      <template v-else-if="s._type !== 'imglocate'">
        <span class="step-icon" :class="task.stepIcon(s._status).cls">{{ task.stepIcon(s._status).icon }}</span>
        <span class="step-num">{{ i + 1 }}.</span>
        <code class="step-code">{{ s.code }}</code>
        <span class="step-dur" v-if="s._duration">{{ s._duration }}s</span>
        <div class="step-btns">
          <button class="sb" @click.stop="runFromHere(i)" title="从此步运行">&#9654;</button>
          <button class="sb" @click.stop="runSingle(i)" title="仅此步">&#9654;&#9654;</button>
          <button class="sb" @click.stop="copyStep(i)" title="复制代码">C</button>
          <button class="sb sb-del" @click.stop="deleteStep(i)" title="删除">X</button>
        </div>
        <!-- Collapsible failure detail -->
        <template v-if="s._detail">
          <div class="step-detail-toggle" @click.stop="s._detailOpen = !s._detailOpen">
            详情 {{ s._detailOpen ? '▴' : '▾' }}
          </div>
          <pre v-if="s._detailOpen" class="step-detail-block">{{ s._detail }}</pre>
        </template>
      </template>

      <!-- Image locate step -->
      <template v-else>
        <div class="img-step-card">
          <div class="img-step-preview"><img :src="s.image" alt="模板图片" /></div>
          <div class="img-step-info">
            <div class="img-step-meta">
              <div class="img-step-title">
                <span class="step-icon" :class="task.stepIcon(s._status).cls">{{ task.stepIcon(s._status).icon }}</span>
                <span class="step-num">{{ i + 1 }}.</span>
                <span class="img-step-badge">{{ s.action === 'click' ? '点击' : s.action === 'wait_show' ? '等待显示' : '等待消失' }}</span>
              </div>
              <div class="img-step-params">
                <span v-if="s.action === 'click'">网格: {{ s.grid_h }}×{{ s.grid_v }}</span>
                <span v-if="s.action === 'click'">点击: 第{{ s.click_col+1 }}列, 第{{ s.click_row+1 }}行</span>
                <span>超时: {{ s.timeout }}s</span>
                <span v-if="s.threshold">阈值: {{ s.threshold }}</span>
              </div>
            </div>
            <span class="step-dur" v-if="s._duration">{{ s._duration }}s</span>
            <div class="img-step-btns">
              <button class="sb" @click.stop="runFromHere(i)" title="从此步运行">&#9654;</button>
              <button class="sb" @click.stop="runSingle(i)" title="仅此步">&#9654;&#9654;</button>
              <button class="sb" @click.stop="copyStep(i)" title="复制代码">C</button>
              <button class="sb sb-del" @click.stop="deleteStep(i)" title="删除">X</button>
            </div>
          </div>
        </div>
        <!-- Detail row stays at step-row level (flex-wrap takes care of full-width row) -->
        <template v-if="s._detail">
          <div class="step-detail-toggle" @click.stop="s._detailOpen = !s._detailOpen">
            详情 {{ s._detailOpen ? '▴' : '▾' }}
          </div>
          <pre v-if="s._detailOpen" class="step-detail-block">{{ s._detail }}</pre>
        </template>
      </template>
    </div>
  </div>

  <!-- CLI -->
  <div class="cli-wrap" :class="{ 'cli-flash': cliFlash }">
    <span class="cli-prefix" v-if="cliPrefix">{{ cliPrefix }}:</span>
    <span class="cli-prompt"><el-icon><Promotion /></el-icon></span>
    <input class="cli-input" ref="cliInput" v-model="cliText"
        @keydown="onCliKeydown" @input="onCliInput"
        :placeholder="cliPlaceholder"
        spellcheck="false" autocomplete="off" />
    <div class="slash-palette" v-if="slashVisible">
      <div v-for="(item, idx) in slashItems" :key="idx"
          class="slash-item" :class="{ 'slash-hl': idx === slashIdx }"
          @mousedown.prevent="pickSlash(item)">
        <span class="slash-key" v-if="!item.isApp">{{ item.key || item.action }}</span>
        <span class="slash-key slash-app" v-else>{{ item.key }}</span>
        <span class="slash-desc" v-if="!item.isApp">{{ item.desc }}</span>
      </div>
    </div>
  </div>

  <!-- Log panel (inline, below CLI) -->
  <div class="log-panel" :class="{ 'log-open': runner.logOpen.value }">
    <div class="log-header" @click="toggleLog">
      日志 {{ runner.logLines.value.length ? '(' + runner.logLines.value.length + ')' : '' }}
      <span class="log-arrow">{{ runner.logOpen.value ? '▼' : '▲' }}</span>
    </div>
    <div class="log-body" v-show="runner.logOpen.value">
      <div class="log-line" v-for="(l, i) in runner.logLines.value" :key="i"
          :class="'log-' + l.level">{{ l.text }}</div>
    </div>
  </div>

  <!-- Settings dialog -->
  <el-dialog title="用例设置" v-model="task.settingsVisible.value" width="520px" top="10vh">
    <el-form label-width="80px" size="small">
      <el-form-item label="名称"><el-input v-model="task.taskName.value"></el-input></el-form-item>
      <el-form-item label="描述"><el-input v-model="task.taskDesc.value" type="textarea" :rows="2"></el-input></el-form-item>
      <el-form-item label="平台">
        <el-select v-model="task.taskPlatform.value" style="width:100%">
          <el-option label="Android"   value="android"></el-option>
          <el-option label="iOS"       value="ios"></el-option>
          <el-option label="HarmonyOS" value="harmony"></el-option>
        </el-select>
      </el-form-item>
      <el-divider></el-divider>
      <p style="color:#8492a6;font-size:12px;margin:0 0 8px 0">Allure / pytest 元数据（可选）</p>
      <el-form-item label="标签">   <el-input v-model="task.taskTag.value"     placeholder="逗号分隔，如 smoke, login"></el-input></el-form-item>
      <el-form-item label="Feature"><el-input v-model="task.taskFeature.value" placeholder="Allure Feature"></el-input></el-form-item>
      <el-form-item label="Story">  <el-input v-model="task.taskStory.value"   placeholder="Allure Story"></el-input></el-form-item>
      <el-form-item label="严重级别">
        <el-select v-model="task.taskSeverity.value" style="width:100%">
          <el-option label="Blocker"  value="blocker"></el-option>
          <el-option label="Critical" value="critical"></el-option>
          <el-option label="Normal"   value="normal"></el-option>
          <el-option label="Minor"    value="minor"></el-option>
          <el-option label="Trivial"  value="trivial"></el-option>
        </el-select>
      </el-form-item>
      <el-form-item label="失败重试"><el-input-number v-model="task.taskRerun.value" :min="0" :max="5"></el-input-number></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="task.settingsVisible.value = false" size="small">取消</el-button>
      <el-button type="primary" @click="applySettings" size="small">确定</el-button>
    </template>
  </el-dialog>
</div>
`;

export default {
  name: 'StepPane',
  template: TEMPLATE,

  setup() {
    const task   = inject('task');
    const device = inject('device');
    const runner = inject('runner');
    const undo   = inject('undo');
    const msg    = inject('msg');

    const cliText        = ref('');
    const cliPrefix      = ref('');
    const cliPlaceholder = ref('tap: UI element');
    const slashVisible   = ref(false);
    const slashIdx       = ref(0);
    const slashItems     = ref([]);
    const cliFlash       = ref(false);
    const stepListRef    = ref(null);
    const cliInputRef    = ref(null);

    let sortableInstance = null;

    // ── Sortable drag ─────────────────────────────────────────────────────

    function initSortable(el) {
      if (sortableInstance) sortableInstance.destroy();
      sortableInstance = Sortable.create(el, {
        handle: '.step-drag-handle',
        animation: 150,
        onEnd: async (evt) => {
          if (evt.oldIndex === evt.newIndex) return;
          const newOrder = task.steps.value.map((_, i) => i);
          const [moved] = newOrder.splice(evt.oldIndex, 1);
          newOrder.splice(evt.newIndex, 0, moved);
          undo.pushUndo(task.steps.value);
          const moved2 = task.steps.value.splice(evt.oldIndex, 1)[0];
          task.steps.value.splice(evt.newIndex, 0, moved2);
          task.selectStep(evt.newIndex);
          if (task.currentYamlFile.value) {
            const res = await reorderTask(task.currentYamlFile.value, newOrder);
            if (!res.success) {
              msg.error('排序失败: ' + res.message);
              task.steps.value = undo.undo(task.steps.value);
            }
          }
        },
      });
    }

    // ── Step actions ──────────────────────────────────────────────────────

    async function screenshotAndDumpHierarchyProxy() {
      // DevicePane's method; call via global proxy
      window._screenshotAndDump && await window._screenshotAndDump();
    }

    function runFromHere(i) {
      runner.runFromStep(i, screenshotAndDumpHierarchyProxy, msg);
    }

    function runSingle(i) {
      runner.runSingleStep(i, screenshotAndDumpHierarchyProxy, msg);
    }

    function deleteStep(i) {
      undo.pushUndo(task.steps.value);
      task.steps.value.splice(i, 1);
      if (task.selectedStepIndex.value >= task.steps.value.length) {
        task.selectedStepIndex.value = task.steps.value.length - 1;
      }
      task.saveCurrentTask(device.serial.value).catch(() => {});
    }

    function copyStep(i) {
      const code = task.steps.value[i].code || '';
      navigator.clipboard.writeText(code).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = code; document.body.appendChild(ta); ta.select();
        document.execCommand('copy'); document.body.removeChild(ta);
      });
      msg.success('已复制');
    }

    // ── Include step (reference another task file) ────────────────────────

    async function toggleInclude(i) {
      const s = task.steps.value[i];
      if (!s || s._type !== 'include') return;
      const opening = !s._open;
      // mutate inline; assign back to keep reactivity for nested fields
      task.steps.value[i] = { ...s, _open: opening };
      if (opening && !s._includedSteps && !s._loading) {
        task.steps.value[i] = { ...task.steps.value[i], _loading: true };
        try {
          const sub = await task.loadStepsFromFile(s.includeFile);
          task.steps.value[i] = { ...task.steps.value[i], _includedSteps: sub, _loading: false };
        } catch (e) {
          task.steps.value[i] = { ...task.steps.value[i], _loading: false };
          msg.error(`加载失败: ${e.message || e}`);
        }
      }
    }

    async function openIncludedFile(filename) {
      if (!filename) return;
      await task.loadYamlFile(filename, msg);
    }

    // ── File operations ───────────────────────────────────────────────────

    async function onFileChange(filename) {
      await task.loadYamlFile(filename, msg);
    }

    function newFile() {
      task.clearTask();
      task.taskName.value = '新建用例';
      task.taskPlatform.value = device.platform.value || 'android';
      task.projectId.value = 'proj_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
      task.settingsVisible.value = true;
    }

    async function openFolder() {
      await fetch('/tasks/open-folder', { method: 'POST' }).catch(() => {});
    }

    function applySettings() {
      task.settingsVisible.value = false;
      if (!task.currentYamlFile.value) {
        const safe = (task.taskName.value || 'untitled').replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
        task.currentYamlFile.value = safe + '.py';
      }
      task.saveCurrentTask(device.serial.value).catch(() => {});
      task.refreshYamlFiles();
    }

    function handleRunCommand(cmd) {
      if (cmd === 'run') runner.runAllSteps(screenshotAndDumpHierarchyProxy, msg, device.serial.value);
      else if (cmd === 'run-allure') runner.runAllStepsAllure(msg);
    }

    // ── CLI ───────────────────────────────────────────────────────────────

    function onCliKeydown(e) {
      if (e.key === 'Enter') {
        if (slashVisible.value) { pickSlash(slashItems.value[slashIdx.value]); e.preventDefault(); return; }
        submitCli();
      } else if (e.key === 'ArrowDown') {
        if (slashVisible.value) { slashIdx.value = Math.min(slashIdx.value + 1, slashItems.value.length - 1); e.preventDefault(); }
      } else if (e.key === 'ArrowUp') {
        if (slashVisible.value) { slashIdx.value = Math.max(slashIdx.value - 1, 0); e.preventDefault(); }
      } else if (e.key === 'Escape') {
        slashVisible.value = false;
        if (cliPrefix.value) { cliPrefix.value = ''; cliText.value = ''; }
        if (device.captureMode.value) device.exitCaptureMode();
        if (device.swipeRecordMode.value) device.exitSwipeRecordMode();
        if (device.elementSelectMode.value) { device.elementSelectMode.value = false; msg.info('已取消元素选择'); }
      }
    }

    function onCliInput() {
      if (cliText.value.startsWith('/')) {
        slashVisible.value = true;
        slashIdx.value = 0;
        const q = cliText.value.slice(1).toLowerCase();
        slashItems.value = task.SLASH_STEP.filter(a => a.action.startsWith(q));
      } else if (cliPrefix.value === 'launchapp') {
        const q = cliText.value.toLowerCase();
        slashVisible.value = true;
        slashItems.value = task.appsCache.value.filter(p => p.toLowerCase().includes(q)).slice(0, 20).map(p => ({ key: p, desc: '', isApp: true }));
        slashIdx.value = 0;
      } else if (cliPrefix.value === 'key') {
        const q = cliText.value.toLowerCase();
        slashVisible.value = true;
        slashItems.value = task.KEY_OPTIONS.filter(k => k.key.includes(q) || k.desc.toLowerCase().includes(q)).slice(0, 30).map(k => ({ key: k.key, desc: k.desc, isKey: true }));
        slashIdx.value = 0;
      } else if (cliPrefix.value === 'include') {
        const q = cliText.value.toLowerCase();
        slashVisible.value = true;
        slashItems.value = task.yamlFiles.value
          .filter(f => f.filename !== task.currentYamlFile.value)
          .filter(f => !q || f.filename.toLowerCase().includes(q) || (f.name || '').toLowerCase().includes(q))
          .slice(0, 30)
          .map(f => ({ key: f.filename, desc: `${f.name || ''} · ${f.step_count} 步 · ${f.platform}`, isFile: true }));
        slashIdx.value = 0;
      } else {
        slashVisible.value = false;
      }
    }

    function addIncludeStep(filename) {
      undo.pushUndo(task.steps.value);
      const step = task.buildIncludeStep(filename);
      const idx = task.steps.value.length;
      task.steps.value.push(step);
      task.saveCurrentTask(device.serial.value).catch(() => {});
      task.selectedStepIndex.value = idx;
    }

    function submitCli() {
      let line = cliText.value.trim();
      if (!line && !cliPrefix.value) return;
      // include prefix: free-text submit not allowed — user must pick from list
      if (cliPrefix.value === 'include') return;
      if (cliPrefix.value) line = `${cliPrefix.value}: ${line}`;
      if (!/^(\w+):\s*(.*)/.test(line)) line = `tap: ${line}`;
      const m = line.match(/^(\w+):\s*(.*)/);
      if (!m) return;
      const action = m[1], value = m[2] || '';

      if (action === 'imglocate') { device.enterCaptureMode(msg); cliText.value = ''; cliPrefix.value = ''; slashVisible.value = false; return; }
      if (action === 'swipe')     { device.enterSwipeRecordMode(msg); cliText.value = ''; cliPrefix.value = ''; slashVisible.value = false; return; }
      if (action === 'element')   {
        device.elementSelectMode.value = true;
        msg.info('请在截图中点击选择一个 UI 元素');
        cliText.value = ''; cliPrefix.value = ''; slashVisible.value = false; return;
      }

      undo.pushUndo(task.steps.value);
      const code = task.stepToCode(action, value);
      const idx = task.steps.value.length;
      task.steps.value.push({ code, remark: '', _status: 'pending', _detail: '', _duration: null });
      task.saveCurrentTask(device.serial.value).catch(() => {});
      task.selectedStepIndex.value = idx;
      cliText.value = ''; cliPrefix.value = ''; slashVisible.value = false;
      if (task.autoRun.value) runSingle(idx);
    }

    function pickSlash(item) {
      if (!item) return;
      if (item.isFile) {
        addIncludeStep(item.key);
        cliText.value = ''; cliPrefix.value = ''; slashVisible.value = false;
        return;
      }
      if (item.isApp || item.isKey) { cliText.value = item.key; slashVisible.value = false; nextTick(() => cliInputRef.value && cliInputRef.value.focus()); return; }
      if (item.action === 'imglocate') { device.enterCaptureMode(msg); slashVisible.value = false; cliText.value = ''; cliPrefix.value = ''; return; }
      if (item.action === 'swipe')     { device.enterSwipeRecordMode(msg); slashVisible.value = false; cliText.value = ''; cliPrefix.value = ''; return; }
      if (item.action === 'element')   { device.elementSelectMode.value = true; msg.info('请在截图中点击选择一个 UI 元素'); slashVisible.value = false; cliText.value = ''; cliPrefix.value = ''; return; }
      cliPrefix.value = item.action;
      cliText.value = '';
      cliPlaceholder.value = item.desc;
      // include and key open a second-stage picker immediately
      if (item.action === 'key' || item.action === 'include') {
        nextTick(() => onCliInput());
      } else {
        slashVisible.value = false;
      }
      nextTick(() => cliInputRef.value && cliInputRef.value.focus());
    }

    function focusCli() {
      if (cliInputRef.value) {
        cliInputRef.value.focus();
        cliFlash.value = true;
        setTimeout(() => { cliFlash.value = false; }, 1500);
      }
    }

    // expose focusCli globally so App.js keydown can call it
    window._focusCli = focusCli;

    function toggleLog() { runner.logOpen.value = !runner.logOpen.value; }

    return {
      task, device, runner, msg,
      cliText, cliPrefix, cliPlaceholder, slashVisible, slashIdx, slashItems, cliFlash,
      stepList: stepListRef, cliInput: cliInputRef,
      initSortable,
      onFileChange, newFile, openFolder, applySettings, handleRunCommand,
      runFromHere, runSingle, deleteStep, copyStep,
      toggleInclude, openIncludedFile,
      onCliKeydown, onCliInput, submitCli, pickSlash, focusCli, toggleLog,
    };
  },

  mounted() {
    nextTick(() => {
      const el = this.$refs.stepList;
      if (el) this.initSortable(el);
    });
  },
};
