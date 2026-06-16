# -*- coding: utf-8 -*-

import ast
import base64
import json
import keyword
import os
import re
import shutil
import subprocess
import string
import sys
import tempfile
import time
from pathlib import Path
from typing import Union, Dict, Any, Optional, List

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse

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
from ha4t.editor._config import (
    get_workspace, get_tasks_dir, get_images_dir, EditorConfig,
)


router = APIRouter()

# 工作区未选定时为 None；所有数据端点先用 _no_ws() 守卫。
TASKS_DIR = None
IMAGES_DIR = None
CASES_DIR = None


def _refresh_paths():
    """Re-read config so updated workspace takes effect without restart."""
    global TASKS_DIR, IMAGES_DIR, CASES_DIR
    ws = get_workspace()
    TASKS_DIR = ws
    IMAGES_DIR = (ws / "images") if ws else None
    CASES_DIR = (ws / "testcases") if ws else None
    if IMAGES_DIR is not None:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    if CASES_DIR is not None:
        CASES_DIR.mkdir(parents=True, exist_ok=True)


def _no_ws():
    return ApiResponse.doError("未选择工作区")


_refresh_paths()


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


def _coerce_legacy_dict_to_element(raw: dict) -> dict:
    """老 dict 格式 → 新 ElementShape。

    老格式：扁平 selector dict，例如 ``{"text": "登录", "_parent": "顶部"}`` 或
    ``{"image": "x.png"}``。新格式按平台分桶 + 图像 + meta 三类拆开存储，让前端
    UI 能按 platform tab 渲染、AI 读 POM 能看见结构化的"哪个平台采集了什么"。

    迁移策略：扁平 dict 视为"老用户只测了一个平台"——所有非 _ 前缀、非 image
    字段都塞进 android 分桶（兼容到目前 HA4T 主用 Android 的现状）。用户切到
    iOS 后会看到 ios 分桶空、出现"未采集"标记，去采集即可。image 元素直接走
    image 字段。
    """
    parent = raw.get('_parent') or ''
    doc = raw.get('_doc') or ''
    image = raw.get('image')
    if image:
        return {'platforms': {}, 'image': image, '_parent': parent, '_doc': doc}
    bucket = {k: v for k, v in raw.items() if not k.startswith('_') and k != 'image'}
    platforms = {'android': bucket} if bucket else {}
    return {'platforms': platforms, 'image': None, '_parent': parent, '_doc': doc}


def _ast_call_to_element(call_node: ast.Call) -> Optional[dict]:
    """``Selector(...)`` AST 节点 → ElementShape；非 Selector 调用返回 None。

    只信赖 `func.id == 'Selector'` 或 `func.attr == 'Selector'` —— round-trip
    用户手工改了文件结构（如改成自定义工厂）我们不解析、当语法错误处理。
    所有 kwargs 用 ast.literal_eval；平台分桶值必须是 dict 字面量。
    """
    func = call_node.func
    name = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name != 'Selector':
        return None

    platforms: dict = {}
    image: Optional[str] = None
    parent = ''
    doc = ''
    for kw in call_node.keywords:
        if kw.arg is None:
            continue   # **expr 不处理
        try:
            val = ast.literal_eval(kw.value)
        except (ValueError, SyntaxError):
            return None
        if kw.arg in ('android', 'ios', 'harmony'):
            if isinstance(val, dict):
                platforms[kw.arg] = val
        elif kw.arg == 'image':
            if isinstance(val, str):
                image = val
        elif kw.arg == '_parent':
            if isinstance(val, str):
                parent = val
        elif kw.arg == '_doc':
            if isinstance(val, str):
                doc = val
        # 其它 `_xxx` meta 暂不处理（保留扩展位）
    return {'platforms': platforms, 'image': image, '_parent': parent, '_doc': doc}


