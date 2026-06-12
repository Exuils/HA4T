const { inject, ref, computed, nextTick, watch } = Vue;

// InspectorPane — 中间面板（grid-area: right），3 个 mutually-exclusive 子 tab：
//   • props      —— 步骤属性（默认）
//   • hierarchy  —— 层级树
//   • detail     —— 元素详情
// POM 采集已移至右栏 StepPane 的「POM 采集」外层 tab，不在此文件内承载。
const TEMPLATE = `
<div class="right">
  <div class="inspector-tabs">
    <button :class="['itab', activeTab === 'props' ? 'active' : '']"
        @click="activeTab = 'props'">步骤属性</button>
    <button :class="['itab', activeTab === 'hierarchy' ? 'active' : '']"
        @click="activeTab = 'hierarchy'">层级</button>
    <button :class="['itab', activeTab === 'detail' ? 'active' : '']"
        @click="activeTab = 'detail'" :disabled="!device.selectedNode.value">元素详情</button>
  </div>

  <div class="inspector-body">
    <!-- ── Hierarchy tree tab ─────────────────────────────────────── -->
    <template v-if="activeTab === 'hierarchy'">
      <el-input placeholder="搜索..." style="margin:6px 10px;width:calc(100% - 20px)" v-model="nodeFilterText" size="small"></el-input>
      <el-tree class="custom-tree" ref="treeRef" :data="device.treeData.value"
          :props="{ children: 'children', label: 'label' }"
          @node-click="handleTreeNodeClick"
          node-key="_id" default-expand-all
          :expand-on-click-node="false" :filter-node-method="filterNode">
        <template #default="{ node, data }">
          <span class="tree-node-label"
                @mouseenter="handleTreeMouseEnter(data)"
                @mouseleave="handleTreeMouseLeave()">
            <span>{{ data.label }}</span>
            <span v-if="data.resourceId" style="color:#666;font-size:11px;margin-left:4px">[{{ data.resourceId }}]</span>
          </span>
        </template>
      </el-tree>
    </template>

    <!-- ── Element detail tab ─────────────────────────────────────── -->
    <template v-else-if="activeTab === 'detail' && device.selectedNode.value">
      <div class="center-header">
        <p class="region-title">元素详情</p>
        <el-button size="small" @click="addLocatorToPom"
            :disabled="!pom.currentFile.value"
            :title="pom.currentFile.value ? '把该元素加入当前 Page' : '请先在 POM 采集 tab 选择或新建 Page'">
          <el-icon><Collection /></el-icon>添加到 POM
        </el-button>
        <el-button size="small" type="primary" @click="insertStepFromElement">
          <el-icon><Plus /></el-icon>插入步骤
        </el-button>
      </div>
      <table class="attr-table">
        <colgroup>
          <col style="width:34%">
          <col>
        </colgroup>
        <thead>
          <tr><th>属性</th><th>值</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in selectedNodeDetails" :key="row.key">
            <td class="attr-key">{{ row.key }}</td>
            <td class="attr-value">
              <code>{{ row.value }}</code>
              <button class="attr-copy" @click="copyVal(row.value)" title="复制">⎘</button>
            </td>
          </tr>
        </tbody>
      </table>
    </template>

    <!-- ── Step properties tab (default) ──────────────────────────── -->
    <template v-else>
      <div class="center-header">
        <p class="region-title">步骤属性</p>
        <span class="step-type-badge" v-if="stepConfig">
          {{ { element:'元素操作', imglocate:'图片定位', tap:'点击', swipe:'滑动', key:'按键', launchapp:'启动', wait:'等待', code:'代码' }[stepConfig.type] || stepConfig.type }}
        </span>
      </div>

      <template v-if="stepConfig && selectedStep">
        <div class="step-props">
          <div class="prop-row">
            <label class="prop-label">代码</label>
            <code class="prop-code-readonly">{{ selectedStep.code }}</code>
          </div>

          <template v-if="stepConfig.type === 'element'">
            <div class="prop-section">
              <div class="prop-section-title">选择器</div>
              <div class="prop-row" v-for="(val, key) in stepConfig.fields.selector" :key="key">
                <label class="prop-label">{{ {text:'文本',resourceId:'资源ID',className:'类型',xpath:'XPath',description:'描述',index:'索引'}[key] || key }}</label>
                <el-input v-if="key !== 'index'" :model-value="val" @update:modelValue="v => upd('selector.'+key, v)" size="small" class="prop-input-wide"></el-input>
                <el-input-number v-else :model-value="val" @update:modelValue="v => upd('selector.'+key, v)" :min="0" size="small"></el-input-number>
                <el-button size="small" v-if="!['text','resourceId','className'].includes(key)" @click="task.removeSelectorField(task.selectedStepIndex.value, key, device.serial.value)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
            </div>
            <div class="prop-section">
              <div class="prop-section-title">操作</div>
              <div class="prop-row">
                <el-select :model-value="stepConfig.fields.elementAction" @update:modelValue="v => upd('elementAction', v)" size="small" style="width:100%">
                  <el-option label="点击 (click)"          value="click"></el-option>
                  <el-option label="双击 (double_click)"   value="double_click"></el-option>
                  <el-option label="长按 (long_press)"     value="long_press"></el-option>
                  <el-option label="拖动偏移 (drag)"        value="drag"></el-option>
                  <el-option label="断言 (assert)"         value="assert"></el-option>
                </el-select>
              </div>
            </div>
            <div class="prop-section" v-if="stepConfig.fields.elementAction !== 'click'">
              <div class="prop-section-title">操作参数</div>
              <template v-if="stepConfig.fields.elementAction === 'double_click'">
                <div class="prop-row"><label class="prop-label">点击间隔</label>
                  <el-slider :model-value="stepConfig.fields.elementParams.interval || 0.05" @update:modelValue="v => upd('interval', v)" :min="0.02" :max="0.5" :step="0.01" show-stops style="flex:1"></el-slider>
                  <span class="prop-val">{{ stepConfig.fields.elementParams.interval || 0.05 }}s</span>
                </div>
              </template>
              <template v-if="stepConfig.fields.elementAction === 'long_press'">
                <div class="prop-row"><label class="prop-label">按压时长</label>
                  <el-slider :model-value="stepConfig.fields.elementParams.duration || 1" @update:modelValue="v => upd('duration', v)" :min="0.5" :max="5" :step="0.1" show-stops style="flex:1"></el-slider>
                  <span class="prop-val">{{ stepConfig.fields.elementParams.duration || 1 }}s</span>
                </div>
              </template>
              <template v-if="stepConfig.fields.elementAction === 'drag'">
                <div class="prop-row"><label class="prop-label">X 偏移</label>
                  <el-input-number :model-value="stepConfig.fields.elementParams.dx || 0" @update:modelValue="v => upd('dx', v)" :min="-500" :max="500" size="small"></el-input-number>
                  <span style="color:#888;font-size:12px">px</span>
                </div>
                <div class="prop-row"><label class="prop-label">Y 偏移</label>
                  <el-input-number :model-value="stepConfig.fields.elementParams.dy || 0" @update:modelValue="v => upd('dy', v)" :min="-500" :max="500" size="small"></el-input-number>
                  <span style="color:#888;font-size:12px">px</span>
                </div>
                <div class="prop-row"><label class="prop-label">拖拽时长</label>
                  <el-slider :model-value="stepConfig.fields.elementParams.dragDuration || 0.5" @update:modelValue="v => upd('dragDuration', v)" :min="0.1" :max="2" :step="0.1" show-stops style="flex:1"></el-slider>
                  <span class="prop-val">{{ stepConfig.fields.elementParams.dragDuration || 0.5 }}s</span>
                </div>
              </template>
              <template v-if="stepConfig.fields.elementAction === 'assert'">
                <div class="prop-row"><label class="prop-label">断言对象</label>
                  <el-radio-group :model-value="stepConfig.fields.elementParams.extract || 'text'" @update:modelValue="v => upd('extract', v)" size="small">
                    <el-radio-button label="text">文本</el-radio-button>
                    <el-radio-button label="exists">存在性</el-radio-button>
                  </el-radio-group>
                </div>
                <div class="prop-row"><label class="prop-label">算子</label>
                  <el-select v-if="stepConfig.fields.elementParams.extract !== 'exists'" :model-value="stepConfig.fields.elementParams.operator || 'eq'" @update:modelValue="v => upd('operator', v)" size="small" style="width:140px">
                    <el-option label="等于 (eq)" value="eq"></el-option>
                    <el-option label="不等于 (ne)" value="ne"></el-option>
                    <el-option label="包含 (contains)" value="contains"></el-option>
                    <el-option label="不包含 (not_contains)" value="not_contains"></el-option>
                    <el-option label="为空 (empty)" value="empty"></el-option>
                    <el-option label="不为空 (not_empty)" value="not_empty"></el-option>
                    <el-option label="正则 (regex)" value="regex"></el-option>
                  </el-select>
                  <el-select v-else :model-value="stepConfig.fields.elementParams.operator || 'exists_true'" @update:modelValue="v => upd('operator', v)" size="small" style="width:140px">
                    <el-option label="存在" value="exists_true"></el-option>
                    <el-option label="不存在" value="exists_false"></el-option>
                  </el-select>
                </div>
                <div class="prop-row" v-if="['eq','ne','contains','not_contains','regex'].includes(stepConfig.fields.elementParams.operator || '') && stepConfig.fields.elementParams.extract !== 'exists'">
                  <label class="prop-label">期望值</label>
                  <el-input :model-value="stepConfig.fields.elementParams.expected || ''" @update:modelValue="v => upd('expected', v)" size="small" class="prop-input-wide"></el-input>
                </div>
              </template>
            </div>
          </template>

          <template v-if="stepConfig.type === 'imglocate'">
            <div class="img-prop-preview">
              <img :src="selectedStep.image" id="imgConfigPreview" @load="renderImgConfigGrid" />
              <canvas id="imgConfigCanvas" @click="onGridCellClick"></canvas>
            </div>
            <div class="prop-row"><label class="prop-label">操作</label>
              <el-radio-group :model-value="selectedStep.action" @update:modelValue="v => upd('action', v)" size="small">
                <el-radio-button label="click">点击</el-radio-button>
                <el-radio-button label="wait_show">等待显示</el-radio-button>
                <el-radio-button label="wait_hide">等待消失</el-radio-button>
              </el-radio-group>
            </div>
            <template v-if="selectedStep.action === 'click'">
              <div class="prop-row"><label class="prop-label">横向分割</label>
                <el-slider :model-value="selectedStep.grid_h" @update:modelValue="v => upd('grid_h', v)" :min="1" :max="15" show-stops style="flex:1"></el-slider>
                <span class="prop-val">{{ selectedStep.grid_h }}</span>
              </div>
              <div class="prop-row"><label class="prop-label">纵向分割</label>
                <el-slider :model-value="selectedStep.grid_v" @update:modelValue="v => upd('grid_v', v)" :min="1" :max="15" show-stops style="flex:1"></el-slider>
                <span class="prop-val">{{ selectedStep.grid_v }}</span>
              </div>
              <div class="prop-row"><label class="prop-label">点击列</label>
                <el-input-number :model-value="selectedStep.click_col" @update:modelValue="v => upd('click_col', v)" :min="0" :max="Math.max(selectedStep.grid_h-1,0)" size="small"></el-input-number>
              </div>
              <div class="prop-row"><label class="prop-label">点击行</label>
                <el-input-number :model-value="selectedStep.click_row" @update:modelValue="v => upd('click_row', v)" :min="0" :max="Math.max(selectedStep.grid_v-1,0)" size="small"></el-input-number>
              </div>
            </template>
            <div class="prop-row"><label class="prop-label">超时</label>
              <el-input-number :model-value="selectedStep.timeout" @update:modelValue="v => upd('timeout', v)" :min="1" :max="60" size="small"></el-input-number>
              <span style="color:#888;font-size:12px;margin-left:4px">秒</span>
            </div>
            <div class="prop-row"><label class="prop-label">阈值</label>
              <el-input :model-value="selectedStep.threshold ?? ''" @update:modelValue="v => upd('threshold', v===''?null:parseFloat(v))" size="small" placeholder="默认 0.8" style="width:120px"></el-input>
            </div>
          </template>

          <template v-if="stepConfig.type === 'swipe'">
            <div class="prop-row" v-for="(v, k) in stepConfig.fields" :key="k">
              <label class="prop-label">{{ {x1:'起点X',y1:'起点Y',x2:'终点X',y2:'终点Y'}[k] || k }}</label>
              <el-input-number :model-value="v" @update:modelValue="val => upd(k, val)" :min="0" :max="1" :step="0.01" size="small" style="width:140px"></el-input-number>
            </div>
          </template>

          <template v-if="stepConfig.type === 'tap'">
            <div class="prop-row"><label class="prop-label">选择器</label>
              <el-input :model-value="stepConfig.fields.selector" @update:modelValue="v => upd('selector', v)" size="small" placeholder='text="..."' class="prop-input-wide"></el-input>
            </div>
          </template>

          <template v-if="stepConfig.type === 'key'">
            <div class="prop-row"><label class="prop-label">按键</label>
              <el-select :model-value="stepConfig.fields.key || ''" @update:modelValue="v => upd('key', v)" size="small" class="prop-input-wide" filterable allow-create default-first-option placeholder="选择或输入按键...">
                <el-option v-for="opt in task.KEY_OPTIONS" :key="opt.key" :label="opt.key + ' (' + opt.desc + ')'" :value="opt.key"></el-option>
              </el-select>
            </div>
          </template>

          <template v-if="stepConfig.type === 'launchapp'">
            <div class="prop-row"><label class="prop-label">包名</label>
              <el-select :model-value="stepConfig.fields.package || ''" @update:modelValue="v => upd('launchapp', v)" size="small" class="prop-input-wide" filterable allow-create default-first-option placeholder="选择或输入包名...">
                <el-option v-for="pkg in task.appsCache.value" :key="pkg" :label="pkg" :value="pkg"></el-option>
              </el-select>
            </div>
          </template>

          <template v-if="stepConfig.type === 'wait'">
            <div class="prop-row"><label class="prop-label">秒数</label>
              <el-input-number :model-value="stepConfig.fields.seconds" @update:modelValue="v => upd('wait', v)" :min="0.1" :step="0.5" size="small"></el-input-number>
            </div>
          </template>

          <template v-if="stepConfig.type === 'code'">
            <div class="prop-row prop-code-row">
              <el-input type="textarea" :model-value="selectedStep.code" @update:modelValue="v => upd('code', v)" :rows="5" class="prop-textarea"></el-input>
            </div>
          </template>

          <div class="prop-row">
            <label class="prop-label">备注</label>
            <el-input :model-value="selectedStep.remark || ''" @update:modelValue="v => upd('remark', v)" size="small" class="prop-input-wide" placeholder="添加备注..."></el-input>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="prop-empty">点击步骤查看和编辑属性</div>
      </template>
    </template>
  </div>
</div>
`;

