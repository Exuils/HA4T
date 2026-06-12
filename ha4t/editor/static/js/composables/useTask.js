import { saveToLocalStorage, getFromLocalStorage } from '../utils.js';
import { listTasks, getTask, saveTask, saveImage, getImage, listPackages, cleanupImages, runAllure } from '../api.js';

const { ref } = Vue;

// ── Helpers (ported from step-editor.js) ──────────────────────────────────

const SLASH_STEP = [
  { action: 'element',   desc: '元素操作 (点击/长按/断言)' },
  { action: 'swipe',     desc: '录制滑动手势 (比例坐标)' },
  { action: 'key',       desc: '系统按键' },
  { action: 'launchapp', desc: '启动应用' },
  { action: 'wait',      desc: '等待秒数' },
  { action: 'imglocate', desc: '图片定位 (模板匹配)' },
  { action: 'include',   desc: '引用其他用例 (复用步骤)' },
  { action: 'code',      desc: '自定义代码' },
];

const KEY_OPTIONS = [
  { key: 'home', desc: '主页键' }, { key: 'back', desc: '返回键' },
  { key: 'menu', desc: '菜单键' }, { key: 'volume_up', desc: '音量+' },
  { key: 'volume_down', desc: '音量-' }, { key: 'power', desc: '电源键' },
  { key: 'camera', desc: '相机键' }, { key: 'clear', desc: '清除键' },
  { key: 'enter', desc: '回车键' }, { key: 'delete', desc: '删除键' },
  { key: 'dpad_up', desc: '方向键 上' }, { key: 'dpad_down', desc: '方向键 下' },
  { key: 'dpad_left', desc: '方向键 左' }, { key: 'dpad_right', desc: '方向键 右' },
  { key: 'search', desc: '搜索键' }, { key: 'recent', desc: '最近任务键' },
  { key: 'space', desc: '空格键' }, { key: 'tab', desc: 'Tab 键' },
  { key: 'escape', desc: 'Esc 键' }, { key: 'enter', desc: '回车键' },
];