def _parse_pom_py(content: str) -> dict:
    """解析 pom page / meta 文件 → {meta, elements, docs, parents, vars}。

    支持两种 ELEMENTS 元素表达：
      1. ``"name": Selector(android={...}, ios={...}, image=..., _parent=..., _doc=...)``
         新格式，平台分桶 + 跨平台 image + meta
      2. ``"name": {"text": "..."}``  老扁平 dict 格式
         自动按 ``_coerce_legacy_dict_to_element`` 升级（默认进 android 分桶）

    elements 在响应里是新 ElementShape；docs / parents 仍并列单独返回（前端模型
    最先是按 name → text/parent 字典化做的，保留这层 API 兼容直到下个迭代统一）。

    用 tokenize 抽每条元素 key 上方紧邻的 `#` 注释作为 doc 兜底——如果 Selector
    字面量里也写了 _doc，源码里那个优先。语法错误时返回空 dict。
    """
    meta = {'page': '', 'desc': '', 'triggers': ''}
    for line in content.split('\n'):
        if line.startswith('# page:'):
            meta['page'] = line.split(':', 1)[1].strip()
        elif line.startswith('# desc:'):
            meta['desc'] = line.split(':', 1)[1].strip()
        elif line.startswith('# triggers:'):
            meta['triggers'] = line.split(':', 1)[1].strip()

    elements: dict = {}
    pvars: dict = {}
    # ELEMENTS dict 里 key string → 行号，用于关联 `#` 注释作为 doc 兜底
    elements_keys_by_line: dict[int, str] = {}
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {'meta': meta, 'elements': {}, 'docs': {}, 'parents': {}, 'vars': {}}

    for node in tree.body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            continue
        target_name = node.targets[0].id
        if target_name == 'VARS':
            try:
                pvars = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                pvars = {}
            if not isinstance(pvars, dict):
                pvars = {}
            continue
        if target_name != 'ELEMENTS' or not isinstance(node.value, ast.Dict):
            continue
        # 遍历 ELEMENTS 每个 entry：key 必须是 string literal，value 可能是
        # Selector(...) Call 或 dict 字面量（向后兼容）
        for key_node, value_node in zip(node.value.keys, node.value.values):
            if not (isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)):
                continue
            key_name = key_node.value
            elements_keys_by_line[key_node.lineno] = key_name
            element_shape: Optional[dict] = None
            if isinstance(value_node, ast.Call):
                element_shape = _ast_call_to_element(value_node)
            if element_shape is None:
                # 老 dict 字面量 → coerce
                try:
                    raw = ast.literal_eval(value_node)
                except (ValueError, SyntaxError):
                    continue
                if isinstance(raw, dict):
                    element_shape = _coerce_legacy_dict_to_element(raw)
            if element_shape is not None:
                elements[key_name] = element_shape

    # tokenize 注释 — 给没在 Selector(_doc=) 里写 doc 但写了顶上 `# ...` 的元素兜底
    comments_by_line: dict[int, str] = {}
    try:
        import io, tokenize as _tok
        for tok in _tok.generate_tokens(io.StringIO(content).readline):
            if tok.type == _tok.COMMENT:
                txt = tok.string
                if txt.startswith('#'):
                    txt = txt[1:]
                    if txt.startswith(' '):
                        txt = txt[1:]
                comments_by_line[tok.start[0]] = txt
    except (_tok.TokenError, IndentationError):
        pass

    code_lines = content.split('\n')
    for key_line, key_name in elements_keys_by_line.items():
        # Selector 字面量里 _doc 优先；否则用 `#` 注释兜底
        existing = elements.get(key_name, {}).get('_doc') or ''
        if existing:
            continue
        doc_parts: list = []
        L = key_line - 1
        while L >= 1:
            if L in comments_by_line:
                doc_parts.append(comments_by_line[L])
                L -= 1
                continue
            raw_line = code_lines[L - 1] if L - 1 < len(code_lines) else ''
            if raw_line.strip() == '':
                break
            break
        if doc_parts:
            doc_parts.reverse()
            elements[key_name]['_doc'] = '\n'.join(doc_parts).rstrip()

    # 抽出独立的 docs / parents 字典（与 elements 并列返回；前端目前还在用）
    docs: dict = {}
    parents: dict = {}
    for k, el in elements.items():
        if el.get('_doc'):
            docs[k] = el['_doc']
        if el.get('_parent'):
            parents[k] = el['_parent']

    return {'meta': meta, 'elements': elements, 'docs': docs, 'parents': parents, 'vars': pvars}


def _render_selector_literal(el: dict) -> str:
    """ElementShape → Python 源代码字面量 ``Selector(...)``。

    输出字段顺序固定：``_parent`` → ``_doc`` → ``image`` → ``android`` → ``ios`` →
    ``harmony``。同一 element 多次保存生成的字符串完全一致，git diff 稳定。
    image 与 platforms 互斥规则在前端保证，这里只负责按 shape 写。
    """
    parts: list = []
    parent = el.get('_parent') or ''
    doc = el.get('_doc') or ''
    image = el.get('image') or None
    platforms = el.get('platforms') or {}
    if parent:
        parts.append(f'_parent={parent!r}')
    if doc:
        parts.append(f'_doc={doc!r}')
    if image:
        parts.append(f'image={image!r}')
    for p in ('android', 'ios', 'harmony'):
        bucket = platforms.get(p)
        if bucket:
            parts.append(f'{p}={bucket!r}')
    return f'Selector({", ".join(parts)})'


def _render_pom_py(
    page: str, desc: str, triggers: str, elements: dict,
    docs: Optional[dict] = None, parents: Optional[dict] = None,
) -> str:
    """渲染 ElementShape 集合 → ``pom/<page>.py`` 源码。

    `docs` / `parents` 参数仍接受（前端旧调用未升级时单独传），会被合并到 elements
    对应 ElementShape 的 `_doc` / `_parent` 字段，最终在 ``Selector(...)`` 字面量
    里以 `_doc=` / `_parent=` 形式输出 —— 不再写顶上的 `#` 注释；这样 round-trip
    走的是结构化字段，比注释更稳。
    """
    docs = docs or {}
    parents = parents or {}
    lines = ['# -*- coding: utf-8 -*-', '# kind: pom', f'# page: {page}']
    if desc:
        lines.append(f'# desc: {desc}')
    if triggers:
        lines.append(f'# triggers: {triggers}')
    lines += ['', 'from ha4t import Selector', '', 'ELEMENTS = {']
    for k, raw in elements.items():
        # 容忍前端传两种形态：新 ElementShape 或老扁平 dict 直接传 selector
        el = raw if isinstance(raw, dict) and ('platforms' in raw or 'image' in raw or '_parent' in raw or '_doc' in raw) else _coerce_legacy_dict_to_element(raw if isinstance(raw, dict) else {})
        # 合并独立 docs / parents 入参（前端旧路径还在用并列字典）
        if k in docs and docs[k]:
            el = {**el, '_doc': docs[k]}
        if k in parents and parents[k]:
            el = {**el, '_parent': parents[k]}
        lines.append(f'    {k!r}: {_render_selector_literal(el)},')
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


