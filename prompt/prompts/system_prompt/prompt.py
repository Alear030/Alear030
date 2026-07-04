from pathlib import Path

from prompt.prompt_register import register_prompt

PROMPT_DIR = Path(__file__).parent


# 底层核心架构prompt，仅main agent注入
@register_prompt(prompt_name='system_prompt',order=0,condition=lambda agent: agent.agent_name=='main')
def build(agent)->str:
    system_prompt_file = PROMPT_DIR/'system_prompt.md'
    if not system_prompt_file.exists():
        return ''
    content = system_prompt_file.read_text(encoding='utf-8').strip()
    return content
