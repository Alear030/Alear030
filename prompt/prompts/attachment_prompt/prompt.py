from pathlib import Path

from prompt import prompt

PROMPT_DIR = Path(__file__).parent


# attachment 运行时提示的协议声明（notification/interrupt 处理约定）
# condition 只给 main:投递管线只有主 Loop 挂着,别的 agent 收不到 attachment,背这份处置规范是空转
@prompt.register_prompt(prompt_name='attachment_prompt',order=5,condition=lambda agent: agent.agent_name=='main',type="static")
def build(agent)->str:
    attachment_prompt_file = PROMPT_DIR/'attachment_prompt.md'
    if not attachment_prompt_file.exists():
        return ''
    content = attachment_prompt_file.read_text(encoding='utf-8').strip()
    return content