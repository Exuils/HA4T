# -*- coding: utf-8 -*-
"""
HA4T pytest 集成 conftest
自动将 # --step-- 任务文件转换为 pytested 用例，集成 Allure 报告。

工作方式：
1. pytest_collect_file hook 检测 .py 文件中是否有 # --step-- 标记
2. StepFile 自定义收集器将每步转为 test_step_N() 函数
3. 自动剥离 connect() 改为 session-scoped fixture
4. 提取头部元数据 (tag/feature/severity/rerun) 作为 Allure 装饰器
"""
import ast
import os
import re
import sys
import types
from pathlib import Path

import allure
import pytest


def _find_project_root():
    """向上查找 ha4t 项目根目录"""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / "ha4t" / "api.py").exists():
            return parent
    return None


def _extract_meta(content: str) -> dict:
    """从文件头注释提取元数据"""
    meta = {
        'name': '', 'desc': '', 'platform': 'android', 'project_id': '',
        'tag': '', 'feature': '', 'story': '', 'severity': 'normal', 'rerun': 0,
    }
    for line in content.split('\n'):
        line_s = line.strip()
        if line_s.startswith('# ') and ':' in line_s:
            key_end = line_s.index(':')
            key = line_s[2:key_end].strip()
            val = line_s[key_end+1:].strip()
            if key in meta:
                if key in ('rerun',):
                    try:
                        meta[key] = int(val)
                    except ValueError:
                        pass
                else:
                    meta[key] = val
    return meta


def _split_preamble_and_steps(content: str):
    """
    将任务文件拆分为前置代码块和步骤列表。

    步骤分割规则：
    - ``# --step--`` 显式步骤标记，后续同级缩进行为步骤代码
    - 同级缩进（column 0）的可执行代码触发隐式步骤分割
    - 更深缩进（column > 0）的代码始终属于当前步骤
    - 前置代码：所有步骤之前的代码

    返回 (preamble_lines, [(remark, code), ...])
    """
    lines = content.split('\n')
    preamble = []
    steps = []
    buf = []
    in_step = False
    remark = ''
    step_marker = '# --step--'

    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        if not stripped:
            # 空行保留在当前步骤 / 前置代码，不触发隐式分割
            if in_step:
                buf.append('')
            else:
                preamble.append('')
            continue

        if stripped.startswith(step_marker):
            if in_step and buf:
                steps.append((remark, '\n'.join(buf).strip()))
                buf = []
                remark = ''
            in_step = True
            remark = stripped[len(step_marker):].strip()
            continue

        if stripped.startswith('#'):
            if not in_step:
                preamble.append(line)
            continue

        if not in_step:
            preamble.append(line)
            continue

        if indent == 0:
            if buf:
                steps.append((remark, '\n'.join(buf).strip()))
                buf = []
                remark = ''
        buf.append(line)

    if in_step and buf:
        steps.append((remark, '\n'.join(buf).strip()))

    return preamble, steps


def _strip_connect_call(preamble_lines):
    """
    从前置代码中移除 connect() 调用行（含赋值形式 dev = connect(...)）。
    返回 (filtered_preamble, connect_kwargs)
    connect() 改为由 session fixture 执行。
    """
    filtered = []
    connect_kwargs = {}
    for line in preamble_lines:
        stripped = line.strip()
        # 裸调用形式：connect(...)
        if stripped.startswith('connect('):
            try:
                start = stripped.index('(')
                end = stripped.rindex(')')
                args_str = stripped[start+1:end]
                for part in args_str.split(','):
                    part = part.strip()
                    if '=' in part:
                        k, v = part.split('=', 1)
                        connect_kwargs[k.strip()] = v.strip().strip('"').strip("'")
            except ValueError:
                pass
            continue
        # 赋值形式：xxx = connect(...)
        m = re.match(r'^(\w+)\s*=\s*connect\((.*)\)\s*$', stripped)
        if m:
            try:
                args_str = m.group(2)
                for part in args_str.split(','):
                    part = part.strip()
                    if '=' in part:
                        k, v = part.split('=', 1)
                        connect_kwargs[k.strip()] = v.strip().strip('"').strip("'")
            except ValueError:
                pass
            continue
        filtered.append(line)
    return filtered, connect_kwargs


