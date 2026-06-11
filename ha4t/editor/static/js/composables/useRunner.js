import { runAllure as apiRunAllure } from '../api.js';

const { ref } = Vue;

export function useRunner(task, device) {
  const isRunning = ref(false);
  const logLines  = ref([]);
  const logOpen   = ref(false);

  function addLog(level, text) {
    logLines.value.push({ level, text: `${new Date().toLocaleTimeString()} ${text}` });
    if (level === 'fail') logOpen.value = true;
  }

  function scheduleDump(screenshotAndDumpHierarchy) {
    clearTimeout(window._dumpTimer);
    window._dumpTimer = setTimeout(() => {
      if (device.isConnected.value) screenshotAndDumpHierarchy();
    }, 1000);
  }

  function wsRun(yaml, stepOffset, screenshotAndDumpHierarchy) {
    return new Promise((resolve, reject) => {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${proto}//${location.host}/ws/run`);
      ws.onopen = () => {
        ws.send(JSON.stringify({
          platform: task.taskPlatform.value,
          serial: device.serial.value,
          filename: task.currentYamlFile.value || undefined,
          content: yaml,
          step_offset: stepOffset || 0,
        }));
      };
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'step') {
          const idx = (msg.index || 1) - 1;
          if (task.steps.value[idx]) {
            const s = { ...task.steps.value[idx], _status: msg.status, _detail: msg.detail || '', _duration: msg.duration };
            if (msg.status === 'fail') s._detailOpen = true;
            task.steps.value[idx] = s;
            if (msg.status === 'fail') logOpen.value = true;
            const color = { ok:'ok', fail:'fail', running:'info', skipped:'warn' }[msg.status] || 'info';
            addLog(color, `Step ${msg.index} → ${msg.status}`);
          }
          if (msg.status === 'ok' || msg.status === 'fail') {
            scheduleDump(screenshotAndDumpHierarchy);
          }
        } else if (msg.type === 'log') {
          addLog('info', msg.text);
        } else if (msg.type === 'done') {
          addLog(msg.fail ? 'fail' : 'ok', `${msg.ok}/${msg.total} 步通过`);
          scheduleDump(screenshotAndDumpHierarchy);
          ws.close();
          resolve();
        } else if (msg.type === 'error') {
          addLog('fail', msg.msg);
          ws.close();
          reject(new Error(msg.msg));
        }
      };
      ws.onerror = () => { addLog('fail', 'WebSocket 连接错误'); reject(new Error('WS 错误')); };
    });
  }

  async function runSingleStep(i, screenshotAndDumpHierarchy, msg) {
    if (!device.isConnected.value) { msg.warn('尚未连接设备'); return; }
    const s = task.steps.value[i];
    task.steps.value[i] = { ...s, _status: 'running' };
    isRunning.value = true;
    try {
      await wsRun(task.taskToYamlSingle(i, device.serial.value), 0, screenshotAndDumpHierarchy);
    } catch (e) {
      task.steps.value[i] = { ...task.steps.value[i], _status: 'fail', _detail: e.message, _detailOpen: true };
      addLog('fail', `步骤 ${i + 1} 错误: ${e.message}`);
    } finally {
      isRunning.value = false;
    }
  }

  async function runFromStep(i, screenshotAndDumpHierarchy, msg) {
    if (!device.isConnected.value) { msg.warn('尚未连接设备'); return; }
    logLines.value = [];
    addLog('info', `从第 ${i + 1} 步开始运行...`);
    isRunning.value = true;
    try {
      await wsRun(task.taskToYamlFrom(i, device.serial.value), i, screenshotAndDumpHierarchy);
    } catch (e) {
      addLog('fail', `运行错误: ${e.message}`);
    } finally {
      isRunning.value = false;
    }
  }

  async function runAllSteps(screenshotAndDumpHierarchy, msg, serial) {
    task.steps.value.forEach((s, i) => {
      task.steps.value[i] = { ...s, _status: 'pending', _detail: '', _duration: null, _detailOpen: false };
    });
    task.currentYamlContent.value = task.taskToYaml(serial);
    logLines.value = [];
    addLog('info', '正在执行全部步骤...');
    isRunning.value = true;
    try {
      await wsRun(task.currentYamlContent.value, 0, screenshotAndDumpHierarchy);
    } catch (e) {
      addLog('fail', `运行错误: ${e.message}`);
    } finally {
      isRunning.value = false;
    }
  }

  async function runAllStepsAllure(msg) {
    if (!task.currentYamlFile.value) return;
    addLog('info', '正在运行并生成 Allure 报告...');
    try {
      const res = await apiRunAllure(task.currentYamlFile.value);
      if (res.success && res.data) {
        addLog('ok', `运行完成, returncode=${res.data.returncode}`);
        if (res.data.report_url) { msg.success('Allure 报告已生成'); window.open(res.data.report_url, '_blank'); }
      } else {
        addLog('fail', `运行失败: ${res.message}`);
      }
    } catch (e) { addLog('fail', `Allure 运行错误: ${e.message}`); }
  }

  return { isRunning, logLines, logOpen, addLog, wsRun, runSingleStep, runFromStep, runAllSteps, runAllStepsAllure };
}
