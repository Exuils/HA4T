import { saveToLocalStorage, getFromLocalStorage, copyToClipboard as utilCopy } from './utils.js';
import { getVersion, listDevices, connectDevice } from './api.js';
import { API_HOST } from './config.js';
import { CanvasMethods } from './canvas.js';
import { HierarchyMethods } from './hierarchy.js';
import { StepEditorMethods } from './step-editor.js';
import { PropertyPanelMethods } from './property-panel.js';

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
        label: 'label'
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
      projectId: '',
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
      _extraLines: [],

      // Image capture state
      captureMode: false,
      captureStart: null,
      captureRect: null,

      // Swipe record state
      swipeRecordMode: false,
      swipePoints: [],

      // Element select mode
      elementSelectMode: false,
    };
  },
  computed: {
    selectedStep() {
      return (this.selectedStepIndex >= 0 && this.selectedStepIndex < this.steps.length)
        ? this.steps[this.selectedStepIndex]
        : null;
    },
    selectedNodeDetails() {
      const isHarmony = this.platform === 'harmony';
      const defaultDetails = this.getDefaultNodeDetails(this.platform);
      if (!this.selectedNode) return defaultDetails;
      const nodeDetails = Object.entries(this.selectedNode)
        .filter(([key]) => !['children', '_id', '_parentId', 'frame'].includes(key))
        .map(([key, value]) => ({
          key: key === '_type' ? (isHarmony ? 'type' : 'className') : key,
          value
        }));
      return [...defaultDetails, ...nodeDetails];
    },
    stepConfig() {
      return this.selectedStepConfig();
    },
  },
  watch: {
    platform(newVal) { saveToLocalStorage('platform', newVal); },
    wdaUrl(newVal) { saveToLocalStorage('wdaUrl', newVal); },
    snapshotMaxDepth(newVal) { saveToLocalStorage('snapshotMaxDepth', newVal); },
    nodeFilterText(val) { this.$refs.treeRef && this.$refs.treeRef.filter(val); },
    autoRun(val) { saveToLocalStorage('autoRun', val); },
    cliText() { this.onCliInput(); },
    selectedStepIndex() {
      this.$nextTick(() => this.renderImgConfigGrid());
    },
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
    // ── Initialization ──
    initPlatform() {
      this.serial = '';
      this.isConnected = false;
      this.selectedNode = null;
      this.treeData = [];
    },
    async fetchVersion() {
      try {
        const response = await getVersion();
        this.version = response.data;
      } catch (err) { console.error(err); }
    },
    async listDevice() {
      try {
        const response = await listDevices(this.platform);
        this.devices = response.data;
        if (!this.serial && this.devices.length > 0) this.serial = this.devices[0];
      } catch (err) {
        this.$message({ showClose: true, message: `错误: ${err.message}`, type: 'error' });
      }
    },
    async connectDevice() {
      this.isConnecting = true;
      try {
        if (!this.serial) throw new Error('请先选择设备');
        if (this.platform === 'ios' && !this.wdaUrl) throw new Error('请输入 WDA 地址');
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

    // ── Swipe record ──
    enterSwipeRecordMode() {
      this.swipeRecordMode = true;
      this.swipePoints = [];
      this.$message({ message: '请点击滑动起点', type: 'info', duration: 3000 });
    },
    exitSwipeRecordMode() {
      this.swipeRecordMode = false;
      this.swipePoints = [];
      this.renderHierarchy();
    },
    finishSwipeRecord() {
      const [p1, p2] = this.swipePoints;
      const code = `swipe((${p1.x.toFixed(3)}, ${p1.y.toFixed(3)}), (${p2.x.toFixed(3)}, ${p2.y.toFixed(3)}))`;
      const idx = this.steps.length;
      this.steps.push({ code, remark: '', _status: 'pending', _detail: '', _duration: null });
      this.ensureFile();
      this.$message({ message: `已添加滑动: ${code}`, type: 'success' });
      this.exitSwipeRecordMode();
      if (this.autoRun) this.runSingleStep(idx);
    },

    // ── Image capture ──
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

    // ── Clipboard ──
    copyToClipboard(value) {
      const success = utilCopy(value);
      this.$message({ showClose: true, message: success ? "复制成功" : "复制失败", type: success ? 'success' : 'error' });
    },

    // ── Divider ──
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
    hoverDivider() { this.isDividerHovered = true; },
    leaveDivider() { this.isDividerHovered = false; },

    // ── Settings ──
    getProjectId() {
      if (this.projectId) return this.projectId;
      this.projectId = 'proj_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
      return this.projectId;
    },

    // ── Merge external methods ──
    ...CanvasMethods,
    ...HierarchyMethods,
    ...StepEditorMethods,
    ...PropertyPanelMethods,
  }
});
