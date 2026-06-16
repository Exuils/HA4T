import { reorderTask } from '../api.js';
import { fileNameFromName } from '../composables/useTask.js';
import { saveToLocalStorage, getFromLocalStorage } from '../utils.js';
import KvRow from './KvRow.js';
import CodeViewer from './CodeViewer.js';
import AllureReportsPane from './AllureReportsPane.js';

const { inject, ref, computed, nextTick, watch } = Vue;

// StepPane — 最右栏（grid-area: center），即「编辑器」面板，顶部 2 个 outer tab：
//   • caseEdit（用例编辑，默认）—— 原步骤列表 + CLI + 日志
//   • pom（POM 采集）—— 上=工具栏/page 选择/按钮组 中=元素列表 下=变量
// 中间栏（grid-area: right）= InspectorPane，不随 tab 变化。
// caseEdit 用 v-show 保留 DOM（Sortable 在 mounted 绑 stepList，destroy 会丢监听）。
const TEMPLATE = `
<div class="center">
  <div class="inspector-tabs">
    <button :class="['itab', outerTab === 'caseEdit' ? 'active' : '']"
        @click="outerTab = 'caseEdit'">用例编辑</button>
    <button :class="['itab', outerTab === 'pom' ? 'active' : '']"
        @click="onSwitchPom">POM 采集</button>
    <button :class="['itab', outerTab === 'allure' ? 'active' : '']"
        @click="outerTab = 'allure'">Allure 报告</button>
  </div>

  <!-- ╔════ 用例编辑 tab — 原步骤编辑器 ═══════════════════════════════ ╗ -->
  <div v-show="outerTab === 'caseEdit'" class="case-edit-region">
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
      <el-tooltip content="查看源码（只读）" placement="top">
        <el-button size="small" :disabled="!task.currentYamlFile.value" @click="openCaseSource">
          <el-icon><Reading /></el-icon>
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
      <div v-for="(s, i) in task.steps.value" :key="s._id"
          :class="['step-row',
                   s._type === 'imglocate' ? 'step-img' : '',
                   s._type === 'include' ? 'step-include' : '',
                   { 'step-selected': task.selectedStepIndex.value === i }]"
          :data-step-id="s._id"
          @click="task.selectStep(i)" style="position:relative">
        <div v-if="s.remark" class="step-remark">
          <span class="step-remark-icon">#</span>{{ s.remark }}
        </div>
        <span class="step-drag-handle"><el-icon><Rank /></el-icon></span>

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
          <template v-if="s._detail">
            <div class="step-detail-toggle" @click.stop="s._detailOpen = !s._detailOpen">
              详情 {{ s._detailOpen ? '▴' : '▾' }}
            </div>
            <pre v-if="s._detailOpen" class="step-detail-block">{{ s._detail }}</pre>
          </template>
        </template>

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

    <!-- LOCAL_VARS 抽屉（用例特有常量） — 与日志同款抽屉布局，放在日志上方 -->
    <div class="drawer-panel" :class="{ 'drawer-open': localVarsOpen }">
      <div class="drawer-header" @click="localVarsOpen = !localVarsOpen">
        <span>LOCAL_VARS <span class="drawer-count" v-if="Object.keys(task.localVars.value).length">({{ Object.keys(task.localVars.value).length }})</span></span>
        <el-tooltip placement="top">
          <template #content>本用例特有常量。写入用例文件顶层 <code>LOCAL_VARS = {...}</code>，代码里 <code>LOCAL_VARS["key"]</code>。<br>跨用例共享的常量请去 POM 的「全局 VARS」</template>
          <el-icon class="kv-help" @click.stop><QuestionFilled /></el-icon>
        </el-tooltip>
        <span class="drawer-arrow">{{ localVarsOpen ? '▼' : '▲' }}</span>
      </div>
      <div class="drawer-body" v-show="localVarsOpen">
        <KvRow
          v-for="(_, k) in task.localVars.value"
          :key="k"
          :key-name="k"
          v-model="task.localVars.value[k]"
          @rename="renameLocalVar"
          @remove="deleteLocalVar(k)"
          @value-blur="saveTaskDebounced"
        ></KvRow>
        <div class="kv-empty" v-if="Object.keys(task.localVars.value).length === 0">空 — 本用例独有的常量（账号 / 文案 / 时间戳种子等）</div>
        <el-button text size="small" @click="addLocalVar" class="kv-add-btn"><el-icon><Plus /></el-icon> 添加</el-button>
      </div>
    </div>

    <!-- Log panel -->
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
  </div>

  <!-- ╔════ POM 采集 tab — 上/中/下三段 ═══════════════════════════════ ╗ -->
  <div v-if="outerTab === 'pom'" class="pom-pane">
    <!-- 上：当前 page 状态 + 工具栏（一行：page 选择 + 按钮组） -->
    <div class="pom-pane-header">
      <div class="pom-status-row">
        <span class="pom-current-page" v-if="pom.currentFile.value">
          采集中 · <b>{{ pom.page.value }}</b> · {{ Object.keys(pom.elements.value).length }} 个元素
        </span>
        <span class="pom-current-page" v-else style="color:var(--fg-2)">未选择 Page — 请先选择或新建</span>
        <span class="pom-hint">双击控件 → selector / 框选区域 → 图像</span>
      </div>

      <div class="pom-toolbar-row">
        <el-select :model-value="pom.currentFile.value" @update:modelValue="onSelectPage"
            placeholder="选择 Page" size="small" filterable class="pom-page-select">
          <el-option v-for="p in pom.pages.value" :key="p.filename"
              :label="p.page + ' (' + p.element_count + ')'" :value="p.filename"></el-option>
        </el-select>
        <el-button size="small" @click="newPageDialogVisible = true">新建</el-button>
        <el-popconfirm title="确定删除该 Page?" @confirm="onDeletePage">
          <template #reference>
            <el-button size="small" type="danger" :disabled="!pom.currentFile.value">删除</el-button>
          </template>
        </el-popconfirm>
        <el-button v-if="!verify.verifyMode.value" size="small" type="primary"
            :disabled="!pom.currentFile.value" @click="verify.beginVerify">验证</el-button>
        <template v-else>
          <el-tooltip content="重新截图 + 重扫未找到的元素 — 已通过的永远保留，直到点「完成验证」清空" placement="top">
            <el-button size="small" @click="verify.rescanPending"><el-icon><RefreshRight /></el-icon> 刷新未找到</el-button>
          </el-tooltip>
          <el-button size="small" type="success" @click="verify.endVerify">完成验证</el-button>
        </template>
        <el-button size="small" :disabled="!pom.currentFile.value" @click="openPomSource"
            title="查看 pom/&lt;page&gt;.py 源码（只读）">
          <el-icon><Reading /></el-icon>
        </el-button>
      </div>

      <!-- 平台 tab —— 显示当前平台分桶；切换只换显示，不动数据 -->
      <div class="pom-platform-row" v-if="pom.currentFile.value">
        <span class="pom-platform-label">平台</span>
        <el-radio-group :model-value="pom.currentPlatform.value"
            @update:modelValue="v => pom.currentPlatform.value = v" size="small">
          <el-radio-button label="android">Android</el-radio-button>
          <el-radio-button label="ios">iOS</el-radio-button>
          <el-radio-button label="harmony">Harmony</el-radio-button>
        </el-radio-group>
        <span class="pom-platform-hint">切换只换显示。新采集进入当前选中平台的分桶；image 元素跨平台共享。</span>
      </div>

      <!-- 当前 page 元数据：desc / triggers，单行紧凑（用 prepend 替代独立 label）-->
      <div class="pom-meta-row" v-if="pom.currentFile.value">
        <el-input :model-value="pom.desc.value" @update:modelValue="v => pom.desc.value = v" @blur="pom.saveCurrentPage" size="small" placeholder="如：登录页">
          <template #prepend>desc</template>
        </el-input>
        <el-input :model-value="pom.triggers.value" @update:modelValue="v => pom.triggers.value = v" @blur="pom.saveCurrentPage" size="small" placeholder="登录,login">
          <template #prepend>triggers</template>
        </el-input>
      </div>

      <div class="pom-tools-verify-status" v-if="verify.verifyMode.value">
        <span class="verify-count">
          已找到 {{ countByStatus('found') }} / {{ totalSelectorElements }} 个元素
        </span>
        <span class="verify-pending" v-if="countByStatus('pending') > 0">
          · 扫描中 {{ countByStatus('pending') }}
        </span>
        <span class="verify-notfound" v-if="countByStatus('not_found') > 0" style="color:var(--el-color-danger)">
          · 未找到 {{ countByStatus('not_found') }}
        </span>
        <span v-if="countByStatus('unsupported') > 0" style="color:#b88cf9">
          · 平台不支持 {{ countByStatus('unsupported') }}
        </span>
      </div>
    </div>

    <!-- 中：元素列表（占满，唯一滚动区） -->
    <div class="pom-pane-body">
      <div class="pom-section" v-if="pom.currentFile.value">
        <div class="prop-section-title">元素</div>
        <template v-if="Object.keys(pom.elements.value).length === 0">
          <div class="prop-empty" style="font-size:11px">双击截图控件 / 框选图像区域来采集</div>
        </template>
        <el-tree
          v-else
          :data="pom.elementTree.value"
          node-key="name"
          default-expand-all
          :expand-on-click-node="false"
          :indent="14"
          draggable
          :allow-drag="canDragNow"
          :allow-drop="allowPomDrop"
          @node-drop="onPomNodeDrop"
          class="pom-el-tree">
          <template #default="{ data: nodeData }">
            <div class="pom-el-card" :class="statusClass(nodeData.name)"
                @mouseenter.stop="onPomRowHover(nodeData.name)"
                @mouseleave.stop="onPomRowHover('')">
              <div class="pom-el-row" v-if="editingElementName !== nodeData.name">
                <el-icon class="pom-drag-handle"
                    title="拖动调整层级 / 顺序"
                    @mousedown="armDrag"><Rank /></el-icon>
                <template v-if="nodeData.sel && nodeData.sel.image">
                  <img v-if="pom.imageCache.value[nodeData.sel.image]"
                      :src="pom.imageCache.value[nodeData.sel.image]"
                      class="pom-el-thumb" :title="nodeData.sel.image" />
                  <span v-else class="pom-el-thumb pom-el-thumb-missing" :title="nodeData.sel.image">[image]</span>
                  <span class="pom-el-name" :title="nodeData.name">{{ nodeData.name }}</span>
                  <span class="pom-el-sel" :title="nodeData.sel.image">{{ nodeData.sel.image }}</span>
                </template>
                <template v-else-if="nodeData.sel">
                  <span class="pom-el-name" :title="nodeData.name">{{ nodeData.name }}</span>
                  <span class="pom-el-sel" :title="JSON.stringify(nodeData.sel)">{{ formatSelector(nodeData.sel) }}</span>
                </template>
                <template v-else>
                  <span class="pom-el-name" :title="nodeData.name">{{ nodeData.name }}</span>
                  <span class="pom-el-sel pom-el-sel-missing" :title="'未在 ' + pom.currentPlatform.value + ' 上采集'">未采集 ({{ pom.currentPlatform.value }})</span>
                </template>
                <template v-if="verify.verifyMode.value">
                  <el-icon v-if="statusOf(nodeData.name) === 'pending'" class="is-loading" style="flex-shrink:0"><Loading /></el-icon>
                  <span v-else-if="statusOf(nodeData.name) === 'not_found'" class="pom-el-status-tag tag-notfound"
                      :title="(verify.results.value[nodeData.name] && verify.results.value[nodeData.name].error) || ''">未找到</span>
                  <span v-else-if="statusOf(nodeData.name) === 'unsupported'" class="pom-el-status-tag tag-unsupported">平台不支持</span>
                </template>
                <el-tooltip v-if="nodeData.doc" :content="nodeData.doc" placement="top" :show-after="200">
                  <el-icon class="pom-el-doc-icon" style="flex-shrink:0;color:var(--fg-2);cursor:help"><InfoFilled /></el-icon>
                </el-tooltip>
                <el-button size="small" v-if="!(nodeData.sel && nodeData.sel.image)"
                    :disabled="!nodeData.sel"
                    @click.stop="verify.flashOne(nodeData.name, nodeData.sel)"
                    title="高亮 3 秒（仅当前平台 selector 可用时）"><el-icon><View /></el-icon></el-button>
                <el-button size="small" @click.stop="beginEditElement(nodeData.name, nodeData.sel)" title="编辑"><el-icon><Edit /></el-icon></el-button>
                <el-button size="small" @click.stop="pom.removeElement(nodeData.name)" title="删除（子节点会上升到当前父级）"><el-icon><Close /></el-icon></el-button>
              </div>
              <!-- ── 编辑状态 ── -->
              <div class="pom-el-edit" v-else>
                <div class="prop-row" style="margin-bottom:4px">
                  <label class="prop-label">名称</label>
                  <el-input v-model="editingName" size="small" autofocus></el-input>
                </div>
                <div class="prop-row" style="margin-bottom:4px;align-items:flex-start">
                  <label class="prop-label" style="padding-top:5px">说明</label>
                  <el-input v-model="editingDoc" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }" size="small" placeholder="可选 — 给 AI / 阅读者的元素说明"></el-input>
                </div>
                <div class="prop-row" style="margin-bottom:4px">
                  <label class="prop-label">父元素</label>
                  <el-select v-model="editingParent" size="small" clearable filterable placeholder="（顶层）"
                      style="flex:1">
                    <el-option
                      v-for="opt in parentOptions(nodeData.name)"
                      :key="opt"
                      :label="opt"
                      :value="opt"
                    ></el-option>
                  </el-select>
                </div>
                <!-- 框选图像入口：编辑状态下把当前元素转为图像定位 -->
                <div class="prop-row" style="margin-bottom:4px">
                  <label class="prop-label"></label>
                  <el-button size="small" type="warning"
                      :disabled="!pom.captureMode.value"
                      @click="convertToImageFromEdit(nodeData.name)"
                      title="框选截图区域替换为图像定位">📷 框选图像</el-button>
                  <span style="font-size:11px;color:var(--fg-2);margin-left:6px">如果当前定位不好用，转为图像</span>
                </div>
                <template v-if="editingSelector.image">
                  <div class="prop-row" style="margin-bottom:4px;align-items:flex-start">
                    <label class="prop-label">图像</label>
                    <div style="flex:1">
                      <img v-if="pom.imageCache.value[editingSelector.image]"
                          :src="pom.imageCache.value[editingSelector.image]"
                          class="pom-el-preview" />
                      <div style="font-size:11px;color:var(--fg-2);margin-top:4px;word-break:break-all">{{ editingSelector.image }}</div>
                    </div>
                  </div>
                </template>
                <template v-else>
                  <div class="prop-row" v-for="key in SELECTOR_KEYS" :key="key" style="margin-bottom:4px">
                    <label class="prop-label">{{ SELECTOR_LABELS[key] }}</label>
                    <el-input v-if="key !== 'index'" :model-value="editingSelector[key] || ''" @update:modelValue="v => editingSelector[key] = v" size="small" :placeholder="key === 'xpath' ? '可选，复杂选择器' : ''"></el-input>
                    <el-input-number v-else :model-value="editingSelector.index === undefined ? null : editingSelector.index" @update:modelValue="v => editingSelector.index = (v === null || v === undefined) ? undefined : v" :min="0" size="small" controls-position="right"></el-input-number>
                  </div>
                </template>
                <div style="display:flex;gap:6px;justify-content:flex-end;margin-top:6px">
                  <el-button size="small" @click="cancelEditElement">取消</el-button>
                  <el-button size="small" type="primary" @click="commitEditElement(nodeData.name)">保存</el-button>
                </div>
              </div>
      <div class="drawer-header" @click="globalVarsOpen = !globalVarsOpen">
        <span>全局 VARS <span class="drawer-count" v-if="Object.keys(pom.metaVars.value).length">({{ Object.keys(pom.metaVars.value).length }})</span></span>
        <el-tooltip placement="top">
          <template #content>跨用例共享常量（包名 / 基础 URL / 测试账号等）。写入 <code>pom/_meta.py</code>，代码里 <code>VARS["key"]</code>。<br>本用例特有的常量请在「用例编辑」tab 底部的 LOCAL_VARS 里加</template>
          <el-icon class="kv-help" @click.stop><QuestionFilled /></el-icon>
        </el-tooltip>
        <span class="drawer-arrow">{{ globalVarsOpen ? '▼' : '▲' }}</span>
      </div>
      <div class="drawer-body" v-show="globalVarsOpen">
        <KvRow
          v-for="(_, k) in pom.metaVars.value"
          :key="k"
          :key-name="k"
          v-model="pom.metaVars.value[k]"
          @rename="renameMetaVar"
          @remove="deleteMetaVar(k)"
          @value-blur="pom.saveMeta"
        ></KvRow>
        <div class="kv-empty" v-if="Object.keys(pom.metaVars.value).length === 0">空 — 点 + 添加（如 package / base_url / username）</div>
        <el-button text size="small" @click="addMetaVar" class="kv-add-btn"><el-icon><Plus /></el-icon> 添加</el-button>
      </div>
    </div>
  </div>

  <!-- ╔════ Allure 报告 tab — 列出工作区下所有报告 ══════════════════════ ╗ -->
  <AllureReportsPane v-if="outerTab === 'allure'" />

  <!-- ── 用例编辑设置对话框（保留原位置） ──────────────────────────── -->
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

  <!-- ── POM 新建 Page 对话框 ──────────────────────────────────────── -->
  <el-dialog v-model="newPageDialogVisible" title="新建 Page" width="420px" :close-on-click-modal="false">
    <div class="prop-row" style="margin-bottom:8px">
      <label class="prop-label">Page 名</label>
      <el-input v-model="newPageName" size="small" placeholder="如 LoginPage" @keyup.enter="onCreatePage" autofocus></el-input>
    </div>
    <div class="prop-row">
      <label class="prop-label">描述</label>
      <el-input v-model="newPageDesc" size="small" placeholder="如 登录页"></el-input>
    </div>
    <template #footer>
      <el-button size="small" @click="newPageDialogVisible = false">取消</el-button>
      <el-button size="small" type="primary" @click="onCreatePage">创建</el-button>
    </template>
  </el-dialog>

  <!-- ── POM 命名元素对话框（采集确认） ────────────────────────────── -->
  <el-dialog v-model="pom.nameDialogVisible.value" title="命名元素" width="520px" :close-on-click-modal="false">
    <div class="prop-row" style="margin-bottom:8px">
      <label class="prop-label">元素名</label>
      <el-input v-model="pom.pendingName.value" size="small" placeholder="如 登录按钮 / login_button" @keyup.enter="pom.confirmCapture(msg)" autofocus></el-input>
    </div>
    <div class="prop-row" style="margin-bottom:8px;align-items:flex-start">
      <label class="prop-label" style="padding-top:5px">说明</label>
      <el-input v-model="pom.pendingDoc.value" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" size="small" placeholder="可选 — 给 AI / 阅读者的元素说明（如「列表项模板，用例追加 [index] 选第几个」）。落到 pom/<page>.py 该元素上方的 # 注释。"></el-input>
    </div>
    <div class="prop-row" style="margin-bottom:8px">
      <label class="prop-label">父元素</label>
      <el-select v-model="pom.pendingParent.value" size="small" clearable filterable placeholder="（顶层 / 默认）" style="flex:1">
        <el-option
          v-for="opt in Object.keys(pom.elements.value)"
          :key="opt"
          :label="opt"
          :value="opt"
        ></el-option>
      </el-select>
    </div>
    <template v-if="pom.pendingSelector.value && pom.pendingSelector.value.image">
      <div style="font-size:11px;color:var(--fg-2);margin:8px 0 4px">图像预览（保存后用 dev.click(image=...) 模板匹配定位）</div>
      <img v-if="pom.imageCache.value[pom.pendingSelector.value.image]"
          :src="pom.imageCache.value[pom.pendingSelector.value.image]"
          class="pom-el-preview" />
      <div style="font-size:11px;color:var(--fg-2);margin-top:4px;word-break:break-all">{{ pom.pendingSelector.value.image }}</div>
    </template>
    <template v-else>
      <div style="font-size:11px;color:var(--fg-2);margin:8px 0 4px">选择器（可编辑；留空字段保存时会自动剔除）</div>
      <div class="prop-row" v-for="key in SELECTOR_KEYS" :key="key" style="margin-bottom:4px">
        <label class="prop-label">{{ SELECTOR_LABELS[key] }}</label>
        <el-input v-if="key !== 'index'"
            :model-value="(pom.pendingSelector.value && pom.pendingSelector.value[key]) || ''"
            @update:modelValue="v => pom.setPendingSelectorField(key, v)"
            size="small"></el-input>
        <el-input-number v-else
            :model-value="pom.pendingSelector.value && pom.pendingSelector.value.index !== undefined ? pom.pendingSelector.value.index : null"
            @update:modelValue="v => pom.setPendingSelectorField('index', (v === null || v === undefined) ? undefined : v)"
            :min="0" size="small" controls-position="right"></el-input-number>
      </div>
    </template>
    <template #footer>
      <el-button size="small" @click="pom.nameDialogVisible.value = false">取消</el-button>
      <el-button size="small" type="primary" @click="pom.confirmCapture(msg)">确认</el-button>
    </template>
  </el-dialog>

  <CodeViewer v-model="codeViewerVisible" :path="codeViewerPath" />
</div>
`;

