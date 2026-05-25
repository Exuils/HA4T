import { saveToLocalStorage, getFromLocalStorage, copyToClipboard } from './utils.js';
import { getVersion, listDevices, connectDevice, fetchScreenshot, fetchHierarchy, fetchXpathLite, listTasks, getTask, saveTask, runTask, listPackages } from './api.js';

const SLASH_STEP = [
  { action: 'tap', desc: 'Click element by text (uiautomator2)' },
  { action: 'drag', desc: 'Drag gesture - generates swipe()' },
  { action: 'type', desc: 'Type text - generates send_keys()' },
  { action: 'key', desc: 'Press system key - generates press()' },
  { action: 'launchapp', desc: 'Launch app - generates start_app()' },
  { action: 'wait', desc: 'Wait seconds - generates time.sleep()' },
  { action: 'code', desc: 'Custom Python code line' },
];


new Vue({
  el: '#app',
  data() {
    return {
      version: "",
      platform: getFromLocalStorage('platform', 'harmony'),
      serial: getFromLocalStorage('serial', ''),
      devices: [],
      isConnected: false,
      isConnecting: false,
      isDumping: false,
      wdaUrl: getFromLocalStorage('wdaUrl', ''),
      snapshotMaxDepth: getFromLocalStorage('snapshotMaxDepth', 30),

      packageName: getFromLocalStorage('packageName', ''),
      activityName: getFromLocalStorage('activityName', ''),
      displaySize: getFromLocalStorage('displaySize', [0, 0]),
      scale: getFromLocalStorage('scale', 1),
      screenshotTransform: {scale: 1, offsetX: 0, offsetY: 0},
      jsonHierarchy: {},
      xpathLite: "//",
      mouseClickCoordinatesPercent: null,
      hoveredNode: null,
      selectedNode: null,

      treeData: [],
      defaultTreeProps: {
        children: 'children',
        label: this.getTreeLabel
      },
      nodeFilterText: '',
      centerWidth: 500,
      isDividerHovered: false,
      isDragging: false,

      rightTab: 'hierarchy',
      yamlFiles: [],
      currentYamlFile: '',
      currentYamlContent: '',

      taskName: '',
      taskDesc: '',
      taskPlatform: 'android',
      steps: [],
      autoRun: false,
      selectedStepIndex: -1,
      cliText: '',
      cliPrefix: '',
      cliPlaceholder: 'tap: UI element',
      slashVisible: false,
      slashIdx: 0,
      slashItems: [],
      settingsVisible: false,
      logOpen: false,
      logLines: [],
      appsCache: [],
      isRunning: false
    };
  },
  computed: {
    selectedNodeDetails() {
      const isHarmony = this.platform === 'harmony';
      const defaultDetails = this.getDefaultNodeDetails(this.platform);
    
      if (!this.selectedNode) {
        return defaultDetails;
      }
    
      const nodeDetails = Object.entries(this.selectedNode)
        .filter(([key]) => !['children', '_id', '_parentId', 'frame'].includes(key))
        .map(([key, value]) => ({
          key: key === '_type' ? (isHarmony ? 'type' : 'className') : key,
          value
        }));
    
      return [...defaultDetails, ...nodeDetails];
    }
  },
    watch: {
      platform(newVal) {
        saveToLocalStorage('platform', newVal);
      },
      wdaUrl(newVal) {
        saveToLocalStorage('wdaUrl', newVal);
      },
      snapshotMaxDepth(newVal) {
        saveToLocalStorage('snapshotMaxDepth', newVal);
      },
      nodeFilterText(val) {
        this.$refs.treeRef.filter(val);
      },
      cliText() {
        this.onCliInput();
      }
    },
  created() {
    this.fetchVersion();
    this.refreshYamlFiles();
  },
  async mounted() {
    this.loadCachedScreenshot();
    const canvas = this.$el.querySelector('#hierarchyCanvas');
    canvas.addEventListener('mousemove', this.onMouseMove);
    canvas.addEventListener('click', this.onMouseClick);
    canvas.addEventListener('dblclick', this.onMouseDblClick);
    canvas.addEventListener('mouseleave', this.onMouseLeave);

    this.setupCanvasResolution('#screenshotCanvas');
    this.setupCanvasResolution('#hierarchyCanvas');

    await this.listDevice();
    if (this.serial && !this.isConnected) {
      await this.connectDevice();
    }
  },
  methods: {
    initPlatform() {
        this.serial = ''
        this.isConnected = false
        this.selectedNode = null
        this.treeData = []
    },
    async fetchVersion() {
      try {
        const response = await getVersion();
        this.version = response.data;
      } catch (err) {
        console.error(err);
      }
    },
    async listDevice() {
      try {
        const response = await listDevices(this.platform);
        this.devices = response.data;
        if (!this.serial && this.devices.length > 0) {
          this.serial = this.devices[0];
        }
      } catch (err) {
        this.$message({ showClose: true, message: `Error: ${err.message}`, type: 'error' });
      }
    },
    async connectDevice() {
      this.isConnecting = true;
      try {
        if (!this.serial) {
          throw new Error('Please select device first');
        }
        if (this.platform === 'ios' && !this.wdaUrl) {
          throw new Error('Please input wdaUrl first');
        }

        const response = await connectDevice(this.platform, this.serial, this.wdaUrl, this.snapshotMaxDepth);
        if (response.success) {
          this.isConnected = true;
          saveToLocalStorage('serial', this.serial);
          await this.screenshotAndDumpHierarchy();
        } else {
          throw new Error(response.message);
        }
      } catch (err) {
        this.$message({ showClose: true, message: `Error: ${err.message}`, type: 'error' });
      } finally {
        this.isConnecting = false;
      }
    },
    async screenshotAndDumpHierarchy() {
      this.isDumping = true;
      try {
        await this.fetchScreenshot();
        await this.fetchHierarchy();
      } catch (err) {
        this.$message({ showClose: true, message: `Error: ${err.message}`, type: 'error' });
      } finally {
        this.isDumping = false;
      }
    },
    async fetchScreenshot() {
      try {
        const response = await fetchScreenshot(this.platform, this.serial);
        if (response.success) {
          const base64Data = response.data;
          this.renderScreenshot(base64Data);
          saveToLocalStorage('cachedScreenshot', base64Data);
        } else {
          throw new Error(response.message);
        }
      } catch (error) {
        console.error(error);
      }
    },
    async fetchHierarchy() {
      try {
        const response = await fetchHierarchy(this.platform, this.serial);
        if (response.success) {
          const ret = response.data;
          this.packageName = ret.packageName;
          this.activityName = ret.activityName;
          this.displaySize = ret.windowSize;
          this.scale = ret.scale;
          this.jsonHierarchy = ret.jsonHierarchy;
          this.treeData = [ret.jsonHierarchy];

          saveToLocalStorage('packageName', ret.packageName);
          saveToLocalStorage('activityName', ret.activityName);
          saveToLocalStorage('displaySize', ret.windowSize);
          saveToLocalStorage('scale', ret.scale);

          this.hoveredNode = null;
          this.selectedNode = null;

          this.renderHierarchy();
        } else {
          throw new Error(response.message);
        }
      } catch (error) {
        console.error(error);
      }
    },
    renderHierarchy() {
      const canvas = this.$el.querySelector('#hierarchyCanvas');
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const { scale, offsetX, offsetY } = this.screenshotTransform;
      ctx.setLineDash([2, 6]);

      const drawNode = (node) => {
        if (node.rect) {
          const { x, y, width, height } = node.rect;
          ctx.strokeStyle = 'red';
          ctx.lineWidth = 0.8;
          ctx.strokeRect(x * scale + offsetX, y * scale + offsetY, width * scale, height * scale);
        }
        if (node.children) {
          node.children.forEach(drawNode);
        }
      };

      drawNode(this.jsonHierarchy);

      if (this.hoveredNode) {
        const { x, y, width, height } = this.hoveredNode.rect;
        ctx.setLineDash([]);
        ctx.globalAlpha = 0.6;
        ctx.fillStyle = '#3679E3';
        ctx.fillRect(x * scale + offsetX, y * scale + offsetY, width * scale, height * scale);
        ctx.globalAlpha = 1.0;
      }

      if (this.selectedNode) {
        const { x, y, width, height } = this.selectedNode.rect;
        ctx.setLineDash([]);
        ctx.strokeStyle = 'red';
        ctx.lineWidth = 2;
        ctx.strokeRect(x * scale + offsetX, y * scale + offsetY, width * scale, height * scale);
      }
    },
    async fetchXpathLite(nodeId) {
      try {
        const response = await fetchXpathLite(this.platform,this.jsonHierarchy, nodeId);
        if (response.success) {
          this.xpathLite = response.data;
        } else {
          throw new Error(response.message);
        }
      } catch (error) {
        console.error(error);
      }
    },
    loadCachedScreenshot() {
      const cachedScreenshot = getFromLocalStorage('cachedScreenshot', null);
      if (cachedScreenshot) {
        this.renderScreenshot(cachedScreenshot);
      }
    },
  
    // 解决在高分辨率屏幕上，Canvas绘制的内容可能会显得模糊。这是因为Canvas的默认分辨率与屏幕的物理像素密度不匹配
    setupCanvasResolution(selector) {
      const canvas = this.$el.querySelector(selector);
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      const ctx = canvas.getContext('2d');
      ctx.scale(dpr, dpr);
    },
    renderScreenshot(base64Data) {
        const img = new Image();
        img.src = `data:image/png;base64,${base64Data}`;
        img.onload = () => {
            const canvas = this.$el.querySelector('#screenshotCanvas');
            const ctx = canvas.getContext('2d');

            const { clientWidth: canvasWidth, clientHeight: canvasHeight } = canvas;

            this.setupCanvasResolution('#screenshotCanvas');

            const { width: imgWidth, height: imgHeight } = img;
            const scale = Math.min(canvasWidth / imgWidth, canvasHeight / imgHeight);
            const x = (canvasWidth - imgWidth * scale) / 2;
            const y = (canvasHeight - imgHeight * scale) / 2;

            this.screenshotTransform = { scale, offsetX: x, offsetY: y };

            ctx.clearRect(0, 0, canvasWidth, canvasHeight);
            ctx.drawImage(img, x, y, imgWidth * scale, imgHeight * scale);

            this.setupCanvasResolution('#hierarchyCanvas');
        };
    },
    findSmallestNode(node, mouseX, mouseY, scale, offsetX, offsetY) {
      let smallestNode = null;

      const checkNode = (node) => {
        if (node.rect) {
          const { x, y, width, height } = node.rect;
          const scaledX = x * scale + offsetX;
          const scaledY = y * scale + offsetY;
          const scaledWidth = width * scale;
          const scaledHeight = height * scale;

          if (mouseX >= scaledX && mouseY >= scaledY && mouseX <= scaledX + scaledWidth && mouseY <= scaledY + scaledHeight) {
            if (!smallestNode || (width * height < smallestNode.rect.width * smallestNode.rect.height)) {
              smallestNode = node;
            }
          }
        }
        if (node.children) {
          node.children.forEach(checkNode);
        }
      };

      checkNode(node);
      return smallestNode;
    },
    getDefaultNodeDetails(platform) {
      const commonDetails = [
        { key: 'displaySize', value: this.displaySize },
        {key: 'scale', value: this.scale },
        { key: '点击坐标 %', value: this.mouseClickCoordinatesPercent }
      ];
    
      switch (platform) {
        case 'ios':
          return [
            { key: 'bundleId', value: this.packageName },
            ...commonDetails
          ];
        case 'android':
          return [
            { key: 'packageName', value: this.packageName },
            { key: 'activityName', value: this.activityName },
            ...commonDetails
          ];
        case 'harmony':
          return [
            { key: 'packageName', value: this.packageName },
            { key: 'pageName', value: this.activityName },
            ...commonDetails
          ];
        default:
          return commonDetails;
      }
    },
    onMouseMove(event) {
      const canvas = this.$el.querySelector('#hierarchyCanvas');
      const rect = canvas.getBoundingClientRect();
      const mouseX = event.clientX - rect.left;
      const mouseY = event.clientY - rect.top;

      const { scale, offsetX, offsetY } = this.screenshotTransform;

      const hoveredNode = this.findSmallestNode(this.jsonHierarchy, mouseX, mouseY, scale, offsetX, offsetY);
      if (hoveredNode !== this.hoveredNode) {
        this.hoveredNode = hoveredNode;
        this.renderHierarchy();
      }
    },
    async onMouseClick(event) {
      const canvas = this.$el.querySelector('#hierarchyCanvas');
      const rect = canvas.getBoundingClientRect();
      const mouseX = event.clientX - rect.left;
      const mouseY = event.clientY - rect.top;

      const { scale, offsetX, offsetY } = this.screenshotTransform;

      const percentX = (mouseX / canvas.width);
      const percentY = (mouseY / canvas.height);

      this.mouseClickCoordinatesPercent = `(${percentX.toFixed(2)}, ${percentY.toFixed(2)})`;

      const selectedNode = this.findSmallestNode(this.jsonHierarchy, mouseX, mouseY, scale, offsetX, offsetY);
      if (selectedNode !== this.selectedNode) {
        this.selectedNode = selectedNode ? selectedNode : null;

        await this.fetchXpathLite(selectedNode._id)
        this.selectedNode && (this.selectedNode.xpath = this.xpathLite);
        
        this.renderHierarchy();

      } else {
        // 保证每次点击重新计算`selectedNodeDetails`，更新点击坐标
        this.selectedNode = { ...this.selectedNode };
      }
    },
    onMouseLeave() {
      if (this.hoveredNode) {
        this.hoveredNode = null;
        this.renderHierarchy();
      }
    },
    async handleTreeNodeClick(node) {
      this.selectedNode = node;

      await this.fetchXpathLite(node._id)
      this.selectedNode && (this.selectedNode.xpath = this.xpathLite);

      this.renderHierarchy();
    },
    filterNode(value, data) {
      if (!value) return true;
      if (!data) return false;
      const { _type, resourceId, lable, text, id } = data;
      const filterMap = {
        android: [_type, resourceId, text],
        ios: [_type, lable],
        harmony: [_type, text, id]
      };
      const fieldsToFilter = filterMap[this.platform];
      const isFieldMatch = fieldsToFilter.some(field => field && field.indexOf(value) !== -1);
      const label = this.getTreeLabel(data);
      const isLabelMatch = label && label.indexOf(value) !== -1;
      return isFieldMatch || isLabelMatch;
    },
    getTreeLabel(node) {
      const { _type="", resourceId="", label="", text="", id="" } = node;
      const labelMap = {
        android: resourceId || text,
        ios: label,
        harmony: text || id
      };
      return `${_type} - ${labelMap[this.platform] || ''}`;
    },
    copyToClipboard(value) {
      const success = copyToClipboard(value);
      this.$message({ showClose: true, message: success ? "复制成功" : "复制失败", type: success ? 'success' : 'error' });
    },
    startDrag(event) {
      this.isDragging = true;
      document.addEventListener('mousemove', this.onDrag);
      document.addEventListener('mouseup', this.stopDrag);
    },
    onDrag(event) {
      this.centerWidth = event.clientX - this.$el.querySelector('.left').offsetWidth;
    },
    stopDrag() {
      this.isDragging = false;
      document.removeEventListener('mousemove', this.onDrag);
      document.removeEventListener('mouseup', this.stopDrag);
    },
    hoverDivider() {
      this.isDividerHovered = true;
    },
    leaveDivider() {
      this.isDividerHovered = false;
    },

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
          this.addLog('info', `Loaded: ${filename}`);
        }
      } catch (err) {
        this.$message({ showClose: true, message: `Error: ${err.message}`, type: 'error' });
      }
    },
    parseYamlToTask(content) {
      const lines = content.split('\n');
      let name = '', desc = '', platform = 'android', inStep = false, stepBuf = [];
      const steps = [];
      const extraLines = [];
      let inExtra = true;
      for (const line of lines) {
        if (line.startsWith('# name:')) { name = line.split(':')[1].trim(); continue; }
        if (line.startsWith('# desc:')) { desc = line.split(':')[1].trim(); continue; }
        if (line.startsWith('# platform:')) { platform = line.split(':')[1].trim(); continue; }
        if (line.trim() === '# --step--') {
          if (inStep && stepBuf.length) { steps.push({ code: stepBuf.join('\n'), _status: 'pending', _detail: '', _duration: null }); stepBuf = []; }
          inStep = true; inExtra = false;
          continue;
        }
        if (inStep) {
          const t = line.trim();
          if (t && !t.startsWith('#') && !t.startsWith('from ha4t') && !t.startsWith('connect(') && !t.startsWith('import ') && !t.startsWith('os.environ')) {
            stepBuf.push(line);
          }
        } else if (inExtra && line.trim()) {
          if (!line.startsWith('from ha4t') && !line.startsWith('connect(') && !line.startsWith('import ') && !line.startsWith('os.environ') && !line.startsWith('# name:') && !line.startsWith('# desc:') && !line.startsWith('# platform:')) {
            extraLines.push(line);
          }
        }
      }
      if (inStep && stepBuf.length) { steps.push({ code: stepBuf.join('\n'), _status: 'pending', _detail: '', _duration: null }); }
      this.taskName = name; this.taskDesc = desc; this.taskPlatform = platform;
      this.steps = steps; this._extraLines = extraLines;
    },
    taskToYaml() {
      let y = `# name: ${this.taskName || 'Untitled'}\n`;
      if (this.taskDesc) y += `# desc: ${this.taskDesc}\n`;
      y += `# platform: ${this.taskPlatform}\n`;
      y += 'import os\nos.environ["FLAGS_use_mkldnn"] = "0"\n';
      y += 'from ha4t import connect\nfrom ha4t.api import *\nconnect(platform="' + this.taskPlatform + '")\n\n';
      if (this._extraLines) this._extraLines.forEach(l => { y += l + '\n'; });
      this.steps.forEach(s => { y += '\n# --step--\n' + s.code + '\n'; });
      return y;
    },
    clearTask() {
      this.currentYamlFile = '';
      this.currentYamlContent = '';
      this.taskName = '';
      this.taskDesc = '';
      this.taskPlatform = 'android';
      this.steps = [];
      this.selectedStepIndex = -1;
    },
    addStep(action, value) {
      const code = this.stepToCode(action, value);
      this.steps.push({ code, _status: 'pending', _detail: '', _duration: null });
      this.saveCurrentTask();
    },
    stepToCode(action, value) {
      const m = {
        tap: `click(text="${value}")`,
        drag: `swipe((300, 300), (300, 700))`,
        type: `device.driver.send_keys("${value}")`,
        key: `device.driver.press("${value}")`,
        launchapp: `start_app("${value}")`,
        wait: `time.sleep(${value})`,
      };
      return m[action] || value;
    },
    stepAction(type, i) {
      if (type === 'run') this.runSingleStep(i);
      else if (type === 'up' && i > 0) { const s = this.steps[i]; this.steps.splice(i, 1); this.steps.splice(i - 1, 0, s); this.selectedStepIndex = i - 1; this.saveCurrentTask(); }
      else if (type === 'down' && i < this.steps.length - 1) { const s = this.steps[i]; this.steps.splice(i, 1); this.steps.splice(i + 1, 0, s); this.selectedStepIndex = i + 1; this.saveCurrentTask(); }
      else if (type === 'edit') { this.cliText = this.steps[i].code; this.cliPrefix = ''; this.selectedStepIndex = i; this.$nextTick(() => this.$refs.cliInput.focus()); }
      else if (type === 'delete') { this.steps.splice(i, 1); if (this.selectedStepIndex >= this.steps.length) this.selectedStepIndex = this.steps.length - 1; this.saveCurrentTask(); }
    },
    selectStep(i) { this.selectedStepIndex = i; },
    stepIcon(status) {
      const m = { pending: '○', running: '◐', ok: '●', fail: '✖' };
      const cls = status ? 'icon-' + status : '';
      return { icon: m[status] || '○', cls: cls };
    },
    async runSingleStep(i) {
      if (!this.isConnected) { this.$message({ message: 'Not connected', type: 'warning' }); return; }
      const s = this.steps[i];
      s._status = 'running';
      this.$set(this.steps, i, { ...s });
      this.isRunning = true;
      try {
        await this.wsRun(this.taskToYamlSingle(i));
      } finally {
        this.isRunning = false;
      }
    },
    async runAllSteps() {
      this.steps.forEach((s, i) => { s._status = 'pending'; s._detail = ''; s._duration = null; this.$set(this.steps, i, { ...s }); });
      this.currentYamlContent = this.taskToYaml();
      this.logLines = [];
      this.addLog('info', 'Running all steps...');
      this.isRunning = true;
      try {
        await this.wsRun(this.currentYamlContent);
      } finally {
        this.isRunning = false;
      }
    },
    wsRun(yaml) {
      return new Promise((resolve, reject) => {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${proto}//${location.host}/ws/run`);
        ws.onopen = () => {
          ws.send(JSON.stringify({
            platform: this.taskPlatform,
            serial: this.serial,
            filename: this.currentYamlFile || undefined,
            content: yaml
          }));
        };
        ws.onmessage = (e) => {
          const msg = JSON.parse(e.data);
          if (msg.type === 'step') {
            const i = msg.index - 1;
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
            this.addLog(msg.fail ? 'fail' : 'ok', `${msg.ok}/${msg.total} steps passed`);
            this.scheduleDump();
            ws.close();
            resolve();
          } else if (msg.type === 'error') {
            this.addLog('fail', msg.msg);
            ws.close();
            reject(new Error(msg.msg));
          }
        };
        ws.onerror = (e) => {
          this.addLog('fail', 'WebSocket connection error');
          reject(new Error('WS error'));
        };
      });
    },
    scheduleDump() {
      if (this._dumpTimer) clearTimeout(this._dumpTimer);
      this._dumpTimer = setTimeout(() => {
        if (this.isConnected) this.screenshotAndDumpHierarchy();
      }, 1000);
    },
    taskToYamlSingle(i) {
      let y = `# name: ${this.taskName}\n# platform: ${this.taskPlatform}\n`;
      y += 'import os\nos.environ["FLAGS_use_mkldnn"] = "0"\n';
      y += 'from ha4t import connect\nfrom ha4t.api import *\nconnect(platform="' + this.taskPlatform + '")\n\n';
      y += '# --step--\n' + this.steps[i].code + '\n';
      return y;
    },
    async runAllSteps() {
      this.steps.forEach((s, i) => { s._status = 'pending'; s._detail = ''; s._duration = null; this.$set(this.steps, i, { ...s }); });
      const yaml = this.taskToYaml();
      this.currentYamlContent = yaml;
      this.logLines = [];
      this.addLog('info', 'Running all steps...');
      this.isRunning = true;
      try {
        const res = await runTask(this.taskPlatform, this.serial, undefined, yaml);
        if (res.success && res.data) {
          const results = res.data.steps || [];
          results.forEach((r, i) => {
            if (this.steps[i]) {
              this.steps[i]._status = r.status;
              this.steps[i]._detail = r.detail || '';
              this.steps[i]._duration = r.duration;
              this.$set(this.steps, i, { ...this.steps[i] });
            }
          });
          this.addLog(res.data.success ? 'ok' : 'fail', res.data.summary);
        } else {
          this.addLog('fail', res.message || 'Unknown error');
        }
      } catch (e) {
        this.addLog('fail', e.message || String(e));
      } finally {
        this.isRunning = false;
      }
    },
    saveCurrentTask() {
      if (!this.currentYamlFile) return;
      this.currentYamlContent = this.taskToYaml();
    },
    async saveYamlFile() {
      if (!this.currentYamlFile) return;
      this.saveCurrentTask();
      try {
        const res = await saveTask(this.currentYamlFile, this.currentYamlContent);
        if (res.success) {
          this.$message({ showClose: true, message: 'Saved', type: 'success' });
          this.refreshYamlFiles();
        }
      } catch (err) {
        this.$message({ showClose: true, message: `Error: ${err.message}`, type: 'error' });
      }
    },
    newYamlFile() {
      this.clearTask();
      this.taskName = 'New Test';
      this.taskPlatform = 'android';
      this.settingsVisible = true;
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
      this.cliText = '';
      this.cliPrefix = '';
      this.selectedStepIndex = -1;
      this.slashVisible = false;
      if (this.autoRun) this.runSingleStep(idx);
    },
    pickSlash(item) {
      if (item.isApp) {
        this.cliText = item.key;
        this.slashVisible = false;
        this.$nextTick(() => this.$refs.cliInput.focus());
        return;
      }
      this.cliPrefix = item.action;
      this.cliText = '';
      if (item.action === 'launchapp') {
        this.loadApps();
        this.$nextTick(() => this.onCliInput());
      }
      this.cliPlaceholder = item.desc;
      this.slashVisible = false;
      this.$nextTick(() => this.$refs.cliInput.focus());
    },
    async loadApps() {
      if (!this.isConnected || !this.serial) {
        this.$message({ message: 'Please connect to a device first', type: 'warning' });
        return;
      }
      if (this.appsCache.length) return;
      try {
        this.addLog('info', 'Fetching installed packages...');
        const res = await listPackages(this.platform, this.serial);
        if (res.success) {
          this.appsCache = res.data || [];
          this.addLog('info', `Found ${this.appsCache.length} packages`);
          this.onCliInput();
        } else {
          this.$message({ message: res.message || 'Failed to fetch packages', type: 'error' });
        }
      } catch (e) {
        this.$message({ message: `Error: ${e.message}`, type: 'error' });
      }
    },
    addLog(level, text) {
      this.logLines.push({ level, text: `${new Date().toLocaleTimeString()} ${text}` });
      if (!this.logOpen) this.logOpen = true;
    },

    onMouseDblClick() {
      if (this.selectedNode && this.rightTab === 'editor') {
        this.insertStepFromElement();
      }
    },
    generateU2Selector(node) {
      const attrs = [];
      if (node.resourceId) attrs.push(`resourceId="${node.resourceId}"`);
      if (node.text) attrs.push(`text="${node.text}"`);
      if (node.description) attrs.push(`description="${node.description}"`);
      if (node._type) attrs.push(`className="${node._type}"`);
      if (node.index !== undefined && node.index !== null && node.index >= 0) attrs.push(`index=${node.index}`);
      if (attrs.length === 0) return null;
      return attrs.join(', ');
    },
    insertStepFromElement() {
      if (!this.selectedNode) return;
      if (this.rightTab !== 'editor') {
        this.$message({ message: 'Switch to Editor tab to insert steps', type: 'info' });
        return;
      }
      const sel = this.generateU2Selector(this.selectedNode);
      if (!sel) {
        this.$message({ message: 'No usable selector found for this element', type: 'warning' });
        return;
      }
      const code = `click(${sel})`;
      const idx = this.steps.length;
      this.steps.push({ code, _status: 'pending', _detail: '', _duration: null });
      this.saveCurrentTask();
      this.$message({ message: `Inserted: ${code}`, type: 'success' });
      if (this.autoRun) this.runSingleStep(idx);
    }
  }
});