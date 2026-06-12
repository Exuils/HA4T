# -*- coding: utf-8 -*-

import ast
import base64
import json
import keyword
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Union, Dict, Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse

from ha4t.editor._device import (
    list_serials, init_device, cached_devices,
    AndroidDevice, IosDevice, HarmonyDevice
)
from ha4t.editor._version import __version__
from ha4t.editor._models import (    ApiResponse, XPathLiteRequest,
    TaskFile, TaskSaveRequest, TaskRunRequest, TaskStepResult, TaskRunResponse
)
from pydantic import BaseModel
from ha4t.editor.parser.xpath_lite import XPathLiteGenerator
from ha4t.editor._config import get_tasks_dir, get_images_dir, EditorConfig


router = APIRouter()

TASKS_DIR = get_tasks_dir()
IMAGES_DIR = get_images_dir()


def _refresh_paths():
    """Re-read config so updated paths take effect without restart."""
    global TASKS_DIR, IMAGES_DIR
    TASKS_DIR = get_tasks_dir()
    IMAGES_DIR = get_images_dir()


_STEP_MARKER = "# --step--"


@router.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@router.get("/health")
def health():
    return "ok"


@router.get("/version", response_model=ApiResponse)
def get_version():
    return ApiResponse.doSuccess(__version__)


@router.get("/{platform}/serials", response_model=ApiResponse)
def get_serials(platform: str):
    serials = list_serials(platform)
    return ApiResponse.doSuccess(serials)


@router.post("/{platform}/{serial}/connect", response_model=ApiResponse)
def connect(
    platform: str, serial: str,
    wdaUrl: Union[str, None] = Query(None),
    maxDepth: Union[int, None] = Query(None)
):
    ret = init_device(platform, serial, wdaUrl, maxDepth)
    return ApiResponse.doSuccess(ret)


@router.get("/{platform}/{serial}/screenshot", response_model=ApiResponse)
def screenshot(platform: str, serial: str):
    device = cached_devices.get((platform, serial))
    data = device.take_screenshot()
    return ApiResponse.doSuccess(data)


@router.get("/{platform}/{serial}/hierarchy", response_model=ApiResponse)
def dump_hierarchy(platform: str, serial: str):
    device = cached_devices.get((platform, serial))
    data = device.dump_hierarchy()
    return ApiResponse.doSuccess(data)


@router.post("/{platform}/hierarchy/xpathLite", response_model=ApiResponse)
async def fetch_xpathLite(platform: str, request: XPathLiteRequest):
    generator = XPathLiteGenerator(platform, request.tree_data)
    xpath = generator.get_xpathLite(request.node_id)
    return ApiResponse.doSuccess(xpath)


@router.get("/{platform}/{serial}/packages", response_model=ApiResponse)
def list_packages(platform: str, serial: str):
    device = cached_devices.get((platform, serial))
    if not device:
        return ApiResponse.doSuccess([])
    try:
        if platform == "android" and hasattr(device, 'd'):
            return ApiResponse.doSuccess(device.d.app_list())
    except Exception:
        pass
    return ApiResponse.doSuccess([])


@router.post("/{platform}/{serial}/key/{key}", response_model=ApiResponse)
def press_key(platform: str, serial: str, key: str):
    device = cached_devices.get((platform, serial))
    if not device:
        return ApiResponse.doError("Device not connected")
    try:
        if platform == "android" and hasattr(device, 'd'):
            device.d.press(key)
        return ApiResponse.doSuccess(f"Pressed {key}")
    except Exception as e:
        return ApiResponse.doError(str(e))


# ── Task API (.py + # --step--) ──────────────────────────


import json as _json

def _parse_py_steps(content: str) -> list:
    """Parse # --step-- markers, return list of {code}"""
    lines = content.split('\n')
    steps = []
    buf = []
    in_step = False
    for line in lines:
        stripped = line.strip()
        if stripped == _STEP_MARKER:
            if in_step and buf:
                steps.append('\n'.join(buf).strip())
                buf = []
            in_step = True
            continue
        if in_step and stripped and not stripped.startswith('#'):
            buf.append(line)
    if in_step and buf:
        steps.append('\n'.join(buf).strip())
    return steps


