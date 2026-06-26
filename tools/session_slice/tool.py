from pathlib import Path


from tools._tool_register import register_tool
from config import SESSION_MEMORTY_DETAIL_PATH



tool_desc = '用于读取特定id历史session的某一个slice片段对话原文'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else None
else:
    tool_prompt = None


@register_tool(tool_name='session_slice',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,role=['main'])
def session_slice(session_id:str,start_round:int,end_round:int)->str:
    from session import _json_read
    session_json = _json_read(file_path=SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json')
    session_slice = []
    for msg in session_json['session_messages']:
        if msg['message_round']>=start_round and msg['message_round']<=end_round:
            if msg['message_role']!='tool_calls' and msg['message_role']!='tool_result':
                session_slice.append(msg)
    return str(session_slice)