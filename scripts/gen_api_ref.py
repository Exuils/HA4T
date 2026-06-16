"""从 HA4T 源码 docstring 自动生成完整的 API_REFERENCE.md。"""
import ast, os

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SOURCES = [
    ('交互操作', 'ha4t/device/interaction.py', 'InteractionMixin'),
    ('查询与断言', 'ha4t/device/queries.py', 'QueryMixin'),
    ('应用管理', 'ha4t/device/apps.py', 'AppMixin'),
    ('文件操作', 'ha4t/device/files.py', 'FileMixin'),
    ('工具函数', 'ha4t/__init__.py', None),
    ('Selector 类', 'ha4t/selector.py', 'Selector'),
    ('异常定义', 'ha4t/exceptions.py', None),
]


def extract_methods(tree, class_name):
    methods = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and not item.name.startswith('_'):
                ds = ast.get_docstring(item) or ''
                sig = _build_sig(item)
                ret = _build_return(item)
                methods.append((sig, ds, ret))
    return methods


def extract_functions(tree):
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
            ds = ast.get_docstring(node) or ''
            sig = _build_sig(node)
            ret = _build_return(node)
            funcs.append((sig, ds, ret))
    return funcs


def _build_sig(node):
    name = node.name
    args = []
    for arg in node.args.args:
        if arg.arg == 'self':
            continue
        txt = arg.arg
        if arg.annotation:
            txt += ': ' + ast.unparse(arg.annotation)
        args.append(txt)
    defaults = node.args.defaults
    offset = len(node.args.args) - len(defaults)
    for i, d in enumerate(defaults):
        idx = offset + i
        if 0 <= idx < len(args):
            try:
                val = ast.literal_eval(d)
                base = args[idx].split(':')[0]
                args[idx] = base + '=' + repr(val)
            except Exception:
                pass
    # *args / **kwargs
    if node.args.vararg:
        args.append('*' + node.args.vararg.arg)
        if node.args.vararg.annotation:
            args[-1] += ': ' + ast.unparse(node.args.vararg.annotation)
    if node.args.kwarg:
        args.append('**' + node.args.kwarg.arg)
        if node.args.kwarg.annotation:
            args[-1] += ': ' + ast.unparse(node.args.kwarg.annotation)
    return name + '(' + ', '.join(args) + ')'


def _build_return(node):
    if node.returns:
        try:
            return ast.unparse(node.returns)
        except Exception:
            pass
    return ''


def _format_doc(name, sig, ds, ret):
    lines = []
    lines.append('### `' + sig + '`')
    if ret:
        lines.append('')
        lines.append('→ `' + ret + '`')
    if not ds:
        lines.append('')
        return '\n'.join(lines)

    parts = ds.split('\n\n')
    # First paragraph = summary
    summary = parts[0].strip()
    if summary:
        lines.append('')
        lines.append(summary)

    # Parse remaining paragraphs
    rest = parts[1:]
    in_args = False
    in_returns = False
    in_raises = False
    for para in rest:
        para = para.strip()
        if not para:
            continue
        # Check section headers
        low = para.lower()
        if low.startswith('args:') or low.startswith('arguments:') or low.startswith('parameters:'):
            in_args = True
            in_returns = False
            in_raises = False
            lines.append('')
            lines.append('| 参数 | 类型 | 说明 |')
            lines.append('|------|------|------|')
            # Parse the lines after "Args:"
            param_lines = para.split('\n')[1:]
            for pl in param_lines:
                pl = pl.strip()
                if not pl:
                    continue
                # Split on first ': ' to get name+type and description
                if pl.startswith('- '):
                    pl = pl[2:]
                if ': ' in pl:
                    first, desc = pl.split(': ', 1)
                    # first could be "name (Type)" or "name"
                    if '(' in first and first.endswith(')'):
                        pname = first[:first.index('(')].strip()
                        ptype = first[first.index('(')+1:-1].strip()
                    else:
                        pname = first.strip()
                        ptype = ''
                    lines.append('| `' + pname + '` | `' + ptype + '` | ' + desc + ' |')
                else:
                    lines.append('| ' + pl + ' | | |')
            continue
        elif low.startswith('returns:') or low.startswith('yields:'):
            in_args = False
            in_returns = True
            in_raises = False
            lines.append('')
            lines.append('**返回**：')
            ret_desc = para.split('\n', 1)[1].strip() if '\n' in para else ''
            if ret_desc:
                lines.append(ret_desc)
            continue
        elif low.startswith('raises:') or low.startswith('raise:'):
            in_args = False
            in_returns = False
            in_raises = True
            lines.append('')
            lines.append('**异常**：')
            raise_lines = para.split('\n')[1:]
            for rl in raise_lines:
                rl = rl.strip()
                if rl:
                    lines.append('- ' + rl)
            continue
        elif low.startswith('note:'):
            lines.append('')
            lines.append('> **注意**：' + para[5:].strip())
            continue
        elif low.startswith('example') or low.startswith('examples:'):
            lines.append('')
            lines.append('**示例**：')
            ex_lines = para.split('\n')[1:]
            in_code = False
            for el in ex_lines:
                el_stripped = el.strip()
                if el_stripped.startswith('>>> ') or el_stripped.startswith('```'):
                    in_code = not in_code
                lines.append(el)
            continue
        elif low.startswith('warning:'):
            lines.append('')
            lines.append('> ⚠ **警告**：' + para[5:].strip())
            continue
        else:
            # Regular paragraph
            lines.append('')
            lines.append(para)
            in_args = in_returns = in_raises = False

    lines.append('')
    return '\n'.join(lines)


def run():
    out = []
    out.append('# HA4T API 参考')
    out.append('')
    out.append('自动从源码 docstring 生成。覆盖 Device 全部接口、工具函数与异常定义。')
    out.append('')
    out.append('## 目录')
    out.append('')
    for title, _, _ in SOURCES:
        out.append('- [' + title + '](#' + title + ')')
    out.append('')

    for title, relpath, class_name in SOURCES:
        abspath = os.path.join(PROJECT, relpath)
        if not os.path.exists(abspath):
            continue
        with open(abspath, 'r', encoding='utf-8') as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                continue

        items = []
        if class_name:
            items = extract_methods(tree, class_name)
        else:
            items = extract_functions(tree)
            if not items:
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        items = extract_methods(tree, node.name)
                        if items:
                            class_name = node.name
                        break

        if not items:
            continue

        out.append('<a name=\\"' + title + '\\"></a>')
        out.append('## ' + title)
        out.append('')
        if class_name:
            out.append('来源：`' + class_name + '` @ `' + relpath + '`')
        else:
            out.append('来源：`' + relpath + '`')
        out.append('')

        for sig, ds, ret in items:
            out.append(_format_doc(title, sig, ds, ret))
        out.append('---')
        out.append('')

    output_path = os.path.join(PROJECT, 'ha4t/editor/skills/API_REFERENCE.md')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        # write without the HTML escaped quotes
        text = '\n'.join(out)
        text = text.replace('<a name=\\"', '<a name=\"').replace('\\"></a>', '\"></a>')
        f.write(text)
    total = sum(1 for l in out if l.startswith('### '))
    print('Generated %s (%d methods)' % (output_path, total))


if __name__ == '__main__':
    run()
