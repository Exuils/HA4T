import { useMsg }    from './composables/useMsg.js';
import { useUndo }   from './composables/useUndo.js';
import { useDevice } from './composables/useDevice.js';
import { useTask }   from './composables/useTask.js';
import { useRunner } from './composables/useRunner.js';
import { usePom }    from './composables/usePom.js';
import { usePomVerify } from './composables/usePomVerify.js';
import DevicePane    from './components/DevicePane.js';
import StepPane      from './components/StepPane.js';
import InspectorPane from './components/InspectorPane.js';
import ConsolePane   from './components/ConsolePane.js';

import { saveToLocalStorage, getFromLocalStorage } from './utils.js';
import { getVersion, listDevices as apiListDevices, connectDevice as apiConnectDevice } from './api.js';

const { defineComponent, provide, watch, onMounted, nextTick, ref } = Vue;

const TEMPLATE = `
<div class="layout" :class="{ 'capture-mode': device.captureMode.value }">
  <!-- Header -->
  <div class="header">
    <div style="margin-right:20px">
      <span style="font-weight:bold;font-size:18px">HA4T Editor</span>
      <span style="color:#8492a6;font-size:12px;margin-left:6px">{{ version }}</span>
    </div>
    <el-select v-model="device.platform.value" placeholder="选择平台"
        style="margin-right:10px;width:140px" @change="device.initPlatform">
      <el-option label="HarmonyOS" value="harmony"></el-option>
      <el-option label="Android"   value="android"></el-option>
      <el-option label="iOS"       value="ios"></el-option>
    </el-select>
    <el-select v-model="device.serial.value" placeholder="选择设备"
        style="margin-right:20px;width:250px" @visible-change="onDeviceDropdown">
      <el-option v-for="d in device.devices.value" :key="d" :label="d" :value="d"></el-option>
    </el-select>
    <el-tooltip v-if="device.platform.value === 'ios'" content="设置 WDA 地址, 如 http://localhost:8100" placement="top">
      <el-input v-model="device.wdaUrl.value" style="width:180px;margin-right:20px" placeholder="WDA 地址" size="default"></el-input>
    </el-tooltip>
    <el-tooltip v-if="device.platform.value === 'ios'" content="设置 iOS 层级最大深度, 默认 30" placement="top">
      <el-input v-model="device.snapshotMaxDepth.value" style="width:110px;margin-right:20px" placeholder="最大深度" size="default"></el-input>
    </el-tooltip>
    <el-button :disabled="device.isConnecting.value" style="margin-right:10px;width:100px" @click="connectDevice">
      <el-icon v-if="device.isConnecting.value" class="is-loading"><Loading /></el-icon>
      <span v-else>{{ device.isConnected.value ? '已连接' : '连接' }}</span>
    </el-button>
    <el-tooltip v-if="!device.isConnected.value" content="请先连接设备" placement="top">
      <el-button :disabled="true" style="margin-right:10px;width:160px">获取层级</el-button>
    </el-tooltip>
    <el-button v-else :disabled="device.isDumping.value" style="margin-right:10px;width:160px" @click="doScreenshotAndDump">
      <el-icon v-if="device.isDumping.value" class="is-loading"><Loading /></el-icon>
      <span>获取层级</span>
    </el-button>
    <div style="flex:1"></div>
    <el-link href="https://github.com/exuils/HA4T" target="_blank" :underline="false" style="color:#8492a6">GitHub</el-link>
  </div>


  <!-- Left divider drag -->
  <div class="divider-v divider-left"
      @mousedown="startDragLeft"
      :class="{ 'divider-active': draggingLeft }"></div>

  <!-- Main content grid areas -->
  <DevicePane />

  <StepPane />

  <!-- Right divider drag -->
  <div class="divider-v divider-right"
      @mousedown="startDragRight"
      :class="{ 'divider-active': draggingRight }"></div>

  <InspectorPane />



</div>
`;

