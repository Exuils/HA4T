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


def _parse_pom_py(content: str) -> dict:
    """解析 pom page / meta 文件 → {'meta': {...}, 'elements': {}, 'docs': {}, 'vars': {}}。

    用 ast.literal_eval 抽顶层 ELEMENTS / VARS 字面量；用 tokenize 抽 ELEMENTS dict 内
    每项 key 紧邻上方的连续 `#` 注释作为该元素的 doc（多行用 \n 合并）。语法错误时返回空 dict。
    docs 与 elements 并列，不进 selector 字典——driver 不会拿到。
    """
    meta = {'page': '', 'desc': '', 'triggers': ''}
    for line in content.split('\n'):
        if line.startswith('# page:'):
            meta['page'] = line.split(':', 1)[1].strip()
        elif line.startswith('# desc:'):
            meta['desc'] = line.split(':', 1)[1].strip()
        elif line.startswith('# triggers:'):
            meta['triggers'] = line.split(':', 1)[1].strip()

    elements, pvars, docs = {}, {}, {}
    elements_keys_by_line: dict[int, str] = {}   # ELEMENTS dict 内每个 key 字符串 → 所在行号
    try:
        tree = ast.parse(content)
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                try:
                    val = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
                if name == 'ELEMENTS' and isinstance(val, dict) and isinstance(node.value, ast.Dict):
                    elements = val
                    # 拿每个 key node 的行号 —— literal_eval 后值已是 python 对象，但 node.value.keys 还在 AST 上
                    for key_node in node.value.keys:
                        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                            elements_keys_by_line[key_node.lineno] = key_node.value
                elif name == 'VARS' and isinstance(val, dict):
                    pvars = val
    except SyntaxError:
        pass

    # 用 tokenize 收集所有注释行 lineno → 注释文本（去掉前导 # 与一个紧邻空格）
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

    # 对 ELEMENTS dict 里每个 key：向上扫连续的 `#` 注释行（不能被代码行/空行截断），
    # 倒序合并成 doc；跳过 ELEMENTS 模块级 meta（`# page:` 等）—— 它们行号在 ELEMENTS 之前。
    code_lines = content.split('\n')
    for key_line, key_name in elements_keys_by_line.items():
        doc_parts: list[str] = []
        L = key_line - 1
        while L >= 1:
            if L in comments_by_line:
                doc_parts.append(comments_by_line[L])
                L -= 1
                continue
            # 整行只剩空白？空行截断，停止收集。
            raw = code_lines[L - 1] if L - 1 < len(code_lines) else ''
            if raw.strip() == '':
                break
            # 非注释、非空行 → 已抵达上一个元素 / 代码，停止。
            break
        if doc_parts:
            doc_parts.reverse()
            docs[key_name] = '\n'.join(doc_parts).rstrip()

    return {'meta': meta, 'elements': elements, 'docs': docs, 'vars': pvars}


