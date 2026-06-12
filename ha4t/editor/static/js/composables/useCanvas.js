import { saveToLocalStorage, getFromLocalStorage } from '../utils.js';
import { fetchScreenshot, fetchHierarchy, saveImage } from '../api.js';

// useCanvas — encapsulates screenshot rendering, hierarchy overlay, hover/click
// pipelines, capture-rectangle / swipe recording, and the dump-hierarchy flow.
//
// Signature: useCanvas({ device, task, runner, msg })
// Returns: { initCanvas, loadCachedScreenshot, screenshotAndDumpHierarchy }
//
// Cross-component bridges (kept for backward compat):
//   window._screenshotAndDump     ← called by App.js, StepPane.js
//   window._renderHierarchyCanvas ← called by InspectorPane tree hover
export function useCanvas({ device, task, runner, msg, pom }) {
  // last loaded screenshot — kept for redraw on resize
  let _lastScreenshotData = null;
  let _moveScheduled = false;
  let _lastMx = 0, _lastMy = 0;

  // ── Coordinate helper ─────────────────────────────────────────────────
  // Every mouse path (hover, click, dblclick, capture, swipe) MUST go through
  // this. No caching — getBoundingClientRect is sub-0.1ms even on big DOMs and
  // rAF throttling keeps actual call rate to ≤60 Hz. Caching here previously
  // produced stale rects after column-divider drags (no `resize` event fires).
  function pointToCanvas(e) {
    const canvas = document.querySelector('#hierarchyCanvas');
    if (!canvas) return { x: 0, y: 0 };
    const r = canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  // ── Screenshot rendering ──────────────────────────────────────────────
  function renderScreenshot(base64Data) {
    if (base64Data) _lastScreenshotData = base64Data;
    const data = _lastScreenshotData;
    if (!data) return;
    const img = new Image();
    img.src = `data:image/png;base64,${data}`;
    img.onload = () => {
      const area = document.querySelector('.canvas-area');
      const ss   = document.querySelector('#screenshotCanvas');
      const hc   = document.querySelector('#hierarchyCanvas');
      if (!area || !ss || !hc) return;

      const dpr   = window.devicePixelRatio || 1;
      const areaW = area.clientWidth;
      const areaH = area.clientHeight;
      const scale = Math.min(areaW / img.width, areaH / img.height);
      const cssW  = Math.round(img.width  * scale);
      const cssH  = Math.round(img.height * scale);

      for (const c of [ss, hc]) {
        c.style.width  = cssW + 'px';
        c.style.height = cssH + 'px';
        c.width  = cssW * dpr;
        c.height = cssH * dpr;
        c.getContext('2d').setTransform(dpr, 0, 0, dpr, 0, 0);
      }

      device.screenshotTransform.scale   = scale;
      device.screenshotTransform.offsetX = 0;
      device.screenshotTransform.offsetY = 0;

      const ctx = ss.getContext('2d');
      ctx.clearRect(0, 0, cssW, cssH);
      ctx.drawImage(img, 0, 0, cssW, cssH);
      renderHierarchy();
    };
  }

  // ── Hierarchy overlay ─────────────────────────────────────────────────
  // Platform-agnostic — all parsers emit rect:{x,y,width,height}. iOS rect is
  // pre-multiplied by scale in ha4t/editor/parser/ios_hierarchy.py.
  function nodeRect(node) {
    const r = node.rect;
    if (r && r.width !== undefined) return { x: r.x, y: r.y, w: r.width, h: r.height };
    const b = node.bounds;
    if (b) return { x: b[0], y: b[1], w: b[2]-b[0], h: b[3]-b[1] };
    return null;
  }

  function renderHierarchy() {
    const canvas = document.querySelector('#hierarchyCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);
    const { scale, offsetX, offsetY } = device.screenshotTransform;
    ctx.setLineDash([2, 6]);
    const drawNode = (node) => {
      if (!node) return;
      const r = nodeRect(node);
      if (r) {
        const x = r.x*scale + offsetX, y = r.y*scale + offsetY;
        ctx.strokeStyle = 'rgba(100,180,255,0.3)';
        ctx.lineWidth = 0.5;
        ctx.strokeRect(x, y, r.w*scale, r.h*scale);
      }
      if (node.children) node.children.forEach(drawNode);
    };
    drawNode(device.jsonHierarchy.value);
    if (device.hoveredNode.value) {
      const r = nodeRect(device.hoveredNode.value);
      if (r) {
        const x=r.x*scale+offsetX, y=r.y*scale+offsetY;
        ctx.setLineDash([]); ctx.strokeStyle='rgba(255,200,0,0.9)'; ctx.lineWidth=1.5;
        ctx.strokeRect(x, y, r.w*scale, r.h*scale);
        ctx.fillStyle='rgba(255,200,0,0.1)'; ctx.fillRect(x, y, r.w*scale, r.h*scale);
      }
    }
    if (device.selectedNode.value) {
      const r = nodeRect(device.selectedNode.value);
      if (r) {
        const x=r.x*scale+offsetX, y=r.y*scale+offsetY;
        ctx.setLineDash([]); ctx.strokeStyle='#409eff'; ctx.lineWidth=2;
        ctx.strokeRect(x, y, r.w*scale, r.h*scale);
        ctx.fillStyle='rgba(64,158,255,0.15)'; ctx.fillRect(x, y, r.w*scale, r.h*scale);
      }
    }
    // ── verify mode overlay（POM 元素定位结果，App.js watch 同步到全局） ──
    // 仅画方框 + 元素名 tag，不填充元素 —— 填充会盖住截图内容，验证多元素时一片绿。
    if (window._pomVerifyResults) {
      const results = window._pomVerifyResults;
      ctx.setLineDash([]);
      ctx.font = '11px Consolas, monospace';
      ctx.textBaseline = 'top';
      for (const name of Object.keys(results)) {
        const r = results[name];
        if (r.status !== 'found' || !r.rect) continue;
        const x = r.rect.x * scale + offsetX;
        const y = r.rect.y * scale + offsetY;
        const w = r.rect.width * scale;
        const h = r.rect.height * scale;

        // 方框
        ctx.strokeStyle = '#67c23a';
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);

        // 元素名 tag —— 实色背景，贴在方框左上角外侧（顶不够就翻进框内）。
        const padX = 4, padY = 2;
        const textW = ctx.measureText(name).width;
        const tagW = textW + padX * 2;
        const tagH = 14;
        let tagX = x;
        let tagY = y - tagH;
        if (tagY < offsetY) tagY = y; // 上方空间不足 → 改贴到框内顶部
        ctx.fillStyle = '#67c23a';
        ctx.fillRect(tagX, tagY, tagW, tagH);
        ctx.fillStyle = '#fff';
        ctx.fillText(name, tagX + padX, tagY + padY);
      }
    }
  }

  // Flat-scan: visit every node and pick the smallest-area rect that contains
  // (mouseX, mouseY). NEVER prune by parent containment — many platforms emit
  // root/container nodes whose rect is null or smaller than the screen
  // (Harmony virtual roots, iOS WindowSceneRoot, Android decor view edges),
  // and the previous "self-rect doesn't contain → return null" recursion
  // killed hover entirely whenever that happened.
  function findSmallestNode(node, mouseX, mouseY, scale, offsetX, offsetY) {
    let smallest = null;
    let smallestArea = Infinity;
    const visit = (n) => {
      if (!n) return;
      const r = nodeRect(n);
      if (r) {
        const x = r.x*scale + offsetX, y = r.y*scale + offsetY;
        const w = r.w*scale, h = r.h*scale;
        if (mouseX >= x && mouseX <= x + w && mouseY >= y && mouseY <= y + h) {
          const area = r.w * r.h;
          if (area < smallestArea) { smallest = n; smallestArea = area; }
        }
      }
      if (n.children) for (const c of n.children) visit(c);
    };
    visit(node);
    return smallest;
  }

  // ── Dump-hierarchy flow ───────────────────────────────────────────────
  async function screenshotAndDumpHierarchy() {
    if (!device.isConnected.value) return;
    device.isDumping.value = true;
    try {
      const [ssRes, hierRes] = await Promise.all([
        fetchScreenshot(device.platform.value, device.serial.value),
        fetchHierarchy(device.platform.value, device.serial.value),
      ]);
      if (ssRes.success) renderScreenshot(ssRes.data);
      if (hierRes.success && hierRes.data) {
        const hier = hierRes.data;
        const rootNode = hier.jsonHierarchy || hier;
        device.jsonHierarchy.value = rootNode;
        // POM 验证模式下，层级刷新 → 自动重扫（App.js onMounted 挂的钩子）
        if (window._pomVerifyOnHierarchy) window._pomVerifyOnHierarchy();
        if (hier.windowSize) {
          device.displaySize.value = hier.windowSize;
          device.scale.value = hier.scale || 1;
        }
        const buildTree = (node) => {
          const label = node.text || node.label || node.name || node.resourceId || node._type || node.type || '(node)';
          const tnode = { ...node, label, children: [] };
          if (node.children && node.children.length) {
            tnode.children = node.children.map(buildTree);
          }
          return tnode;
        };
        device.treeData.value = rootNode ? [buildTree(rootNode)] : [];
        if (ssRes.success) saveToLocalStorage('cachedScreenshot', ssRes.data);
      }
    } finally { device.isDumping.value = false; }
  }

  // ── Mouse events ──────────────────────────────────────────────────────
  // rAF-throttled hover so dense hierarchies stay responsive.
  function onMouseMove(e) {
    if (!device.jsonHierarchy.value || !Object.keys(device.jsonHierarchy.value).length) return;
    const p = pointToCanvas(e);
    _lastMx = p.x; _lastMy = p.y;
    if (_moveScheduled) return;
    _moveScheduled = true;
    requestAnimationFrame(() => {
      _moveScheduled = false;
      const { scale, offsetX, offsetY } = device.screenshotTransform;
      const prev = device.hoveredNode.value;
      const next = findSmallestNode(device.jsonHierarchy.value, _lastMx, _lastMy, scale, offsetX, offsetY);
      if (prev !== next) {
        device.hoveredNode.value = next;
        renderHierarchy();
      }
    });
  }

  function onMouseLeave() { device.hoveredNode.value = null; renderHierarchy(); }

  function onMouseClick(e) {
    if (device.captureMode.value || device.swipeRecordMode.value) return;
    const { x: mx, y: my } = pointToCanvas(e);
    const { scale, offsetX, offsetY } = device.screenshotTransform;
    const node = findSmallestNode(device.jsonHierarchy.value, mx, my, scale, offsetX, offsetY);
    if (node) {
      device.selectNode(node);
      if (device.elementSelectMode.value) {
        device.elementSelectMode.value = false;
        const step = task.elementFromNode(node);
        task.steps.value.push(step);
        task.saveCurrentTask(device.serial.value).catch(() => {});
        if (task.autoRun.value) runner.runSingleStep(task.steps.value.length - 1, screenshotAndDumpHierarchy, msg);
      }
      renderHierarchy();
    }
  }

  // Double-click → record as a step immediately, unless POM capture mode is on.
  function onMouseDblClick(e) {
    if (device.captureMode.value || device.swipeRecordMode.value) return;
    const { x: mx, y: my } = pointToCanvas(e);
    const { scale, offsetX, offsetY } = device.screenshotTransform;
    const node = findSmallestNode(device.jsonHierarchy.value, mx, my, scale, offsetX, offsetY);
    if (!node) return;
    if (pom && pom.captureMode.value) {
      device.selectNode(node);
      renderHierarchy();
      pom.beginCapture(node);
      return;
    }
    device.selectNode(node);
    const step = task.elementFromNode(node);
    task.steps.value.push(step);
    task.saveCurrentTask(device.serial.value).catch(() => {});
    task.selectStep(task.steps.value.length - 1);
    msg.success(`已录制: ${step.code}`);
    if (task.autoRun.value) runner.runSingleStep(task.steps.value.length - 1, screenshotAndDumpHierarchy, msg);
    renderHierarchy();
  }

  // ── Capture-rect (image step) ─────────────────────────────────────────
  function onCaptureMouseDown(e) {
    if (!device.captureMode.value) return;
    device.captureStart.value = pointToCanvas(e);
  }
  function onCaptureMouseMove(e) {
    if (!device.captureMode.value || !device.captureStart.value) return;
    const end = pointToCanvas(e);
    device.captureRect.value = clampCaptureRect({
      x: device.captureStart.value.x,
      y: device.captureStart.value.y,
      w: end.x - device.captureStart.value.x,
      h: end.y - device.captureStart.value.y,
    });
    renderHierarchy();
    const canvas = document.querySelector('#hierarchyCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const r = device.captureRect.value;
    ctx.strokeStyle = 'rgba(64,158,255,0.9)'; ctx.lineWidth = 1.5; ctx.setLineDash([4,4]);
    ctx.strokeRect(r.x, r.y, r.w, r.h);
    ctx.fillStyle = 'rgba(64,158,255,0.1)'; ctx.fillRect(r.x, r.y, r.w, r.h);
  }
  async function onCaptureMouseUp(e) {
    if (!device.captureMode.value || !device.captureStart.value) return;
    device.captureMode.value = false;
    const rect = device.captureRect.value;
    if (rect) await createImageStep(rect);
    device.captureStart.value = null; device.captureRect.value = null;
  }
  function clampCaptureRect(raw) {
    const canvas = document.querySelector('#hierarchyCanvas');
    if (!canvas) return raw;
    const cW = canvas.clientWidth, cH = canvas.clientHeight;
    let { x, y, w, h } = raw;
    if (w < 0) { x += w; w = -w; }
    if (h < 0) { y += h; h = -h; }
    x = Math.max(0, Math.min(x, cW)); y = Math.max(0, Math.min(y, cH));
    w = Math.min(w, cW - x); h = Math.min(h, cH - y);
    return { x, y, w, h };
  }
  async function createImageStep(rect) {
    const ssCanvas = document.querySelector('#screenshotCanvas');
    if (!ssCanvas) return;
    const { scale, offsetX, offsetY } = device.screenshotTransform;
    const sx = (rect.x - offsetX) / scale, sy = (rect.y - offsetY) / scale;
    const sw = rect.w / scale, sh = rect.h / scale;
    const tmp = document.createElement('canvas');
    tmp.width = sw; tmp.height = sh;
    const tctx = tmp.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    tctx.drawImage(ssCanvas, sx * dpr * scale, sy * dpr * scale, sw * dpr * scale, sh * dpr * scale, 0, 0, sw, sh);
    const dataUrl = tmp.toDataURL('image/png');

    // ── POM image-element route ─────────────────────────────────────
    // Active when the user enabled "POM 采集模式" *and* hit the capture button.
    // The cropped image goes to <images_dir>/ under a POM-namespaced filename
    // (so the same file is not co-owned with step images), then the naming
    // dialog opens with selector = { image: filename }.
    if (pom && pom.captureMode.value) {
      const fname = `pom_${pom.page.value || 'page'}_${Date.now()}.png`;
      await saveImage(fname, dataUrl);
      pom.beginImageCapture(fname, dataUrl);
      return;
    }

    // ── Default route: imglocate step ───────────────────────────────
    const pid = task.projectId.value || ('proj_' + Date.now().toString(36));
    const fname = `${pid}_${Date.now()}.png`;
    const step = {
      _type: 'imglocate', action: 'click', image: dataUrl, image_filename: fname,
      grid_h: 1, grid_v: 1, click_col: 0, click_row: 0, timeout: 10, threshold: null,
      _status: 'pending', _detail: '', _duration: null,
    };
    step.code = task.generateImgCode(step);
    task.steps.value.push(step);
    await saveImage(fname, dataUrl);
    step._imageSaved = true;
    task.selectStep(task.steps.value.length - 1);
    msg.success('已添加图片定位步骤');
  }

  // ── Swipe recording ───────────────────────────────────────────────────
  function onSwipeClick(e) {
    if (!device.swipeRecordMode.value) return;
    const { x: mx, y: my } = pointToCanvas(e);
    const { scale, offsetX, offsetY } = device.screenshotTransform;
    const px = ((mx - offsetX) / scale).toFixed(3);
    const py = ((my - offsetY) / scale).toFixed(3);
    device.swipePoints.value.push({ x: +px, y: +py });
    if (device.swipePoints.value.length === 1) {
      msg.info('请点击滑动终点');
    } else if (device.swipePoints.value.length >= 2) {
      const [p1, p2] = device.swipePoints.value;
      const code = `dev.swipe((${p1.x}, ${p1.y}), (${p2.x}, ${p2.y}))`;
      task.steps.value.push({ code, remark: '', _status:'pending', _detail:'', _duration:null });
      msg.success(`已添加滑动: ${code}`);
      device.exitSwipeRecordMode();
      if (task.autoRun.value) runner.runSingleStep(task.steps.value.length - 1, screenshotAndDumpHierarchy, msg);
    }
  }

  // ── Init / cleanup ────────────────────────────────────────────────────
  function initCanvas() {
    const canvas = document.querySelector('#hierarchyCanvas');
    if (!canvas) return;
    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('click', onMouseClick);
    canvas.addEventListener('dblclick', onMouseDblClick);
    canvas.addEventListener('mouseleave', onMouseLeave);
    canvas.addEventListener('mousedown', onCaptureMouseDown);
    canvas.addEventListener('mousemove', onCaptureMouseMove);
    canvas.addEventListener('mouseup', onCaptureMouseUp);
    canvas.addEventListener('click', onSwipeClick);

    // Cross-component bridges (see header comment)
    window._renderHierarchyCanvas = renderHierarchy;
    window._screenshotAndDump = screenshotAndDumpHierarchy;

    // Redraw whenever the left pane resizes (column drag / window resize).
    // Only renderScreenshot is invoked here — hover does not trigger it.
    const container = canvas.closest('.left') || canvas.parentElement;
    if (container && typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(() => {
        renderScreenshot();   // no arg → reuses _lastScreenshotData
      }).observe(container);
    }
  }

  function loadCachedScreenshot() {
    const cached = getFromLocalStorage('cachedScreenshot', null);
    if (cached) renderScreenshot(cached);
  }

  return {
    initCanvas,
    loadCachedScreenshot,
    screenshotAndDumpHierarchy,
  };
}
