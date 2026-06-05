import { saveToLocalStorage } from './utils.js';
import { listTasks, getTask, saveTask, listPackages, cleanupImages, saveImage, getImage } from './api.js';
import { API_HOST } from './config.js';

const SLASH_STEP = [
  { action: 'element', desc: '元素操作 (点击/长按/断言)' },
  { action: 'swipe', desc: '录制滑动手势 (比例坐标)' },
  { action: 'type', desc: '输入文本' },
  { action: 'key', desc: '系统按键' },
  { action: 'launchapp', desc: '启动应用' },
  { action: 'wait', desc: '等待秒数' },
  { action: 'imglocate', desc: '图片定位 (模板匹配)' },
  { action: 'code', desc: '自定义代码' },
];

const KEY_OPTIONS = [
  { key: 'home', desc: '主页键' },
  { key: 'back', desc: '返回键' },
  { key: 'menu', desc: '菜单键' },
  { key: 'volume_up', desc: '音量+' },
  { key: 'volume_down', desc: '音量-' },
  { key: 'power', desc: '电源键' },
  { key: 'camera', desc: '相机键' },
  { key: 'clear', desc: '清除键' },
  { key: 'enter', desc: '回车键' },
  { key: 'delete', desc: '删除键' },
  { key: 'dpad_up', desc: '方向键 上' },
  { key: 'dpad_down', desc: '方向键 下' },
  { key: 'dpad_left', desc: '方向键 左' },
  { key: 'dpad_right', desc: '方向键 右' },
  { key: 'search', desc: '搜索键' },
  { key: 'recent', desc: '最近任务键' },
  { key: 'notifications', desc: '通知栏' },
  { key: 'settings', desc: '系统设置' },
  { key: 'space', desc: '空格键' },
  { key: 'tab', desc: 'Tab 键' },
  { key: 'escape', desc: 'Esc 键' },
  { key: 'del', desc: 'Del 键' },
  { key: 'forward_del', desc: 'Forward Del' },
  { key: 'move_home', desc: '光标移到行首' },
  { key: 'move_end', desc: '光标移到行尾' },
  { key: 'page_up', desc: '上翻页' },
  { key: 'page_down', desc: '下翻页' },
  { key: 'caps_lock', desc: '大写锁定' },
  { key: 'break', desc: 'Break 键' },
  { key: 'insert', desc: 'Insert 键' },
  { key: 'num_lock', desc: '数字锁定' },
  { key: 'call', desc: '拨号键' },
  { key: 'endcall', desc: '挂断键' },
  { key: 'star', desc: '星号键 *' },
  { key: 'pound', desc: '井号键 #' },
  { key: 'comma', desc: '逗号键' },
  { key: 'period', desc: '句号键' },
  { key: 'alt_left', desc: '左 Alt 键' },
  { key: 'alt_right', desc: '右 Alt 键' },
  { key: 'shift_left', desc: '左 Shift 键' },
  { key: 'shift_right', desc: '右 Shift 键' },
  { key: 'ctrl_left', desc: '左 Ctrl 键' },
  { key: 'ctrl_right', desc: '右 Ctrl 键' },
];

