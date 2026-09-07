import importlib

from pathlib import Path


from .hook_core import hooks,Hooks


__all__ = ['hooks']

# 目录名不能叫 hooks:导入子包会把它绑到 hook.hooks 上,顶掉上面导入的同名全局实例
hook_point_dir = Path(__file__).parent / 'hook_point'
root = Path(__file__).parent.parent          # 项目根,用于把文件路径算成模块点路径
for py in sorted(hook_point_dir.rglob('hook.py')):
    rel = py.relative_to(root)               # 例:hook/hook_point/after_loop/memory_pipeline/hook.py
    # 保留原逻辑的禁用语义:路径中任一段以 _ 开头则跳过(如 __pycache__、_ 开头的实验目录)
    if any(part.startswith('_') for part in rel.parts):
        continue
    importlib.import_module('.'.join(rel.with_suffix('').parts))   # → hook.hook_point.after_loop.memory_pipeline.hook