def _extract_meta(content: str) -> dict:
    name = desc = project_id = ''
    platform = 'android'
    for line in content.split('\n'):
        if line.startswith('# name:'):
            name = line.split(':', 1)[1].strip()
        elif line.startswith('# desc:'):
            desc = line.split(':', 1)[1].strip()
        elif line.startswith('# platform:'):
            platform = line.split(':', 1)[1].strip()
        elif line.startswith('# project_id:'):
            project_id = line.split(':', 1)[1].strip()
    return {'name': name, 'desc': desc, 'platform': platform, 'project_id': project_id}


def _generate_py(name, desc, platform, step_codes, extra_lines=None):
    lines = ['# name: ' + name]
    if desc:
        lines.append('# desc: ' + desc)
    lines.append('# platform: ' + platform)
    lines.append('import os')
    lines.append('os.environ["FLAGS_use_mkldnn"] = "0"')
    lines.append('from ha4t import connect')
    lines.append('from time import sleep')
    lines.append('dev = connect(platform="' + platform + '")')
    lines.append('')
    if extra_lines:
        lines.extend(extra_lines)
    for code in step_codes:
        lines.append(_STEP_MARKER)
        lines.append(code)
    lines.append('')
    return '\n'.join(lines)


# ── POM (Page Object Model) helpers ─────────────────────────────────

POM_DIRNAME = "pom"


def _pom_dir() -> Path:
    """POM 包目录 — 必须在每个 handler 内调用（而非模块级缓存），便于测试 monkeypatch TASKS_DIR。"""
    d = TASKS_DIR / POM_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _page_filename(page: str) -> str:
    """生成 page 的磁盘文件名。
    - 纯 ASCII PascalCase（首字母大写、全部字母数字，如 LoginPage / HomePage）
      → snake_case.py（向后兼容旧约定）
    - 其他合法 Python 标识符（含中文、已是 snake_case、含下划线等）
      → <page>.py 原样
    """
    if re.fullmatch(r'[A-Z][a-zA-Z0-9]*', page):
        return re.sub(r'(?<!^)(?=[A-Z])', '_', page).lower() + '.py'
    return page + '.py'


def _parse_pom_py(content: str) -> dict:
    """解析 pom page / meta 文件 → {'meta': {page,desc,triggers}, 'elements': {}, 'vars': {}}。
    用 ast.literal_eval 抽取顶层 ELEMENTS / VARS 赋值；语法错误时返回空 dict（不抛异常）。
    page 文件不写 VARS（只 _meta.py 写）。"""
    meta = {'page': '', 'desc': '', 'triggers': ''}
    for line in content.split('\n'):
        if line.startswith('# page:'):
            meta['page'] = line.split(':', 1)[1].strip()
        elif line.startswith('# desc:'):
            meta['desc'] = line.split(':', 1)[1].strip()
        elif line.startswith('# triggers:'):
            meta['triggers'] = line.split(':', 1)[1].strip()
    elements, pvars = {}, {}
    try:
        tree = ast.parse(content)
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                try:
                    val = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
                if name == 'ELEMENTS' and isinstance(val, dict):
                    elements = val
                elif name == 'VARS' and isinstance(val, dict):
                    pvars = val
    except SyntaxError:
        pass
    return {'meta': meta, 'elements': elements, 'vars': pvars}


def _render_pom_py(page: str, desc: str, triggers: str, elements: dict) -> str:
    lines = ['# -*- coding: utf-8 -*-', '# kind: pom', f'# page: {page}']
    if desc:
        lines.append(f'# desc: {desc}')
    if triggers:
        lines.append(f'# triggers: {triggers}')
    lines += ['', 'ELEMENTS = {']
    for k, v in elements.items():
        lines.append(f'    {k!r}: {v!r},')
    lines += ['}', '']
    return '\n'.join(lines)


def _render_pom_meta(vars_: dict) -> str:
    lines = ['# -*- coding: utf-8 -*-', '# kind: pom-meta', '', 'VARS = {']
    for k, v in vars_.items():
        lines.append(f'    {k!r}: {v!r},')
    lines += ['}', '']
    return '\n'.join(lines)


