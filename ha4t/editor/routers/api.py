# -*- coding: utf-8 -*-

import json
import logging
import os
import time
import traceback
from pathlib import Path
from typing import Union, Dict, Any

import yaml
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse

from ha4t.editor._device import (
    list_serials,
    init_device,
    cached_devices,
    AndroidDevice,
    IosDevice,
    HarmonyDevice
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

SUPPORTED_ACTIONS = {"tap", "drag", "type", "key", "launchapp", "wait"}


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
    platform: str,
    serial: str,
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
    tree_data = request.tree_data
    node_id = request.node_id
    generator = XPathLiteGenerator(platform, tree_data)
    xpath = generator.get_xpathLite(node_id)
    return ApiResponse.doSuccess(xpath)


# ── Task YAML API ────────────────────────────────────────────


@router.get("/{platform}/{serial}/packages", response_model=ApiResponse)
def list_packages(platform: str, serial: str):
    device = cached_devices.get((platform, serial))
    if not device:
        return ApiResponse.doSuccess([])
    try:
        if platform == "android" and hasattr(device, 'd'):
            pkgs = device.d.app_list()
            return ApiResponse.doSuccess(pkgs)
        elif platform == "ios" and hasattr(device, 'client'):
            import wda
            pkgs = [d.serial for d in wda.list_devices()]
            return ApiResponse.doSuccess(pkgs)
        return ApiResponse.doSuccess([])
    except Exception as e:
        return ApiResponse.doSuccess([])


@router.get("/tasks", response_model=ApiResponse)
def list_tasks():
    files = []
    for p in sorted(TASKS_DIR.glob("*.yaml")) + sorted(TASKS_DIR.glob("*.yml")):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            files.append(TaskFile(
                filename=p.name,
                name=data.get("name", p.stem),
                description=data.get("description", ""),
                platform=data.get("platform", "android"),
                step_count=len(data.get("steps", [])),
            ).model_dump())
        except Exception:
            files.append(TaskFile(
                filename=p.name, name=p.stem, description="",
                platform="android", step_count=0,
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

    platform = req.get("platform", "android")
    serial = req.get("serial", "")
    content = req.get("content", "")
    if not content and req.get("filename"):
        path = TASKS_DIR / req.get("filename")
        if path.exists():
            content = path.read_text(encoding="utf-8")

    if not content:
        await ws.send_json({"type": "error", "msg": "No task content"})
        await ws.close()
        return

    try:
        task = yaml.safe_load(content)
    except yaml.YAMLError as e:
        await ws.send_json({"type": "error", "msg": f"YAML error: {e}"})
        await ws.close()
        return

    steps_raw = task.get("steps", [])
    ok = 0
    fail = 0
    for i, step in enumerate(steps_raw, start=1):
        if not isinstance(step, dict) or len(step) != 1:
            await ws.send_json({"type": "step", "index": i, "action": "?",
                "value": str(step), "status": "skipped", "detail": "Invalid format"})
            fail += 1
            continue
        action, value = next(iter(step.items()))
        if action not in SUPPORTED_ACTIONS:
            await ws.send_json({"type": "step", "index": i, "action": action,
                "value": str(value), "status": "skipped", "detail": f"Unknown action: {action}"})
            fail += 1
            continue

        await ws.send_json({"type": "step", "index": i, "action": action,
            "value": str(value), "status": "running"})
        t0 = time.time()
        try:
            detail = _execute_step(platform, serial, action, value)
            duration = round(time.time() - t0, 2)
            await ws.send_json({"type": "step", "index": i, "action": action,
                "value": str(value), "status": "ok", "detail": detail, "duration": duration})
            ok += 1
        except Exception as e:
            duration = round(time.time() - t0, 2)
            await ws.send_json({"type": "step", "index": i, "action": action,
                "value": str(value), "status": "fail", "detail": str(e), "duration": duration})
            fail += 1
            break

    await ws.send_json({"type": "done", "ok": ok, "fail": fail, "total": ok + fail})
    await ws.close()


def _execute_step(platform: str, serial: str, action: str, value: str) -> str:
    device = cached_devices.get((platform, serial))
    if not device:
        raise RuntimeError("Device not connected")

    if platform == "android":
        driver = device.d if hasattr(device, 'd') else None
    elif platform == "ios":
        driver = device.client if hasattr(device, 'client') else None
    else:
        driver = device.hdc if hasattr(device, 'hdc') else None

    if not driver:
        raise RuntimeError("Device driver not available")

    if action == "launchapp":
        driver.app_start(value)
        time.sleep(2)
        return f"Launched {value}"

    elif action == "tap":
        if platform == "android":
            driver(text=value).click(timeout=5)
        else:
            driver.click_text(value)
        return f"Tapped '{value}'"

    elif action == "drag":
        parts = value.split()
        if len(parts) >= 4:
            x1, y1, x2, y2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        else:
            x1 = y1 = 300
            x2 = 300
            y2 = 700
        driver.swipe(x1, y1, x2, y2)
        return f"Swiped ({x1},{y1}) to ({x2},{y2})"

    elif action == "key":
        if platform == "android":
            driver.press(value)
        return f"Pressed key '{value}'"

    elif action == "type":
        driver.send_keys(value)
        return f"Typed '{value}'"

    elif action == "wait":
        if value.isdigit():
            seconds = int(value)
            time.sleep(seconds)
            return f"Waited {seconds}s"
        parts = value.split("|")
        seconds = int(parts[0])
        time.sleep(seconds)
        return f"Waited {seconds}s"

    return f"Done: {action} {value}"
