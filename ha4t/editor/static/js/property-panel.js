export const PropertyPanelMethods = {
  computedStepType() {
    const s = this.selectedStep;
    if (!s) return null;
    const c = s.code;
    if (s.stepType === 'element') return 'element';
    if (s._type === 'imglocate') return 'imglocate';
    if (/^swipe\(/.test(c)) return 'swipe';
    if (/^click\(/.test(c)) return 'tap';
    if (c.startsWith('type(')) return 'type';
    if (c.startsWith('key(')) return 'key';
    if (c.startsWith('launchapp(')) return 'launchapp';
    if (c.startsWith('sleep(')) return 'wait';
    return 'code';
  },

  selectedStepConfig() {
    const s = this.selectedStep;
    if (!s) return null;
    const config = { type: this.computedStepType(), fields: {} };
    const c = s.code;
    switch (config.type) {
      case 'element':
        config.fields = this._elementFields();
        break;
      case 'imglocate':
        config.fields = this._imgFields();
        break;
      case 'swipe': {
        const m = c.match(/swipe\(\(([\d.]+),\s*([\d.]+)\)\s*,\s*\(([\d.]+),\s*([\d.]+)\)\)/);
        config.fields = m ? { x1: +m[1], y1: +m[2], x2: +m[3], y2: +m[4] } : { _raw: c };
        break;
      }
      case 'tap': {
        const m = c.match(/^click\((.*)\)$/);
        config.fields = { selector: m ? m[1] : '' };
        break;
      }
      case 'type': {
        const m = c.match(/(?:send_keys|type)\("([^"]*)"\)/);
        config.fields = { text: m ? m[1] : '' };
        break;
      }
      case 'key': {
        const m = c.match(/(?:press|key)\("([^"]*)"\)/);
        config.fields = { key: m ? m[1] : '' };
        break;
      }
      case 'launchapp': {
        const m = c.match(/(?:start_app|launchapp)\("([^"]*)"\)/);
        config.fields = { package: m ? m[1] : '' };
        break;
      }
      case 'wait': {
        const m = c.match(/(?:time\.)?sleep\(([\d.]+)\)/);
        config.fields = { seconds: m ? +m[1] : 1 };
        break;
      }
      default:
        config.fields = { _raw: c };
    }
    return config;
  },

  updateStepField(field, value) {
    const step = this.selectedStep;
    if (!step) return;
    const type = this.computedStepType();
    const esc = (s) => (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n');

    // Handle remark (common to all step types)
    if (field === 'remark') {
      step.remark = value;
      this._dirtyStep();
      return;
    }

    if (type === 'element') {
      this._updateElementField(field, value);
      return;
    }

    if (type === 'imglocate') {
      this._updateImgField(field, value);
      return;
    }

    switch (type) {
      case 'swipe': {
        const m = step.code.match(/swipe\(\(([\d.]+),\s*([\d.]+)\)\s*,\s*\(([\d.]+),\s*([\d.]+)\)\)/);
        if (!m) return;
        const f = { x1: m[1], y1: m[2], x2: m[3], y2: m[4], [field]: value };
        step.code = `swipe((${+f.x1}, ${+f.y1}), (${+f.x2}, ${+f.y2}))`;
        break;
      }
      case 'tap':
        step.code = `click(${value})`;
        break;
      case 'type':
        step.code = `type("${esc(value)}")`;
        break;
      case 'key':
        step.code = `key("${esc(value)}")`;
        break;
      case 'launchapp':
        step.code = `start_app("${esc(value)}")`;
        break;
      case 'wait':
        step.code = `sleep(${value})`;
        break;
      case 'code':
        step.code = value;
        break;
    }
    this._dirtyStep();
  },

  // ── Element step helpers ──

  _elementFields() {
    const s = this.selectedStep;
    if (!s) return {};
    return {
      stepType: 'element',
      elementAction: s.elementAction || 'click',
      selector: s.selector || {},
      elementParams: s.elementParams || {},
    };
  },

  _updateElementField(field, value) {
    const step = this.selectedStep;
    if (!step) return;

    // Handle selector.subfield format
    if (field.startsWith('selector.')) {
      const subKey = field.slice(9);
      if (!step.selector) step.selector = {};
      step.selector[subKey] = value;
      if (!value) delete step.selector[subKey];
    }
    // Handle elementAction
    else if (field === 'elementAction') {
      step.elementAction = value;
      if (!step.elementParams) step.elementParams = {};
    }
    // Handle param.subfield format
    else if (field.startsWith('param.')) {
      const subKey = field.slice(6);
      if (!step.elementParams) step.elementParams = {};
      step.elementParams[subKey] = value;
    }
    // Handle action parameter fields directly
    else if (['interval', 'duration', 'dx', 'dy', 'dragDuration', 'operator', 'expected', 'extract'].includes(field)) {
      if (!step.elementParams) step.elementParams = {};
      step.elementParams[field] = value;
    }

    // Regenerate code
    if (this._generateElementCode) {
      step.code = this._generateElementCode(step);
    } else {
      step.code = this.generateElementCodeSimple(step);
    }
    this._dirtyStep();
  },

  generateElementCodeSimple(step) {
    const sel = this._buildSelectorStringSimple(step.selector);
    const p = step.elementParams || {};
    switch (step.elementAction) {
      case 'click':
        return sel ? `click(${sel})` : `click()`;
      case 'double_click':
        return `double_click(${sel}, interval=${p.interval || 0.05})`;
      case 'long_press':
        return `long_press(${sel}, duration=${p.duration || 1.0})`;
      case 'drag':
        return `drag(${sel}, dx=${p.dx || 0}, dy=${p.dy || 0}, duration=${p.dragDuration || 0.5})`;
      case 'assert': {
        if (p.extract === 'exists') {
          return `assert_element(${sel}, operator="${p.operator || 'exists_true'}")`;
        }
        const exp = p.expected ? `, expected="${p.expected}"` : '';
        return `assert_element(${sel}, operator="${p.operator || 'eq'}"${exp})`;
      }
      default:
        return `click(${sel})`;
    }
  },

  _buildSelectorStringSimple(selector) {
    if (!selector) return '';
    const esc = (s) => (s || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t');
    const parts = [];
    if (selector.text) parts.push(`text="${esc(selector.text)}"`);
    if (selector.resourceId) parts.push(`resourceId="${esc(selector.resourceId)}"`);
    if (selector.className) parts.push(`className="${esc(selector.className)}"`);
    if (selector.xpath) parts.push(`xpath="${esc(selector.xpath)}"`);
    if (selector.description) parts.push(`description="${esc(selector.description)}"`);
    if (selector.index != null && selector.index >= 0) parts.push(`index=${selector.index}`);
    return parts.join(', ');
  },

  _removeSelectorField(key) {
    const step = this.selectedStep;
    if (!step || !step.selector) return;
    delete step.selector[key];
    this._updateElementField('code', '');
  },

  // ── Image step helpers ──

  _imgFields() {
    const s = this.selectedStep;
    if (!s) return {};
    return {
      action: s.action || 'click',
      grid_h: s.grid_h || 1,
      grid_v: s.grid_v || 1,
      click_col: s.click_col || 0,
      click_row: s.click_row || 0,
      timeout: s.timeout || 10,
      threshold: s.threshold ?? '',
      image: s.image || null,
    };
  },

  _updateImgField(field, value) {
    const step = this.selectedStep;
    if (!step) return;
    step[field] = value;
    if (['action','grid_h','grid_v','click_col','click_row','timeout','threshold'].includes(field)) {
      step.code = this.generateImgCode(step);
    }
    this._dirtyStep();
    if (['grid_h','grid_v','click_col','click_row'].includes(field)) {
      this.$nextTick(() => this.renderImgConfigGrid());
    }
  },

  generateImgCode(step) {
    const imgPath = step.image_filename || 'template.png';
    const t = step.threshold ? `, threshold=${step.threshold}` : '';
    if (step.action === 'click') {
      if (step.grid_h === 1 && step.grid_v === 1) return `click(image="${imgPath}"${t})`;
      return `click(image="${imgPath}", grid=(${step.click_col}, ${step.click_row}), splits=(${step.grid_h}, ${step.grid_v})${t})`;
    } else if (step.action === 'wait_show') {
      return `wait(image="${imgPath}", timeout=${step.timeout}${t})`;
    } else if (step.action === 'wait_hide') {
      return `wait(image="${imgPath}", timeout=${step.timeout}, reverse=True${t})`;
    }
    return `click(image="${imgPath}"${t})`;
  },

  renderImgConfigGrid() {
    const canvas = this.$el.querySelector('#imgConfigCanvas');
    const img = this.$el.querySelector('#imgConfigPreview');
    if (!canvas || !img || !img.naturalWidth || !img.naturalHeight) return;

    const imgRect = img.getBoundingClientRect();
    const wrapRect = img.parentElement.getBoundingClientRect();
    const offX = imgRect.left - wrapRect.left;
    const offY = imgRect.top - wrapRect.top;
    const rW = imgRect.width, rH = imgRect.height;

    canvas.style.left = offX + 'px';
    canvas.style.top = offY + 'px';
    canvas.style.width = rW + 'px';
    canvas.style.height = rH + 'px';
    canvas.width = rW * (window.devicePixelRatio || 1);
    canvas.height = rH * (window.devicePixelRatio || 1);

    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, rW, rH);

    const step = this.selectedStep;
    if (!step || step._type !== 'imglocate') return;
    const cols = step.grid_h, rows = step.grid_v;
    const cw = rW / cols, ch = rH / rows;

    ctx.strokeStyle = 'rgba(255,255,255,0.6)';
    ctx.lineWidth = 1;
    for (let c = 1; c < cols; c++) { ctx.beginPath(); ctx.moveTo(c * cw, 0); ctx.lineTo(c * cw, rH); ctx.stroke(); }
    for (let r = 1; r < rows; r++) { ctx.beginPath(); ctx.moveTo(0, r * ch); ctx.lineTo(rW, r * ch); ctx.stroke(); }

    if (step.action === 'click') {
      ctx.fillStyle = 'rgba(54,121,227,0.4)';
      ctx.fillRect(step.click_col * cw, step.click_row * ch, cw, ch);
      ctx.strokeStyle = '#3679E3';
      ctx.lineWidth = 2;
      ctx.strokeRect(step.click_col * cw, step.click_row * ch, cw, ch);
      const cx = step.click_col * cw + cw / 2, cy = step.click_row * ch + ch / 2;
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(cx - 6, cy); ctx.lineTo(cx + 6, cy); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx, cy - 6); ctx.lineTo(cx, cy + 6); ctx.stroke();
    }
  },

  onGridCellClick(event) {
    const step = this.selectedStep;
    if (!step || step._type !== 'imglocate' || step.action !== 'click') return;
    const canvas = this.$el.querySelector('#imgConfigCanvas');
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left, y = event.clientY - rect.top;
    const cols = step.grid_h, rows = step.grid_v;
    step.click_col = Math.min(Math.max(Math.floor(x / (rect.width / cols)), 0), cols - 1);
    step.click_row = Math.min(Math.max(Math.floor(y / (rect.height / rows)), 0), rows - 1);
    step.code = this.generateImgCode(step);
    this._dirtyStep();
    this.renderImgConfigGrid();
  },

  _dirtyStep() {
    const i = this.selectedStepIndex;
    if (i >= 0) { this.pushUndo(); this.$set(this.steps, i, { ...this.steps[i] }); }
    this.ensureFile();
  },
};
