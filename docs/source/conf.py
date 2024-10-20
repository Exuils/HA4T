import sys
import os
import mock

# 将项目根目录添加到系统路径
sys.path.insert(0, os.path.abspath('../..'))

# 模拟未安装的模块
MOCK_MODULES = ['cv2', 'numpy', 'PIL', 'wda', 'uiautomator2', 'paddleocr', "PIL.Image"]
for mod_name in MOCK_MODULES:
    sys.modules[mod_name] = mock.MagicMock()

# 为 cv2 模块添加 __version__ 属性
sys.modules['cv2'].__version__ = '4.5.0'

# Sphinx 扩展
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.doctest',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'sphinx.ext.imgmath',
    'sphinx.ext.ifconfig',
    'sphinx.ext.viewcode',
    'sphinx.ext.autosectionlabel',
    'sphinx.ext.napoleon',
    'recommonmark',
    'sphinx_markdown_tables',
]

# 源文件后缀
source_suffix = ['.rst', '.md']

# 主文档
master_doc = 'index'

# 项目信息
project = 'HA4T'
copyright = '2024, caishilong'
author = 'caishilong'
version = u''  # 主要版本号
release = u''  # 完整版本号

# 代码高亮
pygments_style = 'sphinx'

# 显示 todo 列表
todo_include_todos = True


# 语言设置
language = 'zh_CN'

# HTML 主题
html_theme = 'sphinx_rtd_theme'

# autodoc 配置
autodoc_member_order = 'bysource'
add_module_names = False
napoleon_use_param = True
napoleon_use_rtype = True

# 如果需要支持多语言
# locale_dirs = ['locale/']
# gettext_compact = False

# Read the Docs 主题配置
html_context = {
    "display_github": True,
    "github_user": "Exuils",
    "github_repo": "HA4T",
    "github_version": "main",
    "conf_py_path": "/docs/source/",
    "current_language": "zh_CN",
    "current_version": version,
}

latex_documents = [
    (master_doc, 'HA4T.tex', u'HA4T Documentation',
     u'caishilong', 'manual'),
]

# 手册页输出配置
man_pages = [
    (master_doc, 'ha4t', u'HA4T Documentation',
     [author], 1)
]

# Texinfo 输出配置
texinfo_documents = [
    (master_doc, 'HA4T', u'HA4T Documentation',
     author, 'HA4T', 'One line description of project.',
     'Miscellaneous'),
]
