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