def _render_pom_py(page: str, desc: str, triggers: str, elements: dict, docs: dict | None = None) -> str:
    lines = ['# -*- coding: utf-8 -*-', '# kind: pom', f'# page: {page}']
    if desc:
        lines.append(f'# desc: {desc}')
    if triggers:
        lines.append(f'# triggers: {triggers}')
    lines += ['', 'ELEMENTS = {']
    docs = docs or {}
    for k, v in elements.items():
        doc = (docs.get(k) or '').strip()
        if doc:
            for dl in doc.split('\n'):
                lines.append(f'    # {dl}'.rstrip())
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
    (target / 'testcases').mkdir(parents=True, exist_ok=True)
    (target / '.claude' / 'skills' / 'ha4t-case-writer').mkdir(parents=True, exist_ok=True)

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

    skill_src = Path(__file__).parent.parent / 'skills' / 'ha4t-case-writer' / 'SKILL.md'
    if skill_src.exists():
        _put(
            '.claude/skills/ha4t-case-writer/SKILL.md',
            skill_src.read_text(encoding='utf-8'),
        )

    _put(
        'conftest.py',
        '# -*- coding: utf-8 -*-\n'
        'import os\n'
        'import sys\n'
        'from ha4t.config import global_config\n'
        '\n'
        '# 工作区根入 sys.path —— 用例在 testcases/ 下仍可 `from pom import ...`\n'
        '_WS_ROOT = os.path.dirname(os.path.abspath(__file__))\n'
        'if _WS_ROOT not in sys.path:\n'
        '    sys.path.insert(0, _WS_ROOT)\n'
        '\n'
        'def pytest_configure(config):\n'
        '    global_config.current_path = os.path.join(_WS_ROOT, "images")\n',
    )

    _put(
        'pyproject.toml',
        '[project]\n'
        'name = "ha4t-cases"\n'
        'version = "0.1.0"\n'
        'description = "HA4T automation test cases workspace"\n'
        'requires-python = ">=3.10"\n'
        'dependencies = [\n'
        '    "ha4t",\n'
        ']\n'
        '\n'
        '[tool.pytest.ini_options]\n'
        'testpaths = ["testcases"]\n',
    )

    _put(
        'README.md',
        '# HA4T 用例工作区\n'
        '\n'
        '本目录由 HA4T 编辑器初始化，作为测试用例的独立工程；HA4T 作为依赖库使用。\n'
        '\n'
        '## 安装依赖\n'
        '```\n'
        'uv sync          # 或：pip install -U ha4t\n'
        '```\n'
        '\n'
        '## 目录\n'
        '- `pom/`         Page Object 元素库（编辑器「POM 采集」维护，勿手改 `__init__.py`）\n'
        '- `images/`      模板图片（`dev.click(image="x.png")` 按裸名解析到此目录）\n'
        '- `screenshots/` POM 图像元素裁剪源\n'
        '- `testcases/`   测试用例（.py，编辑器新建用例落在此目录）\n'
        '\n'
        '## 用例写法\n'
        '```python\n'
        'from ha4t import connect\n'
        'from pom import 登录页, VARS          # 只 import 用到的 page + 全局 VARS\n'
        '\n'
        'LOCAL_VARS = {"username": "tester"}   # 本用例特有常量（编辑器自动识别渲染）\n'
        '\n'
        'dev = connect(platform="android", device_serial="")\n'
        'dev.start_app(VARS["package"])\n'
        'dev.click(**登录页.ELEMENTS["登录按钮"])\n'
        '```\n'
        '- 全局常量 → POM 编辑器「全局 VARS」（写入 `pom/_meta.py`，代码 `VARS["key"]`）\n'
        '- 用例常量 → 顶层 `LOCAL_VARS = {...}`（代码 `LOCAL_VARS["key"]`）\n'
        '\n'
        '详见 `.claude/skills/ha4t-case-writer/SKILL.md`。\n',
    )

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
        _render_pom_py(req.page, req.desc, req.triggers, req.elements, req.docs),
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


@router.post("/pom/install-skill", response_model=ApiResponse)
def pom_install_skill():
    if TASKS_DIR is None:
        return _no_ws()
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
            run_file.unlink(missing_ok=True)
        except Exception:
            pass
    await ws.close()


ALLURE_REPORTS_DIR = Path.home() / "Documents" / "HA4T" / "allure-reports"


@router.post("/tasks/{filename:path}/run-allure")
async def run_task_allure(filename: str):
    """Run task via pytest + Allure, return report URL.

    用例直接在工作区根运行：`from pom import ...`、`include(...)`、
    `dev.click(image="x.png")` 全部按工作区相对路径解析。图片基准由工作区
    `conftest.py`（pytest_configure 设 ``global_config.current_path``）负责。
    """
    if TASKS_DIR is None:
        return _no_ws()
    task_path = CASES_DIR / filename
    if not task_path.exists():
        return ApiResponse.doError(f"File not found: {filename}")

    # PYTHONPATH：工作区根（pom 导入）+ 项目根（开发态 ha4t 源码树场景）。
    project_root = Path(__file__).parent.parent.parent
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "").split(os.pathsep) if env.get("PYTHONPATH") else []
    for p in [str(TASKS_DIR), str(project_root), str(project_root.parent)]:
        if p not in existing:
            existing.insert(0, p)
    env["PYTHONPATH"] = os.pathsep.join(existing)

    result_dir = TASKS_DIR / "allure-results"
    report_dir = TASKS_DIR / "allure-report"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(task_path),
             "--alluredir", str(result_dir), "--clean-alluredir",
             "-v", "--tb=short"],
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
