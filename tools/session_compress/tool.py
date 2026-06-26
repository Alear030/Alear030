from pathlib import Path

from tools._tool_register import register_tool


tool_desc = '压缩当前对话信息'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else ''

@register_tool(tool_name='session_compress',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,role=['main'])
def session_summary(session_id:str):
    from session import _session_summary,_session_slice,_message_list_reform
    _session_slice(session_id=session_id)
    _session_summary(session_id=session_id)
    _message_list_reform(session_id=session_id)
    return 'session_summary completed...'