export default {
  name: 'StepPane',
  template: TEMPLATE,
  components: { KvRow, CodeViewer, AllureReportsPane },
  setup() {
    const task   = inject('task');
    const device = inject('device');
    const runner = inject('runner');
    const undo   = inject('undo');
    const msg    = inject('msg');
    const pom    = inject('pom');
    const verify = inject('verify');

    // 顶层 tab：'caseEdit'（默认）| 'pom'。从 localStorage 恢复，刷新页面回到上次位置。
    const outerTab = ref(getFromLocalStorage('outerTab', 'caseEdit'));
    watch(outerTab, (v) => saveToLocalStorage('outerTab', v));

    // 启动时若停留在 POM tab：拉 page 列表 + 元数据 + 上次选中的 page（usePom
    // 内 currentFile 已经从 localStorage 读出来了，这里只是触发实时加载验证文件
    // 还存在并拿最新内容；文件没了的话 selectPage 内部会清状态并报错提示）。
    if (outerTab.value === 'pom') {
      pom.loadPages();
      pom.loadMeta();
      if (pom.currentFile.value) {
        pom.selectPage(pom.currentFile.value, msg);
      }
      pom.captureMode.value = true;
    }

    // 切到 POM tab：刷新数据 + 自动开启采集；离开/验证中按互斥规则控制采集开关
    function onSwitchPom() {
      outerTab.value = 'pom';
      pom.loadPages();
      pom.loadMeta();
      pom.captureMode.value = true;   // 进入即采集，无需手动开关
    }
    watch(outerTab, (t) => {
      if (t !== 'pom') {
        verify.endVerify();
        pom.captureMode.value = false;
      } else {
        // 兜底：任何路径下停留在 POM tab 都保持采集 ON（除非验证中互斥）
        if (!verify.verifyMode.value) pom.captureMode.value = true;
      }
    });
    // 验证开始时强制关采集；结束时恢复采集（保持 POM tab 语义）
    watch(() => verify.verifyMode.value, (on) => {
      if (outerTab.value !== 'pom') return;
      pom.captureMode.value = !on;
    });

    // ── 原 StepPane state ────────────────────────────────────────────────
    const cliText        = ref('');
    const cliPrefix      = ref('');
    const cliPlaceholder = ref('tap: UI element');
    const slashVisible   = ref(false);
    const slashIdx       = ref(0);
    const slashItems     = ref([]);
    const cliFlash       = ref(false);
    const stepListRef    = ref(null);
    const cliInputRef    = ref(null);
    let _stepIdCounter = Date.now();
    function _nextStepId() { return _stepIdCounter++; }

    let sortableInstance = null;

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
          // 根据 DOM 实际视觉顺序重建 steps 数组，避免 :key="s._id" + sortable DOM 移动冲突
          const container = evt.to || evt.from;
          if (container) {
            const domIds = Array.from(container.querySelectorAll('[data-step-id]')).map(el => el.dataset.stepId);
            const idMap = {};
            task.steps.value.forEach(s => { idMap[s._id] = s; });
            const reordered = domIds.map(id => idMap[id]).filter(Boolean);
            if (reordered.length === task.steps.value.length) {
              task.steps.value = reordered;
            }
          }
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

    async function screenshotAndDumpHierarchyProxy() {
      window._screenshotAndDump && await window._screenshotAndDump();
    }
    function runFromHere(i) { runner.runFromStep(i, screenshotAndDumpHierarchyProxy, msg); }
    function runSingle(i)   { runner.runSingleStep(i, screenshotAndDumpHierarchyProxy, msg); }
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

    async function toggleInclude(i) {
      const s = task.steps.value[i];
      if (!s || s._type !== 'include') return;
      const opening = !s._open;
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
    async function applySettings() {
      task.settingsVisible.value = false;
      // 新建用例：文件名由用例名推导（fileNameFromName，单一来源）。
      // 若同名文件已存在，覆盖前二次确认；用户取消则中止保存。
      if (!task.currentYamlFile.value) {
        const candidate = fileNameFromName(task.taskName.value || '新建用例');
        const clash = (task.yamlFiles.value || []).some(f => f.filename === candidate);
        if (clash) {
          try {
            await ElementPlus.ElMessageBox.confirm(
              `用例「${candidate}」已存在，继续将覆盖原文件。是否覆盖？`,
              '文件已存在',
              { type: 'warning', confirmButtonText: '覆盖', cancelButtonText: '取消' },
            );
          } catch (e) {
            task.settingsVisible.value = true;  // 取消：留在设置弹窗，便于改名
            return;
          }
        }
        task.currentYamlFile.value = candidate;
      }
      task.saveCurrentTask(device.serial.value).catch(() => {});
      task.refreshYamlFiles();
    }
    function handleRunCommand(cmd) {
      if (cmd === 'run') runner.runAllSteps(screenshotAndDumpHierarchyProxy, msg, device.serial.value);
      else if (cmd === 'run-allure') runner.runAllStepsAllure(msg);
    }

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
      } else if (cliPrefix.value === 'launchapp' || cliPrefix.value === 'stopapp' || cliPrefix.value === 'restartapp' || cliPrefix.value === 'clearapp') {
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
      } else if (cliPrefix.value === 'pom') {
        const q = cliText.value.toLowerCase();
        slashVisible.value = true;
        slashItems.value = task.pomElementsCache.value
          .filter(it => {
            if (!q) return true;
            // 支持 `page.element` 整体过滤、单独过滤、忽略大小写
            return (it.page + '.' + it.name).toLowerCase().includes(q)
                || it.page.toLowerCase().includes(q)
                || it.name.toLowerCase().includes(q);
          })
          .slice(0, 30)
          .map(it => ({
            key: `${it.page}.${it.name}`,
            desc: it.doc ? it.doc : (it.hasImage ? '图像元素' : it.platforms.join(',')),
            isPom: true,
            pomPage: it.page,
            pomName: it.name,
            hasImage: it.hasImage,
          }));
        slashIdx.value = 0;
      } else {
        slashVisible.value = false;
      }
    }
    function addIncludeStep(filename) {
      undo.pushUndo(task.steps.value);
      const step = task.buildIncludeStep(filename);
      step._id = _nextStepId();
      const idx = task.steps.value.length;
      task.steps.value.push(step);
      task.saveCurrentTask(device.serial.value).catch(() => {});
      task.selectedStepIndex.value = idx;
    }

    function addPomRefStep(page, name) {
      undo.pushUndo(task.steps.value);
      // 默认动作 click —— 用户可以在步骤属性里改成 wait / exists / get_text 等
      const step = {
        _type: 'pom_ref',
        _pomRef: { page, name, action: 'click' },
        code: `dev.click(${page}.ELEMENTS[${JSON.stringify(name)}])`,
        _open: false,
        _id: _nextStepId(),
      };
      const idx = task.steps.value.length;
      task.steps.value.push(step);
      task.saveCurrentTask(device.serial.value).catch(() => {});
      task.selectedStepIndex.value = idx;
    }
    function submitCli() {
      let line = cliText.value.trim();
      if (!line && !cliPrefix.value) return;
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
      const newStep = { code, remark: '', _status: 'pending', _detail: '', _duration: null, _id: _nextStepId() };
      if (['stopapp','restartapp','clearapp','screenshot','input','assert'].includes(action)) {
        newStep._type = action;
      }
      task.steps.value.push(newStep);
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
      if (item.isPom) {
        // 选了具体 POM 元素 → 插一个引用步骤
        addPomRefStep(item.pomPage, item.pomName);
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
      if (item.action === 'key' || item.action === 'include') {
        nextTick(() => onCliInput());
      } else if (item.action === 'launchapp' || item.action === 'stopapp' || item.action === 'restartapp' || item.action === 'clearapp') {
        const p = (task.loadApps && task.loadApps(device.platform.value, device.serial.value, msg)) || Promise.resolve();
        Promise.resolve(p).then(() => nextTick(() => onCliInput()));
      } else if (item.action === 'pom') {
        // 拉所有 POM page 元素到缓存，再展开 slash 子菜单。已有缓存秒返回。
        const p = (task.loadAllPomElements && task.loadAllPomElements()) || Promise.resolve();
        Promise.resolve(p).then(() => {
          if (!task.pomElementsCache.value.length) {
            msg && msg.warn && msg.warn('当前工作区还没有任何 POM 元素 —— 请先到「POM 采集」tab 录一个');
            cliPrefix.value = '';
            slashVisible.value = false;
            return;
          }
          nextTick(() => onCliInput());
        });
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
    window._focusCli = focusCli;
    function toggleLog() { runner.logOpen.value = !runner.logOpen.value; }

    // ─────────────────────────────────────────────────────────────────────
    // ── POM tab 内部状态 ────────────────────────────────────────────────
    // ─────────────────────────────────────────────────────────────────────
    const SELECTOR_KEYS = ['text', 'resourceId', 'className', 'xpath', 'description', 'index'];
    const SELECTOR_LABELS = {
      text: '文本', resourceId: '资源ID', className: '类型',
      xpath: 'XPath', description: '描述', index: '索引',
    };

    const editingElementName = ref('');
    const editingName        = ref('');
    const editingSelector    = ref({});
    const editingDoc         = ref('');     // 编辑中的说明文本；与 pom.elementDocs[name] 同步
    const editingParent      = ref('');     // 编辑中的父元素名（空 = 顶层）

    function formatSelector(sel) {
      if (!sel) return '';
      const parts = [];
      for (const k of SELECTOR_KEYS) {
        if (sel[k] === undefined || sel[k] === null || sel[k] === '') continue;
        parts.push(k + '=' + (typeof sel[k] === 'string' ? sel[k] : JSON.stringify(sel[k])));
      }
      return parts.join(' · ');
    }
    function beginEditElement(name, sel) {
      editingElementName.value = name;
      editingName.value = name;
      editingSelector.value = { ...(sel || {}) };
      editingDoc.value = pom.elementDocs.value[name] || '';
      editingParent.value = pom.elementParents.value[name] || '';
    }
    function cancelEditElement() {
      editingElementName.value = '';
      editingName.value = '';
      editingSelector.value = {};
      editingDoc.value = '';
      editingParent.value = '';
    }
    function convertToImageFromEdit(name) {
      pom.fillImageOnElement(name, editingDoc.value, editingParent.value);
      cancelEditElement();
    }
    function commitEditElement(oldName) {
      const ok = pom.updateElement(
        oldName, editingName.value, editingSelector.value,
        editingDoc.value, editingParent.value, msg,
      );
      if (ok) cancelEditElement();
    }

    // 「父元素」下拉候选 —— 排除自己 + 自己的全部后代（防循环引用）。
    function parentOptions(self) {
      const banned = new Set([self]);
      // BFS 向下收集所有后代
      const queue = [self];
      while (queue.length) {
        const cur = queue.shift();
        for (const [c, p] of Object.entries(pom.elementParents.value)) {
          if (p === cur && !banned.has(c)) { banned.add(c); queue.push(c); }
        }
      }
      return Object.keys(pom.elements.value).filter(n => !banned.has(n));
    }

    // el-tree 拖拽：始终允许成兄弟（before/after）；变子(inner) 要不能形成循环。
    // el-tree 的 allow-drop(draggingNode, dropNode, type) 返回 false 阻止该 type。
    function allowPomDrop(dragNode, dropNode, type) {
      if (!dragNode || !dropNode) return false;
      const dragName = dragNode.data && dragNode.data.name;
      const dropName = dropNode.data && dropNode.data.name;
      if (!dragName || !dropName) return false;
      if (type === 'inner') {
        // 不能拖到自己 / 自己的后代里 —— 循环
        if (dragName === dropName) return false;
        let cursor = dropName, hops = 0;
        const seen = new Set();
        while (cursor && !seen.has(cursor) && hops++ < 1000) {
          if (cursor === dragName) return false;
          seen.add(cursor);
          cursor = pom.elementParents.value[cursor] || '';
        }
        return true;
      }
      // before / after 同层 sibling，总是允许
      return true;
    }

    // 节点放下后：根据落点位置算新 parent，调 pom.setElementParent。
    function onPomNodeDrop(dragNode, dropNode, dropType /*, ev */) {
      if (!dragNode || !dropNode) return;
      const dragName = dragNode.data && dragNode.data.name;
      if (!dragName) return;
      let newParent = '';
      if (dropType === 'inner') {
        newParent = dropNode.data.name;
      } else {
        // before / after：兄弟。新 parent = dropNode 的父；dropNode 在顶层时新 parent=''。
        const parentNode = dropNode.parent;
        if (parentNode && parentNode.data && parentNode.data.name) {
          newParent = parentNode.data.name;
        }
      }
      pom.setElementParent(dragName, newParent, msg);
      dragArmed.value = false;
    }

    // 拖拽授权：el-tree 默认整行可拖会和编辑文字 / 双击 / 点按钮的鼠标动作打架，
    // 改成「只有从把手 icon 按下才进入可拖状态」。canDragNow 由 el-tree :allow-drag 调用。
    // 全局 mouseup/dragend 兜底：松开 / 拖完后立刻 disarm，下一次必须重新从把手按。
    const dragArmed = ref(false);
    function armDrag() { dragArmed.value = true; }
    function disarmDrag() { dragArmed.value = false; }
    if (typeof window !== 'undefined') {
      window.addEventListener('mouseup', disarmDrag);
      window.addEventListener('dragend', disarmDrag);
    }
    function canDragNow(/* node */) { return dragArmed.value; }

    function onSelectPage(v) {
      verify.endVerify();
      pom.selectPage(v, msg);
    }

    // ── 查看源码（只读弹窗） ─────────────────────────────────────────
    const codeViewerVisible = ref(false);
    const codeViewerPath    = ref('');     // 相对工作区根的路径

    function openCaseSource() {
      const fn = task.currentYamlFile.value;
      if (!fn) { msg && msg.warn && msg.warn('请先选择一个用例'); return; }
      codeViewerPath.value = `testcases/${fn}`;
      codeViewerVisible.value = true;
    }
    function openPomSource() {
      const fn = pom.currentFile.value;
      if (!fn) { msg && msg.warn && msg.warn('请先选择一个 Page'); return; }
      codeViewerPath.value = `pom/${fn}`;
      codeViewerVisible.value = true;
    }

    // POM 元素行 hover：验证模式下 canvas overlay 只画 hover 的那一条 found 元素，
    // 其它隐藏；非验证模式或目标元素不是 found（待扫 / 未找到 / image / 平台不支持）
    // 直接清掉 hover —— 不画即可。
    function onPomRowHover(name) {
      if (!verify.verifyMode.value) return;
      const r = name ? verify.results.value[name] : null;
      window._pomVerifyHover = (r && r.status === 'found') ? name : '';
      if (window._renderHierarchyCanvas) window._renderHierarchyCanvas();
    }

    const newPageDialogVisible = ref(false);
    const newPageName = ref('');
    const newPageDesc = ref('');
    async function onCreatePage() {
      const name = (newPageName.value || '').trim();
      if (!name) { msg.error('请输入 Page 名'); return; }
      const ok = await pom.createPage(name, (newPageDesc.value || '').trim(), msg);
      if (ok) {
        newPageDialogVisible.value = false;
        newPageName.value = '';
        newPageDesc.value = '';
      }
    }
    async function onDeletePage() {
      verify.endVerify();
      await pom.deletePage(pom.currentFile.value, msg);
    }

    const totalSelectorElements = computed(() => Object.keys(pom.elements.value).length);
    function statusOf(name) {
      const r = verify.results.value[name];
      return r ? r.status : '';
    }
    const STATUS_CLASS = {
      found: 'pom-el-status-found', not_found: 'pom-el-status-notfound',
      pending: 'pom-el-status-pending',
      unsupported: 'pom-el-status-unsupported',
    };
    function statusClass(name) {
      if (!verify.verifyMode.value) return '';
      return STATUS_CLASS[statusOf(name)] || '';
    }
    function countByStatus(s) {
      return Object.values(verify.results.value).filter(r => r.status === s).length;
    }

    // ── 底部抽屉（log-panel 风格） ───────────────────────────────────────
    const localVarsOpen  = ref(false);   // 用例编辑 tab 的 LOCAL_VARS 抽屉
    const globalVarsOpen = ref(false);   // POM tab 的全局 VARS 抽屉

    // 用例 LOCAL_VARS 编辑：改完 debounce 写回用例文件
    let _saveTaskTimer = null;
    function saveTaskDebounced() {
      clearTimeout(_saveTaskTimer);
      _saveTaskTimer = setTimeout(() => {
        task.saveCurrentTask(device.serial.value).catch(() => {});
      }, 400);
    }
    function setLocalVar(k, v) {
      task.localVars.value[k] = v;
      saveTaskDebounced();
    }
    function renameLocalVar(oldK, newK) {
      if (!newK || newK === oldK) return;
      if (Object.prototype.hasOwnProperty.call(task.localVars.value, newK)) { msg.error('变量名已存在'); return; }
      const next = {};
      for (const [k, v] of Object.entries(task.localVars.value)) next[k === oldK ? newK : k] = v;
      task.localVars.value = next;
      saveTaskDebounced();
    }
    function deleteLocalVar(k) {
      delete task.localVars.value[k];
      saveTaskDebounced();
    }
    function addLocalVar() {
      let i = 1, k = 'var1';
      while (Object.prototype.hasOwnProperty.call(task.localVars.value, k)) { i++; k = 'var' + i; }
      task.localVars.value[k] = '';
      saveTaskDebounced();
    }

    // 全局 VARS（pom/_meta.py）同模式：mutate 优先，避免按键卡顿。
    function setMetaVar(k, v) {
      pom.metaVars.value[k] = v;
      pom.saveMeta();
    }
    function renameMetaVar(oldK, newK) {
      if (!newK || newK === oldK) return;
      if (Object.prototype.hasOwnProperty.call(pom.metaVars.value, newK)) { msg.error('变量名已存在'); return; }
      const next = {};
      for (const [k, v] of Object.entries(pom.metaVars.value)) next[k === oldK ? newK : k] = v;
      pom.metaVars.value = next;
      pom.saveMeta();
    }
    function deleteMetaVar(k) {
      delete pom.metaVars.value[k];
      pom.saveMeta();
    }
    function addMetaVar() {
      let i = 1, k = 'var1';
      while (Object.prototype.hasOwnProperty.call(pom.metaVars.value, k)) { i++; k = 'var' + i; }
      pom.metaVars.value[k] = '';
      pom.saveMeta();
    }

    return {
      task, device, runner, msg, pom, verify,
      outerTab, onSwitchPom,
      // case edit
      cliText, cliPrefix, cliPlaceholder, slashVisible, slashIdx, slashItems, cliFlash,
      stepList: stepListRef, cliInput: cliInputRef,
      initSortable,
      onFileChange, newFile, openFolder, applySettings, handleRunCommand,
      runFromHere, runSingle, deleteStep, copyStep,
      toggleInclude, openIncludedFile,
      onCliKeydown, onCliInput, submitCli, pickSlash, focusCli, toggleLog,
      // pom
      SELECTOR_KEYS, SELECTOR_LABELS,
      editingElementName, editingName, editingSelector, editingDoc, editingParent,
      formatSelector, beginEditElement, cancelEditElement, commitEditElement,
      parentOptions, allowPomDrop, onPomNodeDrop,
      canDragNow, armDrag,
      onSelectPage, onDeletePage,
      newPageDialogVisible, newPageName, newPageDesc, onCreatePage,
      codeViewerVisible, codeViewerPath, openCaseSource, openPomSource,
      onPomRowHover,
      totalSelectorElements, statusOf, statusClass, countByStatus,
      // local vars (case-level)
      localVarsOpen, globalVarsOpen,
      setLocalVar, renameLocalVar, deleteLocalVar, addLocalVar, saveTaskDebounced,
      setMetaVar, renameMetaVar, deleteMetaVar, addMetaVar,
    };
  },

  mounted() {
    nextTick(() => {
      const el = this.$refs.stepList;
      if (el) this.initSortable(el);
    });
  },
};
