from pathlib import Path

from prompt import prompt

PROMPT_DIR = Path(__file__).parent


# attachment 运行时提示的协议声明（notification/interrupt 处理约定）
# condition 覆盖的是「会收到 interrupt、需要据此改变行动」的 agent,不是所有 attachment target:
# 只收 notification 的 agent 靠渲染时那句「仅供知晓」就够,不必背这份 interrupt 处置规范
@prompt.register_prompt(prompt_name='attachment_prompt',order=5,condition=lambda agent: agent.agent_name in ('main','plan'),type="static")
def build(agent)->str:
    attachment_prompt_file = PROMPT_DIR/'attachment_prompt.md'
    if not attachment_prompt_file.exists():
        return ''
    content = attachment_prompt_file.read_text(encoding='utf-8').strip()
    return content