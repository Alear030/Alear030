import json

from pathlib import Path

from prompt.prompt_register import register_prompt
from config import SESSION_MEMORTY_DETAIL_PATH


# 最近3轮历史session的切片摘要，用于跨session的短期记忆，仅main agent注入
@register_prompt(prompt_name='session_recent',order=30,condition=lambda agent: agent.agent_name=='main',enabled=False)
def build(agent)->str:
    session_recent_ids = sorted(file.stem for file in Path(SESSION_MEMORTY_DETAIL_PATH).glob("*.json"))[-3:]
    session_prompt = f"# 最近{len(session_recent_ids)}轮对话信息" + '\n\n' if session_recent_ids else ''

    for id in session_recent_ids:
        session_prompt += f'## session{id}对话内容摘要' + '\n\n'
        session_json = json.loads((SESSION_MEMORTY_DETAIL_PATH/f'{id}.json').read_text(encoding='utf-8'))
        session_slices = session_json['session_slice']
        for slice in session_slices:
            session_prompt += f'片段所属session_id:{id}  片段主题:{slice["slice_anchor"]["topic"]} 片段详情:{slice["slice_anchor"]["summary_detail"]} 片段开始round:{slice["start_round"]} 片段结束round:{slice["end_round"]}' + '\n\n'

    return session_prompt
