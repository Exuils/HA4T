# -*- coding: utf-8 -*-

import base64
import json
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


router = APIRouter()

TASKS_DIR = Path(os.environ.get(
    "HA4T_TASKS_DIR",
    Path.home() / "Documents" / "HA4T" / "tasks" if os.name == "nt"
    else Path.home() / "ha4t" / "tasks"
))
TASKS_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/tasks/open-folder", response_model=ApiResponse)
def open_tasks_folder():
    import subprocess, sys
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
    """Parse # --step-- markers, return list of {code, meta}"""
    lines = content.split('\n')
    steps = []
    buf = []
    meta = None
    in_step = False
    for line in lines:
        stripped = line.strip()
        if stripped == _STEP_MARKER:
            if in_step and buf:
                steps.append({'code': '\n'.join(buf).strip(), 'meta': meta})
                buf = []
                meta = None
            in_step = True
            continue
        if in_step:
            if stripped.startswith('# @imglocate'):
                try:
                    meta = _json.loads(stripped[len('# @imglocate'):].strip())
                except Exception:
                    pass
                continue
            if stripped and not stripped.startswith('#'):
                buf.append(line)
    if in_step and buf:
        steps.append({'code': '\n'.join(buf).strip(), 'meta': meta})
    return steps


def _extract_meta(content: str) -> dict:
    name = desc = ''
    platform = 'android'
    for line in content.split('\n'):
        if line.startswith('# name:'):
            name = line.split(':', 1)[1].strip()
        elif line.startswith('# desc:'):
            desc = line.split(':', 1)[1].strip()
        elif line.startswith('# platform:'):
            platform = line.split(':', 1)[1].strip()
    return {'name': name, 'desc': desc, 'platform': platform}


def _generate_py(name, desc, platform, steps, extra_lines=None):
    lines = ['# name: ' + name]
    if desc:
        lines.append('# desc: ' + desc)
    lines.append('# platform: ' + platform)
    lines.append('import os')
    lines.append('os.environ["FLAGS_use_mkldnn"] = "0"')
    lines.append('from ha4t import connect')
    lines.append('from ha4t.api import *')
    lines.append('connect(platform="' + platform + '")')
    lines.append('')
    if extra_lines:
        lines.extend(extra_lines)
    for step in steps:
        lines.append(_STEP_MARKER)
        meta = step.get('meta')
        if meta and meta.get('_type') == 'imglocate':
            lines.append('# @imglocate ' + _json.dumps(meta, ensure_ascii=False, separators=(',', ':')))
        lines.append(step['code'])
    lines.append('')
    return '\n'.join(lines)


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


@router.get("/tasks/{filename:path}/images", response_model=ApiResponse)
def list_task_images(filename: str):
    stem = Path(filename).stem
    img_dir = TASKS_DIR / f"{stem}_imgs"
    if not img_dir.exists():
        return ApiResponse.doSuccess([])
    files = [p.name for p in sorted(img_dir.glob("*.png"))]
    return ApiResponse.doSuccess(files)


@router.get("/tasks/{filename:path}/images/{imgname}", response_model=ApiResponse)
def get_task_image(filename: str, imgname: str):
    stem = Path(filename).stem
    img_path = TASKS_DIR / f"{stem}_imgs" / imgname
    if not img_path.exists():
        return ApiResponse.doError(f"Image not found: {imgname}")
    data = base64.b64encode(img_path.read_bytes()).decode("utf-8")
    return ApiResponse.doSuccess({"filename": imgname, "data": data})


class ImageUploadRequest(BaseModel):
    data: str

@router.post("/tasks/{filename:path}/images/{imgname}", response_model=ApiResponse)
def save_task_image(filename: str, imgname: str, req: ImageUploadRequest):
    stem = Path(filename).stem
    img_dir = TASKS_DIR / f"{stem}_imgs"
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / imgname
    data = req.data or ""
    if data.startswith("data:image"):
        data = data.split(",", 1)[1]
    img_path.write_bytes(base64.b64decode(data))
    return ApiResponse.doSuccess({"filename": imgname, "saved": True})


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
    stem = Path(filename).stem
    img_dir = TASKS_DIR / f"{stem}_imgs"
    if img_dir.exists():
        for img in img_dir.glob("*.png"):
            try:
                shutil.copy(img, tmpdir / img.name)
            except Exception:
                pass

    step_codes = _parse_py_steps(content)
    total = len(step_codes)

    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", str(tmppy)],
            cwd=Path(__file__).parent.parent.parent.parent,
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
