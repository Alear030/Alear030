import json

from datetime import datetime
from pathlib import Path


from core.rich_output import rich_print
from config import SESSION_MEMORTY_DETAIL_PATH
from agent.agent_core import main_agent


def _session_id_generate()->str:
    time_now = datetime.now()
    time_part = time_now.strftime('%Y%m%d_%H%M%S')
    return time_part


def _json_read(file_path:Path):
    if file_path.is_dir():
        rich_print(message='error:path is dir',type='system_error')
        return
    file_text = file_path.read_text(encoding='utf-8')

    if not file_text.strip():
        return []
    
    file_json = json.loads(file_text)
    return file_json


def _json_write(content:str=None,file_path:Path=None):
    if file_path.is_dir():
        print('system error target file is dir')
        return
    
    if not content:
        print('null content is none can not write in a json file')
        return
    
    file_path.write_text(
        json.dumps(content,ensure_ascii=False,indent=2),
        encoding='utf-8'
    )


def _get_sessison_detail_ids()->list:
    session_detail_ids = sorted(file.stem for file in Path(SESSION_MEMORTY_DETAIL_PATH).glob("*.json"))
    return session_detail_ids


def _get_session_detail_slice(session_id:str=None)->list[dict]:
    if not session_id:
        return None
    session_json = _json_read(file_path=SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json')
    return session_json['session_slice']


def _get_unslice_content(session_id:str,has_tool:bool)->list[dict]:
    session_json = _json_read(file_path=SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json')
    session_unslice_content = []
    for msg in session_json['session_messages']:
        if msg['message_round'] > session_json['unslice_pointer']:
            if has_tool:
                session_unslice_content.append(msg)
            else:
                if  msg['message_role'] != 'tool_calls' and msg['message_role'] != 'tool_result':
                    session_unslice_content.append(msg)
    return session_unslice_content


def _session_memory_recently(current_sesssion_id:str=None)->list:
    session_detail_ids = _get_sessison_detail_ids()
    if current_sesssion_id in session_detail_ids:
        session_detail_ids.remove(current_sesssion_id)

    session_detail_ids = session_detail_ids[:3]
    session_memory_recently = []

    for session_detail_id in session_detail_ids:
        session_detail_json = _json_read(file_path=SESSION_MEMORTY_DETAIL_PATH/f'{session_detail_id}.json')
        session_slice = session_detail_json['session_slice']

        if session_slice:
            for slice in session_slice:
                if slice['summary_detail']:
                    session_memory_recently.append({
                        "session_id":session_detail_json['session_id'],
                        "start_round":slice['start_round'],
                        "end_round":slice['end_round'],
                        "topic":slice['topic'],
                        "key_words":slice['key_words'],
                        "summary_detail":slice['summary_detail']
                    })
                else:
                    session_memory_recently.append({
                        "session_id":session_detail_json['session_id'],
                        "start_round":slice['start_round'],
                        "end_round":slice['end_round'],
                        "slice_reference":slice['slice_reference']
                    })
    return session_memory_recently


def session_init()->str:

    session_id_time = _session_id_generate()
    if not SESSION_MEMORTY_DETAIL_PATH.exists():
        rich_print(message='error:session memory file does not exist',type='system_error')
        return None
    
    session_detail_init = {
        "session_id": session_id_time,
        "unslice_pointer":0,
        "session_slice":[],
        "session_messages": []
    }
    _json_write(content=session_detail_init,file_path=SESSION_MEMORTY_DETAIL_PATH/f'{session_id_time}.json')

    rich_print(message=f'session {session_id_time} has been inited',type='system_message')

    # main_agent.message_list[0]['content']+=f'\n\n#历史近期三轮对话摘要\n\n以下是最近对话的摘要，请注意：摘要中的「用户」即 Alear030 大人，摘要中的「助手」即你自己.\n\n{str(_session_memory_recently(current_sesssion_id=session_id_time))}'
    main_agent.message_list[0]['content'] += f'\n\n #系统提示:当前时间是:{session_id_time}当前session_id是:{session_id_time}'
    
    return session_id_time 


def session_message_insert(session_id:str,role:str='',message:str='',session_round:int=None):
    session_file_path = Path(__file__).parent/f'session_detail/{session_id}.json'
    if not session_file_path:
        rich_print(message='session file does not exist',type='system_error')
        return
    
    session_json = _json_read(file_path=session_file_path)
    session_json['session_messages'].append({
        "message_round":session_round,
        "message_role":role,
        "message_content":message
    })

    _json_write(content=session_json,file_path=session_file_path)