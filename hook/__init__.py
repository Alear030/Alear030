import importlib

from pathlib import Path


from .hook_core import hooks,HookManager


__all__ = ['hooks']

hooks_dir = Path(__file__).parent / 'hooks'
root = Path(__file__).parent.parent          # 项目根,用于把文件路径算成模块点路径
for py in sorted(hooks_dir.rglob('hook.py')):
    rel = py.relative_to(root)               # 例:hook/hooks/after_round/memory_pipeline/hook.py
    # 保留原逻辑的禁用语义:路径中任一段以 _ 开头则跳过(如 __pycache__、_ 开头的实验目录)
    if any(part.startswith('_') for part in rel.parts):
        continue
    importlib.import_module('.'.join(rel.with_suffix('').parts))   # → hook.hooks.after_round.memory_pipeline.hook