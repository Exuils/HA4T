import { saveToLocalStorage, getFromLocalStorage } from './utils.js';
import { fetchScreenshot } from './api.js';

export const CanvasMethods = {
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

  loadCachedScreenshot() {
    const cachedScreenshot = getFromLocalStorage('cachedScreenshot', null);
    if (cachedScreenshot) {
      this.renderScreenshot(cachedScreenshot);
    }
  },

  getScreenshotBoundsOnCanvas() {
    const canvas = this.$el.querySelector('#hierarchyCanvas');
    const { offsetX, offsetY } = this.screenshotTransform;
    const w = canvas.clientWidth - 2 * offsetX;
    const h = canvas.clientHeight - 2 * offsetY;
    return { left: offsetX, top: offsetY, right: offsetX + w, bottom: offsetY + h, width: w, height: h };
  },

  renderHierarchy() {
    const canvas = this.$el.querySelector('#hierarchyCanvas');
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (this.captureMode) {
      if (this.captureRect && this.captureRect.w > 0) {
        ctx.setLineDash([]);
        ctx.strokeStyle = '#00ff00';
        ctx.lineWidth = 2;
        ctx.strokeRect(this.captureRect.x, this.captureRect.y, this.captureRect.w, this.captureRect.h);
        ctx.fillStyle = 'rgba(0, 255, 0, 0.15)';
        ctx.fillRect(this.captureRect.x, this.captureRect.y, this.captureRect.w, this.captureRect.h);
      }
      return;
    }

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

    if (this.swipeRecordMode && this.swipePoints.length) {
      ctx.setLineDash([]);
      const [w, h] = [canvas.clientWidth, canvas.clientHeight];
      this.swipePoints.forEach((p, i) => {
        const px = p.x * w;
        const py = p.y * h;
        ctx.beginPath();
        ctx.arc(px, py, 8, 0, 2 * Math.PI);
        ctx.fillStyle = i === 0 ? '#00ff00' : '#ff4444';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 12px sans-serif';
        ctx.fillText(i === 0 ? '起点' : '终点', px + 12, py - 12);
      });
      if (this.swipePoints.length === 2) {
        const p1 = this.swipePoints[0];
        const p2 = this.swipePoints[1];
        ctx.beginPath();
        ctx.moveTo(p1.x * w, p1.y * h);
        ctx.lineTo(p2.x * w, p2.y * h);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
      }
    }
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

  async screenshotAndDumpHierarchy() {
    this.isDumping = true;
    try {
      await this.fetchScreenshot();
      await this._fetchHierarchy();
    } catch (err) {
      this.$message({ showClose: true, message: `错误: ${err.message}`, type: 'error' });
    } finally {
      this.isDumping = false;
    }
  },
};
