import importlib

from pathlib import Path


from .hook_core import hooks


__all__ = ['hooks']

hooks_dir = Path(__file__).parent/'hooks'
for d in sorted(hooks_dir.iterdir()):
    if d.is_dir() and not d.name.startswith('_') and not d.name.startswith('__'):
        importlib.import_module(f'hook.hooks.{d.name}')