import importlib

from pathlib import Path

from ..tui_widgets_core import TuiWidgets,widget_register

__all__ = ['TuiWidgets','widget_register']

# 拉起所有 widget 子包，触发各 @widget_register 装饰器注册
for _d in sorted(Path(__file__).parent.iterdir()):
    if _d.is_dir() and not _d.name.startswith('_') and not _d.name.startswith('__'):
        importlib.import_module(f'{__name__}.{_d.name}')
