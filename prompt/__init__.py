import importlib

from pathlib import Path

from .prompt_register import register_prompt,build_prompt
from .prompt_core import Prompt


__all__ = ['register_prompt','build_prompt','Prompt']

prompts_dir = Path(__file__).parent/'prompts'
for d in sorted(prompts_dir.iterdir()):
    if d.is_dir() and not d.name.startswith('_'):
        importlib.import_module(f'prompt.prompts.{d.name}.prompt')

# done(@claude): memory_prompt 的 order 已定为 35
# system_prompt:0 tool_prompt:10 skill_prompt:20 session_recent:30 agent_prompt:40 basic_prompt:50 memory_prompt:35