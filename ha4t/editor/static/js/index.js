import { saveToLocalStorage, getFromLocalStorage, copyToClipboard } from './utils.js';
import { getVersion, listDevices, connectDevice, fetchScreenshot, fetchHierarchy, fetchXpathLite, listTasks, getTask, saveTask, listPackages, saveTaskImage, getTaskImage } from './api.js';
import { API_HOST } from './config.js';

const SLASH_STEP = [
  { action: 'tap', desc: '点击元素 (uiautomator2)' },
  { action: 'drag', desc: '拖拽手势' },
  { action: 'type', desc: '输入文本' },
  { action: 'key', desc: '系统按键' },
  { action: 'launchapp', desc: '启动应用' },
  { action: 'wait', desc: '等待秒数' },
  { action: 'imglocate', desc: '图片定位 (模板匹配)' },
  { action: 'code', desc: '自定义代码' },
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

      rightTab: 'editor',
      yamlFiles: [],
      currentYamlFile: getFromLocalStorage('currentYamlFile', ''),
      currentYamlContent: '',

      taskName: '',
      taskDesc: '',
      taskPlatform: 'android',
      steps: [],
      autoRun: getFromLocalStorage('autoRun', false),
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
      isRunning: false,

      // Image capture state
      captureMode: false,
      captureStart: null,
      captureRect: null,

      // Image step config panel
      imgConfigVisible: false,
      imgConfigStep: null,
      imgConfigIndex: -1,

      // New image step data
      newImageStep: null
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
      autoRun(val) {
        saveToLocalStorage('autoRun', val);
      },
      cliText() {
        this.onCliInput();
      },
      imgConfigVisible(val) {
        if (val) {
          this.$nextTick(() => this.renderImgConfigGrid());
        }
      }
    },
  created() {
    this.fetchVersion();
    this.refreshYamlFiles();
    if (this.currentYamlFile) {
      this.$nextTick(() => this.loadYamlFile(this.currentYamlFile));
    }
  },
  async mounted() {
    this.loadCachedScreenshot();
    const canvas = this.$el.querySelector('#hierarchyCanvas');
    canvas.addEventListener('mousemove', this.onMouseMove);
    canvas.addEventListener('click', this.onMouseClick);
    canvas.addEventListener('dblclick', this.onMouseDblClick);
    canvas.addEventListener('mouseleave', this.onMouseLeave);
    canvas.addEventListener('mousedown', this.onCaptureMouseDown);
    canvas.addEventListener('mousemove', this.onCaptureMouseMove);
    canvas.addEventListener('mouseup', this.onCaptureMouseUp);

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
        this.$message({ showClose: true, message: `错误: ${err.message}`, type: 'error' });
      }
    },
    async connectDevice() {
      this.isConnecting = true;
      try {
        if (!this.serial) {
          throw new Error('请先选择设备');
        }
        if (this.platform === 'ios' && !this.wdaUrl) {
          throw new Error('请输入 WDA 地址');
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
        this.$message({ showClose: true, message: `错误: ${err.message}`, type: 'error' });
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
        this.$message({ showClose: true, message: `错误: ${err.message}`, type: 'error' });
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
      if (this.captureMode) return;
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
      if (this.captureMode) return;
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
    onCaptureMouseDown(event) {
      if (!this.captureMode) return;
      const canvas = this.$el.querySelector('#hierarchyCanvas');
      const rect = canvas.getBoundingClientRect();
      this.captureStart = {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top
      };
    },
    onCaptureMouseMove(event) {
      if (!this.captureMode || !this.captureStart) return;
      const canvas = this.$el.querySelector('#hierarchyCanvas');
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      this.captureRect = {
        x: Math.min(this.captureStart.x, x),
        y: Math.min(this.captureStart.y, y),
        w: Math.abs(x - this.captureStart.x),
        h: Math.abs(y - this.captureStart.y)
      };
      this.renderCaptureRect();
    },
    async onCaptureMouseUp(event) {
      if (!this.captureMode || !this.captureStart) return;
      const canvas = this.$el.querySelector('#hierarchyCanvas');
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const captureRect = {
        x: Math.min(this.captureStart.x, x),
        y: Math.min(this.captureStart.y, y),
        w: Math.abs(x - this.captureStart.x),
        h: Math.abs(y - this.captureStart.y)
      };
      this.captureStart = null;
      this.captureRect = null;
      this.renderCaptureRect();
      if (captureRect.w < 10 || captureRect.h < 10) {
        this.$message({ message: '选择区域太小，已取消', type: 'warning' });
        this.exitCaptureMode();
        return;
      }
      await this.createImageStep(captureRect);
      this.exitCaptureMode();
    },
    renderCaptureRect() {
      const canvas = this.$el.querySelector('#hierarchyCanvas');
      const ctx = canvas.getContext('2d');
      // Redraw hierarchy first
      this.renderHierarchy();
      if (this.captureRect && this.captureRect.w > 0) {
        ctx.setLineDash([]);
        ctx.strokeStyle = '#00ff00';
        ctx.lineWidth = 2;
        ctx.strokeRect(this.captureRect.x, this.captureRect.y, this.captureRect.w, this.captureRect.h);
        ctx.fillStyle = 'rgba(0, 255, 0, 0.15)';
        ctx.fillRect(this.captureRect.x, this.captureRect.y, this.captureRect.w, this.captureRect.h);
      }
    },
    async createImageStep(rect) {
      const { scale, offsetX, offsetY } = this.screenshotTransform;
      // Convert canvas coords to screenshot image coords
      const imgX = Math.round((rect.x - offsetX) / scale);
      const imgY = Math.round((rect.y - offsetY) / scale);
      const imgW = Math.round(rect.w / scale);
      const imgH = Math.round(rect.h / scale);
      // Get cached screenshot base64
      const base64Data = getFromLocalStorage('cachedScreenshot', null);
      if (!base64Data) {
        this.$message({ message: '无截图缓存，请刷新后重试', type: 'warning' });
        return;
      }
      // Create image and crop
      const img = new Image();
      img.src = `data:image/png;base64,${base64Data}`;
      await new Promise(r => { img.onload = r; });
      const cropCanvas = document.createElement('canvas');
      cropCanvas.width = imgW;
      cropCanvas.height = imgH;
      const ctx = cropCanvas.getContext('2d');
      ctx.drawImage(img, imgX, imgY, imgW, imgH, 0, 0, imgW, imgH);
      const croppedBase64 = cropCanvas.toDataURL('image/png');
      // Generate filename
      const imgName = `step_${Date.now()}.png`;
      const stepIdx = this.steps.length;
      const step = {
        _type: 'imglocate',
        action: 'click',
        image: croppedBase64,
        image_filename: imgName,
        grid_h: 1,
        grid_v: 1,
        click_col: 0,
        click_row: 0,
        timeout: 10,
        code: `click(image="${imgName}")`,
        _status: 'pending',
        _detail: '',
        _duration: null,
        _imageSaved: false
      };
      this.steps.push(step);
      this.selectedStepIndex = stepIdx;
      // Save image to server
      this.ensureFile();
      if (this.currentYamlFile) {
        await saveTaskImage(this.currentYamlFile, imgName, croppedBase64)
          .then(() => { step._imageSaved = true; })
          .catch(() => {});
      }
      this.$message({ message: `已添加图片定位步骤`, type: 'success' });
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
    handleTreeHover(node) {
      if (this.hoveredNode !== node) {
        this.hoveredNode = node;
        this.renderHierarchy();
      }
    },
    handleTreeLeave() {
      this.hoveredNode = null;
      this.renderHierarchy();
    },
    renderTreeContent(h, { node, data }) {
      return h('span', {
        on: {
          mouseenter: () => this.handleTreeHover(data),
          mouseleave: () => this.handleTreeLeave(),
        }
      }, node.label);
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
          // Load images for imglocate steps
          for (const step of this.steps) {
            if (step._type === 'imglocate' && step.image_filename) {
              try {
                const imgRes = await getTaskImage(filename, step.image_filename);
                if (imgRes.success && imgRes.data && imgRes.data.data) {
                  step.image = 'data:image/png;base64,' + imgRes.data.data;
                }
              } catch (e) { /* ignore */ }
            }
          }
          saveToLocalStorage('currentYamlFile', filename);
          this.addLog('info', `已加载: ${filename}`);
        }
      } catch (err) {
        this.$message({ showClose: true, message: `错误: ${err.message}`, type: 'error' });
      }
    },
    parseYamlToTask(content) {
      const lines = content.split('\n');
      let name = '', desc = '', platform = 'android', inStep = false, stepBuf = [];
      let stepMeta = null;
      const steps = [];
      const extraLines = [];
      let inExtra = true;
      for (const line of lines) {
        if (line.startsWith('# name:')) { name = line.split(':')[1].trim(); continue; }
        if (line.startsWith('# desc:')) { desc = line.split(':')[1].trim(); continue; }
        if (line.startsWith('# platform:')) { platform = line.split(':')[1].trim(); continue; }
        if (line.trim() === '# --step--') {
          if (inStep && stepBuf.length) {
            const s = { code: stepBuf.join('\n'), _status: 'pending', _detail: '', _duration: null };
            if (stepMeta) { Object.assign(s, stepMeta); s._type = 'imglocate'; }
            steps.push(s); stepBuf = []; stepMeta = null;
          }
          inStep = true; inExtra = false;
          continue;
        }
        if (inStep) {
          const t = line.trim();
          if (t.startsWith('# @imglocate')) {
            try { stepMeta = JSON.parse(t.slice('# @imglocate'.length).trim()); } catch (e) { stepMeta = null; }
            continue;
          }
          if (t && !t.startsWith('#') && !t.startsWith('from ha4t') && !t.startsWith('connect(') && !t.startsWith('import ') && !t.startsWith('os.environ')) {
            stepBuf.push(line);
          }
        } else if (inExtra && line.trim()) {
          if (!line.startsWith('from ha4t') && !line.startsWith('connect(') && !line.startsWith('import ') && !line.startsWith('os.environ') && !line.startsWith('# name:') && !line.startsWith('# desc:') && !line.startsWith('# platform:')) {
            extraLines.push(line);
          }
        }
      }
      if (inStep && stepBuf.length) {
        const s = { code: stepBuf.join('\n'), _status: 'pending', _detail: '', _duration: null };
        if (stepMeta) { Object.assign(s, stepMeta); s._type = 'imglocate'; }
        steps.push(s);
      }
      this.taskName = name; this.taskDesc = desc; this.taskPlatform = platform;
      this.steps = steps; this._extraLines = extraLines;
    },
    taskToYaml() {
      let y = `# name: ${this.taskName || '未命名'}\n`;
      if (this.taskDesc) y += `# desc: ${this.taskDesc}\n`;
      y += `# platform: ${this.taskPlatform}\n`;
      y += 'import os\nos.environ["FLAGS_use_mkldnn"] = "0"\n';
      y += 'from ha4t import connect\nfrom ha4t.api import *\nconnect(platform="' + this.taskPlatform + '")\n\n';
      if (this._extraLines) this._extraLines.forEach(l => { y += l + '\n'; });
      this.steps.forEach(s => {
        y += '\n# --step--\n';
        if (s._type === 'imglocate') {
          const meta = {};
          ['action','image_filename','grid_h','grid_v','click_col','click_row','timeout'].forEach(k => { if (s[k] !== undefined) meta[k] = s[k]; });
          y += '# @imglocate ' + JSON.stringify(meta) + '\n';
        }
        y += s.code + '\n';
      });
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
      if (action === 'imglocate') {
        this.enterCaptureMode();
        return;
      }
      const code = this.stepToCode(action, value);
      this.steps.push({ code, _status: 'pending', _detail: '', _duration: null });
      this.ensureFile();
    },
    enterCaptureMode() {
      this.captureMode = true;
      this.captureStart = null;
      this.captureRect = null;
      this.$message({ message: '请在截图上拖拽选择目标区域', type: 'info', duration: 3000 });
    },
    exitCaptureMode() {
      this.captureMode = false;
      this.captureStart = null;
      this.captureRect = null;
    },
    stepToCode(action, value) {
      if (action === 'imglocate') return '# 图片定位 - 等待配置';
      const esc = (s) => (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n');
      const m = {
        tap: `click(text="${esc(value)}")`,
        drag: `swipe((300, 300), (300, 700))`,
        type: `device.driver.send_keys("${esc(value)}")`,
        key: `device.driver.press("${esc(value)}")`,
        launchapp: `start_app("${esc(value)}")`,
        wait: `time.sleep(${value})`,
      };
      return m[action] || esc(value);
    },
    stepAction(type, i) {
      if (type === 'run') this.runSingleStep(i);
      else if (type === 'up' && i > 0) { const s = this.steps[i]; this.steps.splice(i, 1); this.steps.splice(i - 1, 0, s); this.selectedStepIndex = i - 1; this.ensureFile(); }
      else if (type === 'down' && i < this.steps.length - 1) { const s = this.steps[i]; this.steps.splice(i, 1); this.steps.splice(i + 1, 0, s); this.selectedStepIndex = i + 1; this.ensureFile(); }
      else if (type === 'edit') { this.cliText = this.steps[i].code; this.cliPrefix = ''; this.selectedStepIndex = i; this.$nextTick(() => this.$refs.cliInput.focus()); }
      else if (type === 'delete') { this.steps.splice(i, 1); if (this.selectedStepIndex >= this.steps.length) this.selectedStepIndex = this.steps.length - 1; this.ensureFile(); }
    },
    selectStep(i) { 
      this.selectedStepIndex = i; 
      if (this.steps[i] && this.steps[i]._type === 'imglocate') {
        this.openImgConfig(i);
      }
    },
    openImgConfig(i) {
      this.imgConfigIndex = i;
      this.imgConfigStep = JSON.parse(JSON.stringify(this.steps[i]));
      this.imgConfigVisible = true;
    },
    renderImgConfigGrid() {
      const canvas = this.$refs.imgConfigCanvas;
      const img = this.$refs.imgConfigPreview;
      if (!canvas || !img) return;
      canvas.width = img.clientWidth;
      canvas.height = img.clientHeight;
      canvas.style.width = img.clientWidth + 'px';
      canvas.style.height = img.clientHeight + 'px';
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const step = this.imgConfigStep;
      if (!step) return;
      const cols = step.grid_h;
      const rows = step.grid_v;
      const cellW = canvas.width / cols;
      const cellH = canvas.height / rows;
      // Draw grid lines
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)';
      ctx.lineWidth = 1;
      for (let c = 1; c < cols; c++) {
        ctx.beginPath();
        ctx.moveTo(c * cellW, 0);
        ctx.lineTo(c * cellW, canvas.height);
        ctx.stroke();
      }
      for (let r = 1; r < rows; r++) {
        ctx.beginPath();
        ctx.moveTo(0, r * cellH);
        ctx.lineTo(canvas.width, r * cellH);
        ctx.stroke();
      }
      // Highlight selected cell
      if (step.action === 'click') {
        ctx.fillStyle = 'rgba(54, 121, 227, 0.4)';
        ctx.fillRect(step.click_col * cellW, step.click_row * cellH, cellW, cellH);
        ctx.strokeStyle = '#3679E3';
        ctx.lineWidth = 2;
        ctx.strokeRect(step.click_col * cellW, step.click_row * cellH, cellW, cellH);
        // Draw cross at center
        const cx = step.click_col * cellW + cellW / 2;
        const cy = step.click_row * cellH + cellH / 2;
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(cx - 6, cy);
        ctx.lineTo(cx + 6, cy);
        ctx.moveTo(cx, cy - 6);
        ctx.lineTo(cx, cy + 6);
        ctx.stroke();
      }
    },
    onGridCellClick(event) {
      if (!this.imgConfigStep || this.imgConfigStep.action !== 'click') return;
      const canvas = this.$refs.imgConfigCanvas;
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      const cols = this.imgConfigStep.grid_h;
      const rows = this.imgConfigStep.grid_v;
      const cellW = canvas.width / cols;
      const cellH = canvas.height / rows;
      const col = Math.min(Math.max(Math.floor(x / cellW), 0), cols - 1);
      const row = Math.min(Math.max(Math.floor(y / cellH), 0), rows - 1);
      this.imgConfigStep.click_col = col;
      this.imgConfigStep.click_row = row;
      this.renderImgConfigGrid();
    },
    applyImgConfig() {
      if (this.imgConfigIndex < 0 || !this.imgConfigStep) return;
      const step = this.steps[this.imgConfigIndex];
      // Update step properties
      step.action = this.imgConfigStep.action;
      step.grid_h = this.imgConfigStep.grid_h;
      step.grid_v = this.imgConfigStep.grid_v;
      step.click_col = this.imgConfigStep.click_col;
      step.click_row = this.imgConfigStep.click_row;
      step.timeout = this.imgConfigStep.timeout;
      // Regenerate code
      step.code = this.generateImgCode(step);
      this.$set(this.steps, this.imgConfigIndex, { ...step });
      this.imgConfigVisible = false;
      this.saveCurrentTask();
    },
    generateImgCode(step) {
      const imgPath = step.image_filename || 'template.png';
      if (step.action === 'click') {
        if (step.grid_h === 1 && step.grid_v === 1) {
          return `click(image="${imgPath}")`;
        }
        return `click(image="${imgPath}", grid=(${step.click_col}, ${step.click_row}), splits=(${step.grid_h}, ${step.grid_v}))`;
      } else if (step.action === 'wait_show') {
        return `wait(image="${imgPath}", timeout=${step.timeout})`;
      } else if (step.action === 'wait_hide') {
        return `wait(image="${imgPath}", timeout=${step.timeout}, reverse=True)`;
      }
      return `click(image="${imgPath}")`;
    },
    stepIcon(status) {
      status = status || 'pending';
      const m = { pending: '○', running: '◐', ok: '●', fail: '✖' };
      return { icon: m[status] || '○', cls: 'icon-' + status };
    },
    async runSingleStep(i) {
      if (!this.isConnected) {       this.$message({ showClose: true, message: '尚未连接设备', type: 'warning' }); return; }
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
        ws.onerror = (e) => {
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
    taskToYamlSingle(i) {
      let y = `# name: ${this.taskName}\n# platform: ${this.taskPlatform}\n`;
      y += 'import os\nos.environ["FLAGS_use_mkldnn"] = "0"\n';
      y += 'from ha4t import connect\nfrom ha4t.api import *\nconnect(platform="' + this.taskPlatform + '")\n\n';
      const s = this.steps[i];
      y += '# --step--\n';
      if (s._type === 'imglocate') {
        const meta = {};
        ['action','image_filename','grid_h','grid_v','click_col','click_row','timeout'].forEach(k => { if (s[k] !== undefined) meta[k] = s[k]; });
        y += '# @imglocate ' + JSON.stringify(meta) + '\n';
      }
      y += s.code + '\n';
      return y;
    },
    saveCurrentTask() {
      if (!this.currentYamlFile) {
        this.currentYamlFile = `untitled_${Date.now()}.py`;
        this.taskName = this.taskName || '新建用例';
        this.taskPlatform = this.platform || 'android';
        saveToLocalStorage('currentYamlFile', this.currentYamlFile);
      }
      this.currentYamlContent = this.taskToYaml();
      saveTask(this.currentYamlFile, this.currentYamlContent).catch(() => {});
      // Save any unsaved images for imglocate steps
      this.steps.forEach((s) => {
        if (s._type === 'imglocate' && s.image && s.image_filename && !s._imageSaved) {
          saveTaskImage(this.currentYamlFile, s.image_filename, s.image)
            .then(() => { s._imageSaved = true; })
            .catch(() => {});
        }
      });
      this.refreshYamlFiles();
    },
    ensureFile() {
      this.saveCurrentTask();
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
      this.settingsVisible = true;
    },
    async openTasksFolder() {
      await fetch(`${API_HOST}tasks/open-folder`, { method: 'POST' });
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
        if (this.captureMode) { this.exitCaptureMode(); }
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

      // Image locate steps require screenshot selection first
      if (action === 'imglocate') {
        this.addStep('imglocate', value);
        this.cliText = '';
        this.cliPrefix = '';
        this.selectedStepIndex = -1;
        this.slashVisible = false;
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
      if (item.action === 'imglocate') {
        this.addStep('imglocate', '');
        this.slashVisible = false;
        this.cliText = '';
        this.cliPrefix = '';
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
          this.$message({ message: res.message || '失败 to fetch 个应用', type: 'error' });
        }
      } catch (e) {
        this.$message({ message: `Error: ${e.message}`, type: 'error' });
      }
    },
    addLog(level, text) {
      this.logLines.push({ level, text: `${new Date().toLocaleTimeString()} ${text}` });
      if (!this.logOpen) this.logOpen = true;
    },

    async deviceAction(key) {
      if (!this.isConnected) return;
      if (this.rightTab !== 'editor') return;
      const idx = this.steps.length;
      this.steps.push({ code: `device.driver.press("${key}")`, _status: 'pending', _detail: '', _duration: null });
      this.ensureFile();
      this.addLog('info', `已插入: press("${key}")`);
      if (this.autoRun) this.runSingleStep(idx);
    },

    onMouseDblClick() {
      if (this.captureMode) return;
      if (this.selectedNode && this.rightTab === 'editor') {
        this.insertStepFromElement();
      }
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
      const sel = this.generateU2Selector(this.selectedNode);
      if (!sel) {
        this.$message({ message: '该元素无可用选择器', type: 'warning' });
        return;
      }
      const code = `click(${sel})`;
      const idx = this.steps.length;
      this.steps.push({ code, _status: 'pending', _detail: '', _duration: null });
      this.ensureFile();
      this.$message({ message: `已插入: ${code}`, type: 'success' });
      if (this.autoRun) this.runSingleStep(idx);
    }
  }
});