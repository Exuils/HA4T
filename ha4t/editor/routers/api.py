# -*- coding: utf-8 -*-

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
from ha4t.editor._models import (
    ApiResponse, XPathLiteRequest,
    TaskFile, TaskSaveRequest, TaskRunRequest, TaskStepResult, TaskRunResponse
)
from ha4t.editor.parser.xpath_lite import XPathLiteGenerator


router = APIRouter()

TASKS_DIR = Path(os.environ.get(
    "HA4T_TASKS_DIR",
    Path(__file__).parent.parent.parent.parent / "tasks"
))
TASKS_DIR.mkdir(parents=True, exist_ok=True)

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


# ── Task API (.py + # --step--) ──────────────────────────


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


def _generate_py(name, desc, platform, step_codes, extra_lines=None):
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
    for code in step_codes:
        lines.append(_STEP_MARKER)
        lines.append(code)
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
    if not content and filename:
        path = TASKS_DIR / filename
        if path.exists():
            content = path.read_text(encoding="utf-8")
    if not content:
        await ws.send_json({"type": "error", "msg": "No task content"})
        await ws.close()
        return

    step_codes = _parse_py_steps(content)
    total = len(step_codes)
    if not total:
        await ws.send_json({"type": "error", "msg": "No # --step-- markers found"})
        await ws.close()
        return

    tmpdir = Path(tempfile.mkdtemp())
    tmppy = tmpdir / (filename or "untitled.py")
    tmppy.write_text(content, encoding="utf-8")

    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", str(tmppy)],
            cwd=Path(__file__).parent.parent.parent.parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        step_idx = 0
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if _STEP_MARKER in line and step_idx < total:
                await ws.send_json({"type": "step", "index": step_idx + 1, "status": "running"})
                step_idx += 1
            await ws.send_json({"type": "log", "text": line})
        proc.wait()

        ok = total if proc.returncode == 0 else 0
        for i in range(total):
            status = "ok" if i < ok else "fail"
            await ws.send_json({"type": "step", "index": i + 1, "status": status})
        await ws.send_json({"type": "done", "ok": ok, "fail": total - ok, "total": total})
    except Exception as e:
        await ws.send_json({"type": "error", "msg": str(e)})
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass
    await ws.close()
