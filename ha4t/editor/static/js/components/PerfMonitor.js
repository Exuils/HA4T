// 性能监控 — 每项指标一张折线图。
// CPU 图包含：app CPU% + 系统 CPU% + 各核心%（core_0 ~ core_N）。

import { listPerfRecords, deletePerfRecord, listPackages } from '../api.js';

const { ref, computed, onMounted, onBeforeUnmount, inject, nextTick, watch } = Vue;

const CORE_COLORS = [
  '#f56c6c','#909399','#409eff','#67c23a',
  '#e6a23c','#b88cf9','#36cfc9','#ff85c0',
  '#ffc53d','#597ef7','#73d13d','#ff7a45',
];

const TEMPLATE = `
<div class="perf-pane">
  <div class="perf-sub-tabs">
    <button :class="['perf-sub-tab', subTab === 'monitor' ? 'active' : '']" @click="subTab = 'monitor'">实时监控</button>
    <button :class="['perf-sub-tab', subTab === 'records' ? 'active' : '']" @click="subTab = 'records'; loadRecords()">历史记录</button>
  </div>

  <template v-if="subTab === 'monitor'">
    <div class="perf-toolbar">
      <span class="perf-toolbar-title">性能监控</span>
      <span class="perf-toolbar-hint" v-if="status === 'idle'">准备就绪</span>
      <span class="perf-toolbar-recording" v-else-if="status === 'recording'">采集中 {{ elapsed }}s</span>
      <span class="perf-toolbar-hint" v-else-if="status === 'stopped'">已停止</span>
      <span style="flex:1"></span>
      <label class="perf-label" :class="{ disabled: status === 'recording' }"><input type="checkbox" v-model="checked.cpu" :disabled="status === 'recording'"> CPU</label>
      <label class="perf-label" :class="{ disabled: status === 'recording' }"><input type="checkbox" v-model="checked.mem" :disabled="status === 'recording'"> 内存</label>
      <label class="perf-label" :class="{ disabled: status === 'recording' }"><input type="checkbox" v-model="checked.battery" :disabled="status === 'recording'"> 电量</label>
      <el-switch v-model="trackSubprocesses" size="small" :disabled="status === 'recording'" active-text="子进程" inactive-text="主进程" style="margin-left:4px" />
      <el-tooltip content="子进程(:push/:remote)CPU加入统计还是仅主进程" placement="top" :show-after="300">
        <el-icon style="font-size:14px;color:var(--fg-2);cursor:pointer;margin-right:4px;"><InfoFilled /></el-icon>
      </el-tooltip>
      <el-switch v-model="memoryMode" active-value="pss" inactive-value="rss" size="small" :disabled="status === 'recording'" active-text="PSS" inactive-text="RSS" />
      <el-tooltip content="RSS(快速偏高) vs PSS(精确慢~180ms)" placement="top" :show-after="300">
        <el-icon style="font-size:14px;color:var(--fg-2);cursor:pointer;margin-right:4px;"><InfoFilled /></el-icon>
      </el-tooltip>
      <el-select v-model="packageName" placeholder="包名" size="small" filterable allow-create class="perf-pkg-select" :disabled="status === 'recording'" clearable @visible-change="onPkgVisible">
        <el-option v-for="pkg in pkgSuggestions" :key="pkg" :label="pkg" :value="pkg" />
      </el-select>
      <input v-model.number="interval" placeholder="间隔(s)" class="perf-input perf-interval" :disabled="status === 'recording'" />
      <button v-if="status !== 'recording'" class="perf-btn perf-btn-start" @click="startCollect" :disabled="!canStart">&#9654; 开始</button>
      <button v-else class="perf-btn perf-btn-stop" @click="stopCollect">&#9646;&#9646; 停止</button>
    </div>

    <div v-if="showCpuChart" class="perf-chart-block">
      <div class="perf-chart-label">CPU</div>
      <div class="perf-chart-canvas-wrap"><canvas ref="cpuCanvas"></canvas></div>
    </div>
    <div v-if="showMemChart" class="perf-chart-block">
      <div class="perf-chart-label">内存</div>
      <div class="perf-chart-canvas-wrap"><canvas ref="memCanvas"></canvas></div>
    </div>
    <div v-if="showBatteryChart" class="perf-chart-block">
      <div class="perf-chart-label">电量</div>
      <div class="perf-chart-canvas-wrap"><canvas ref="battCanvas"></canvas></div>
    </div>

    <div v-if="csvPath" class="perf-csv-row">
      <span>已保存：</span>
      <a :href="'/perf/records/' + encodeURIComponent(csvPath)" download class="perf-csv-link">{{ csvPath }}</a>
      <span class="perf-csv-points">{{ csvPoints }} 个采集点</span>
    </div>
  </template>

  <template v-if="subTab === 'records'">
    <!-- 二级页面：详情 -->
    <div v-if="viewMode === 'detail'" class="perf-view-page">
      <div class="perf-view-head">
        <button class="perf-btn-sm" @click="closeView">&#x2190; 返回</button>
        <span class="perf-view-title">{{ viewedRecord }}</span>
        <span style="flex:1"></span>
      </div>
      <div class="perf-view-meta" v-if="viewMeta.device || viewMeta.package">
        <span class="perf-meta-item"><span class="perf-meta-lbl">设备</span>{{ viewMeta.device || '--' }}</span>
        <span class="perf-meta-item"><span class="perf-meta-lbl">系统</span>{{ viewMeta.android || '--' }}</span>
        <span class="perf-meta-item"><span class="perf-meta-lbl">包名</span><code>{{ viewMeta.package || '全局' }}</code></span>
        <span class="perf-meta-item"><span class="perf-meta-lbl">间隔</span>{{ viewMeta.interval || '--' }}s</span>
        <span class="perf-meta-item"><span class="perf-meta-lbl">采集</span>{{ viewMeta.points || '0' }} 点</span>
      </div>

      <div class="perf-chart-block">
        <div class="perf-chart-label">CPU</div>
        <div class="perf-chart-canvas-wrap"><canvas ref="viewCpuCanvas"></canvas></div>
        <div class="perf-chart-stats">
          <span v-for="s in cpuViewStats" :key="s.field" class="perf-cstat">
            <span class="perf-cstat-lbl">{{ s.label }}</span>
            <span class="perf-cstat-val"><b>{{ s.avg }}</b>{{ s.unit }}</span>
            <span class="perf-cstat-ext">min {{ s.min }} | max {{ s.max }}</span>
          </span>
        </div>
      </div>

      <div class="perf-chart-block">
        <div class="perf-chart-label">内存</div>
        <div class="perf-chart-canvas-wrap"><canvas ref="viewMemCanvas"></canvas></div>
        <div class="perf-chart-stats">
          <span v-for="s in memViewStats" :key="s.field" class="perf-cstat">
            <span class="perf-cstat-lbl">{{ s.label }}</span>
            <span class="perf-cstat-val"><b>{{ s.avg }}</b>{{ s.unit }}</span>
            <span class="perf-cstat-ext">min {{ s.min }} | max {{ s.max }}</span>
          </span>
        </div>
      </div>

      <!-- 电量图 + 统计 -->
      <div class="perf-chart-block">
        <div class="perf-chart-label">电量</div>
        <div class="perf-chart-canvas-wrap"><canvas ref="viewBattCanvas"></canvas></div>
        <div class="perf-chart-stats">
          <span v-for="s in battViewStats" :key="s.field" class="perf-cstat">
            <span class="perf-cstat-lbl">{{ s.label }}</span>
            <span class="perf-cstat-val"><b>{{ s.avg }}</b>{{ s.unit }}</span>
            <span class="perf-cstat-ext">min {{ s.min }} | max {{ s.max }}</span>
          </span>
        </div>
      </div>
    </div>
    <!-- 一级页面：列表 -->
    <div v-else class="perf-records-section">
      <div class="perf-records-header">
        <span class="perf-records-title">历史记录</span>
        <span class="perf-records-count">{{ records.length }} 个</span>
        <span style="flex:1"></span>
        <button class="perf-btn-sm" @click="loadRecords" :disabled="loadingRecords">&#x21bb; 刷新</button>
      </div>
      <div v-if="loadingRecords" class="perf-records-empty">加载中…</div>
      <div v-else-if="records.length === 0" class="perf-records-empty">还没有性能记录。</div>
      <div v-else class="perf-records-list">
        <div v-for="r in records" :key="r.name" class="perf-record-card">
          <div class="perf-record-card-head">
            <span class="perf-record-card-name">{{ r.name }}</span>
            <span class="perf-record-card-time">{{ fmtTs(r.mtime) }}</span>
          </div>
          <div class="perf-record-card-summary"><span class="perf-record-card-size">{{ fmtSize(r.size) }}</span></div>
          <div class="perf-record-card-actions">
            <button class="perf-btn-sm" @click="viewRecord(r)">&#9654; 查看</button>
            <button class="perf-btn-sm" @click="downloadRecord(r)">&#x21E9; 下载</button>
            <button class="perf-btn-sm perf-btn-danger" @click="onDelete(r)">&#x2715; 删除</button>
          </div>
        </div>
      </div>
    </div>
  </template>
`;

