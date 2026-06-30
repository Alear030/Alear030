import json

from datetime import datetime
from pathlib import Path


from config import ROOT_DIRECTORY,SESSION_MEMORTY_DETAIL_PATH
from rich_output import rich_print

def _get_agent_prompt(type:str,agent_name:str)->str:
    agent_memory = ROOT_DIRECTORY/f'agent/agent_prompt/{agent_name}_agent.md'
    if not agent_memory.exists():
        rich_print(message=f'{agent_name} agent_memory dose not exist...',type='system_error')
        return ''
    else:
        rich_print(message=f'{agent_name} agent_memory has been loaded...',type='system_message')
        agent_memory_content = agent_memory.read_text(encoding='utf-8')
        return agent_memory_content.strip() if agent_memory_content.strip() else ''
    
    
def _get_system_prompt(type:str,agent_name:str)->str:
    system_prompt_file = ROOT_DIRECTORY/'agent/agent_prompt/system_prompt.md'
    system_prompt_content = system_prompt_file.read_text(encoding='utf-8') if system_prompt_file.exists() else None
    
    if not system_prompt_content:
        rich_print(message=f'{agent_name} system_prompt does not exist...',type='system_error')
        return ''
    
    system_prompt_content_detail = system_prompt_content.strip() if system_prompt_content.strip() else None
    if system_prompt_content_detail:
        rich_print(message=f'{agent_name} system_prompt has been loaded...',type='system_message')
        return system_prompt_content_detail


def _get_time_now():
    time_now = datetime.now()
    return f"## 当前时间为：{time_now}"


def _get_recently_session_slice():
    # 找到最近三轮对话id
    session_detail_ids = sorted(file.stem for file in Path(SESSION_MEMORTY_DETAIL_PATH).glob("*.json"))[-3:]
    
    # 得到最近三轮对话全部slice同时注入session id
    slices = []
    for id in session_detail_ids:
        session_json = json.loads((SESSION_MEMORTY_DETAIL_PATH/f'{id}.json').read_text(encoding='utf-8'))
        session_slices = session_json['session_slice']
        for slice in session_slices:
            slices.append({
                "session_id":id,
                "topic":slice["topic"],
                "start_round":slice["start_round"],
                "end_round":slice["end_round"],
                "key_words":slice["key_words"],
                "summary_detail":slice["summary_detail"]
            })
    return json.dumps(slices,ensure_ascii=False)


def prompt_structor(type:str,agent_name:str)->str:

    # 得到当前的时间
    time_now = datetime.now()

    # 得到三种prompt
    system_prompt = _get_system_prompt(type=type,agent_name=agent_name) if agent_name == 'main' else ''
    agent_prompt = _get_agent_prompt(type=type,agent_name=agent_name)
    recent_slices = _get_recently_session_slice()if agent_name=='main' else ''
    return system_prompt + '\n\n' + agent_prompt + f'\n\n# 系统提示 \n\n## 当前时间为{_get_time_now()} \n\n ## 最近三轮对话摘要内容为:\n\n{recent_slices}'