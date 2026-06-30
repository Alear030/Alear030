import json

from pathlib import Path


from tool.tool_core import register_tool
from config import SESSION_MEMORTY_DETAIL_PATH
from session import _json_read


# 设置tool的基本描述和prompt信息
tool_desc = '用于读取特定id历史session的某一个slice片段对话原文'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else None
else:
    tool_prompt = None


@register_tool(tool_name='session_slice',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='basic_tool')
def session_slice(session_id:str,start_round:int,end_round:int)->str:

    # 得到对应的session detail json 数据
    session_json = _json_read(file_path=SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json')

    # 防护json文件不存在问题
    if not session_json:
        return json.dumps({"error":f"session {session_id} not found"},ensure_ascii=False)
    
    # 得到对应round的msg
    session_slice = []
    for msg in session_json['session_messages']:
        if msg['message_round']>=start_round and msg['message_round']<=end_round:
            if msg['message_role']!='tool_calls' and msg['message_role']!='tool_result':
                session_slice.append(msg)
    
    return json.dumps(session_slice,ensure_ascii=False)