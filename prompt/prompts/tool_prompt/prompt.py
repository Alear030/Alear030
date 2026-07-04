from pathlib import Path

from prompt.prompt_register import register_prompt
from tool import get_tool_brief

PROMPT_DIR = Path(__file__).parent


# 工具使用原则 + agent自身持有的每个工具的名称和简短说明（完整tool_prompt已在function-calling schema中传给模型，这里不重复）
@register_prompt(prompt_name='tool_prompt',order=10)
def build(agent)->str:
    tools_prompt = ''
    tool_briefs = get_tool_brief(agent.tool_autho)
    if tool_briefs:
        tool_prompt_file = PROMPT_DIR/'tool_prompt.md'
        if tool_prompt_file.exists():
            text = tool_prompt_file.read_text(encoding='utf-8').strip()
            tools_prompt = text + '\n\n' if text else ''
        for tool in tool_briefs:
            tools_prompt += f'工具名称:{tool["name"]}  工具说明:{tool["description"]}' + '\n\n'
    return tools_prompt