# ── Workspace / FS browse (must be before /tasks/{filename:path}) ─────


class WorkspaceOpenRequest(BaseModel):
    path: str


class WorkspaceInitRequest(BaseModel):
    parent: str
    name: str


def _init_workspace(target: Path) -> dict:
    """在 ``target`` 下幂等铺出 HA4T 工作区骨架。

    所有文件都「不存在才写」—— 已有的 ``conftest.py`` / ``pyproject.toml`` /
    ``README.md`` / ``pom/_meta.py`` 等用户文件一律不动。目录用 ``exist_ok=True``。
    返回 ``{path: 已创建的相对路径列表}``，调用方可日志/响应里告诉用户补了啥。
    """
    created: list[str] = []

    def _put(rel: str, content: str) -> None:
        f = target / rel
        if f.exists():
            return
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding='utf-8')
        created.append(rel)

    (target / 'pom').mkdir(parents=True, exist_ok=True)
    (target / 'images').mkdir(parents=True, exist_ok=True)
    (target / 'screenshots').mkdir(parents=True, exist_ok=True)

    _put('pom/__init__.py', '# -*- coding: utf-8 -*-\n')
    _put('pom/_meta.py', _render_pom_meta({}))
    _put('images/.gitkeep', '')
    _put('screenshots/.gitkeep', '')
    _put('testcases/.gitkeep', '')

    # 迁移：把历史遗留在工作区根的用例 .py 移入 testcases/（与 list_tasks 同一过滤口径）。
    # 幂等——移动后根目录不再有用例文件；同名已存在则跳过、不覆盖。
    cases_dir = target / 'testcases'
    for f in target.glob('*.py'):
        if f.name in ('conftest.py', '__init__.py') or f.name.startswith(('_', '.')):
            continue
        dest = cases_dir / f.name
        if not dest.exists():
            f.rename(dest)
            created.append(f'testcases/{f.name} (migrated)')
    # 铺 CLAUDE.md + 根级模板（conftest.py / pyproject.toml / README.md）
    skills_dir = Path(__file__).parent.parent / 'skills'
    for f in skills_dir.iterdir():
        if f.is_file():
            _put(f.name, f.read_text(encoding='utf-8'))

    return {"created": created}


@router.get("/fs/list", response_model=ApiResponse)
def fs_list(path: str = ""):
    """目录浏览：path 为空 → 根（盘符 / 根 + HOME），否则列子目录。"""
    if not path:
        roots = []
        if sys.platform == "win32":
            for c in string.ascii_uppercase:
                d = Path(f"{c}:/")
                if d.exists():
                    roots.append({"name": f"{c}:", "path": str(d)})
        else:
            roots.append({"name": "/", "path": "/"})
        home = Path.home()
        roots.append({"name": f"~ ({home.name})", "path": str(home)})
        return ApiResponse.doSuccess({"path": "", "parent": None, "entries": roots})
    p = Path(path).expanduser()
    if not p.is_dir():
        return ApiResponse.doError("不是有效目录")
    entries = []
    try:
        for child in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            if child.is_dir() and not child.name.startswith('.'):
                entries.append({"name": child.name, "path": str(child)})
    except PermissionError:
        entries = []
    parent = str(p.parent) if p.parent != p else None
    return ApiResponse.doSuccess({"path": str(p), "parent": parent, "entries": entries})


@router.get("/files/raw", response_model=ApiResponse)
def files_raw(path: str):
    """读取工作区内任意文本文件的原始内容，供前端「查看源码」弹窗用。

    `path` 是相对工作区根的路径（如 `testcases/test_login.py`、`pom/login_page.py`）。
    限制：只允许 .py / .md / .toml / .txt / .json / .yaml / .yml；目标必须在工作区根
    之下（防 `..` 遍历）；非文本/超大文件拒绝。
    """
    if TASKS_DIR is None:
        return _no_ws()
    if not path:
        return ApiResponse.doError("path 必填")
    try:
        # 拼接后 resolve；is_relative_to 确保没逃出工作区根
        target = (TASKS_DIR / path).resolve()
        ws_root = TASKS_DIR.resolve()
        if not target.is_relative_to(ws_root):
            return ApiResponse.doError("路径越界")
    except (OSError, ValueError):
        return ApiResponse.doError("非法路径")
    if not target.is_file():
        return ApiResponse.doError("文件不存在")
    if target.suffix.lower() not in {'.py', '.md', '.toml', '.txt', '.json', '.yaml', '.yml', '.cfg', '.ini'}:
        return ApiResponse.doError(f"不支持的文件类型: {target.suffix}")
    # 1 MB 上限——源码查看器不应该用于大文件
    if target.stat().st_size > 1 * 1024 * 1024:
        return ApiResponse.doError("文件超过 1 MB，不予显示")
    try:
        content = target.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return ApiResponse.doError("非 UTF-8 文本文件")
    return ApiResponse.doSuccess({
        "path": str(target.relative_to(ws_root)).replace('\\', '/'),
        "content": content,
    })