def _regen_pom_init() -> None:
    """重新生成 pom/__init__.py：模块别名即 PageObject（LoginPage.ELEMENTS 可用）。
    _meta.py 不存在时先写默认空版本。"""
    d = _pom_dir()
    meta_f = d / '_meta.py'
    if not meta_f.exists():
        meta_f.write_text(_render_pom_meta({}), encoding='utf-8')
    lines = ['# -*- coding: utf-8 -*-',
             '# auto-generated by HA4T editor — do not edit',
             'from . import _meta',
             'VARS = _meta.VARS', '']
    for p in sorted(d.glob('*.py')):
        if p.name.startswith('_') or p.name == '__init__.py':
            continue
        parsed = _parse_pom_py(p.read_text(encoding='utf-8', errors='ignore'))
        page = parsed['meta']['page']
        if page:
            lines.append(f'from . import {p.stem} as {page}')
    lines.append('')
    (d / '__init__.py').write_text('\n'.join(lines), encoding='utf-8')


# ── Config (must be before /tasks/{filename:path}) ─────────────────

class ConfigUpdateRequest(BaseModel):
    key: str
    value: str

@router.get("/config", response_model=ApiResponse)
def get_config():
    cfg = EditorConfig()
    return ApiResponse.doSuccess({
        "tasks_dir": cfg.get("tasks_dir"),
        "images_dir": cfg.get("images_dir"),
        "screenshots_dir": cfg.get("screenshots_dir"),
    })

@router.post("/config", response_model=ApiResponse)
def set_config(req: ConfigUpdateRequest):
    cfg = EditorConfig()
    cfg.set(req.key, req.value)
    _refresh_paths()
    return ApiResponse.doSuccess({"key": req.key, "value": req.value})


@router.post("/tasks/open-folder", response_model=ApiResponse)
def open_tasks_folder():
    try:
        path = str(TASKS_DIR)
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return ApiResponse.doSuccess(path)
    except Exception as e:
        return ApiResponse.doError(str(e))


# ── Images (must be before /tasks/{filename:path}) ─────────────────

@router.get("/images/{imgname}", response_model=ApiResponse)
def get_image(imgname: str):
    img_path = IMAGES_DIR / imgname
    if not img_path.exists():
        return ApiResponse.doError(f"Image not found: {imgname}")
    data = base64.b64encode(img_path.read_bytes()).decode("utf-8")
    return ApiResponse.doSuccess({"filename": imgname, "data": data})


class ImageUploadRequest(BaseModel):
    data: str

@router.post("/images/{imgname}", response_model=ApiResponse)
def save_image(imgname: str, req: ImageUploadRequest):
    data = req.data or ""
    print(f"[save_image] received imgname={imgname}, data_len={len(data)}, starts_with_data={data.startswith('data:image')}")
    if data.startswith("data:image"):
        data = data.split(",", 1)[1]
    img_path = IMAGES_DIR / imgname
    try:
        decoded = base64.b64decode(data)
        img_path.write_bytes(decoded)
        print(f"[save_image] saved {imgname} ({len(decoded)} bytes) to {img_path}")
        return ApiResponse.doSuccess({"filename": imgname, "saved": True})
    except Exception as e:
        print(f"[save_image] error: {e}")
        return ApiResponse.doError(str(e))


# ── POM (Page Object Model) endpoints ──────────────────────────────

class PomPageSaveRequest(BaseModel):
    page: str
    desc: str = ''
    triggers: str = ''
    elements: dict = {}


class PomMetaSaveRequest(BaseModel):
    vars: dict = {}


@router.get("/pom/pages", response_model=ApiResponse)
def pom_list_pages():
    d = _pom_dir()
    items = []
    for p in sorted(d.glob('*.py')):
        if p.name.startswith('_') or p.name == '__init__.py':
            continue
        parsed = _parse_pom_py(p.read_text(encoding='utf-8', errors='ignore'))
        if not parsed['meta']['page']:
            continue
        items.append({
            'filename': p.name,
            'page': parsed['meta']['page'],
            'desc': parsed['meta']['desc'],
            'triggers': parsed['meta']['triggers'],
            'element_count': len(parsed['elements']),
        })
    return ApiResponse.doSuccess(items)


