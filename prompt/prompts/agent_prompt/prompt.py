from pathlib import Path

from prompt.prompt_register import register_prompt

PROMPT_DIR = Path(__file__).parent


# agent自身身份/职责设定，读取agents/{agent_name}_agent.md
@register_prompt(prompt_name='agent_prompt',order=40)
def build(agent)->str:
    agent_prompt_file = PROMPT_DIR/'agents'/f'{agent.agent_name}_agent.md'
    if not agent_prompt_file.exists():
        return ''
    content = agent_prompt_file.read_text(encoding='utf-8').strip()
    return content