export default {
  name: 'InspectorPane',
  template: TEMPLATE,

  setup() {
    const task   = inject('task');
    const device = inject('device');
    const msg    = inject('msg');
    const pom    = inject('pom');

    const activeTab       = ref('props');
    const nodeFilterText  = ref('');
    const treeRef         = ref(null);

    // selecting a node on the canvas auto-switches to detail tab
    watch(() => device.selectedNode.value, (node) => {
      if (node) activeTab.value = 'detail';
    });

    // selecting a step auto-switches back to props tab
    watch(() => task.selectedStepIndex.value, (i) => {
      if (i >= 0) activeTab.value = 'props';
    });

    watch(nodeFilterText, (val) => {
      treeRef.value && treeRef.value.filter(val);
    });

    const selectedStep = computed(() => {
      const i = task.selectedStepIndex.value;
      return (i >= 0 && i < task.steps.value.length) ? task.steps.value[i] : null;
    });

    const stepConfig = computed(() => {
      return selectedStep.value ? task.selectedStepConfig(selectedStep.value) : null;
    });

    // 节点详情：过滤空值（空字符串 / null / undefined / false 中 falsy 的字符串属性都不展示）。
    // Flutter / 非原生渲染框架常导致 text/resourceId/xpath 空字符串 — 显示出来反而像"字段丢了"。
    // 数字 0、布尔 false 仍要显示（语义有意义，如 index=0、clickable=false）。
    const selectedNodeDetails = computed(() => {
      const node = device.selectedNode.value;
      if (!node) return [];
      const HIDDEN = new Set(['children', '_id', '_parentId', 'bounds']);
      const isEmpty = (v) => v === null || v === undefined || v === '';
      return Object.entries(node)
        .filter(([k, v]) => !HIDDEN.has(k) && !isEmpty(v))
        .map(([key, value]) => {
          let display;
          if (key === 'rect' && value && typeof value === 'object') {
            display = `x=${value.x}, y=${value.y}, w=${value.width}, h=${value.height}`;
          } else if (value && typeof value === 'object') {
            try { display = JSON.stringify(value); } catch { display = String(value); }
          } else {
            display = String(value);
          }
          return { key, value: display };
        });
    });

    function upd(field, value) {
      task.updateStepField(task.selectedStepIndex.value, field, value, device.serial.value);
      nextTick(() => renderImgConfigGrid());
    }

    function handleTreeNodeClick(data) {
      device.selectNode(data);
      activeTab.value = 'detail';
    }

    function handleTreeMouseEnter(data) {
      device.hoveredNode.value = data;
      if (window._renderHierarchyCanvas) window._renderHierarchyCanvas();
    }

    function handleTreeMouseLeave() {
      device.hoveredNode.value = null;
      if (window._renderHierarchyCanvas) window._renderHierarchyCanvas();
    }

    function filterNode(value, data) {
      if (!value) return true;
      const label = (data.label || '').toLowerCase();
      return label.includes(value.toLowerCase());
    }

    function insertStepFromElement() {
      if (!device.selectedNode.value) return;
      const step = task.elementFromNode(device.selectedNode.value);
      task.steps.value.push(step);
      task.saveCurrentTask(device.serial.value).catch(() => {});
      task.selectStep(task.steps.value.length - 1);
      msg.success(`已插入: ${step.code}`);
    }

    function addLocatorToPom() {
      const node = device.selectedNode.value;
      if (!node) return;
      if (!pom.currentFile.value) {
        msg.warn('请先在 POM 采集 tab 选择或新建 Page');
        return;
      }
      // 复用 POM 采集流程：弹命名对话框、填 selector、确认后写入当前 page
      pom.beginCapture(node);
    }

    function copyVal(value) {
      navigator.clipboard.writeText(String(value)).catch(() => {});
      msg.success('已复制');
    }

    // ── Image grid canvas ─────────────────────────────────────────────────
    function renderImgConfigGrid() {
      const canvas = document.querySelector('#imgConfigCanvas');
      const img    = document.querySelector('#imgConfigPreview');
      if (!canvas || !img || !img.naturalWidth) return;
      const imgRect  = img.getBoundingClientRect();
      const wrapRect = img.parentElement.getBoundingClientRect();
      const offX = imgRect.left - wrapRect.left;
      const offY = imgRect.top  - wrapRect.top;
      const rW = imgRect.width, rH = imgRect.height;
      canvas.style.left = offX + 'px'; canvas.style.top = offY + 'px';
      canvas.style.width = rW + 'px';  canvas.style.height = rH + 'px';
      canvas.width  = rW * (window.devicePixelRatio || 1);
      canvas.height = rH * (window.devicePixelRatio || 1);
      const ctx = canvas.getContext('2d');
      const dpr = window.devicePixelRatio || 1;
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, rW, rH);
      const step = selectedStep.value;
      if (!step || step._type !== 'imglocate') return;
      const cols = step.grid_h, rows = step.grid_v;
      const cw = rW / cols, ch = rH / rows;
      ctx.strokeStyle = 'rgba(255,255,255,0.6)'; ctx.lineWidth = 1;
      for (let c = 1; c < cols; c++) { ctx.beginPath(); ctx.moveTo(c*cw, 0); ctx.lineTo(c*cw, rH); ctx.stroke(); }
      for (let r = 1; r < rows; r++) { ctx.beginPath(); ctx.moveTo(0, r*ch); ctx.lineTo(rW, r*ch); ctx.stroke(); }
      if (step.action === 'click') {
        ctx.fillStyle = 'rgba(54,121,227,0.4)';
        ctx.fillRect(step.click_col*cw, step.click_row*ch, cw, ch);
        ctx.strokeStyle = '#3679E3'; ctx.lineWidth = 2;
        ctx.strokeRect(step.click_col*cw, step.click_row*ch, cw, ch);
        const cx = step.click_col*cw + cw/2, cy = step.click_row*ch + ch/2;
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(cx-6, cy); ctx.lineTo(cx+6, cy); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(cx, cy-6); ctx.lineTo(cx, cy+6); ctx.stroke();
      }
    }

    function onGridCellClick(e) {
      const step = selectedStep.value;
      if (!step || step._type !== 'imglocate' || step.action !== 'click') return;
      const canvas = document.querySelector('#imgConfigCanvas');
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left, y = e.clientY - rect.top;
      const cols = step.grid_h, rows = step.grid_v;
      const newCol = Math.min(Math.max(Math.floor(x / (rect.width / cols)), 0), cols - 1);
      const newRow = Math.min(Math.max(Math.floor(y / (rect.height / rows)), 0), rows - 1);
      upd('click_col', newCol);
      upd('click_row', newRow);
    }

    return {
      task, device, msg, pom, activeTab, nodeFilterText, treeRef,
      selectedStep, stepConfig, selectedNodeDetails,
      upd, handleTreeNodeClick, handleTreeMouseEnter, handleTreeMouseLeave,
      filterNode,
      insertStepFromElement, addLocatorToPom, copyVal, renderImgConfigGrid, onGridCellClick,
    };
  },
};
