from pathlib import Path

from prompt.prompt_register import register_prompt

PROMPT_DIR = Path(__file__).parent


# attachment 运行时提示的协议声明（notification/interrupt 处理约定），仅main agent注入
@register_prompt(prompt_name='attachment_prompt',order=5,condition=lambda agent: agent.agent_name=='main')
def build(agent)->str:
    attachment_prompt_file = PROMPT_DIR/'attachment_prompt.md'
    if not attachment_prompt_file.exists():
        return ''
    content = attachment_prompt_file.read_text(encoding='utf-8').strip()
    return content