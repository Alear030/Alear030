from pathlib import Path

from prompt import prompt
from tool import get_tool_brief

PROMPT_DIR = Path(__file__).parent


# 工具使用原则 + agent自身持有的每个工具的名称和简短说明（完整tool_prompt已在function-calling schema中传给模型，这里不重复）
# 归 static 的前提:get_tool_brief 已排除运行时接入的 mcp_tool,内容只由 import 期的静态注册表决定
@prompt.register_prompt(prompt_name='tool_prompt',order=10,condition=lambda agent:agent.tool_autho,type="static")
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