@router.get("/pom/pages/{filename}", response_model=ApiResponse)
def pom_get_page(filename: str):
    path = _pom_dir() / filename
    if not path.exists() or path.name.startswith('_'):
        return ApiResponse.doError("not found")
    parsed = _parse_pom_py(path.read_text(encoding='utf-8', errors='ignore'))
    return ApiResponse.doSuccess({
        'filename': filename,
        'page': parsed['meta']['page'],
        'desc': parsed['meta']['desc'],
        'triggers': parsed['meta']['triggers'],
        'elements': parsed['elements'],
    })


@router.post("/pom/pages", response_model=ApiResponse)
def pom_save_page(req: PomPageSaveRequest):
    # page 名必须是合法 Python 标识符：覆盖 ASCII (LoginPage)、中文 (登录页)、
    # snake_case (login_page) 等；PEP 3131 已纳入中文为合法标识字符。
    # keyword.iskeyword() 阻止 'class' / 'def' 等保留字。
    if not req.page or not req.page.isidentifier() or keyword.iskeyword(req.page):
        return ApiResponse.doError("页面名必须是合法 Python 标识符（如 LoginPage、登录页、login_page），不能以数字开头或为保留字")
    filename = _page_filename(req.page)
    path = _pom_dir() / filename
    path.write_text(
        _render_pom_py(req.page, req.desc, req.triggers, req.elements),
        encoding='utf-8',
    )
    _regen_pom_init()
    return ApiResponse.doSuccess({"filename": filename})


@router.delete("/pom/pages/{filename}", response_model=ApiResponse)
def pom_delete_page(filename: str):
    path = _pom_dir() / filename
    if path.name.startswith('_') or not path.suffix == '.py':
        return ApiResponse.doError("not found")
    if not path.exists():
        return ApiResponse.doError("not found")
    path.unlink()
    _regen_pom_init()
    return ApiResponse.doSuccess({"deleted": True})


@router.get("/pom/meta", response_model=ApiResponse)
def pom_get_meta():
    meta_f = _pom_dir() / '_meta.py'
    if not meta_f.exists():
        _regen_pom_init()
    parsed = _parse_pom_py(meta_f.read_text(encoding='utf-8', errors='ignore'))
    return ApiResponse.doSuccess({"vars": parsed['vars']})


@router.post("/pom/meta", response_model=ApiResponse)
def pom_save_meta(req: PomMetaSaveRequest):
    meta_f = _pom_dir() / '_meta.py'
    meta_f.write_text(_render_pom_meta(req.vars), encoding='utf-8')
    return ApiResponse.doSuccess({"saved": True})


@router.post("/pom/install-skill", response_model=ApiResponse)
def pom_install_skill():
    src = Path(__file__).parent.parent / 'skills' / 'ha4t-case-writer' / 'SKILL.md'
    if not src.exists():
        return ApiResponse.doError("skill 模板缺失")
    dst = TASKS_DIR / '.claude' / 'skills' / 'ha4t-case-writer' / 'SKILL.md'
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    return ApiResponse.doSuccess({"path": str(dst)})


class PomVerifySelectorRequest(BaseModel):
    platform: str
    serial: str
    selector: dict


@router.post("/pom/verify-selector", response_model=ApiResponse)
def pom_verify_selector(req: PomVerifySelectorRequest):
    """对单个 POM selector 调底层 driver 实际查找，返回命中区域。

    验证结果不落盘 — 纯实时查询。image 元素需在设备上手工验证，直接报错。
    """
    if not req.selector:
        return ApiResponse.doError("selector 不能为空")
    if 'image' in req.selector:
        return ApiResponse.doError("image 元素需在设备上手工验证")
    device = cached_devices.get((req.platform, req.serial))
    if device is None:
        return ApiResponse.doError("设备未连接")
    try:
        rect = device.find_element_rect(req.selector)
    except Exception as e:
        return ApiResponse.doError(f"查找失败: {type(e).__name__}: {e}")
    return ApiResponse.doSuccess({
        "found": rect is not None,
        "rect": rect,
        "platform_supported": not isinstance(device, HarmonyDevice),
    })