@router.get("/workspace", response_model=ApiResponse)
def workspace_status():
    ws = get_workspace()
    return ApiResponse.doSuccess({
        "current": str(ws) if ws else "",
        "recent": EditorConfig().recent(),
        "initialized": ws is not None,
    })


@router.post("/workspace/open", response_model=ApiResponse)
def workspace_open(req: WorkspaceOpenRequest):
    try:
        p = EditorConfig().set_workspace(req.path)
    except ValueError as e:
        return ApiResponse.doError(str(e))
    # 幂等补骨架：已有的文件不动，缺的（skill / conftest / pyproject / pom 等）补上。
    # 让「选一个普通目录」直接可用，避免用户还得手工跑一次 init。
    info = _init_workspace(p)
    _refresh_paths()
    return ApiResponse.doSuccess({"path": str(p), "created": info["created"]})


@router.post("/workspace/init", response_model=ApiResponse)
def workspace_init(req: WorkspaceInitRequest):
    parent = Path(req.parent).expanduser()
    if not parent.is_dir():
        return ApiResponse.doError("父目录不存在")
    name = (req.name or "").strip()
    if not name or any(c in name for c in r'\/:*?"<>|'):
        return ApiResponse.doError("工作区名非法")
    target = parent / name
    if target.exists() and any(target.iterdir()):
        return ApiResponse.doError("目录已存在且非空")
    info = _init_workspace(target)
    EditorConfig().set_workspace(str(target))
    _refresh_paths()
    return ApiResponse.doSuccess({"path": str(target), "created": info["created"]})


@router.post("/tasks/open-folder", response_model=ApiResponse)
def open_tasks_folder():
    if TASKS_DIR is None:
        return _no_ws()
    try:
        path = str(CASES_DIR)
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
    if IMAGES_DIR is None:
        return _no_ws()
    img_path = IMAGES_DIR / imgname
    if not img_path.exists():
        return ApiResponse.doError(f"Image not found: {imgname}")
    data = base64.b64encode(img_path.read_bytes()).decode("utf-8")
    return ApiResponse.doSuccess({"filename": imgname, "data": data})


class ImageUploadRequest(BaseModel):
    data: str

@router.post("/images/{imgname}", response_model=ApiResponse)
def save_image(imgname: str, req: ImageUploadRequest):
    if IMAGES_DIR is None:
        return _no_ws()
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
    docs: dict = {}     # 元素名 → 自由文本注释；渲染时插在该元素上方 `# ...` 行
    parents: dict = {}  # 元素名 → 父元素名；为前端树形 UI 提供层级语义


class PomMetaSaveRequest(BaseModel):
    vars: dict = {}


@router.get("/pom/pages", response_model=ApiResponse)
def pom_list_pages():
    if TASKS_DIR is None:
        return _no_ws()
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
    if TASKS_DIR is None:
        return _no_ws()
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
        'docs': parsed['docs'],
        'parents': parsed.get('parents', {}),
    })


@router.post("/pom/pages", response_model=ApiResponse)
def pom_save_page(req: PomPageSaveRequest):
    if TASKS_DIR is None:
        return _no_ws()
    # page 名必须是合法 Python 标识符：覆盖 ASCII (LoginPage)、中文 (登录页)、
    # snake_case (login_page) 等；PEP 3131 已纳入中文为合法标识字符。
    # keyword.iskeyword() 阻止 'class' / 'def' 等保留字。
    if not req.page or not req.page.isidentifier() or keyword.iskeyword(req.page):
        return ApiResponse.doError("页面名必须是合法 Python 标识符（如 LoginPage、登录页、login_page），不能以数字开头或为保留字")
    filename = _page_filename(req.page)
    path = _pom_dir() / filename
    path.write_text(
        _render_pom_py(req.page, req.desc, req.triggers, req.elements, req.docs, req.parents),
        encoding='utf-8',
    )
    _regen_pom_init()
    return ApiResponse.doSuccess({"filename": filename})


@router.delete("/pom/pages/{filename}", response_model=ApiResponse)
def pom_delete_page(filename: str):
    if TASKS_DIR is None:
        return _no_ws()
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
    if TASKS_DIR is None:
        return _no_ws()
    meta_f = _pom_dir() / '_meta.py'
    if not meta_f.exists():
        _regen_pom_init()
    parsed = _parse_pom_py(meta_f.read_text(encoding='utf-8', errors='ignore'))
    return ApiResponse.doSuccess({"vars": parsed['vars']})


