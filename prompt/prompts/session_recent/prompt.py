import json

from pathlib import Path

from prompt import prompt
from config import SESSION_MEMORTY_DETAIL_PATH


# 最近3轮历史session的切片摘要，用于跨session的短期记忆
# 每结束一个 session 就多一份历史 JSON,内容必然跨 session 变动,故走 attachment
@prompt.register_prompt(prompt_name='session_recent',order=30,enabled=False,type="notification",target=['main'])
def build()->str:
    session_recent_ids = sorted(file.stem for file in Path(SESSION_MEMORTY_DETAIL_PATH).glob("*.json"))[-3:]
    session_prompt = f"# 最近{len(session_recent_ids)}轮对话信息" + '\n\n' if session_recent_ids else ''

    for id in session_recent_ids:
        session_prompt += f'## session{id}对话内容摘要' + '\n\n'
        session_json = json.loads((SESSION_MEMORTY_DETAIL_PATH/f'{id}.json').read_text(encoding='utf-8'))
        session_slices = session_json['session_slice']
        for slice in session_slices:
            session_prompt += f'片段所属session_id:{id}  片段主题:{slice["slice_anchor"]["topic"]} 片段详情:{slice["slice_anchor"]["summary_detail"]} 片段开始round:{slice["start_round"]} 片段结束round:{slice["end_round"]}' + '\n\n'

    return session_prompt