export const StepEditorMethods = {
  // ── File operations ──

  async refreshYamlFiles() {
    try {
      const res = await listTasks();
      if (res.success) this.yamlFiles = res.data;
    } catch (err) { console.error(err); }
  },

  async loadYamlFile(filename) {
    if (!filename) { this.clearTask(); return; }
    try {
      const res = await getTask(filename);
      if (res.success) {
        this.currentYamlFile = filename;
        this.currentYamlContent = res.data.content;
        this.parseYamlToTask(res.data.content);
        if (!this.projectId) {
          this.projectId = 'proj_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
          this.saveCurrentTask();
        }
        for (let i = 0; i < this.steps.length; i++) {
          const step = this.steps[i];
          if (step._type === 'imglocate' && step.image_filename) {
            try {
              const imgRes = await getImage(step.image_filename);
              if (imgRes.success && imgRes.data && imgRes.data.data) {
                this.$set(this.steps, i, { ...step, image: 'data:image/png;base64,' + imgRes.data.data });
              } else {
                console.warn('图片加载失败:', step.image_filename, imgRes.message);
              }
            } catch (e) {
              console.warn('图片加载异常:', step.image_filename, e.message);
            }
          }
        }
        saveToLocalStorage('currentYamlFile', filename);
        this.addLog('info', `已加载: ${filename}`);
      }
    } catch (err) {
      this.$message({ showClose: true, message: `错误: ${err.message}`, type: 'error' });
    }
  },

  async saveYamlFile() {
    if (!this.currentYamlFile) return;
    this.saveCurrentTask();
    try {
      const res = await saveTask(this.currentYamlFile, this.currentYamlContent);
      if (res.success) {
        this.$message({ showClose: true, message: '已保存', type: 'success' });
        this.refreshYamlFiles();
      }
    } catch (err) {
      this.$message({ showClose: true, message: `错误: ${err.message}`, type: 'error' });
    }
  },

  newYamlFile() {
    this.clearTask();
    this.taskName = '新建用例';
    this.taskPlatform = 'android';
    this.projectId = 'proj_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
    this.settingsVisible = true;
  },

  async openTasksFolder() {
    await fetch(`${API_HOST}tasks/open-folder`, { method: 'POST' });
  },

  clearTask() {
    this.currentYamlFile = '';
    this.currentYamlContent = '';
    this.taskName = '';
    this.taskDesc = '';
    this.taskPlatform = 'android';
    this.projectId = '';
    this.steps = [];
    this.selectedStepIndex = -1;
  },

  applySettings() {
    this.settingsVisible = false;
    if (!this.currentYamlFile) {
      const safe = (this.taskName || 'untitled').replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase();
      this.currentYamlFile = safe + '.py';
    }
    this.saveCurrentTask();
    this.refreshYamlFiles();
  },

  // ── Steps parsing ──

  _parseStepCode(code, stepMeta) {
    // If metadata is provided, use it to restore structured step
    if (stepMeta) {
      if (stepMeta.stepType === 'element') {
        const s = {
          code,
          stepType: 'element',
          elementAction: stepMeta.elementAction || 'click',
          selector: stepMeta.selector || {},
          elementParams: stepMeta.elementParams || {},
          _status: 'pending', _detail: '', _duration: null
        };
        return s;
      }
      if (stepMeta.stepType === 'imglocate') {
        const s = {
          code,
          _type: 'imglocate',
          action: stepMeta.action || 'click',
          image_filename: stepMeta.image_filename,
          image: null,
          grid_h: stepMeta.grid_h || 1,
          grid_v: stepMeta.grid_v || 1,
          click_col: stepMeta.click_col || 0,
          click_row: stepMeta.click_row || 0,
          timeout: stepMeta.timeout || 10,
          threshold: stepMeta.threshold || null,
          _status: 'pending', _detail: '', _duration: null
        };
        return s;
      }
    }
    const s = { code, _status: 'pending', _detail: '', _duration: null };
    const imgMatch = code.match(/image=["']([^"']+)["']/);
    if (!imgMatch) return s;
    s._type = 'imglocate';
    s.image_filename = imgMatch[1];
    if (code.includes('click(image=')) {
      s.action = 'click';
      const gridMatch = code.match(/grid=\((\d+)\s*,\s*(\d+)\)/);
      const splitsMatch = code.match(/splits=\((\d+)\s*,\s*(\d+)\)/);
      if (gridMatch && splitsMatch) {
        s.click_col = parseInt(gridMatch[1], 10);
        s.click_row = parseInt(gridMatch[2], 10);
        s.grid_h = parseInt(splitsMatch[1], 10);
        s.grid_v = parseInt(splitsMatch[2], 10);
      } else {
        s.click_col = 0; s.click_row = 0; s.grid_h = 1; s.grid_v = 1;
      }
    } else if (code.includes('wait(image=')) {
      s.action = code.includes('reverse=True') ? 'wait_hide' : 'wait_show';
      s.grid_h = 1; s.grid_v = 1; s.click_col = 0; s.click_row = 0;
    }
    const timeoutMatch = code.match(/timeout=(\d+)/);
    s.timeout = timeoutMatch ? parseInt(timeoutMatch[1], 10) : 10;
    const thresholdMatch = code.match(/threshold=(0\.\d+)/);
    s.threshold = thresholdMatch ? parseFloat(thresholdMatch[1]) : null;
    return s;
  },

  parseYamlToTask(content) {
    const lines = content.split('\n');
    let name = '', desc = '', platform = 'android', projectId = '', inStep = false, stepBuf = [], stepMeta = null;
    const steps = [];
    const extraLines = [];
    let inExtra = true;
    for (const line of lines) {
      if (line.startsWith('# name:')) { name = line.split(':')[1].trim(); continue; }
      if (line.startsWith('# desc:')) { desc = line.split(':')[1].trim(); continue; }
      if (line.startsWith('# platform:')) { platform = line.split(':')[1].trim(); continue; }
      if (line.startsWith('# project_id:')) { projectId = line.split(':')[1].trim(); continue; }
      if (line.trim() === '# --step--') {
        if (inStep && stepBuf.length) {
          steps.push(this._parseStepCode(stepBuf.join('\n'), stepMeta));
          stepBuf = []; stepMeta = null;
        }
        inStep = true; inExtra = false;
        continue;
      }
      if (inStep) {
        const t = line.trim();
        if (t.startsWith('# @step ')) {
          try { stepMeta = JSON.parse(t.slice('# @step '.length)); } catch (e) { stepMeta = null; }
          continue;
        }
        if (t && !t.startsWith('#') && !t.startsWith('from ha4t') && !t.startsWith('connect(') && !t.startsWith('import ') && !t.startsWith('os.environ')) {
          stepBuf.push(line);
        }
      } else if (inExtra && line.trim()) {
        if (!line.startsWith('from ha4t') && !line.startsWith('connect(') && !line.startsWith('import ') && !line.startsWith('os.environ') && !line.startsWith('# name:') && !line.startsWith('# desc:') && !line.startsWith('# platform:') && !line.startsWith('# project_id:')) {
          extraLines.push(line);
        }
      }
    }
    if (inStep && stepBuf.length) {
      steps.push(this._parseStepCode(stepBuf.join('\n'), stepMeta));
    }
    this.taskName = name; this.taskDesc = desc; this.taskPlatform = platform; this.projectId = projectId;
    this.steps = steps; this._extraLines = extraLines;
  },

  taskToYaml() {
    let y = `# name: ${this.taskName || '未命名'}\n`;
    if (this.taskDesc) y += `# desc: ${this.taskDesc}\n`;
    y += `# platform: ${this.taskPlatform}\n`;
    if (this.projectId) y += `# project_id: ${this.projectId}\n`;
    y += 'import os\nos.environ["FLAGS_use_mkldnn"] = "0"\n';
    y += 'from ha4t import connect\nfrom ha4t.api import *\n';
    y += `connect(platform="${this.taskPlatform}", device_serial="${this.serial}")\n\n`;
    if (this._extraLines) this._extraLines.forEach(l => { y += l + '\n'; });
    this.steps.forEach(s => {
      y += '\n# --step--\n';
      const meta = this._stepMeta(s);
      if (meta) y += '# @step ' + JSON.stringify(meta) + '\n';
      y += s.code + '\n';
    });
    return y;
  },

  _stepMeta(s) {
    if (s.stepType === 'element') {
      return {
        stepType: 'element',
        elementAction: s.elementAction,
        selector: s.selector || {},
        elementParams: s.elementParams || {}
      };
    }
    if (s._type === 'imglocate') {
      return {
        stepType: 'imglocate',
        action: s.action,
        image_filename: s.image_filename,
        grid_h: s.grid_h || 1,
        grid_v: s.grid_v || 1,
        click_col: s.click_col || 0,
        click_row: s.click_row || 0,
        timeout: s.timeout || 10,
        threshold: s.threshold || null
      };
    }
    return null;
  },

  taskToYamlSingle(i) {
    let y = `# name: ${this.taskName}\n# platform: ${this.taskPlatform}\n`;
    y += 'import os\nos.environ["FLAGS_use_mkldnn"] = "0"\n';
    y += 'from ha4t import connect\nfrom ha4t.api import *\n';
    y += `connect(platform="${this.taskPlatform}", device_serial="${this.serial}")\n\n`;
    y += '# --step--\n' + this.steps[i].code + '\n';
    return y;
  },

  saveCurrentTask() {
    if (!this.currentYamlFile) {
      this.currentYamlFile = `untitled_${Date.now()}.py`;
      this.taskName = this.taskName || '新建用例';
      this.taskPlatform = this.platform || 'android';
      if (!this.projectId) {
        this.projectId = 'proj_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
      }
      saveToLocalStorage('currentYamlFile', this.currentYamlFile);
    }
    this.currentYamlContent = this.taskToYaml();
    saveTask(this.currentYamlFile, this.currentYamlContent).catch(() => {});
    this.steps.forEach((s) => {
      if (s._type === 'imglocate' && s.image && s.image_filename && !s._imageSaved) {
        saveImage(s.image_filename, s.image)
          .then(() => { s._imageSaved = true; })
          .catch(() => {});
      }
    });
    this.refreshYamlFiles();
  },

  ensureFile() {
    this.saveCurrentTask();
  },

  // ── Step management ──

  addStep(action, value) {
    if (action === 'imglocate') {
      this.enterCaptureMode();
      return;
    }
    if (action === 'swipe') {
      this.enterSwipeRecordMode();
      return;
    }
    if (action === 'element') {
      this.$message({ message: '请在截图中点击选择一个 UI 元素', type: 'info', duration: 3000 });
      this.elementSelectMode = true;
      return;
    }
    const code = this.stepToCode(action, value);
    const idx = this.steps.length;
    this.steps.push({ code, _status: 'pending', _detail: '', _duration: null });
    this.ensureFile();
    this.selectStep(idx);
    if (this.autoRun) this.runSingleStep(idx);
  },

  stepToCode(action, value) {
    if (action === 'imglocate') return '# 图片定位 - 等待配置';
    if (action === 'swipe') return '# 滑动 - 请在截图上录制起点和终点';
    if (action === 'element') {
      // Create a placeholder element step - code will be generated when selector is filled
      return this._generateElementCode({
        stepType: 'element',
        elementAction: 'click',
        selector: { text: value || '' },
        elementParams: {}
      });
    }
    const esc = (s) => (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n');
    const m = {
      tap: `click(text="${esc(value)}")`,
      drag: `swipe((300, 300), (300, 700))`,
      type: `type("${esc(value)}")`,
      key: `key("${esc(value)}")`,
      launchapp: `start_app("${esc(value)}")`,
      wait: `sleep(${value})`,
    };
    return m[action] || esc(value);
  },

  // ── Element step helpers ──

  _buildSelectorString(selector) {
    if (!selector) return '';
    const esc = (s) => (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t');
    const parts = [];
    if (selector.text) parts.push(`text="${esc(selector.text)}"`);
    if (selector.resourceId) parts.push(`resourceId="${esc(selector.resourceId)}"`);
    if (selector.className) parts.push(`className="${esc(selector.className)}"`);
    if (selector.xpath) parts.push(`xpath="${esc(selector.xpath)}"`);
    if (selector.description) parts.push(`description="${esc(selector.description)}"`);
    if (selector.index != null && selector.index >= 0) parts.push(`index=${selector.index}`);
    return parts.join(', ');
  },

  _generateElementCode(step) {
    const { selector, elementAction, elementParams } = step;
    const sel = this._buildSelectorString(selector);
    const p = elementParams || {};

    switch (elementAction) {
      case 'click':
        return sel ? `click(${sel})` : `click()`;
      case 'double_click':
        return `double_click(${sel}, interval=${p.interval || 0.05})`;
      case 'long_press':
        return `long_press(${sel}, duration=${p.duration || 1.0})`;
      case 'drag':
        return `drag(${sel}, dx=${p.dx || 0}, dy=${p.dy || 0}, duration=${p.dragDuration || 0.5})`;
      case 'assert': {
        if (p.extract === 'exists') {
          return `assert_element(${sel}, operator="${p.operator || 'exists_true'}")`;
        }
        const exp = p.expected ? `, expected="${p.expected}"` : '';
        return `assert_element(${sel}, operator="${p.operator || 'eq'}"${exp})`;
      }
      default:
        return `click(${sel})`;
    }
  },

  _elementFromNode(node) {
    const selector = {};
    if (node.text) selector.text = node.text;
    if (node.resourceId) selector.resourceId = node.resourceId;
    if (node._type) selector.className = node._type;
    if (node.xpath) selector.xpath = node.xpath;
    if (node.description) selector.description = node.description;
    if (node.index !== undefined && node.index !== null && node.index >= 0) selector.index = node.index;
    const step = {
      stepType: 'element',
      selector,
      elementAction: 'click',
      elementParams: {},
      _status: 'pending', _detail: '', _duration: null
    };
    step.code = this._generateElementCode(step);
    return step;
  },

  stepAction(type, i) {
    if (type === 'run') this.runSingleStep(i);
    else if (type === 'up' && i > 0) { const s = this.steps[i]; this.steps.splice(i, 1); this.steps.splice(i - 1, 0, s); this.selectStep(i - 1); this.ensureFile(); }
    else if (type === 'down' && i < this.steps.length - 1) { const s = this.steps[i]; this.steps.splice(i, 1); this.steps.splice(i + 1, 0, s); this.selectStep(i + 1); this.ensureFile(); }
    else if (type === 'edit') { this.cliText = this.steps[i].code; this.cliPrefix = ''; this.selectStep(i); this.$nextTick(() => this.$refs.cliInput.focus()); }
    else if (type === 'delete') { this.steps.splice(i, 1); if (this.selectedStepIndex >= this.steps.length) this.selectedStepIndex = this.steps.length - 1; this.ensureFile(); this.selectedNode = null; }
  },

  selectStep(i) {
    this.selectedNode = null;
    this.selectedStepIndex = i;
  },

  stepIcon(status) {
    status = status || 'pending';
    const m = { pending: '○', running: '◐', ok: '●', fail: '✖' };
    return { icon: m[status] || '○', cls: 'icon-' + status };
  },

  // ── CLI ──

  onCliKeydown(e) {
    if (e.key === 'Enter') {
      if (this.slashVisible) { this.pickSlash(this.slashItems[this.slashIdx]); e.preventDefault(); return; }
      this.submitCli();
    } else if (e.key === 'ArrowDown') {
      if (this.slashVisible) { this.slashIdx = Math.min(this.slashIdx + 1, this.slashItems.length - 1); e.preventDefault(); }
    } else if (e.key === 'ArrowUp') {
      if (this.slashVisible) { this.slashIdx = Math.max(this.slashIdx - 1, 0); e.preventDefault(); }
    } else if (e.key === 'Escape') {
      this.slashVisible = false;
      if (this.cliPrefix) { this.cliPrefix = ''; this.cliText = ''; }
      if (this.captureMode) { this.exitCaptureMode(); }
      if (this.swipeRecordMode) { this.exitSwipeRecordMode(); this.$message({ message: '已取消滑动录制', type: 'info' }); }
      if (this.elementSelectMode) { this.elementSelectMode = false; this.$message({ message: '已取消元素选择', type: 'info' }); }
    }
  },

  onCliInput() {
    if (this.cliText.startsWith('/')) {
      this.slashVisible = true;
      this.slashIdx = 0;
      const q = this.cliText.slice(1).toLowerCase();
      this.slashItems = SLASH_STEP.filter(a => a.action.startsWith(q));
    } else if (this.cliPrefix === 'launchapp') {
      const q = this.cliText.toLowerCase();
      this.slashVisible = true;
      this.slashItems = this.appsCache
        .filter(p => p.toLowerCase().includes(q))
        .slice(0, 20)
        .map(p => ({ key: p, desc: '', isApp: true }));
      this.slashIdx = 0;
    } else if (this.cliPrefix === 'key') {
      const q = this.cliText.toLowerCase();
      this.slashVisible = true;
      this.slashItems = KEY_OPTIONS
        .filter(k => k.key.includes(q) || k.desc.toLowerCase().includes(q))
        .slice(0, 30)
        .map(k => ({ key: k.key, desc: k.desc, isKey: true }));
      this.slashIdx = 0;
    } else {
      this.slashVisible = false;
    }
  },

  submitCli() {
    let line = this.cliText.trim();
    if (!line && !this.cliPrefix) return;
    if (this.cliPrefix) line = `${this.cliPrefix}: ${line}`;
    const m = line.match(/^(\w+):\s*(.*)/);
    if (!m) { line = `tap: ${line}`; }
    const m2 = line.match(/^(\w+):\s*(.*)/);
    if (!m2) return;
    const action = m2[1], value = m2[2] || '';

    if (action === 'imglocate') {
      this.addStep('imglocate', value);
      this.cliText = ''; this.cliPrefix = ''; this.selectedStepIndex = -1; this.slashVisible = false;
      return;
    }

    // Handle element: prefix - create element step
    if (action === 'element') {
      const step = {
        stepType: 'element',
        elementAction: 'click',
        selector: { text: value || '' },
        elementParams: {},
        code: this._generateElementCode({ stepType: 'element', elementAction: 'click', selector: { text: value || '' }, elementParams: {} }),
        _status: 'pending', _detail: '', _duration: null
      };
      this.steps.push(step);
      this.ensureFile();
      this.selectStep(this.steps.length - 1);
      this.cliText = ''; this.cliPrefix = ''; this.slashVisible = false;
      if (this.autoRun) this.runSingleStep(this.steps.length - 1);
      return;
    }

    const code = this.stepToCode(action, value);
    let idx = this.selectedStepIndex;
    if (idx >= 0 && idx < this.steps.length) {
      this.steps[idx].code = code;
      this.steps[idx]._status = 'pending';
      this.saveCurrentTask();
    } else {
      idx = this.steps.length;
      this.steps.push({ code, _status: 'pending', _detail: '', _duration: null });
      this.saveCurrentTask();
    }
    this.selectedNode = null;
    this.cliText = ''; this.cliPrefix = ''; this.selectedStepIndex = idx; this.slashVisible = false;
    if (this.autoRun) this.runSingleStep(idx);
  },

  pickSlash(item) {
    if (item.isApp) {
      this.cliText = item.key;
      this.slashVisible = false;
      this.$nextTick(() => this.$refs.cliInput.focus());
      return;
    }
    if (item.isKey) {
      this.cliText = item.key;
      this.slashVisible = false;
      this.$nextTick(() => this.$refs.cliInput.focus());
      return;
    }
    if (item.action === 'imglocate') {
      this.addStep('imglocate', ''); this.slashVisible = false; this.cliText = ''; this.cliPrefix = '';
      return;
    }
    if (item.action === 'swipe') {
      this.addStep('swipe', ''); this.slashVisible = false; this.cliText = ''; this.cliPrefix = '';
      return;
    }
    if (item.action === 'element') {
      this.addStep('element', ''); this.slashVisible = false; this.cliText = ''; this.cliPrefix = '';
      return;
    }
    this.cliPrefix = item.action;
    this.cliText = '';
    if (item.action === 'launchapp') {
      this.loadApps();
      this.$nextTick(() => this.onCliInput());
    }
    if (item.action === 'key') {
      this.$nextTick(() => this.onCliInput());
    }
    this.cliPlaceholder = item.desc;
    this.slashVisible = false;
    this.$nextTick(() => this.$refs.cliInput.focus());
  },

  async loadApps() {
    if (!this.isConnected || !this.serial) {
      this.$message({ message: '请先连接设备', type: 'warning' });
      return;
    }
    if (this.appsCache.length) return;
    try {
      this.addLog('info', '正在获取已安装应用...');
      const res = await listPackages(this.platform, this.serial);
      if (res.success) {
        this.appsCache = res.data || [];
        this.addLog('info', `找到 ${this.appsCache.length} 个应用`);
        this.onCliInput();
      } else {
        this.$message({ message: res.message || '获取应用列表失败', type: 'error' });
      }
    } catch (e) {
      this.$message({ message: `Error: ${e.message}`, type: 'error' });
    }
  },

  // ── Step execution ──

  async runSingleStep(i) {
    if (!this.isConnected) { this.$message({ showClose: true, message: '尚未连接设备', type: 'warning' }); return; }
    const s = this.steps[i];
    s._status = 'running';
    this.$set(this.steps, i, { ...s });
    this.isRunning = true;
    try {
      await this.wsRun(this.taskToYamlSingle(i), i);
    } catch (e) {
      s._status = 'fail';
      s._detail = e.message;
      this.$set(this.steps, i, { ...s });
      this.addLog('fail', `步骤 ${i + 1} 错误: ${e.message}`);
      this.isRunning = false;
    }
  },

  async runAllSteps() {
    this.steps.forEach((s, i) => { s._status = 'pending'; s._detail = ''; s._duration = null; this.$set(this.steps, i, { ...s }); });
    this.currentYamlContent = this.taskToYaml();
    this.logLines = [];
    this.addLog('info', '正在执行全部步骤...');
    this.isRunning = true;
    try {
      await this.wsRun(this.currentYamlContent);
    } catch (e) {
      this.addLog('fail', `运行错误: ${e.message}`);
      this.isRunning = false;
    }
  },

  wsRun(yaml, stepOffset) {
    return new Promise((resolve, reject) => {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${proto}//${location.host}/ws/run`);
      ws.onopen = () => {
        ws.send(JSON.stringify({
          platform: this.taskPlatform,
          serial: this.serial,
          filename: this.currentYamlFile || undefined,
          content: yaml,
          step_offset: stepOffset || 0
        }));
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'step') {
          const i = (msg.index || 1) - 1;
          if (this.steps[i]) {
            this.steps[i]._status = msg.status;
            this.steps[i]._detail = msg.detail || '';
            this.steps[i]._duration = msg.duration;
            this.$set(this.steps, i, { ...this.steps[i] });
            const color = { ok: 'ok', fail: 'fail', running: 'info', skipped: 'warn' }[msg.status] || 'info';
            this.addLog(color, `Step ${msg.index} → ${msg.status}`);
          }
          if (msg.status === 'ok' || msg.status === 'fail') {
            this.scheduleDump();
          }
        } else if (msg.type === 'log') {
          this.addLog('info', msg.text);
        } else if (msg.type === 'done') {
          this.addLog(msg.fail ? 'fail' : 'ok', `${msg.ok}/${msg.total} 步通过`);
          this.scheduleDump();
          ws.close();
          resolve();
        } else if (msg.type === 'error') {
          this.addLog('fail', msg.msg);
          ws.close();
          reject(new Error(msg.msg));
        }
      };
      ws.onerror = () => {
        this.addLog('fail', 'WebSocket 连接错误');
        reject(new Error('WS 错误'));
      };
    });
  },

  scheduleDump() {
    if (this._dumpTimer) clearTimeout(this._dumpTimer);
    this._dumpTimer = setTimeout(async () => {
      if (this.isConnected) await this.screenshotAndDumpHierarchy();
      this.isRunning = false;
    }, 1000);
  },

  addLog(level, text) {
    this.logLines.push({ level, text: `${new Date().toLocaleTimeString()} ${text}` });
    if (!this.logOpen) this.logOpen = true;
  },

  async cleanupTaskImages() {
    if (!this.currentYamlFile || !this.projectId) {
      this.$message({ message: '无项目ID，无法清理', type: 'warning' });
      return;
    }
    try {
      this.addLog('info', '正在清理未引用图片...');
      const res = await cleanupImages(this.currentYamlFile);
      if (res.success) {
        const removed = res.data.removed || 0;
        const referenced = res.data.referenced || 0;
        this.$message({ message: `清理完成: 删除 ${removed} 张, 保留 ${referenced} 张`, type: 'success' });
        this.addLog('ok', `清理完成: 删除 ${removed} 张未引用图片`);
      } else {
        this.$message({ message: res.message || '清理失败', type: 'error' });
      }
    } catch (e) {
      this.$message({ message: `清理错误: ${e.message}`, type: 'error' });
    }
  },

  async deviceAction(key) {
    if (!this.isConnected) return;
    if (this.rightTab !== 'editor') return;
    const idx = this.steps.length;
    this.steps.push({ code: `key("${key}")`, _status: 'pending', _detail: '', _duration: null });
    this.ensureFile();
    this.addLog('info', `已插入: press("${key}")`);
    if (this.autoRun) this.runSingleStep(idx);
  },

  generateU2Selector(node) {
    const esc = (s) => (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t');
    const attrs = [];
    if (node.xpath) attrs.push(`xpath="${esc(node.xpath)}"`);
    if (node.resourceId) attrs.push(`resourceId="${esc(node.resourceId)}"`);
    if (node.text) attrs.push(`text="${esc(node.text)}"`);
    if (node.description) attrs.push(`description="${esc(node.description)}"`);
    if (node._type) attrs.push(`className="${esc(node._type)}"`);
    if (node.index !== undefined && node.index !== null && node.index >= 0) attrs.push(`index=${node.index}`);
    if (attrs.length === 0) return null;
    return attrs.join(', ');
  },

  insertStepFromElement() {
    if (!this.selectedNode) return;
    if (this.rightTab !== 'editor') {
      this.$message({ message: '切换到编辑器标签页后再插入步骤', type: 'info' });
      return;
    }
    const step = this._elementFromNode(this.selectedNode);
    const idx = this.steps.length;
    this.steps.push(step);
    this.ensureFile();
    this.selectStep(idx);
    this.$message({ message: `已插入元素操作: ${step.code}`, type: 'success' });
    if (this.autoRun) this.runSingleStep(idx);
  },
};