export default {
  name: 'PerfMonitor',
  template: TEMPLATE,

  setup() {
    const device = inject('device');
    const msg    = inject('msg', null);
    const packageName   = ref('');
    const csvPath       = ref('');
    const csvPoints     = ref(0);
    const ws            = ref(null);
    const interval      = ref(1);

    const subTab        = ref('monitor');
    const status        = ref('idle');
    const checked       = ref({ cpu: true, mem: true, battery: true });
    const viewedRecord  = ref('');
    const viewStats     = ref([]);
    const viewMeta      = ref({});
    const trackSubprocesses = ref(true);
    const memoryMode = ref('rss');
    const records       = ref([]);
    const loadingRecords = ref(false);
    const elapsed       = ref(0);
    const pkgSuggestions = ref([]);
    const cpuCanvas     = ref(null);
    const memCanvas     = ref(null);
    const battCanvas    = ref(null);
    const viewMode      = ref('list');   // 'list' | 'detail'
    const viewCpuCanvas = ref(null);
    const viewMemCanvas = ref(null);
    const viewBattCanvas = ref(null);

    let elapsedTimer = null;
    let pkgAllCache  = [];
    let pkgFetching  = false;
    let cpuChart     = null;
    let memChart     = null;
    let battChart    = null;
    let coreCount    = 0;

    const deviceSerial = computed(() => (device && device.serial && device.serial.value) || '');
    const canStart = computed(() => (checked.value.cpu || checked.value.mem || checked.value.battery) && !!deviceSerial.value);
    const showCpuChart = computed(() => checked.value.cpu);
    const showMemChart = computed(() => checked.value.mem);
    const showBatteryChart = computed(() => checked.value.battery);

    const cpuViewStats = computed(() => viewStats.value.filter(s => s.field === 'cpu_percent' || s.field === 'sys_cpu_percent' || s.field.startsWith('core_')));
    const memViewStats = computed(() => viewStats.value.filter(s => s.field === 'mem_rss_kb' || s.field === 'mem_pss_kb'));
    const battViewStats = computed(() => viewStats.value.filter(s => s.field === 'battery_level' || s.field === 'battery_temp'));

    function fmtTs(ts) {
      if (!ts) return '';
      const d = new Date(ts * 1000);
      const z = n => String(n).padStart(2, '0');
      return d.getFullYear()+'-'+z(d.getMonth()+1)+'-'+z(d.getDate())+' '+z(d.getHours())+':'+z(d.getMinutes())+':'+z(d.getSeconds());
    }
    function fmtSize(bytes) {
      if (bytes < 1024) return bytes + ' B';
      if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
      return (bytes/(1024*1024)).toFixed(1) + ' MB';
    }

    // ── 创建单张图表（复刻之前能用的模式） ──
    function makeChart(canvasRef, opts) {
      opts = opts || {};
      if (!canvasRef || !canvasRef.value) return null;
      const canvas = canvasRef.value;
      const ctx = canvas.getContext('2d');
      if (!ctx) return null;
      try {
        const yOpts = { display: true, beginAtZero: opts.yStartZero !== false, ticks: { color: '#888', font: { size: 9 } }, grid: { color: '#2a2a2a' } };
        if (opts.yMax != null) yOpts.max = opts.yMax;
        if (opts.yGrace) yOpts.grace = opts.yGrace;
        return new Chart(ctx, {
          type: 'line',
          data: { labels: [], datasets: [] },
          options: {
            responsive: true, maintainAspectRatio: false,
            animation: { duration: 200 },
            interaction: { intersect: false, mode: 'index' },
            plugins: {
              legend: { labels: { color: '#ccc', font: { size: 9 } } },
              tooltip: { callbacks: { label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y != null ? ctx.parsed.y.toFixed(1) : '-') } },
            },
            scales: { x: { display: true, ticks: { color: '#888', font: { size: 9 }, maxTicksLimit: 10 }, grid: { color: '#2a2a2a' } }, y: yOpts },
          },
        });
      } catch(e) { console.error('Chart create error:', e); return null; }
    }

    function initCharts() {
      destroyCharts();
      cpuChart  = makeChart(cpuCanvas, { yMax: 100 });
      memChart  = makeChart(memCanvas, { yGrace: '10%', yStartZero: false });
      battChart = makeChart(battCanvas, { yGrace: '10%', yStartZero: false });
    }

    function destroyCharts() {
      [cpuChart, memChart, battChart].forEach(c => { if (c) { try { c.destroy(); } catch(e) {} } });
      cpuChart = null; memChart = null; battChart = null;
    }

    // ── 向已有图表追加数据点 ──
    function pushChart(chart, sec, datasets) {
      if (!chart) return;
      chart.data.labels.push(sec);
      for (const d of datasets) {
        let ds = chart.data.datasets.find(x => x._field === d.field);
        if (!ds) {
          ds = { label:d.label, data:[], borderColor:d.color, borderWidth:d.bw||1.5, pointRadius:d.pointRadius!=null?d.pointRadius:1, pointHoverRadius:3, tension:0.2, _field:d.field, backgroundColor:d.color+'33' };
          chart.data.datasets.push(ds);
        }
        ds.data.push(d.val != null ? d.val : null);
      }
      chart.data.datasets.forEach(ds => { while (ds.data.length < chart.data.labels.length) ds.data.push(null); });
      if (chart.data.labels.length > 300) {
        const n = chart.data.labels.length - 300;
        chart.data.labels.splice(0, n);
        chart.data.datasets.forEach(ds => ds.data.splice(0, n));
      }
      chart.update('none');
    }

    function feedData(data) {
      const sec = ((Date.now()/1000) - (window._perfStartTs || 0)).toFixed(0);
      // 检测核心数
      let maxC = -1;
      for (const k of Object.keys(data)) if (k.startsWith('core_')) maxC = Math.max(maxC, parseInt(k.slice(5)));
      coreCount = maxC + 1;

      // CPU
      if (cpuChart && checked.value.cpu) {
        const ds = [];
        if (data.cpu_percent != null) ds.push({ field:'cpu_percent', label:'CPU%', color:'#409eff', val:data.cpu_percent, bw:3 });
        if (data.sys_cpu_percent != null) ds.push({ field:'sys_cpu_percent', label:'系统', color:'#909399', val:data.sys_cpu_percent, bw:3 });
        for (let i = 0; i < coreCount; i++) {
          const v = data['core_'+i];
          if (v != null) ds.push({ field:'core_'+i, label:'核心'+i, color:CORE_COLORS[i%CORE_COLORS.length]+'88', val:v, bw:1, pointRadius:0.5 });
        }
        pushChart(cpuChart, sec, ds);
      }
      // 内存
      if (memChart && checked.value.mem) {
        const ds = [];
        if (data.mem_rss_kb != null) ds.push({ field:'mem_rss_kb', label:'RSS(MB)', color:'#67c23a', val:data.mem_rss_kb/1024 });
        if (data.mem_pss_kb != null) ds.push({ field:'mem_pss_kb', label:'PSS(MB)', color:'#36cfc9', val:data.mem_pss_kb/1024 });
        if (ds.length) pushChart(memChart, sec, ds);
      }
      // 电量
      if (battChart && checked.value.battery) {
        const ds = [];
        if (data.battery_level != null) ds.push({ field:'battery_level', label:'电量%', color:'#e6a23c', val:data.battery_level });
        if (data.battery_temp != null) ds.push({ field:'battery_temp', label:'温度°C', color:'#b88cf9', val:data.battery_temp });
        if (ds.length) pushChart(battChart, sec, ds);
      }
    }

    // ── WebSocket ──
    function startCollect() {
      const serial = deviceSerial.value;
      if (!serial) { msg && msg.warn && msg.warn('请先连接设备'); return; }
      const arr = [];
      if (checked.value.cpu) arr.push('cpu');
      if (checked.value.mem) arr.push('mem');
      if (checked.value.battery) arr.push('battery');
      if (!arr.length) { msg && msg.warn && msg.warn('请至少勾选一个指标'); return; }

      csvPath.value = ''; csvPoints.value = 0;
      status.value = 'recording'; elapsed.value = 0;
      window._perfStartTs = Date.now() / 1000;
      coreCount = 0;
      if (elapsedTimer) clearInterval(elapsedTimer);
      elapsedTimer = setInterval(() => { elapsed.value++; }, 1000);

      // 创建空图表
      initCharts();

      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = proto + '//' + window.location.host + '/ws/perf?platform=android&serial=' + encodeURIComponent(serial);
      const socket = new WebSocket(url);
      ws.value = socket;

      socket.onopen = () => { socket.send(JSON.stringify({ action:'start', package: packageName.value || '', metrics: arr, interval: interval.value || 2, track_subprocesses: trackSubprocesses.value, memory_mode: memoryMode.value })); };
      socket.onmessage = (evt) => {
        try {
          const m = JSON.parse(evt.data);
          if (m.type === 'point') {
            feedData(m.data);
          } else if (m.type === 'done') {
            csvPath.value = m.csv_path || ''; csvPoints.value = m.points || 0;
            status.value = 'stopped';
            if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
            loadRecords();
          } else if (m.type === 'error') { msg && msg.error && msg.error(m.msg); }
        } catch(e) { console.error('Perf WS', e); }
      };
      socket.onerror = () => { msg && msg.error && msg.error('WebSocket 失败'); status.value = 'idle'; if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; } };
      socket.onclose = () => { if (status.value === 'recording') { status.value = 'idle'; if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; } } };
    }

    function stopCollect() { if (ws.value && ws.value.readyState === WebSocket.OPEN) ws.value.send(JSON.stringify({ action:'stop' })); }

    async function fetchPkgList() {
      const s = deviceSerial.value; if (!s) return; if (pkgAllCache.length || pkgFetching) return;
      pkgFetching = true;
      try { const r = await listPackages('android', s); if (r.success && Array.isArray(r.data)) pkgAllCache = r.data; } catch(_) {}
      finally { pkgFetching = false; }
    }
    function onPkgVisible(v) { if (v && deviceSerial.value) fetchPkgList().then(() => { pkgSuggestions.value = [...pkgAllCache]; }); }

    async function loadRecords() {
      loadingRecords.value = true;
      try { const r = await listPerfRecords(); records.value = (r.success ? (r.data.records || []) : []); } catch(_) { records.value = []; }
      finally { loadingRecords.value = false; }
    }
    function downloadRecord(r) { window.open('/perf/records/' + encodeURIComponent(r.name), '_blank'); }

    let viewCpuChart = null, viewMemChart = null, viewBattChart = null;

    function _destroyViewCharts() {
      [viewCpuChart, viewMemChart, viewBattChart].forEach(c => { if (c) { try { c.destroy(); } catch(e) {} } });
      viewCpuChart = null; viewMemChart = null; viewBattChart = null;
    }

    function _pushViewChart(chart, row, sec, fieldMap) {
      if (!chart) return;
      const COLORS = { cpu_percent:'#409eff', sys_cpu_percent:'#909399', mem_rss_kb:'#67c23a', mem_pss_kb:'#36cfc9', battery_level:'#e6a23c', battery_temp:'#b88cf9' };
      const LABELS = { cpu_percent:'CPU%', sys_cpu_percent:'系统', mem_rss_kb:'RSS(MB)', mem_pss_kb:'PSS(MB)', battery_level:'电量%', battery_temp:'温度°C' };
      const DIVS = { mem_rss_kb:1024, mem_pss_kb:1024 };
      const datasets = [];
      for (const [field, div] of Object.entries(fieldMap)) {
        const val = row[field];
        if (val == null) continue;
        const color = COLORS[field] || CORE_COLORS[parseInt(field.slice(5)) % CORE_COLORS.length] || '#888';
        datasets.push({ field, label: LABELS[field] || ('核心'+field.slice(5)), color, val: val / (div || 1), bw: (field === 'cpu_percent' || field === 'sys_cpu_percent') ? 3 : 1.5, pointRadius: field.startsWith('core_') ? 0.5 : 1 });
      }
      if (datasets.length) pushChart(chart, sec, datasets);
    }

    async function viewRecord(r) {
      try {
        const resp = await fetch('/perf/records/' + encodeURIComponent(r.name));
        const text = await resp.text();
        const lines = text.trim().split('\n');
        if (lines.length < 2) { msg && msg.warn && msg.warn('记录为空'); return; }
        let dataStart = 0;
        while (dataStart < lines.length && lines[dataStart].startsWith('#')) dataStart++;
        if (dataStart >= lines.length) { msg && msg.warn && msg.warn('无数据'); return; }
        // 解析 meta
        const meta = { time: fmtTs(r.mtime), points: lines.length - dataStart - 1 };
        for (let i = 0; i < dataStart; i++) {
          const m = lines[i].match(/^#\s*([^=]+)=(.*)$/);
          if (m) meta[m[1].trim()] = m[2].trim();
        }
        viewMeta.value = meta;
        const headers = lines[dataStart].split(',');

        const dataRows = [];
        const fields = {};
        for (let j = 0; j < headers.length; j++) {
          if (headers[j] === 'ts') continue;
          fields[headers[j]] = { vals: [], min: Infinity, max: -Infinity, sum: 0 };
        }
        for (let i = dataStart + 1; i < lines.length; i++) {
          const vals = lines[i].split(',');
          const row = {};
          for (let j = 0; j < headers.length; j++) {
            const v = parseFloat(vals[j]);
            if (isNaN(v)) continue;
            row[headers[j]] = v;
            if (headers[j] === 'ts') continue;
            fields[headers[j]].vals.push(v);
            fields[headers[j]].min = Math.min(fields[headers[j]].min, v);
            fields[headers[j]].max = Math.max(fields[headers[j]].max, v);
            fields[headers[j]].sum += v;
          }
          dataRows.push(row);
        }

        viewedRecord.value = r.name;
        viewMode.value = 'detail';
        await nextTick();

        // 统计
        const st = [];
        const stLabels = { cpu_percent:'CPU%', sys_cpu_percent:'系统', mem_rss_kb:'RSS', mem_pss_kb:'PSS', battery_level:'电量', battery_temp:'温度' };
        for (const [k, f] of Object.entries(fields)) {
          if (f.vals.length === 0) continue;
          const isMem = (k === 'mem_rss_kb' || k === 'mem_pss_kb');
          const div = isMem ? 1024 : 1;
          const avg = (f.sum / f.vals.length / div);
          st.push({ field: k, label: stLabels[k] || (k.startsWith('core_') ? '核心'+k.slice(5) : k), count: f.vals.length, avg: avg.toFixed(1), min: (f.min/div).toFixed(1), max: (f.max/div).toFixed(1), unit: isMem ? 'MB' : '%' });
        }
        viewStats.value = st;

        // 创建空图表（与监控完全一致的 makeChart + pushChart）
        _destroyViewCharts();
        viewCpuChart  = makeChart(viewCpuCanvas, { yMax: 100 });
        viewMemChart  = makeChart(viewMemCanvas, { yGrace: '10%', yStartZero: false });
        viewBattChart = makeChart(viewBattCanvas, { yGrace: '10%', yStartZero: false });

        // 逐行喂数据（每行只调一次 pushChart）
        for (let i = 0; i < dataRows.length; i++) {
          const sec = i.toString();
          const row = dataRows[i];
          // CPU — 包含核心
          const cMap = { cpu_percent:1, sys_cpu_percent:1 };
          for (const k of Object.keys(row)) if (k.startsWith('core_')) cMap[k] = 1;
          _pushViewChart(viewCpuChart, row, sec, cMap);
          // 内存
          _pushViewChart(viewMemChart, row, sec, { mem_rss_kb:1024, mem_pss_kb:1024 });
          // 电量
          _pushViewChart(viewBattChart, row, sec, { battery_level:1, battery_temp:1 });
        }
      } catch(e) { console.error('View record error:', e); msg && msg.error && msg.error('加载记录失败'); }
    }

    function closeView() {
      _destroyViewCharts();
      viewMode.value = 'list';
      viewedRecord.value = '';
      viewStats.value = [];
      viewMeta.value = {};
    }
    async function onDelete(r) {
      if (!window.confirm('删除记录「'+r.name+'」?')) return;
      const res = await deletePerfRecord(r.name);
      if (!res.success) { msg && msg.error && msg.error('删除失败：'+(res.message||'')); return; }
      msg && msg.success && msg.success('已删除');
      await loadRecords();
    }

    onMounted(() => { loadRecords(); initCharts(); });
    onBeforeUnmount(() => {
      if (ws.value) { if (ws.value.readyState === WebSocket.OPEN || ws.value.readyState === WebSocket.CONNECTING) ws.value.close(); ws.value = null; }
      if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
      destroyCharts();
    });
    // 切回监控 tab 时重建空图表
    watch(subTab, (v) => { if (v === 'monitor') initCharts(); }, { flush: 'post' });

    return {
      subTab, status, checked, packageName, interval, trackSubprocesses, memoryMode,
      csvPath, csvPoints, records, loadingRecords,
      elapsed, deviceSerial, canStart, showCpuChart, showMemChart, showBatteryChart,
      cpuCanvas, memCanvas, battCanvas, ws,
      viewMode, viewedRecord, viewStats, viewMeta, cpuViewStats, memViewStats, battViewStats,
      viewCpuCanvas, viewMemCanvas, viewBattCanvas,
      pkgSuggestions, fmtTs, fmtSize,
      startCollect, stopCollect, viewRecord, closeView, loadRecords, downloadRecord, onDelete,
      onPkgVisible,
    };
  },
};