@router.post("/pom/meta", response_model=ApiResponse)
def pom_save_meta(req: PomMetaSaveRequest):
    if TASKS_DIR is None:
        return _no_ws()
    meta_f = _pom_dir() / '_meta.py'
    meta_f.write_text(_render_pom_meta(req.vars), encoding='utf-8')
    return ApiResponse.doSuccess({"saved": True})

class PomVerifySelectorRequest(BaseModel):
    platform: str
    serial: str
    selector: dict


@router.post("/pom/verify-selector", response_model=ApiResponse)
def pom_verify_selector(req: PomVerifySelectorRequest):
    """对单个 POM selector 调底层 driver 实际查找，返回命中区域。

    req.selector 兼容两种 shape：
      - ElementShape `{platforms: {<plat>: {...}}, image, _parent, _doc}`：取 platforms[req.platform]
      - 老扁平 dict `{text:..., resourceId:...}`：直接当当前平台 native kwargs
    image 元素需在设备上手工验证，直接报错。
    """
    if not req.selector:
        return ApiResponse.doError("selector 不能为空")
    raw = dict(req.selector)
    # ElementShape：抽出当前平台的 bucket，image 直接报错
    if 'platforms' in raw or 'image' in raw:
        if raw.get('image'):
            return ApiResponse.doError("image 元素需在设备上手工验证")
        bucket = (raw.get('platforms') or {}).get(req.platform) or {}
        if not bucket:
            return ApiResponse.doError(f"该元素在 {req.platform} 平台未采集")
        sel = {k: v for k, v in bucket.items() if not k.startswith('_')}
    else:
        if 'image' in raw:
            return ApiResponse.doError("image 元素需在设备上手工验证")
        sel = {k: v for k, v in raw.items() if not k.startswith('_')}
    device = cached_devices.get((req.platform, req.serial))
    if device is None:
        return ApiResponse.doError("设备未连接")
    try:
        rect = device.find_element_rect(sel)
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
    if TASKS_DIR is None:
        return _no_ws()
    files = []
    for p in sorted(CASES_DIR.glob("*.py")):
        # 跳过 conftest / 包 init / 下划线/点开头的临时与隐藏文件
        if p.name in ("conftest.py", "__init__.py") or p.name.startswith(('_', '.')):
            continue
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
    if TASKS_DIR is None:
        return _no_ws()
    path = CASES_DIR / filename
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
    if TASKS_DIR is None:
        return _no_ws()
    path = CASES_DIR / filename
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


@router.get("/tasks/{filename:path}/project-id", response_model=ApiResponse)
def get_project_id(filename: str):
    if TASKS_DIR is None:
        return _no_ws()
    path = CASES_DIR / filename
    if not path.exists():
        return ApiResponse.doSuccess("")
    content = path.read_text(encoding="utf-8")
    meta = _extract_meta(content)
    return ApiResponse.doSuccess(meta.get('project_id', ''))