def pytest_collect_file(file_path, parent):
    """检测 # --step-- 文件，返回 StepFile 收集器"""
    if file_path.suffix != '.py':
        return None
    try:
        content = file_path.read_text('utf-8', errors='ignore')
    except Exception:
        return None
    if '# --step--' not in content:
        return None
    return StepFile.from_parent(parent, path=file_path)


class StepFile(pytest.Module):
    """将 # --step-- 文件的每一步收集为一个 pytest 测试函数"""

    def collect(self):
        content = self.path.read_text('utf-8', errors='ignore')
        meta = _extract_meta(content)
        preamble_lines, steps = _split_preamble_and_steps(content)

        # 剥离 connect() 改为使用 fixture
        preamble_lines, connect_kwargs = _strip_connect_call(preamble_lines)
        preamble_code = '\n'.join(preamble_lines)

        # 创建模块，执行前置代码（import 等）
        module_name = self.path.stem
        mod = types.ModuleType(module_name)
        mod.__file__ = str(self.path)

        # 获取项目根并加入 sys.path
        project_root = _find_project_root()
        if project_root and str(project_root) not in sys.path:
            mod.__dict__['__project_root__'] = str(project_root)

        try:
            exec(compile(preamble_code, str(self.path), 'exec'), mod.__dict__)
        except Exception as e:
            raise Exception(f"Failed to compile {self.path.name}: {e}") from e

        # 为每一步生成 test function
        for i, (remark, code) in enumerate(steps, 1):
            yield self._make_test_fn(i, remark, code, meta, mod, connect_kwargs)

    def _make_test_fn(self, idx, remark, code, meta, mod, connect_kwargs):
        """生成单个 test_step_N 函数"""
        fn_name = f'test_step_{idx}'
        test_title = remark or f'Step {idx}: {code[:60]}'

        # 使用 allure.dynamic 在函数体内设置元数据
        def test_fn(device_connect):
            # Allure 动态元数据
            if meta.get('feature'):
                allure.dynamic.feature(meta['feature'])
            if meta.get('story'):
                allure.dynamic.story(meta['story'])
            if meta.get('severity') and meta['severity'] != 'normal':
                allure.dynamic.severity(meta['severity'])
            if meta.get('tag'):
                for t in meta['tag'].split(','):
                    allure.dynamic.tag(t.strip())
            if remark:
                allure.dynamic.title(f"Step {idx}: {remark}")

            # 执行步骤代码
            # 注入 session fixture 的 Device 实例，供步骤体中的 dev.xxx() 使用
            mod.__dict__['dev'] = device_connect
            compiled = compile(code, f'{self.path.stem}:{fn_name}', 'exec')
            exec(compiled, mod.__dict__)

        # 应用 pytest 标记
        marks = []
        if meta.get('tag'):
            for t in meta['tag'].split(','):
                marks.append(getattr(pytest.mark, t.strip(), None) or pytest.mark.custom_tag(t.strip()))
        if meta.get('rerun', 0) > 0:
            try:
                from pytest_rerunfailures import reruns
                marks.append(pytest.mark.flaky(reruns=meta['rerun']))
            except ImportError:
                pass

        test_fn.__name__ = fn_name
        test_fn.__doc__ = f"Step {idx}: {test_title}"
        if marks:
            test_fn = pytest.mark.parametrize('_', [None])(test_fn)  # dummy
            for m in marks:
                test_fn = m(test_fn)
        # 设置 allure 标题
        test_fn = allure.title(test_title)(test_fn)
        test_fn = allure.description(code)(test_fn)

        return pytest.Function.from_parent(self, name=fn_name, callobj=test_fn)


# ── Session-scoped fixtures ──


@pytest.fixture(scope="session")
def device_connect(request):
    """
    设备连接 fixture (session 级别)
    所有测试用例共享同一个设备连接，返回 Device 实例。
    """
    platform = request.config.getoption("--ha4t-platform", default="android")
    serial = request.config.getoption("--ha4t-serial", default=None)

    from ha4t import connect
    dev = connect(platform=platform, device_serial=serial)
    return dev


def pytest_addoption(parser):
    """添加自定义命令行参数"""
    parser.addoption(
        "--ha4t-platform", action="store", default="android",
        help="HA4T platform: android / ios / harmony"
    )
    parser.addoption(
        "--ha4t-serial", action="store", default=None,
        help="HA4T device serial number"
    )
