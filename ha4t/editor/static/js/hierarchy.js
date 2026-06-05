import { saveToLocalStorage, getFromLocalStorage } from './utils.js';
import { fetchHierarchy, fetchXpathLite, saveImage, getImage } from './api.js';

export const HierarchyMethods = {
  async _fetchHierarchy() {
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

  async fetchXpathLite(nodeId) {
    try {
      const response = await fetchXpathLite(this.platform, this.jsonHierarchy, nodeId);
      if (response.success) {
        this.xpathLite = response.data;
      } else {
        throw new Error(response.message);
      }
    } catch (error) {
      console.error(error);
    }
  },

  async handleTreeNodeClick(node) {
    this.selectedStepIndex = -1;
    this.selectedNode = node;
    await this.fetchXpathLite(node._id);
    this.selectedNode && (this.selectedNode.xpath = this.xpathLite);
    this.renderHierarchy();
    // If in element select mode, insert step immediately
    if (this.elementSelectMode && this.selectedNode && this.rightTab === 'editor') {
      this.elementSelectMode = false;
      this.insertStepFromElement();
    }
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
    }, this.getTreeLabel(data));
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
    const { _type = "", resourceId = "", label = "", text = "", id = "" } = node;
    const labelMap = {
      android: resourceId || text,
      ios: label,
      harmony: text || id
    };
    return `${_type} - ${labelMap[this.platform] || ''}`;
  },

  getDefaultNodeDetails(platform) {
    const commonDetails = [
      { key: 'displaySize', value: this.displaySize },
      { key: 'scale', value: this.scale },
      { key: '点击坐标 %', value: this.mouseClickCoordinatesPercent }
    ];
    switch (platform) {
      case 'ios':
        return [{ key: 'bundleId', value: this.packageName }, ...commonDetails];
      case 'android':
        return [{ key: 'packageName', value: this.packageName }, { key: 'activityName', value: this.activityName }, ...commonDetails];
      case 'harmony':
        return [{ key: 'packageName', value: this.packageName }, { key: 'pageName', value: this.activityName }, ...commonDetails];
      default:
        return commonDetails;
    }
  },

  onMouseMove(event) {
    if (this.captureMode || this.swipeRecordMode) return;
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

  onMouseLeave() {
    if (this.hoveredNode) {
      this.hoveredNode = null;
      this.renderHierarchy();
    }
  },

  onMouseClick(event) {
    if (this.captureMode) return;
    const canvas = this.$el.querySelector('#hierarchyCanvas');
    const rect = canvas.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;
    const { scale, offsetX, offsetY } = this.screenshotTransform;
    const percentX = (mouseX / canvas.width);
    const percentY = (mouseY / canvas.height);
    this.mouseClickCoordinatesPercent = `(${percentX.toFixed(2)}, ${percentY.toFixed(2)})`;

    if (this.swipeRecordMode) {
      this.swipePoints.push({ x: percentX, y: percentY, px: mouseX, py: mouseY });
      this.renderHierarchy();
      if (this.swipePoints.length === 1) {
        this.$message({ message: '已记录起点，请点击终点', type: 'info', duration: 2000 });
      } else if (this.swipePoints.length === 2) {
        this.finishSwipeRecord();
      }
      return;
    }

    this.selectedStepIndex = -1;
    const selectedNode = this.findSmallestNode(this.jsonHierarchy, mouseX, mouseY, scale, offsetX, offsetY);
    if (selectedNode !== this.selectedNode) {
      this.selectedNode = selectedNode ? selectedNode : null;
      this.fetchXpathLite(selectedNode._id).then(() => {
        this.selectedNode && (this.selectedNode.xpath = this.xpathLite);
        this.renderHierarchy();
        // If in element select mode, insert step immediately
        if (this.elementSelectMode && this.selectedNode) {
          this.elementSelectMode = false;
          this.insertStepFromElement();
        }
      });
    } else {
      this.selectedNode = { ...this.selectedNode };
    }
  },

  onMouseDblClick() {
    if (this.captureMode || this.swipeRecordMode) return;
    if (this.selectedNode && this.rightTab === 'editor') {
      this.insertStepFromElement();
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

  clampCaptureRect(raw) {
    const b = this.getScreenshotBoundsOnCanvas();
    let x = Math.max(raw.x, b.left);
    let y = Math.max(raw.y, b.top);
    let x2 = Math.min(raw.x + raw.w, b.right);
    let y2 = Math.min(raw.y + raw.h, b.bottom);
    let w = Math.max(0, x2 - x);
    let h = Math.max(0, y2 - y);
    return { x, y, w, h };
  },

  onCaptureMouseMove(event) {
    if (!this.captureMode || !this.captureStart) return;
    const canvas = this.$el.querySelector('#hierarchyCanvas');
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const raw = {
      x: Math.min(this.captureStart.x, x),
      y: Math.min(this.captureStart.y, y),
      w: Math.abs(x - this.captureStart.x),
      h: Math.abs(y - this.captureStart.y)
    };
    this.captureRect = this.clampCaptureRect(raw);
    this.renderHierarchy();
  },

  async onCaptureMouseUp(event) {
    if (!this.captureMode || !this.captureStart) return;
    const canvas = this.$el.querySelector('#hierarchyCanvas');
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const raw = {
      x: Math.min(this.captureStart.x, x),
      y: Math.min(this.captureStart.y, y),
      w: Math.abs(x - this.captureStart.x),
      h: Math.abs(y - this.captureStart.y)
    };
    let captureRect = this.clampCaptureRect(raw);
    this.captureStart = null;
    this.captureRect = null;
    this.renderHierarchy();
    if (captureRect.w < 10 || captureRect.h < 10) {
      this.$message({ message: '选择区域太小，已取消', type: 'warning' });
      this.exitCaptureMode();
      return;
    }
    await this.createImageStep(captureRect);
    this.exitCaptureMode();
  },

  async createImageStep(rect) {
    const { scale, offsetX, offsetY } = this.screenshotTransform;
    const imgX = Math.round((rect.x - offsetX) / scale);
    const imgY = Math.round((rect.y - offsetY) / scale);
    const imgW = Math.round(rect.w / scale);
    const imgH = Math.round(rect.h / scale);
    const base64Data = getFromLocalStorage('cachedScreenshot', null);
    if (!base64Data) {
      this.$message({ message: '无截图缓存，请刷新后重试', type: 'warning' });
      return;
    }
    if (!this.projectId) {
      this.projectId = 'proj_' + Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
    }
    const img = new Image();
    img.src = `data:image/png;base64,${base64Data}`;
    await new Promise(r => { img.onload = r; });
    const cropCanvas = document.createElement('canvas');
    cropCanvas.width = imgW;
    cropCanvas.height = imgH;
    const ctx = cropCanvas.getContext('2d');
    ctx.drawImage(img, imgX, imgY, imgW, imgH, 0, 0, imgW, imgH);
    const croppedBase64 = cropCanvas.toDataURL('image/png');
    const imgName = `${this.projectId}_step_${Date.now()}.png`;
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
    this.selectStep(stepIdx);
    saveImage(imgName, croppedBase64)
      .then(() => { step._imageSaved = true; })
      .catch((e) => { console.error('保存图片失败', e); });
    this.ensureFile();
    this.$message({ message: `已添加图片定位步骤`, type: 'success' });
    if (this.autoRun) this.runSingleStep(stepIdx);
  },
};
