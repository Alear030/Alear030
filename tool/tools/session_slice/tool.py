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


@register_tool(tool_name='session_slice',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='memory_tool')
def session_slice(session_id:str,start_round:int,end_round:int,include_tool_messages:bool=False,**kwargs)->str:

    # 得到对应的session detail json 数据
    session_file = SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json'
    if not session_file.exists():
        return json.dumps({"error":f"session {session_id} not found"},ensure_ascii=False)
    session_json = _json_read(file_path=session_file)

    # 防护空 session 数据
    if not session_json:
        return json.dumps({"error":f"session {session_id} not found"},ensure_ascii=False)

    # 默认保持原来的纯对话视图；任务流程核对可显式保留 tool_calls/tool_result。
    session_slice = []
    for msg in session_json['session_messages']:
        if msg['message_round']>=start_round and msg['message_round']<=end_round:
            if include_tool_messages or msg['message_role'] not in ('tool_calls','tool_result'):
                session_slice.append(msg)

    return json.dumps(session_slice,ensure_ascii=False)