# ── Tasks ──────────────────────────────────────────────────────────

@router.get("/tasks", response_model=ApiResponse)
def list_tasks():
    files = []
    for p in sorted(TASKS_DIR.glob("*.py")):
        content = p.read_text(encoding="utf-8", errors='ignore')
        steps = _parse_py_steps(content)
        meta = _extract_meta(content)
        files.append(TaskFile(
            filename=p.name,
            name=meta['name'] or p.stem,
            description=meta.get('desc', ''),
            platform=meta.get('platform', 'android'),
            step_count=len(steps),
        ).model_dump())
    return ApiResponse.doSuccess(files)


class ReorderRequest(BaseModel):
    new_order: list[int]


@router.get("/tasks/{filename:path}/meta", response_model=ApiResponse)
def get_task_meta(filename: str):
    path = TASKS_DIR / filename
    if not path.exists():
        return ApiResponse.doError("not found")
    content = path.read_text(encoding="utf-8")
    meta = _extract_meta(content)
    steps = _parse_py_steps(content)
    return ApiResponse.doSuccess({
        "steps_count": len(steps),
        "platform": meta.get("platform", "android"),
        "name": meta.get("name", ""),
        "desc": meta.get("desc", ""),
        "project_id": meta.get("project_id", ""),
    })


@router.post("/tasks/{filename:path}/reorder", response_model=ApiResponse)
def reorder_task_v2(filename: str, req: ReorderRequest):
    path = TASKS_DIR / filename
    if not path.exists():
        return ApiResponse.doError("not found")
    content = path.read_text(encoding="utf-8")
    lines = content.split('\n')
    first_step_line = -1
    for idx, line in enumerate(lines):
        if line.strip() == _STEP_MARKER:
            first_step_line = idx
            break
    if first_step_line == -1:
        return ApiResponse.doError("no steps found")
    header_lines = lines[:first_step_line]
    step_blocks = []
    current_block = []
    pending_remarks = []
    in_block = False
    for line in lines[first_step_line:]:
        if line.strip() == _STEP_MARKER:
            if in_block:
                step_blocks.append(pending_remarks + [_STEP_MARKER] + current_block)
            pending_remarks = []
            current_block = []
            in_block = True
        elif in_block:
            current_block.append(line)
        else:
            pending_remarks.append(line)
    if in_block:
        step_blocks.append(pending_remarks + [_STEP_MARKER] + current_block)
    n = len(step_blocks)
    if len(req.new_order) != n or any(i < 0 or i >= n for i in req.new_order):
        return ApiResponse.doError("invalid order")
    reordered = [step_blocks[i] for i in req.new_order]
    new_lines = header_lines[:]
    for block in reordered:
        new_lines.extend(block)
    path.write_text('\n'.join(new_lines), encoding="utf-8")
    return ApiResponse.doSuccess({"steps_count": n, "reordered": True})


@router.get("/tasks/{filename:path}", response_model=ApiResponse)
def load_task(filename: str):
    path = TASKS_DIR / filename
    if not path.exists():
        return ApiResponse.doError(f"File not found: {filename}")
    content = path.read_text(encoding="utf-8")
    return ApiResponse.doSuccess({"filename": filename, "content": content})


@router.post("/tasks/{filename:path}", response_model=ApiResponse)
def save_task(filename: str, req: TaskSaveRequest):
    path = TASKS_DIR / filename
    path.write_text(req.content, encoding="utf-8")
    return ApiResponse.doSuccess({"filename": filename, "saved": True})


@router.get("/tasks/{filename:path}/project-id", response_model=ApiResponse)
def get_project_id(filename: str):
    path = TASKS_DIR / filename
    if not path.exists():
        return ApiResponse.doSuccess("")
    content = path.read_text(encoding="utf-8")
    meta = _extract_meta(content)
    return ApiResponse.doSuccess(meta.get('project_id', ''))




