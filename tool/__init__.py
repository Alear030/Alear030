import importlib

from pathlib import Path


from .tool_core import register_tool,get_tool,match_tool


__all__ = ['register_tool','get_tool','match_tool']

tools_dir = Path(__file__).parent/'tools'
for d in sorted(tools_dir.iterdir()):
    if d.is_dir() and not d.name.startswith('_') and not d.name.startswith('__'):
        importlib.import_module(f'tool.tools.{d.name}')