function esc(s) {
  return (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n');
}

// Derive a disk filename from a human case name. Keeps CJK / unicode intact —
// only strips characters illegal in a file path (Windows-superset:
// \ / : * ? " < > | and control chars), collapses whitespace, and trims
// leading/trailing dots & spaces. Falls back to a timestamped name when nothing
// usable remains, so an empty name never produces a bare ".py".
export function fileNameFromName(name) {
  const base = (name || '')
    .replace(/[\\/:*?"<>|\x00-\x1f]/g, '')
    .replace(/^[.\s]+|[.\s]+$/g, '')
    .replace(/\s+/g, '_');
  return (base || `用例_${Date.now()}`) + '.py';
}

// Build a locator dict from a parsed hierarchy node — module-level so POM
// capture can reuse the exact same selector shape as element step recording.
export function selectorFromNode(node) {
  const selector = {};
  if (node.text) selector.text = node.text;
  if (node.resourceId) selector.resourceId = node.resourceId;
  if (node._type) selector.className = node._type;
  if (node.xpath) selector.xpath = node.xpath;
  if (node.description) selector.description = node.description;
  if (node.index !== undefined && node.index !== null && node.index >= 0) selector.index = node.index;
  return selector;
}

function buildSelectorString(selector) {
  if (!selector) return '';
  const e = (s) => (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t');
  const parts = [];
  if (selector.text)        parts.push(`text="${e(selector.text)}"`);
  if (selector.resourceId)  parts.push(`resourceId="${e(selector.resourceId)}"`);
  if (selector.className)   parts.push(`className="${e(selector.className)}"`);
  if (selector.xpath)       parts.push(`xpath="${e(selector.xpath)}"`);
  if (selector.description) parts.push(`description="${e(selector.description)}"`);
  if (selector.index != null && selector.index >= 0) parts.push(`index=${selector.index}`);
  return parts.join(', ');
}

function generateElementCode(step) {
  const sel = buildSelectorString(step.selector);
  const p = step.elementParams || {};
  switch (step.elementAction) {
    case 'click':        return sel ? `dev.click(${sel})` : `dev.click()`;
    case 'double_click': return `dev.double_click(${sel}, interval=${p.interval || 0.05})`;
    case 'long_press':   return `dev.long_press(${sel}, duration=${p.duration || 1.0})`;
    case 'drag':         return `dev.drag(${sel}, dx=${p.dx || 0}, dy=${p.dy || 0}, duration=${p.dragDuration || 0.5})`;
    case 'assert': {
      if (p.extract === 'exists') return `dev.assert_element(${sel}, operator="${p.operator || 'exists_true'}")`;
      const exp = p.expected ? `, expected="${p.expected}"` : '';
      return `dev.assert_element(${sel}, operator="${p.operator || 'eq'}"${exp})`;
    }
    default: return `dev.click(${sel})`;
  }
}

function generateImgCode(step) {
  const imgPath = step.image_filename || 'template.png';
  const t = step.threshold ? `, threshold=${step.threshold}` : '';
  if (step.action === 'click') {
    if (step.grid_h === 1 && step.grid_v === 1) return `dev.click(image="${imgPath}"${t})`;
    return `dev.click(image="${imgPath}", grid=(${step.click_col}, ${step.click_row}), splits=(${step.grid_h}, ${step.grid_v})${t})`;
  } else if (step.action === 'wait_show') {
    return `dev.wait(image="${imgPath}", timeout=${step.timeout}${t})`;
  } else if (step.action === 'wait_hide') {
    return `dev.wait(image="${imgPath}", timeout=${step.timeout}, reverse=True${t})`;
  }
  return `dev.click(image="${imgPath}"${t})`;
}

function parseKwArgs(argsStr) {
  const args = {};
  const re = /(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([\d.]+)|(true|false|null|undefined))/g;
  let m;
  while ((m = re.exec(argsStr)) !== null) {
    const key = m[1];
    const val = m[2] !== undefined ? m[2] : (m[3] !== undefined ? m[3] : (m[4] !== undefined ? parseFloat(m[4]) : m[5]));
    args[key] = val;
  }
  return args;
}

function parseStepCode(code) {
  const s = { code, _status: 'pending', _detail: '', _duration: null };
  // Include marker: 'include("xxx.py")' — calls ha4t.include() at runtime,
  // which exec's the referenced .py in this script's globals (sharing dev /
  // sleep). The editor expands this into a foldable preview card.
  const incMatch = code.match(/^\s*include\(\s*['"]([^'"]+)['"]\s*\)\s*$/);
  if (incMatch) {
    s._type = 'include';
    s.includeFile = incMatch[1].trim();
    s._open = false;            // collapsed by default
    s._includedSteps = null;    // lazy-loaded on first expand
    return s;
  }
  const elMatch = code.match(/^(?:dev\.)?(click|double_click|long_press|drag|assert_element)\((.*)\)$/);
  if (elMatch) {
    const func = elMatch[1];
    const argsStr = elMatch[2];
    const args = parseKwArgs(argsStr);
    const selector = {};
    for (const k of ['text','resourceId','className','xpath','description','index']) {
      if (args[k] !== undefined) selector[k] = args[k];
    }
    ['text','resourceId','className','xpath','description','index'].forEach(k => delete args[k]);
    if (func === 'click')        { s.stepType = 'element'; s.elementAction = 'click';        s.selector = selector; s.elementParams = {}; }
    else if (func === 'double_click') { s.stepType = 'element'; s.elementAction = 'double_click'; s.selector = selector; s.elementParams = { interval: args.interval || 0.05 }; }
    else if (func === 'long_press')   { s.stepType = 'element'; s.elementAction = 'long_press';   s.selector = selector; s.elementParams = { duration: args.duration || 1.0 }; }
    else if (func === 'drag')         { s.stepType = 'element'; s.elementAction = 'drag';         s.selector = selector; s.elementParams = { dx: args.dx || 0, dy: args.dy || 0, dragDuration: args.duration || 0.5 }; }
    else if (func === 'assert_element') {
      s.stepType = 'element'; s.elementAction = 'assert'; s.selector = selector;
      const op = args.operator || 'eq';
      s.elementParams = { operator: op, extract: args.extract || 'text' };
      if (args.expected !== undefined) s.elementParams.expected = args.expected;
    }
    return s;
  }
  const imgMatch = code.match(/image=["']([^"']+)["']/);
  if (!imgMatch) return s;
  s._type = 'imglocate';
  s.image_filename = imgMatch[1];
  if (code.includes('click(image=')) {
    s.action = 'click';
    const gridMatch = code.match(/grid=\((\d+)\s*,\s*(\d+)\)/);
    const splitsMatch = code.match(/splits=\((\d+)\s*,\s*(\d+)\)/);
    if (gridMatch && splitsMatch) { s.click_col = +gridMatch[1]; s.click_row = +gridMatch[2]; s.grid_h = +splitsMatch[1]; s.grid_v = +splitsMatch[2]; }
    else { s.click_col = 0; s.click_row = 0; s.grid_h = 1; s.grid_v = 1; }
  } else if (code.includes('wait(image=')) {
    s.action = code.includes('reverse=True') ? 'wait_hide' : 'wait_show';
    s.grid_h = 1; s.grid_v = 1; s.click_col = 0; s.click_row = 0;
  }
  const timeoutMatch = code.match(/timeout=(\d+)/);
  s.timeout = timeoutMatch ? +timeoutMatch[1] : 10;
  const thresholdMatch = code.match(/threshold=(0\.\d+)/);
  s.threshold = thresholdMatch ? parseFloat(thresholdMatch[1]) : null;
  return s;
}

// ── Main composable ───────────────────────────────────────────────────────

export function useTask() {
  const yamlFiles      = ref([]);
  const currentYamlFile = ref(getFromLocalStorage('currentYamlFile', ''));
  const currentYamlContent = ref('');

  const taskName     = ref('');
  const taskDesc     = ref('');
  const taskPlatform = ref('android');
  const projectId    = ref('');
  const taskTag      = ref('');
  const taskFeature  = ref('');
  const taskStory    = ref('');
  const taskSeverity = ref('normal');
  const taskRerun    = ref(0);
  const steps        = ref([]);
  const _extraLines  = ref([]);
  // 用例特有常量（顶层 LOCAL_VARS = {...} 字典，自动检测并从 _extraLines 中剥离）
  const localVars    = ref({});

  const selectedStepIndex = ref(-1);
  const settingsVisible   = ref(false);
  const autoRun           = ref(getFromLocalStorage('autoRun', false));
  const appsCache         = ref([]);

  // computed-like helper (used where computed not applicable)
  function getSelectedStep() {
    const i = selectedStepIndex.value;
    return (i >= 0 && i < steps.value.length) ? steps.value[i] : null;
  }

  function clearTask() {
    currentYamlFile.value = '';
    currentYamlContent.value = '';
    taskName.value = ''; taskDesc.value = '';
    taskPlatform.value = 'android'; projectId.value = '';
    taskTag.value = ''; taskFeature.value = '';
    taskStory.value = ''; taskSeverity.value = 'normal'; taskRerun.value = 0;
    steps.value = []; selectedStepIndex.value = -1; _extraLines.value = [];
    localVars.value = {};
  }

  function parseYamlToTask(content) {
    const lines = content.split('\n');
    let name = '', desc = '', platform = 'android', pid = '';
    let inStep = false, stepBuf = [], remark = '';
    let tag = '', feature = '', story = '', severity = 'normal', rerun = 0;
    const parsedSteps = [];
    const extraLines = [];
    // 先从原始 content 中识别 LOCAL_VARS = { ... } 块（必须是单引号/双引号字符串字面量；
    // 找到后从 lines 移除，避免落进 _extraLines 重复输出）
    const lv = _extractLocalVarsBlock(lines);
    let workLines = lines;
    if (lv) {
      workLines = lines.slice(0, lv.startIdx).concat(lines.slice(lv.endIdx + 1));
    }
    let inExtra = true;
    for (const line of workLines) {
      if (line.startsWith('# name:'))        { name     = line.split(':')[1].trim(); continue; }
      if (line.startsWith('# desc:'))        { desc     = line.split(':')[1].trim(); continue; }
      if (line.startsWith('# platform:'))    { platform = line.split(':')[1].trim(); continue; }
      if (line.startsWith('# project_id:'))  { pid      = line.split(':')[1].trim(); continue; }
      if (line.startsWith('# tag:'))         { tag      = line.split(':')[1].trim(); continue; }
      if (line.startsWith('# feature:'))     { feature  = line.split(':')[1].trim(); continue; }
      if (line.startsWith('# story:'))       { story    = line.split(':')[1].trim(); continue; }
      if (line.startsWith('# severity:'))    { severity = line.split(':')[1].trim(); continue; }
      if (line.startsWith('# rerun:'))       { rerun    = parseInt(line.split(':')[1].trim()) || 0; continue; }
      const trimmed = line.trim();
      if (trimmed.startsWith('# --step--')) {
        if (inStep && stepBuf.length) {
          const s = parseStepCode(stepBuf.join('\n'));
          if (remark) s.remark = remark;
          parsedSteps.push(s);
          stepBuf = []; remark = '';
        }
        inStep = true; inExtra = false;
        remark = trimmed.slice('# --step--'.length).trim();
        continue;
      }
      if (inStep) {
        const t = line.trim();
        if (t && !t.startsWith('#') && !t.startsWith('from ') && !t.startsWith('connect(') && !t.startsWith('import ') && !t.startsWith('os.environ') && !/^\w+\s*=\s*connect\(/.test(t)) {
          stepBuf.push(line);
        }
      } else if (inExtra && line.trim()) {
        const l = line;
        if (!l.startsWith('from ') && !l.startsWith('connect(') && !l.startsWith('import ') && !l.startsWith('os.environ') && !/^\w+\s*=\s*connect\(/.test(l.trim()) && !l.startsWith('# ')) {
          extraLines.push(l);
        }
      }
    }
    if (inStep && stepBuf.length) {
      const s = parseStepCode(stepBuf.join('\n'));
      if (remark) s.remark = remark;
      parsedSteps.push(s);
    }
    taskName.value = name; taskDesc.value = desc; taskPlatform.value = platform; projectId.value = pid;
    taskTag.value = tag; taskFeature.value = feature; taskStory.value = story;
    taskSeverity.value = severity; taskRerun.value = rerun;
    steps.value = parsedSteps; _extraLines.value = extraLines;
    localVars.value = lv ? lv.vars : {};
  }

  function taskToYaml(serial) {
    let y = `# name: ${taskName.value || '未命名'}\n`;
    if (taskDesc.value) y += `# desc: ${taskDesc.value}\n`;
    y += `# platform: ${taskPlatform.value}\n`;
    if (projectId.value) y += `# project_id: ${projectId.value}\n`;
    if (taskTag.value) y += `# tag: ${taskTag.value}\n`;
    if (taskFeature.value) y += `# feature: ${taskFeature.value}\n`;
    if (taskStory.value) y += `# story: ${taskStory.value}\n`;
    if (taskSeverity.value && taskSeverity.value !== 'normal') y += `# severity: ${taskSeverity.value}\n`;
    if (taskRerun.value) y += `# rerun: ${taskRerun.value}\n`;
    y += 'import os\nos.environ["FLAGS_use_mkldnn"] = "0"\n';
    y += 'from ha4t import connect, include\nfrom time import sleep\n';
    y += `dev = connect(platform="${taskPlatform.value}", device_serial="${serial || ''}")\n\n`;
    const lvBlock = _serializeLocalVars(localVars.value);
    if (lvBlock) y += lvBlock + '\n';
    if (_extraLines.value) _extraLines.value.forEach(l => { y += l + '\n'; });
    steps.value.forEach(s => {
      const sep = s.remark ? `# --step-- ${s.remark}` : '# --step--';
      y += `\n${sep}\n${s.code}\n`;
    });
    return y;
  }

  function taskToYamlSingle(i, serial) {
    let y = `# name: ${taskName.value}\n# platform: ${taskPlatform.value}\n`;
    y += 'import os\nos.environ["FLAGS_use_mkldnn"] = "0"\n';
    y += 'from ha4t import connect, include\nfrom time import sleep\n';
    y += `dev = connect(platform="${taskPlatform.value}", device_serial="${serial || ''}")\n\n`;
    y += '# --step--\n' + steps.value[i].code + '\n';
    return y;
  }

  function taskToYamlFrom(i, serial) {
    let y = `# name: ${taskName.value}\n# platform: ${taskPlatform.value}\n`;
    y += 'import os\nos.environ["FLAGS_use_mkldnn"] = "0"\n';
    y += 'from ha4t import connect, include\nfrom time import sleep\n';
    y += `dev = connect(platform="${taskPlatform.value}", device_serial="${serial || ''}")\n\n`;
    steps.value.slice(i).forEach(s => {
      const sep = s.remark ? `# --step-- ${s.remark}` : '# --step--';
      y += `\n${sep}\n${s.code}\n`;
    });
    return y;
  }

  async function saveCurrentTask(serial) {
    if (!currentYamlFile.value) {
      taskName.value = taskName.value || '新建用例';
      currentYamlFile.value = fileNameFromName(taskName.value);
      taskPlatform.value = taskPlatform.value || 'android';
      if (!projectId.value) projectId.value = 'proj_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
      saveToLocalStorage('currentYamlFile', currentYamlFile.value);
    }
    currentYamlContent.value = taskToYaml(serial);
    saveTask(currentYamlFile.value, currentYamlContent.value).catch(() => {});
    steps.value.forEach(s => {
      if (s._type === 'imglocate' && s.image && s.image_filename && !s._imageSaved) {
        saveImage(s.image_filename, s.image).then(() => { s._imageSaved = true; }).catch(() => {});
      }
    });
    await refreshYamlFiles();
  }

  async function refreshYamlFiles() {
    try {
      const res = await listTasks();
      if (res.success) yamlFiles.value = res.data;
    } catch (e) { console.error(e); }
  }

  async function loadYamlFile(filename, msg) {
    if (!filename) { clearTask(); return; }
    try {
      const res = await getTask(filename);
      if (res.success) {
        currentYamlFile.value = filename;
        currentYamlContent.value = res.data.content;
        parseYamlToTask(res.data.content);
        if (!projectId.value) {
          projectId.value = 'proj_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
        }
        // load images for imglocate steps
        for (let i = 0; i < steps.value.length; i++) {
          const step = steps.value[i];
          if (step._type === 'imglocate' && step.image_filename) {
            try {
              const imgRes = await getImage(step.image_filename);
              if (imgRes.success && imgRes.data && imgRes.data.data) {
                steps.value[i] = { ...step, image: 'data:image/png;base64,' + imgRes.data.data };
              }
            } catch (e) { console.warn('图片加载失败:', step.image_filename); }
          }
        }
        saveToLocalStorage('currentYamlFile', filename);
        if (msg) msg.info(`已加载: ${filename}`);
      }
    } catch (e) {
      if (msg) msg.error(`错误: ${e.message}`);
    }
  }

  // Fetch + parse another task file's steps without touching current-task state.
  // Used by the include-step expand panel to lazily render referenced steps.
  async function loadStepsFromFile(filename) {
    if (!filename) return [];
    const res = await getTask(filename);
    if (!res.success || !res.data || !res.data.content) return [];
    const content = res.data.content;
    const lines = content.split('\n');
    let inStep = false, buf = [], remark = '';
    const out = [];
    const flush = () => {
      if (!inStep || !buf.length) return;
      const s = parseStepCode(buf.join('\n'));
      if (remark) s.remark = remark;
      out.push(s);
      buf = []; remark = '';
    };
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('# --step--')) {
        flush();
        inStep = true;
        remark = trimmed.slice('# --step--'.length).trim();
        continue;
      }
      if (inStep) {
        const t = line.trim();
        if (t && !t.startsWith('from ') && !t.startsWith('connect(') && !t.startsWith('import ') && !t.startsWith('os.environ') && !/^\w+\s*=\s*connect\(/.test(t)) {
          // Keep '# include:' marker lines (parseStepCode needs them); drop other comments.
          if (!t.startsWith('#') || /^#\s*include:/.test(t)) buf.push(line);
        }
      }
    }
    flush();
    return out;
  }

  // Factory for a freshly inserted include step.
  function buildIncludeStep(filename) {
    return {
      _type: 'include',
      includeFile: filename,
      _open: false,
      _includedSteps: null,
      code: `include("${filename}")`,
      remark: '',
      _status: 'pending', _detail: '', _duration: null,
    };
  }

  function stepToCode(action, value) {
    const m = {
      tap:       `dev.click(text="${esc(value)}")`,
      drag:      `dev.swipe((300, 300), (300, 700))`,
      key:       `dev.press("${esc(value)}")`,
      launchapp: `dev.start_app("${esc(value)}")`,
      wait:      `sleep(${value})`,
    };
    return m[action] || esc(value);
  }

  function elementFromNode(node) {
    const selector = selectorFromNode(node);
    const step = { stepType: 'element', selector, elementAction: 'click', elementParams: {}, _status: 'pending', _detail: '', _duration: null };
    step.code = generateElementCode(step);
    return step;
  }

  function selectStep(i) {
    selectedStepIndex.value = i;
  }

  function stepIcon(status) {
    status = status || 'pending';
    const m = { pending: '○', running: '◐', ok: '●', fail: '✖' };
    return { icon: m[status] || '○', cls: 'icon-' + status };
  }

  async function loadApps(platform, serial, msg) {
    // 已缓存就直接复用 —— 同一设备的包列表用一次拉取即可。
    if (appsCache.value.length) {
      console.debug('[loadApps] cache hit, n=', appsCache.value.length);
      return;
    }
    if (!platform || !serial) {
      console.debug('[loadApps] skipped: no device', { platform, serial });
      msg && msg.warn && msg.warn('请先连接设备再选择应用');
      return;
    }
    console.debug('[loadApps] fetching', platform, serial);
    try {
      const res = await listPackages(platform, serial);
      console.debug('[loadApps] response', res);
      if (res.success && Array.isArray(res.data)) {
        appsCache.value = res.data;
        if (!res.data.length) {
          msg && msg.warn && msg.warn(`${platform} 暂不支持获取应用列表，请手动输入包名`);
        }
      } else if (msg && msg.error) {
        msg.error(res.message || '获取应用列表失败');
      }
    } catch (e) {
      console.error('[loadApps] error', e);
      msg && msg.error && msg.error('获取应用列表失败: ' + (e.message || e));
    }
  }

  async function cleanupTaskImages(msg) {
    if (!currentYamlFile.value || !projectId.value) { msg.warn('无项目ID，无法清理'); return; }
    try {
      const res = await cleanupImages(currentYamlFile.value);
      if (res.success) {
        msg.success(`清理完成: 删除 ${res.data.removed} 张`);
      } else { msg.error(res.message || '清理失败'); }
    } catch (e) { msg.error('清理错误: ' + e.message); }
  }

  // ── Step property helpers (ported from property-panel.js) ─────────────

  function computedStepType(step) {
    if (!step) return null;
    const c = step.code;
    if (step._type === 'include') return 'include';
    if (step.stepType === 'element') return 'element';
    if (step._type === 'imglocate') return 'imglocate';
    if (/^(dev\.)?swipe\(/.test(c)) return 'swipe';
    if (c.startsWith('# --step--')) return 'code';
    if (c.startsWith('key(')) return 'key';
    if (c.startsWith('sleep(')) return 'wait';
    if (/^(dev\.)?start_app\(/.test(c)) return 'launchapp';
    if (/^(dev\.)?press\(/.test(c)) return 'key';
    return 'code';
  }

  function selectedStepConfig(step) {
    if (!step) return null;
    const config = { type: computedStepType(step), fields: {} };
    const c = step.code;
    switch (config.type) {
      case 'element':  config.fields = { stepType:'element', elementAction: step.elementAction||'click', selector: step.selector||{}, elementParams: step.elementParams||{} }; break;
      case 'imglocate':config.fields = { action:step.action||'click', grid_h:step.grid_h||1, grid_v:step.grid_v||1, click_col:step.click_col||0, click_row:step.click_row||0, timeout:step.timeout||10, threshold:step.threshold??'', image:step.image||null }; break;
      case 'swipe': { const m = c.match(/swipe\(\(([\d.]+),\s*([\d.]+)\)\s*,\s*\(([\d.]+),\s*([\d.]+)\)\)/); config.fields = m ? { x1:+m[1], y1:+m[2], x2:+m[3], y2:+m[4] } : { _raw:c }; break; }
      case 'tap': { const m = c.match(/^(?:dev\.)?click\((.*)\)$/); config.fields = { selector: m ? m[1] : '' }; break; }
      case 'key': { const m = c.match(/(?:press|key)\("([^"]*)"\)/); config.fields = { key: m ? m[1] : '' }; break; }
      case 'launchapp': { const m = c.match(/start_app\("([^"]*)"\)/); config.fields = { package: m ? m[1] : '' }; break; }
      case 'wait': { const m = c.match(/(?:time\.)?sleep\(([\d.]+)\)/); config.fields = { seconds: m ? +m[1] : 1 }; break; }
      default: config.fields = { _raw: c };
    }
    return config;
  }

  function updateStepField(stepIndex, field, value, serial) {
    const step = steps.value[stepIndex];
    if (!step) return;
    const type = computedStepType(step);
    if (field === 'remark') { step.remark = value; _dirtyStep(stepIndex, serial); return; }
    if (field === 'code')   { step.code = value; _dirtyStep(stepIndex, serial); return; }
    if (type === 'element') { _updateElementField(stepIndex, field, value, serial); return; }
    if (type === 'imglocate') { _updateImgField(stepIndex, field, value, serial); return; }
    switch (type) {
      case 'swipe': { const m = step.code.match(/swipe\(\(([\d.]+),\s*([\d.]+)\)\s*,\s*\(([\d.]+),\s*([\d.]+)\)\)/); if (!m) break; const f = { x1:m[1], y1:m[2], x2:m[3], y2:m[4], [field]:value }; step.code = `swipe((${+f.x1}, ${+f.y1}), (${+f.x2}, ${+f.y2}))`; break; }
      case 'tap':      step.code = `dev.click(${value})`; break;
      case 'key':      step.code = `dev.press("${esc(value)}")`; break;
      case 'launchapp':step.code = `dev.start_app("${esc(value)}")`; break;
      case 'wait':     step.code = `sleep(${value})`; break;
    }
    _dirtyStep(stepIndex, serial);
  }

  function _updateElementField(stepIndex, field, value, serial) {
    const step = steps.value[stepIndex];
    if (!step) return;
    if (field.startsWith('selector.')) {
      const subKey = field.slice(9);
      if (!step.selector) step.selector = {};
      step.selector[subKey] = value;
      if (!value) delete step.selector[subKey];
    } else if (field === 'elementAction') {
      step.elementAction = value;
      if (!step.elementParams) step.elementParams = {};
    } else if (['interval','duration','dx','dy','dragDuration','operator','expected','extract'].includes(field)) {
      if (!step.elementParams) step.elementParams = {};
      step.elementParams[field] = value;
    }
    step.code = generateElementCode(step);
    _dirtyStep(stepIndex, serial);
  }

  function _updateImgField(stepIndex, field, value, serial) {
    const step = steps.value[stepIndex];
    if (!step) return;
    step[field] = value;
    if (['action','grid_h','grid_v','click_col','click_row','timeout','threshold'].includes(field)) {
      step.code = generateImgCode(step);
    }
    _dirtyStep(stepIndex, serial);
  }

  function removeSelectorField(stepIndex, key, serial) {
    const step = steps.value[stepIndex];
    if (!step || !step.selector) return;
    delete step.selector[key];
    step.code = generateElementCode(step);
    _dirtyStep(stepIndex, serial);
  }

  function _dirtyStep(stepIndex, serial) {
    // trigger reactivity
    if (stepIndex >= 0) {
      steps.value[stepIndex] = { ...steps.value[stepIndex] };
    }
    // fire-and-forget save
    if (currentYamlFile.value) {
      saveCurrentTask(serial).catch(() => {});
    }
  }

  // ── LOCAL_VARS 块（用例特有变量字典）解析 / 序列化 ─────────────────────
  // 约定：用例文件顶层声明 `LOCAL_VARS = {...}`，编辑器自动 parse 出来。
  // 仅支持 JSON 兼容值（字符串 / 数字 / bool / null），不支持嵌套 Python repr 字面量。
  // 多行格式按 4-space 缩进、允许末尾逗号；超出此规范的 dict 视为无 LOCAL_VARS。
  function _extractLocalVarsBlock(lines) {
    for (let i = 0; i < lines.length; i++) {
      const m = lines[i].match(/^\s*LOCAL_VARS\s*=\s*(\{.*)$/);
      if (!m) continue;
      let buf = m[1];
      let end = i;
      if (buf.trimEnd().endsWith('}')) {
        // 单行
      } else {
        // 多行：累积直到独占一行的 }
        let closed = false;
        for (let j = i + 1; j < lines.length; j++) {
          buf += '\n' + lines[j];
          if (lines[j].trim() === '}' || lines[j].trim().startsWith('}')) {
            end = j;
            closed = true;
            break;
          }
        }
        if (!closed) return null;
      }
      try {
        const obj = JSON.parse(buf.replace(/,(\s*[}\]])/g, '$1'));
        if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
          return { vars: obj, startIdx: i, endIdx: end };
        }
      } catch (_) { /* fall through */ }
      return null;
    }
    return null;
  }

  function _serializeLocalVars(vars) {
    const keys = Object.keys(vars);
    if (keys.length === 0) return '';
    const out = ['LOCAL_VARS = {'];
    for (const k of keys) {
      out.push(`    ${JSON.stringify(k)}: ${JSON.stringify(vars[k])},`);
    }
    out.push('}');
    return out.join('\n');
  }

  return {
    // state
    yamlFiles, currentYamlFile, currentYamlContent,
    taskName, taskDesc, taskPlatform, projectId,
    taskTag, taskFeature, taskStory, taskSeverity, taskRerun,
    steps, _extraLines, localVars, selectedStepIndex, settingsVisible, autoRun, appsCache,
    // constants
    SLASH_STEP, KEY_OPTIONS,
    // methods
    clearTask, parseYamlToTask, taskToYaml, taskToYamlSingle, taskToYamlFrom,
    saveCurrentTask, refreshYamlFiles, loadYamlFile, stepToCode, elementFromNode,
    loadStepsFromFile, buildIncludeStep,
    selectStep, stepIcon, cleanupTaskImages, loadApps,
    computedStepType, selectedStepConfig, updateStepField,
    _updateElementField, _updateImgField, removeSelectorField,
    generateElementCode, generateImgCode, buildSelectorString,
  };
}