@router.post("/tasks/{filename:path}/cleanup-images", response_model=ApiResponse)
def cleanup_task_images(filename: str):
    if TASKS_DIR is None:
        return _no_ws()
    path = CASES_DIR / filename
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
    if TASKS_DIR is None:
        await ws.send_json({"type": "error", "msg": "未选择工作区"})
        await ws.close()
        return
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

    # preamble：令 dev.click(image="x.png") 解析到 <workspace>/images
    preamble = (
        "import os as _os\n"
        "from ha4t.config import global_config as _gc\n"
        "_gc.current_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'images')\n"
    )
    content = preamble + content

    # 把运行文件写到工作区根 —— 让 `from pom import ...`/`include(...)`/__file__ 都按
    # 工作区相对路径解析；运行后清掉。文件名带 pid+ts，避免并发碰撞、list_tasks 跳过。
    run_file = TASKS_DIR / f".harun_{os.getpid()}_{int(time.time() * 1000)}.py"
    run_file.write_text(content, encoding="utf-8")

    step_codes = _parse_py_steps(content)
    total = len(step_codes)

    # PYTHONPATH：工作区根（pom 导入）+ 项目根（开发态 ha4t 源码树场景）。
    project_root = Path(__file__).parent.parent.parent
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "").split(os.pathsep) if env.get("PYTHONPATH") else []
    for p in [str(TASKS_DIR), str(project_root), str(project_root.parent)]:
        if p not in existing:
            existing.insert(0, p)
    env["PYTHONPATH"] = os.pathsep.join(existing)

    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", str(run_file)],
            cwd=str(TASKS_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        # step.index 始终是子 yaml 内的 1-based 序号；前端按 stepOffset 把它换成
        # 完整 task steps[] 里的下标（idx = index - 1 + stepOffset）。
        # 之前后端也把 step_offset 加到 index 里，前端又加一次 → 单步/分段执行时
        # idx 翻倍越界，step UI 永远卡在 loading。
        step_idx = 0
        prev = None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if _STEP_MARKER in line and step_idx < total:
                if prev is not None:
                    await ws.send_json({"type": "step", "index": prev, "status": "ok"})
                step_idx += 1
                await ws.send_json({"type": "step", "index": step_idx, "status": "running"})
                prev = step_idx
            await ws.send_json({"type": "log", "text": line})
        proc.wait()

        all_ok = (proc.returncode == 0)
        if prev:
            await ws.send_json({"type": "step", "index": prev, "status": "ok" if all_ok else "fail"})
        ok = total if all_ok else 0
        fail = 0 if all_ok else total
        await ws.send_json({"type": "done", "ok": ok, "fail": fail, "total": total})
    except Exception as e:
        await ws.send_json({"type": "error", "msg": str(e)})
    finally:
        try:
            run_file.unlink(missing_ok=True)
        except Exception:
            pass
    await ws.close()


# ── Allure 报告 ─────────────────────────────────────────────────────────
#
# 报告统一存进 ``<workspace>/allure-reports/<safe_name>/``：
#  - 跟工作区同生命周期（切工作区列表跟着变；删工作区报告也一并去掉）
#  - 不再用全局 ~/Documents/HA4T/allure-reports 池
#  - 静态文件通过 GET /allure/{path:path} 端点动态 serve，避免 FastAPI mount
#    必须启动时绑死目录的限制


def _allure_dir() -> Optional[Path]:
    """当前工作区的报告目录；未选工作区返 None。惰性创建。"""
    if TASKS_DIR is None:
        return None
    d = TASKS_DIR / "allure-reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_report_summary(report_dir: Path) -> dict:
    """从 ``widgets/summary.json`` 抽测试统计；缺失/损坏时返空字典让前端兜底。"""
    summary_file = report_dir / "widgets" / "summary.json"
    if not summary_file.exists():
        return {}
    try:
        data = json.loads(summary_file.read_text(encoding="utf-8"))
        stat = data.get("statistic", {}) or {}
        return {
            "passed":  int(stat.get("passed", 0)),
            "failed":  int(stat.get("failed", 0)),
            "broken":  int(stat.get("broken", 0)),
            "skipped": int(stat.get("skipped", 0)),
            "unknown": int(stat.get("unknown", 0)),
            "total":   int(stat.get("total", 0)),
        }
    except (ValueError, OSError):
        return {}


@router.post("/tasks/{filename:path}/run-allure")
async def run_task_allure(filename: str):
    """跑用例 + 生成 Allure 报告到 ``<workspace>/allure-reports/<safe>/``。返回 ``report_url``。

    实现：动态在工作区下生成 ``.harun_<pid>.py`` 测试 runner，pytest 收集到一个
    ``test_case()`` 用例，里面按 ``# --step--`` 切用户原 .py、每段 exec 在
    ``with allure.step(...)`` 上下文里 —— allure 报告就能看到 1 个 test + N 个
    step（带标题、单独 pass/fail）。用户原 .py 完全不动。

    为什么不直接喂用户的 .py：用户用例是脚本风格（模块顶层就 dev.click(...)），
    pytest 既收不到 test_ 函数（cases=0），collection 阶段还会真跑代码导致 import
    失败时报告整体崩。
    """
    if TASKS_DIR is None:
        return _no_ws()
    task_path = CASES_DIR / filename
    if not task_path.exists():
        return ApiResponse.doError(f"File not found: {filename}")

    project_root = Path(__file__).parent.parent.parent
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "").split(os.pathsep) if env.get("PYTHONPATH") else []
    for p in [str(TASKS_DIR), str(project_root), str(project_root.parent)]:
        if p not in existing:
            existing.insert(0, p)
    env["PYTHONPATH"] = os.pathsep.join(existing)

    # ── 解析用例 .py 顶部注释为 allure / pytest 元数据 ────────────────────
    src_text = task_path.read_text(encoding='utf-8')
    case_title = task_path.stem    # fallback
    case_desc  = ''
    case_tag      = ''   # # tag: smoke,login   → @allure.tag(...)
    case_feature  = ''   # # feature: 登录      → @allure.feature(...) — 让 Behaviors tab 有数据
    case_story    = ''   # # story: 正常登录    → @allure.story(...)
    case_severity = ''   # # severity: critical → @allure.severity(<level>)
    case_rerun    = 0    # # rerun: N           → pytest --reruns N（需 pytest-rerunfailures 已装）
    for line in src_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('# name:'):
            case_title = stripped[len('# name:'):].strip() or case_title
        elif stripped.startswith('# desc:'):
            case_desc = stripped[len('# desc:'):].strip()
        elif stripped.startswith('# tag:'):
            case_tag = stripped[len('# tag:'):].strip()
        elif stripped.startswith('# feature:'):
            case_feature = stripped[len('# feature:'):].strip()
        elif stripped.startswith('# story:'):
            case_story = stripped[len('# story:'):].strip()
        elif stripped.startswith('# severity:'):
            case_severity = stripped[len('# severity:'):].strip().lower()
        elif stripped.startswith('# rerun:'):
            try:
                case_rerun = max(0, int(stripped[len('# rerun:'):].strip()))
            except ValueError:
                case_rerun = 0
        elif not stripped.startswith('#'):
            break   # 命中第一行代码 → 停（顶部注释块只在文件最前）

    # Allure severity 仅接受固定五档；非法值降回 normal 静默兼容
    _VALID_SEVERITY = {'blocker', 'critical', 'normal', 'minor', 'trivial'}
    if case_severity and case_severity not in _VALID_SEVERITY:
        case_severity = ''

    # 运行 runner 放到 <workspace>/.ha4t-runs/test_<safe>_<pid>.py —— 不污染
    # 工作区根（list_tasks 也跳过 `.` 开头目录），同时 pytest 仍按 test_* 收集到
    runs_dir = TASKS_DIR / '.ha4t-runs'
    runs_dir.mkdir(parents=True, exist_ok=True)
    # 清理：删早于 1 小时的旧 runner（防进程崩 / 异常退出留垃圾）
    _now = time.time()
    for stale in runs_dir.glob('test_*.py'):
        try:
            if _now - stale.stat().st_mtime > 3600:
                stale.unlink(missing_ok=True)
        except OSError:
            pass

    safe_base = re.sub(r'[^A-Za-z0-9_\u4e00-\u9fff]+', '_', task_path.stem).strip('_') or 'case'
    runner_path = runs_dir / f"test_{safe_base}_{os.getpid()}.py"
    # ── 装饰器拼接 —— 按字段是否非空择优 emit，避免空字段污染报告 ──
    decorators = ['@allure.title(CASE_TITLE)']
    if case_desc:                 decorators.append('@allure.description(CASE_DESC)')
    if case_feature:              decorators.append('@allure.feature(CASE_FEATURE)')
    if case_story:                decorators.append('@allure.story(CASE_STORY)')
    if case_severity:             decorators.append(f'@allure.severity(allure.severity_level.{case_severity.upper()})')
    if case_tag:
        # 逗号分隔多 tag —— @allure.tag(*tags) 支持 varargs
        decorators.append('@allure.tag(*CASE_TAGS)')

    tag_list = [t.strip() for t in case_tag.split(',') if t.strip()] if case_tag else []

    runner_src = (
        '# -*- coding: utf-8 -*-\n'
        '# Auto-generated by HA4T editor — do not edit. Deleted after run.\n'
        'import re\n'
        'import allure\n'
        'from pathlib import Path\n'
        '\n'
        f'CASE_PATH    = Path(r"""{task_path}""")\n'
        f'CASE_TITLE   = {case_title!r}\n'
        f'CASE_DESC    = {case_desc!r}\n'
        f'CASE_FEATURE = {case_feature!r}\n'
        f'CASE_STORY   = {case_story!r}\n'
        f'CASE_TAGS    = {tag_list!r}\n'
        '\n'
        + '\n'.join(decorators) + '\n'
        'def test_case():\n'
        '    src = CASE_PATH.read_text(encoding="utf-8")\n'
        '    # 按 # --step-- 切；第一段是 import + dev=connect(...) 等 setup\n'
        '    parts = re.split(r"\\n# --step--[^\\n]*\\n", src)\n'
        '    step_titles = re.findall(r"# --step--\\s*([^\\n]*)", src)\n'
        '    ns = {"__file__": str(CASE_PATH), "__name__": "__main__"}\n'
        '    exec(compile(parts[0], str(CASE_PATH), "exec"), ns)\n'
        '    for i, body in enumerate(parts[1:]):\n'
        '        title = (step_titles[i].strip() if i < len(step_titles) else "") or f"步骤 {i+1}"\n'
        '        try:\n'
        '            with allure.step(title):\n'
        '                exec(compile(body, str(CASE_PATH), "exec"), ns)\n'
        '        except Exception:\n'
        '            # 失败时拍一张当前屏当 allure attachment；dev 来自 setup 段\n'
        '            try:\n'
        '                dev = ns.get("dev")\n'
        '                if dev is not None and hasattr(dev, "screenshot"):\n'
        '                    import io\n'
        '                    img = dev.screenshot()\n'
        '                    buf = io.BytesIO()\n'
        '                    img.save(buf, format="PNG")\n'
        '                    allure.attach(buf.getvalue(), name=f"失败截图: {title}",\n'
        '                                  attachment_type=allure.attachment_type.PNG)\n'
        '            except Exception:\n'
        '                pass   # 截图本身失败别淹没原始报错\n'
        '            raise\n'
    )
    runner_path.write_text(runner_src, encoding='utf-8')

    result_dir = TASKS_DIR / "allure-results"
    report_dir = TASKS_DIR / "allure-report"
    try:
        pytest_cmd = [sys.executable, "-m", "pytest", str(runner_path),
                      "--alluredir", str(result_dir), "--clean-alluredir",
                      "-v", "--tb=short"]
        # 失败重试：用 pytest-rerunfailures。插件未装 → pytest 启动报错，
        # 我们事先 probe 一下，缺插件时只警告不阻断（runner 仍能正常跑一次）。
        if case_rerun > 0:
            try:
                import importlib
                importlib.import_module("pytest_rerunfailures")
                pytest_cmd += ["--reruns", str(case_rerun)]
            except ImportError:
                # 写到 stdout 让用户看到 "为什么 rerun 没生效" 而不是闷头执行
                pass
        result = subprocess.run(
            pytest_cmd,
            cwd=str(TASKS_DIR), capture_output=True, text=True, env=env,
        )

        allure_cmd = shutil.which("allure")
        report_url = ""
        if allure_cmd:
            subprocess.run(
                [allure_cmd, "generate", str(result_dir),
                 "-o", str(report_dir), "--clean"],
                capture_output=True, cwd=str(TASKS_DIR),
            )
            report_index = report_dir / "index.html"
            if report_index.exists():
                # 加时间戳后缀避免覆盖：同一用例每次跑保留独立目录便于历史对比。
                # 格式 `<filename-no-ext>_<YYYYMMDD-HHMMSS>` —— 用 - 不用 : 避免 Windows 文件名非法
                base_name = filename.replace('.py', '').replace('/', '_').replace('\\', '_')
                ts = time.strftime('%Y%m%d-%H%M%S', time.localtime())
                safe_name = f"{base_name}_{ts}"
                out_dir = _allure_dir() / safe_name
                shutil.rmtree(out_dir, ignore_errors=True)
                shutil.copytree(report_dir, out_dir)
                report_url = f"/allure/{safe_name}/index.html"

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
        try: runner_path.unlink(missing_ok=True)
        except Exception: pass


