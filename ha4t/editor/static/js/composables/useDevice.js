import { saveToLocalStorage, getFromLocalStorage } from '../utils.js';
import { listDevices as apiListDevices, connectDevice as apiConnectDevice, fetchScreenshot as apiFetchScreenshot, fetchHierarchy as apiFetchHierarchy } from '../api.js';
import { buildXPath } from '../utils/xpathLite.js';

const { ref, reactive } = Vue;

export function useDevice() {
  const platform     = ref(getFromLocalStorage('platform', 'harmony'));
  const serial       = ref(getFromLocalStorage('serial', ''));
  const devices      = ref([]);
  const isConnected  = ref(false);
  const isConnecting = ref(false);
  const isDumping    = ref(false);
  const wdaUrl       = ref(getFromLocalStorage('wdaUrl', ''));
  const snapshotMaxDepth = ref(getFromLocalStorage('snapshotMaxDepth', 30));
  // displaySize / scale 是设备运行时元数据，每次 dump hierarchy 都会被刷新 ——
  // 不持久化，避免重启后看到的是上次设备的尺寸残留误导。
  const displaySize  = ref([0, 0]);
  const scale        = ref(1);
  // 当前前台应用 {package, activity} —— 每次 dump hierarchy 由后端塞过来，
  // UI header 显示「当前页面：xxx · yyy」。后端拿不到时为 null。
  const currentApp   = ref(null);
  const screenshotTransform = reactive({ scale: 1, offsetX: 0, offsetY: 0 });
  const jsonHierarchy = ref({});
  const treeData     = ref([]);
  const hoveredNode  = ref(null);
  const selectedNode = ref(null);
  const captureMode  = ref(false);
  const captureStart = ref(null);
  const captureRect  = ref(null);
  const swipeRecordMode = ref(false);
  const swipePoints  = ref([]);
  const elementSelectMode = ref(false);

  function initPlatform() {
    serial.value = '';
    isConnected.value = false;
    selectedNode.value = null;
    treeData.value = [];
    devices.value = [];
    currentApp.value = null;
    // refresh device list for the new platform
    listDevice();
  }

  async function listDevice() {
    try {
      const res = await apiListDevices(platform.value);
      devices.value = res.data || [];
      if (!serial.value && devices.value.length > 0) serial.value = devices.value[0];
    } catch (e) {
      console.error('listDevice:', e);
    }
  }

  async function connectDevice(msg) {
    isConnecting.value = true;
    try {
      if (!serial.value) throw new Error('请先选择设备');
      if (platform.value === 'ios' && !wdaUrl.value) throw new Error('请输入 WDA 地址');
      const res = await apiConnectDevice(platform.value, serial.value, wdaUrl.value, snapshotMaxDepth.value);
      if (res.success) {
        isConnected.value = true;
        saveToLocalStorage('serial', serial.value);
      } else {
        throw new Error(res.message);
      }
    } catch (e) {
      msg.error('错误: ' + e.message);
    } finally {
      isConnecting.value = false;
    }
  }

  function enterCaptureMode(msg) {
    captureMode.value = true;
    captureStart.value = null;
    captureRect.value = null;
    msg.info('请在截图上拖拽选择目标区域');
  }

  function exitCaptureMode() {
    captureMode.value = false;
    captureStart.value = null;
    captureRect.value = null;
  }

  function enterSwipeRecordMode(msg) {
    swipeRecordMode.value = true;
    swipePoints.value = [];
    msg.info('请点击滑动起点');
  }

  function exitSwipeRecordMode() {
    swipeRecordMode.value = false;
    swipePoints.value = [];
  }
  // 选中节点：同步算出 xpath 写到 node 上（mutate hierarchy 同引用），再赋值 selectedNode。
  // 这样 selectorFromNode / 详情面板都能立刻看到 xpath。
  // 算法 O(K) 查询 + O(N) 索引（< 1ms / 几千节点），同步无 HTTP。
  function selectNode(node) {
    if (!node) {
      selectedNode.value = null;
      return null;
    }
    if (!node.xpath && jsonHierarchy.value) {
      node.xpath = buildXPath(platform.value, jsonHierarchy.value, node._id);
    }
    selectedNode.value = node;
    return node;
  }


  return {
    platform, serial, devices, isConnected, isConnecting, isDumping,
    wdaUrl, snapshotMaxDepth, displaySize, scale, currentApp, screenshotTransform,
    jsonHierarchy, treeData, hoveredNode, selectedNode,
    captureMode, captureStart, captureRect,
    swipeRecordMode, swipePoints, elementSelectMode,
    initPlatform, listDevice, connectDevice, selectNode,
  };
}