export default defineComponent({
  name: 'App',
  template: TEMPLATE,
  components: { DevicePane, StepPane, InspectorPane },

  setup() {
    const msg    = useMsg();
    const undo   = useUndo();
    const device = useDevice();
    const task   = useTask();
    const runner = useRunner(task, device);
    const pom    = usePom();
    const verify = usePomVerify({ pom, device, msg });


    provide('msg',    msg);
    provide('undo',   undo);
    provide('device', device);
    provide('task',   task);
    provide('runner', runner);
    provide('pom',    pom);
    provide('verify', verify);

    const version = ref('');

    // ── watchers ──────────────────────────────────────────────────────────

    watch(() => device.platform.value, (v) => saveToLocalStorage('platform', v));
    watch(() => device.wdaUrl.value,   (v) => saveToLocalStorage('wdaUrl', v));
    watch(() => device.snapshotMaxDepth.value, (v) => saveToLocalStorage('snapshotMaxDepth', v));


    // 验证结果 → 截图 overlay 同步（useCanvas.renderHierarchy 读 window._pomVerifyResults）
    watch(() => verify.results.value, (v) => {
      window._pomVerifyResults = verify.verifyMode.value ? v : null;
      if (window._renderHierarchyCanvas) window._renderHierarchyCanvas();
    }, { deep: true });
    watch(() => verify.verifyMode.value, (on) => {
      window._pomVerifyResults = on ? verify.results.value : null;
      if (window._renderHierarchyCanvas) window._renderHierarchyCanvas();
    });
    watch(() => task.autoRun.value,    (v) => saveToLocalStorage('autoRun', v));

    // ── device actions ────────────────────────────────────────────────────

    async function onDeviceDropdown(visible) {
      if (visible) await device.listDevice();
    }

    async function connectDevice() {
      await device.connectDevice(msg);
      if (device.isConnected.value) {
        await doScreenshotAndDump();
      }
    }

    async function doScreenshotAndDump() {
      // DevicePane registers itself as window._screenshotAndDump
      if (window._screenshotAndDump) await window._screenshotAndDump();
    }

    // ── drag dividers ─────────────────────────────────────────────────────

    const draggingLeft  = ref(false);
    const draggingRight = ref(false);

    function startDragLeft(e) {
      draggingLeft.value = true;
      const onMove = (ev) => {
        const leftW = Math.max(200, Math.min(600, ev.clientX));
        document.documentElement.style.setProperty('--col-left', leftW + 'px');
      };
      const onUp = () => {
        draggingLeft.value = false;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    }

    function startDragRight(e) {
      draggingRight.value = true;
      // right divider sits between inspector (middle) and editor (rightmost).
      // dragging adjusts middle column width = clientX − (left col + left divider).
      const cs = getComputedStyle(document.documentElement);
      const leftW = parseInt(cs.getPropertyValue('--col-left')) || 360;
      const onMove = (ev) => {
        const midW = Math.max(220, Math.min(700, ev.clientX - leftW - 8));
        document.documentElement.style.setProperty('--col-mid', midW + 'px');
      };
      const onUp = () => {
        draggingRight.value = false;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    }

    // ── lifecycle ──────────────────────────────────────────────────────────

    onMounted(async () => {
      // hierarchy 重新 dump 后自动重扫（useCanvas 调 window._pomVerifyOnHierarchy）
      window._pomVerifyOnHierarchy = verify.onHierarchyUpdated;

      // fetch version
      try {
        const res = await getVersion();
        version.value = res.data || '';
      } catch (e) { /* ignore */ }

      // load file list and saved file
      await task.refreshYamlFiles();
      if (task.currentYamlFile.value) {
        await task.loadYamlFile(task.currentYamlFile.value, msg);
      }

      // keyboard shortcuts
      document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
          e.preventDefault();
          if (e.shiftKey) { task.steps.value = undo.redo(task.steps.value); }
          else            { task.steps.value = undo.undo(task.steps.value); }
          task.selectedStepIndex.value = -1;
          task.saveCurrentTask(device.serial.value).catch(() => {});
        }
        if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
          e.preventDefault();
          task.steps.value = undo.redo(task.steps.value);
          task.selectedStepIndex.value = -1;
          task.saveCurrentTask(device.serial.value).catch(() => {});
        }
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
          e.preventDefault();
          window._focusCli && window._focusCli();
        }
      });

      await device.listDevice();
      if (device.serial.value && !device.isConnected.value) {
        await connectDevice();
      }
    });

    return {
      version, device, task, runner, msg,
      onDeviceDropdown, connectDevice, doScreenshotAndDump,
      draggingLeft, draggingRight, startDragLeft, startDragRight,
    };
  },
});