@router.get("/allure-reports", response_model=ApiResponse)
def list_allure_reports():
    """列出当前工作区下所有 Allure 报告，按 mtime 倒序（最近在前）。"""
    if TASKS_DIR is None:
        return _no_ws()
    d = _allure_dir()
    items = []
    for sub in d.iterdir():
        if not sub.is_dir():
            continue
        index = sub / "index.html"
        if not index.exists():
            continue
        stat = sub.stat()
        items.append({
            "name": sub.name,
            "url": f"/allure/{sub.name}/index.html",
            "mtime": stat.st_mtime,
            "summary": _read_report_summary(sub),
        })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return ApiResponse.doSuccess({"reports": items})


@router.delete("/allure-reports/{name}", response_model=ApiResponse)
def delete_allure_report(name: str):
    """删除当前工作区下指定的 Allure 报告。"""
    if TASKS_DIR is None:
        return _no_ws()
    if not name or '/' in name or '\\' in name or name.startswith('.'):
        return ApiResponse.doError("非法的报告名")
    target = _allure_dir() / name
    if not target.exists() or not target.is_dir():
        return ApiResponse.doError("报告不存在")
    shutil.rmtree(target, ignore_errors=True)
    return ApiResponse.doSuccess({"deleted": name})


@router.get("/allure/{path:path}")
def serve_allure(path: str):
    """从 ``<workspace>/allure-reports/<path>`` serve 静态报告文件。

    报告本身是 Allure 生成的 SPA（index.html + js/css/data），相对路径在 page
    内部自洽，所以路由前缀 ``/allure/<report-name>/`` 等价于把那个目录当 web root。

    特殊处理：Allure SPA 会无脑 fetch 所有 plugin 的数据文件（behaviors / packages
    等），缺数据时 Allure 自己不生成对应 json —— 真 404 会让 console 红一片让人误以为
    报告坏掉。这里对一组已知的"可选"文件返回空对象 ``{}``，让 SPA 走"空数据"分支
    平静降级。
    """
    if TASKS_DIR is None:
        raise HTTPException(status_code=404, detail="未选择工作区")
    if not path:
        raise HTTPException(status_code=404, detail="缺少路径")
    base = _allure_dir().resolve()
    target = (base / path).resolve()
    # 防 path traversal —— 报告目录之外的文件一律拒绝
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=403, detail="路径越界")
    if target.is_file():
        return FileResponse(target)
    # Allure 可选 plugin 数据：缺失时返空 JSON 给 SPA，不报 404 不污染 console
    rel_norm = path.replace('\\', '/').rsplit('/', 1)[-1]
    _OPTIONAL_EMPTY = {
        'behaviors.json', 'packages.json', 'behaviors-trend.json',
        'allure-version.json', 'tags.json',
    }
    if rel_norm in _OPTIONAL_EMPTY:
        return JSONResponse({})
    raise HTTPException(status_code=404, detail="文件不存在")


# ── 注意：以下两个 catch-all 路由必须保持在文件末尾。 ──
# FastAPI 用 `path` converter 时贪婪匹配剩余所有段；`/tasks/{filename:path}` 会吃下
# `/tasks/foo.py/run-allure` 之类带后缀的 URL，必须等所有具体后缀路由先声明后再放这两个。


@router.get("/tasks/{filename:path}", response_model=ApiResponse)
def load_task(filename: str):
    if TASKS_DIR is None:
        return _no_ws()
    path = CASES_DIR / filename
    if not path.exists():
        return ApiResponse.doError(f"File not found: {filename}")
    content = path.read_text(encoding="utf-8")
    return ApiResponse.doSuccess({"filename": filename, "content": content})


@router.post("/tasks/{filename:path}", response_model=ApiResponse)
def save_task(filename: str, req: TaskSaveRequest):
    if TASKS_DIR is None:
        return _no_ws()
    path = CASES_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(req.content, encoding="utf-8")
    return ApiResponse.doSuccess({"filename": filename, "saved": True})