@router.post("/tasks/{filename:path}/cleanup-images", response_model=ApiResponse)
def cleanup_task_images(filename: str):
    path = TASKS_DIR / filename
    if not path.exists():
        return ApiResponse.doSuccess({"removed": 0})
    content = path.read_text(encoding="utf-8")
    meta = _extract_meta(content)
    project_id = meta.get('project_id', '')
    if not project_id:
        return ApiResponse.doSuccess({"removed": 0})

    # Find all referenced image filenames in the content
    referenced = set()
    for line in content.split('\n'):
        # Match image="..." or image='...'
        m = re.search(r'image=["\']([^"\']+)["\']', line)
        if m:
            referenced.add(m.group(1))
        # Also match image_filename in metadata
        m2 = re.search(r'"image_filename":"([^"]+)"', line)
        if m2:
            referenced.add(m2.group(1))

    removed = 0
    prefix = f"{project_id}_"
    for img_path in IMAGES_DIR.glob(f"{prefix}*.png"):
        if img_path.name not in referenced:
            try:
                img_path.unlink()
                removed += 1
            except Exception:
                pass

    return ApiResponse.doSuccess({"removed": removed, "referenced": len(referenced)})


@router.websocket("/ws/run")
async def ws_run_task(ws: WebSocket):
    await ws.accept()
    try:
        raw = await ws.receive_text()
        req = json.loads(raw)
    except Exception as e:
        await ws.send_json({"type": "error", "msg": f"Invalid request: {e}"})
        await ws.close()
        return

    content = req.get("content", "")
    filename = req.get("filename", "untitled.py")
    step_offset = req.get("step_offset", 0)

    content = re.sub(r'\r?\n# --step--\r?\n', '\nprint("# --step--")\n# --step--\n', content)

    tmpdir = Path(tempfile.mkdtemp())
    tmppy = tmpdir / (filename or "untitled.py")
    tmppy.write_text(content, encoding="utf-8")

    # Copy referenced images to temp dir so the script can find them
    meta = _extract_meta(content)
    project_id = meta.get('project_id', '')
    await ws.send_json({"type": "log", "text": f"[runner] project_id={project_id}, images_dir={IMAGES_DIR}"})
    copied = 0
    for line in content.split('\n'):
        m = re.search(r'image=["\']([^"\']+)["\']', line)
        if m:
            img_name = m.group(1)
            img_path = IMAGES_DIR / img_name
            await ws.send_json({"type": "log", "text": f"[runner] checking image: {img_name} -> exists={img_path.exists()}"})
            if img_path.exists():
                try:
                    shutil.copy(img_path, tmpdir / img_name)
                    copied += 1
                    await ws.send_json({"type": "log", "text": f"[runner] copied {img_name} to tmpdir"})
                except Exception as e:
                    await ws.send_json({"type": "log", "text": f"[runner] copy failed: {e}"})
    await ws.send_json({"type": "log", "text": f"[runner] total copied: {copied}"})

    # Copy referenced included task files (ha4t.include("xxx.py")) recursively
    # so the subprocess can find them in cwd. Also copy any images those files
    # reference. Cycle-safe via a visited set.
    visited: set = set()
    pending = [content]
    inc_copied = 0
    while pending:
        text = pending.pop()
        for line in text.split('\n'):
            m = re.search(r'\binclude\(\s*["\']([^"\']+)["\']\s*\)', line)
            if not m:
                continue
            ref = m.group(1)
            if ref in visited:
                continue
            visited.add(ref)
            src = TASKS_DIR / ref
            if not src.exists():
                await ws.send_json({"type": "log", "text": f"[runner] include source missing: {ref}"})
                continue
            try:
                shutil.copy(src, tmpdir / ref)
                inc_copied += 1
                await ws.send_json({"type": "log", "text": f"[runner] copied include {ref} to tmpdir"})
                sub_text = src.read_text(encoding="utf-8")
                pending.append(sub_text)
                # Also copy images referenced inside the included file
                for sub_line in sub_text.split('\n'):
                    im = re.search(r'image=["\']([^"\']+)["\']', sub_line)
                    if im:
                        img_name = im.group(1)
                        img_path = IMAGES_DIR / img_name
                        if img_path.exists() and not (tmpdir / img_name).exists():
                            try:
                                shutil.copy(img_path, tmpdir / img_name)
                                await ws.send_json({"type": "log", "text": f"[runner] copied image {img_name} (via include)"})
                            except Exception as e:
                                await ws.send_json({"type": "log", "text": f"[runner] copy image failed: {e}"})
            except Exception as e:
                await ws.send_json({"type": "log", "text": f"[runner] copy include failed: {e}"})
    if inc_copied:
        await ws.send_json({"type": "log", "text": f"[runner] total includes copied: {inc_copied}"})

    step_codes = _parse_py_steps(content)
    total = len(step_codes)

    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", str(tmppy)],
            cwd=str(tmpdir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        step_idx = 0
        prev = None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if _STEP_MARKER in line and step_idx < total:
                if prev is not None:
                    await ws.send_json({"type": "step", "index": prev + step_offset, "status": "ok"})
                step_idx += 1
                await ws.send_json({"type": "step", "index": step_idx + step_offset, "status": "running"})
                prev = step_idx
            await ws.send_json({"type": "log", "text": line})
        proc.wait()

        all_ok = (proc.returncode == 0)
        if prev:
            await ws.send_json({"type": "step", "index": prev + step_offset, "status": "ok" if all_ok else "fail"})
        ok = total if all_ok else 0
        fail = 0 if all_ok else total
        await ws.send_json({"type": "done", "ok": ok, "fail": fail, "total": total})
    except Exception as e:
        await ws.send_json({"type": "error", "msg": str(e)})
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
    await ws.close()


ALLURE_REPORTS_DIR = Path.home() / "Documents" / "HA4T" / "allure-reports"


@router.post("/tasks/{filename:path}/run-allure")
async def run_task_allure(filename: str):
    """Run task via pytest + Allure, return report URL"""
    task_path = TASKS_DIR / filename
    if not task_path.exists():
        return ApiResponse.doError(f"File not found: {filename}")

    tmpdir = Path(tempfile.mkdtemp(prefix="ha4t-allure-"))
    try:
        run_file = tmpdir / filename
        shutil.copy(task_path, run_file)

        # Copy conftest.py to tmpdir
        conftest_src = Path(__file__).parent.parent / "conftest.py"
        if conftest_src.exists():
            shutil.copy(conftest_src, tmpdir / "conftest.py")

        # Copy referenced images
        content = task_path.read_text("utf-8")
        for line in content.split('\n'):
            m = re.search(r'image=["\']([^"\']+)["\']', line)
            if m:
                img_name = m.group(1)
                img_path = IMAGES_DIR / img_name
                if img_path.exists():
                    try:
                        shutil.copy(img_path, tmpdir / img_name)
                    except Exception:
                        pass

        # Add project root to PYTHONPATH for subprocess
        project_root = Path(__file__).parent.parent.parent
        env = os.environ.copy()
        env.setdefault("PYTHONPATH", "")
        paths = [str(project_root), str(project_root.parent)]
        existing = env["PYTHONPATH"].split(os.pathsep) if env["PYTHONPATH"] else []
        for p in paths:
            if p not in existing:
                existing.insert(0, p)
        env["PYTHONPATH"] = os.pathsep.join(existing)

        # Run pytest
        result_dir = tmpdir / "allure-results"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(run_file),
             "--alluredir", str(result_dir), "--clean-alluredir",
             "-v", "--tb=short"],
            cwd=str(tmpdir), capture_output=True, text=True, env=env
        )

        # Generate report
        report_dir = tmpdir / "allure-report"
        allure_cmd = shutil.which("allure")
        report_url = ""
        if allure_cmd:
            subprocess.run(
                [allure_cmd, "generate", str(result_dir),
                 "-o", str(report_dir), "--clean"],
                capture_output=True, cwd=str(tmpdir)
            )
            report_index = report_dir / "index.html"
            if report_index.exists():
                safe_name = filename.replace('.py', '').replace('/', '_').replace('\\', '_')
                out_dir = ALLURE_REPORTS_DIR / safe_name
                shutil.rmtree(out_dir, ignore_errors=True)
                shutil.copytree(report_dir, out_dir)
                report_url = f"/allure-reports/{safe_name}/index.html"

        return ApiResponse.doSuccess({
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "report_url": report_url,
            "result_dir": str(result_dir),
        })
    except Exception as e:
        return ApiResponse.doError(str(e))
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
