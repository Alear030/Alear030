import json
import tiktoken

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed


from core import rich_print
from .session_core import _json_read,_json_write,_get_sessison_detail_ids
from config import SESSION_MEMORTY_DETAIL_PATH,MAX_SESSION_TOKEN
from agent import summary_agent,summary_agent_ai,slice_agent,slice_agent_ai,main_agent


def _get_session_messages(session_id:str=None)->dict:
    session_detail_path = SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json'
    
    if not session_detail_path.exists():
        print(f'session {session_id} dose not exist...')
        return None
    
    session_messages = json.loads(session_detail_path.read_text(encoding='utf-8'))['session_messages']

    return session_messages


def _count_tokens(session_id:str=None,model:str='gpt-4o')->int:
    session_file_path = SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json'
    session_json = _json_read(session_file_path)
    session_unslice_pointer = session_json['unslice_pointer']
    message_encoding = tiktoken.encoding_for_model(model)
    session_messages = session_json['session_messages']

    token_count_messages = []
    for msg in session_messages:
        if msg['message_round'] >= session_unslice_pointer:
            token_count_messages.append(msg)
    
    token_total = int(0)
    token_total += len(token_count_messages)
    
    for msg in token_count_messages:
        token_total+=4
        message_content = json.dumps(msg['message_content'],ensure_ascii=False)
        token_total+=len(message_encoding.encode(message_content))

    return token_total


def _session_slice(session_id:str=None):
    
    session_file_path = SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json'
    if not session_file_path.exists():
        print(f'system error:{session_id}.json does not exist...')
        return None
    
    session_json = _json_read(file_path=session_file_path)
    session_slice = session_json['session_slice']
    session_messages = session_json['session_messages'][1:]

    if session_json['unslice_pointer'] == session_messages[-1]['message_round']:  
        print('all slice already been sliced...')
        return None

    summary_session_messages = []
    for msg in session_messages:
        if msg['message_round'] > session_json['unslice_pointer'] and msg['message_role'] != 'tool_calls' and msg['message_role'] != 'tool_result':
            summary_session_messages.append(msg)

    message_list = []
    slice_agent.message_list = slice_agent.message_list[:1]
    slice_agent.message_list.append({"role":"user","content":json.dumps(summary_session_messages,ensure_ascii=False,indent=2)})
    slice_agent_rq = slice_agent_ai.chat.completions.create(messages=slice_agent.message_list,model=slice_agent.model_name).choices[0].message.content
    slice_agent_json = json.loads(slice_agent_rq)

    for msg in slice_agent_json:
        session_slice.append({
            "worthy_summary":msg['worthy_summary'],
            "topic": msg['topic'],
            "start_round": msg['start_round'],
            "end_round": msg['end_round'],       
            "key_words": msg['key_words'],
            "summary_detail":""
        })

    session_json['unslice_pointer'] = session_messages[-1]['message_round']
    _json_write(content=session_json,file_path=session_file_path)


def _slice_summary(session_id:str,session_slice:dict):
    if not session_slice['worthy_summary']:
        return session_slice
    
    session_message_list = _get_session_messages(session_id=session_id)
    
    slice_message_list = []
    for msg in session_message_list:
        if msg['message_round'] >= session_slice['start_round'] and msg['message_round'] <= session_slice['end_round']:
            if msg['message_role'] == 'assistant' or msg['message_role'] == 'user':
                slice_message_list.append({'role':msg['message_role'],'content':msg['message_content']})

    summary_agent_system_prompt = summary_agent.message_list[0]['content']
    summary_agent_message_list = [
        {'role':'system','content':summary_agent_system_prompt},
        {'role':'user','content':json.dumps(slice_message_list,ensure_ascii=False,indent=2)}
    ]

    summary_agent_rq = json.loads(summary_agent_ai.chat.completions.create(messages=summary_agent_message_list,model=summary_agent.model_name).choices[0].message.content)[0]

    # #测试
    # print(summary_agent_rq['summary_detail'])

    session_slice['summary_detail'] = summary_agent_rq['summary_detail']
    session_slice['worthy_summary'] = False

    return session_slice


def _session_summary(session_id:str):
    session_file_path = SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json'
    session_json = _json_read(session_file_path)
    session_slice = session_json['session_slice']

    with ThreadPoolExecutor(max_workers=5) as executor:
        slice_summary_queue = {
            executor.submit(_slice_summary,session_id,s):s for s in session_slice
        }

        slice_summary_results = []
        for future in as_completed(slice_summary_queue):
            s = slice_summary_queue[future]
            try:
                result = future.result()
                slice_summary_results.append(result)
            except Exception as ee:
                print(f"✗ rounds {s['start_round']}-{s['end_round']} 失败: {ee}")

    slice_summary_results.sort(key=lambda x:x['start_round'])

    session_json['session_slice'] = slice_summary_results
    _json_write(content=session_json,file_path=session_file_path)


def _message_list_reform(session_id:str=None):

    session_file_path = SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json'
    session_json = _json_read(file_path=session_file_path)
    session_message_list = session_json['session_messages']
    session_slice = session_json['session_slice']

    message_list = []

    session_slice_last = session_slice[-1]
    system_prompt = session_message_list[0]['message_content'] if session_message_list[0]['message_role'] == 'system' else ''

    # 将summary融入到system_prompt中
    slice_summary = []
    for slice in session_slice:
        if slice['topic']:
            slice_summary.append({
                "start_round":slice['start_round'],
                "end_round":slice["end_round"],
                "topic":slice["topic"],
                "key_words":slice["key_words"],
                "summary_detail":slice["summary_detail"]
            })
    system_prompt = system_prompt + '\n\n' + str(slice_summary).strip()
    message_list.append({'role':'system','content':system_prompt})

    #将最后一个summary的对话拼入对话列表中
    for msg in session_message_list:
        if msg['message_round'] >= session_slice_last['start_round'] and msg['message_round'] <= session_slice_last['end_round']:
            if msg['message_role'] == 'tool_calls':
                message_list[-1]['tool_calls'] = json.loads(msg['message_content'])
            elif msg['message_role'] == 'tool_result':
                message_list.append(json.loads(msg['message_content']))
            else:
                message_list.append({'role':msg['message_role'],'content':msg['message_content']})
    
    main_agent.message_list = message_list


def judge_compress(session_id:str=None):
    if _count_tokens(session_id=session_id) >= int(MAX_SESSION_TOKEN):
        rich_print(message='session token has over max_token compressing...',type='system_message')
        _session_slice(session_id=session_id)
        _session_summary(session_id=session_id)
        _message_list_reform(session_id=session_id)


# ## 清除session的全部slice
# session_detail_ids = _get_sessison_detail_ids()
# for id in session_detail_ids:
#     session_json = _json_read(file_path=SESSION_MEMORTY_DETAIL_PATH/f'{id}.json')
#     session_json['unslice_pointer'] = 0
#     session_json['session_slice'] = []
#     _json_write(content=session_json,file_path=SESSION_MEMORTY_DETAIL_PATH/f'{id}.json')


# ##主动压缩全部的json对话历史
# session_detail_files = _get_sessison_detail_ids()
# for session_detail in session_detail_files:
#     print(f'{session_detail}.json summaring...')
#     _session_slice(session_id=session_detail)
#     _session_summary(session_id=session_detail)
#     print(f'{session_detail}.json has been summaried')


# ## 测试单个session压缩流程
# session_id = '20260625_210411'
# _session_slice(session_id=session_id)
# _session_summary(session_id=session_id)
