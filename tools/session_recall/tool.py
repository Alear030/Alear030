import jieba
jieba.setLogLevel(20)
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import json

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed

from tools._tool_register import register_tool
from config import LOCAL_EMBEDDING_MODEL,SESSION_MEMORTY_DETAIL_PATH


import threading

_embedding_model = None
_embedding_lock = threading.Lock()

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:  # 双重检查，拿到锁后再确认一次
                from sentence_transformers import SentenceTransformer
                _embedding_model = SentenceTransformer(str(LOCAL_EMBEDDING_MODEL), device="cpu")
    return _embedding_model



tool_desc = '用于历史对话片段召回&回忆'

tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else None
else:
    tool_prompt = None


def _unslice_message_hitPoint(session_id:str,message_dict:dict,keywords:list[str])->dict:
    message_content = message_dict['message_content']
    keywords_set = set(keywords)
    content_words = jieba.lcut(message_content)
    keywords_counter = 0
    for word in content_words:
        if word in keywords_set:
            keywords_counter += 1
    return {
        "session_id":session_id,
        "message_round":message_dict['message_round'],
        "hit_point":keywords_counter
    }


def _get_similiar_session_unslice(session_id:str,unslice_content_list:list[dict],keywords:list[str])->list[dict]:
    message_hit_point = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        message_unslice_hit = {
            executor.submit(_unslice_message_hitPoint,session_id,unslice_message,keywords):unslice_message for unslice_message in unslice_content_list
        }
        results = []
        for future in as_completed(message_unslice_hit):
            try:
                result = future.result()
                message_hit_point.append(result)
            except Exception as ee:
                print(f'unslice message hit point has ee:{ee}')

    return message_hit_point


def _get_message_slice(session_id:str,slice_list:list[dict],message_round:int)->dict:
    slice_target = {}
    for slice in slice_list:
        if message_round >= slice['start_round'] and message_round <= slice['end_round']:
            slice_target = slice
            break
    return {
        "session_id":session_id,
        "start_round":slice_target['start_round'],
        "end_round":slice_target['end_round'],
        "abstract":slice_target['topic']
    }


def _hit_keywords(session_id:str,session_slice:dict,keywords:list[str])->dict:
    session_slice_keyword = session_slice['key_words']
    hit_words = []

    def _char_ouverlap(word_a:str,word_b:str)->float:
        wa,wb = set(word_a),set(word_b)
        if not wa or not wb:
            return 0.0
        return len(wa&wb)/len(wa|wb)
    
    for key in keywords:
        for sk in session_slice_keyword:
            if key in sk or sk in key:
                hit_words.append(key)
                break

            if _char_ouverlap(key,sk) >= 0.5:
                hit_words.append(key)
                break
    return {
        "session_id":session_id,
        "start_round":session_slice['start_round'],
        "end_round":session_slice['end_round'],
        "abstract":session_slice['summary_detail'],
        "hit_point":len(hit_words)
    }


def _get_similiar_session_slice(session_id:str,session_detail_slice:list[dict],keywords:list[str])->list[dict]:

    with ThreadPoolExecutor(max_workers=5) as executor:
        slice_hit_keywords_queue = {
            executor.submit(_hit_keywords,session_id,session_slice,keywords):session_slice for session_slice in session_detail_slice if not session_slice['worthy_summary']
        }

        results = []
        for future in as_completed(slice_hit_keywords_queue):
            try:
                result = future.result()
                results.append(result)
            except Exception as ee:
                print(f'session slice similiar has an ee:{ee}')
    return results


def _embedding_point(final_list_slice:dict,user_intention:str)->dict:
    user_intention_vec = _get_embedding_model().encode([user_intention])
    slice_abstract_vec = _get_embedding_model().encode([final_list_slice['abstract']])
    sim = _get_embedding_model().similarity(user_intention_vec,slice_abstract_vec)
    rag_score = sim.item()
    return{
        "session_id":final_list_slice['session_id'],
        "start_round":final_list_slice['start_round'],
        "end_round":final_list_slice['end_round'],
        "abstract":final_list_slice['abstract'],
        "rag_score":rag_score
    }


def _get_embedding_list(session_final_list:list[dict],user_intention:str)->list[dict]:
    model = _get_embedding_model()
    results = []
    for list_slice in session_final_list:
        try:
            result = _embedding_point(list_slice, user_intention)
            results.append(result)
        except Exception as ee:
            print(f"final slice embedding has ee: {ee}")
    return results


@register_tool(tool_name='session_recall',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,role=['main'])
def session_recall(key_words:list[str],user_intention:str)->str:
    from session import _get_sessison_detail_ids,_json_read,_get_unslice_content,_session_slice,_get_session_detail_slice
    
    session_detail_ids = _get_sessison_detail_ids()
    session_slice_point_list = []
    session_unslice_point_list_org = []

    for id in session_detail_ids:
        session_json = _json_read(SESSION_MEMORTY_DETAIL_PATH/f'{id}.json')
        session_slice_point_list += _get_similiar_session_slice(session_id=id,session_detail_slice=session_json['session_slice'],keywords=key_words)
        session_unslice_point_list_org += _get_similiar_session_unslice(session_id=id,unslice_content_list=_get_unslice_content(session_id=id,has_tool=False),keywords=key_words)
    
    session_slice_point_list_final = sorted(session_slice_point_list,key=lambda x:x['hit_point'],reverse=True)[:3]
    session_unslice_point_list_final = []

    session_unslice_point_list_org_order = sorted(session_unslice_point_list_org,key=lambda x:x['hit_point'],reverse=True)[:3]
    for session in session_unslice_point_list_org_order:
        _session_slice(session_id=session['session_id'])
        session_unslice_point_list_final.append(_get_message_slice(session_id=session['session_id'],slice_list=_get_session_detail_slice(session_id=session['session_id']),message_round=session['message_round']))

    session_slice_final_list = sorted(_get_embedding_list(session_final_list=session_slice_point_list_final+session_unslice_point_list_final,user_intention=user_intention),key=lambda x:x['rag_score'],reverse=True)
    return json.dumps(session_slice_final_list, ensure_ascii=False, indent=2)



    

    
