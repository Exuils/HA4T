import { useCanvas } from '../composables/useCanvas.js';

const { inject } = Vue;

const TEMPLATE = `
<div class="left" :class="{ 'capture-mode': device.captureMode.value }">
  <div class="screen-toolbar">
    <div class="toolbar-left">
      <el-button size="small" @click="deviceAction('home')"      :disabled="!device.isConnected.value" title="主页">
        <el-icon><ArrowUp /></el-icon>
      </el-button>
      <el-button size="small" @click="deviceAction('back')"      :disabled="!device.isConnected.value" title="返回">
        <el-icon><Back /></el-icon>
      </el-button>
      <el-button size="small" @click="deviceAction('volume_up')" :disabled="!device.isConnected.value" title="音量+">
        <el-icon><Plus /></el-icon>
      </el-button>
      <el-button size="small" @click="deviceAction('volume_down')" :disabled="!device.isConnected.value" title="音量-">
        <el-icon><Minus /></el-icon>
      </el-button>
    </div>
    <div class="toolbar-right">
      <el-button size="small" @click="enterCapture" :disabled="!device.isConnected.value || device.captureMode.value || device.swipeRecordMode.value" title="添加图片定位步骤">
        <el-icon><Picture /></el-icon>
      </el-button>
      <el-button size="small" @click="enterSwipe"   :disabled="!device.isConnected.value || device.captureMode.value || device.swipeRecordMode.value" title="录制滑动手势">
        <el-icon><Rank /></el-icon>
      </el-button>
      <el-button size="small" @click="refresh"      :disabled="!device.isConnected.value || device.isDumping.value" title="刷新">
        <el-icon><Refresh /></el-icon>
      </el-button>
    </div>
  </div>
  <div v-if="device.captureMode.value" class="capture-indicator">拖拽选择目标区域 (按 Esc 取消)</div>
  <div v-if="device.swipeRecordMode.value" class="capture-indicator swipe-indicator">点击截图记录滑动起点和终点 (按 Esc 取消)</div>
  <div class="canvas-area" ref="canvasArea">
    <div v-if="device.isDumping.value" class="canvas-loading-overlay">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <div class="canvas-loading-text">正在获取层级…</div>
    </div>
    <div class="canvas-stack">
      <canvas id="screenshotCanvas"></canvas>
      <canvas id="hierarchyCanvas"></canvas>
    </div>
  </div>
</div>
`;

export default {
  name: 'DevicePane',
  template: TEMPLATE,

  setup() {
    const device = inject('device');
    const task   = inject('task');
    const runner = inject('runner');
    const msg    = inject('msg');

    const canvas = useCanvas({ device, task, runner, msg });

    function deviceAction(key) {
      if (!device.isConnected.value) return;
      task.steps.value.push({ code: `dev.press("${key}")`, remark: '', _status: 'pending', _detail: '', _duration: null });
      if (task.autoRun.value) runner.runSingleStep(task.steps.value.length - 1, canvas.screenshotAndDumpHierarchy, msg);
    }

    function enterCapture() { device.enterCaptureMode(msg); }
    function enterSwipe()   { device.enterSwipeRecordMode(msg); }
    function refresh()      { canvas.screenshotAndDumpHierarchy(); }

    return { device, canvas, deviceAction, enterCapture, enterSwipe, refresh };
  },

  mounted() {
    this.canvas.initCanvas();
    this.canvas.loadCachedScreenshot();
  },
};
