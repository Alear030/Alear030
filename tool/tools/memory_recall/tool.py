import json
import numpy as np

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed


from tool.tool_core import register_tool
from session import _json_read
from config import SESSION_MEMORTY_DETAIL_PATH
from local_model import _get_embedding_model,embedding_to_b64,embedding_from_b64

# 设置tool的desc和prompt基本信息
tool_desc = '用于历史对话片段召回&回忆'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else None
else:
    tool_prompt = None


# 得到全部的session_detail id 为后续得到slices准备，且排除当前session的id
def _get_session_detail_ids():
    session_detail_ids = sorted(file.stem for file in Path(SESSION_MEMORTY_DETAIL_PATH).glob("*.json"))[:-1]
    return session_detail_ids

# 得到一个session detail中的slice,并注入session_id
def _get_slice(session_file)->list:
    # 得到slice
    session_json = _json_read(file_path=session_file)
    session_slice = session_json['session_slice']

    # 将session_id注入到每个slice中 并且附上embedding数值
    for slice in session_slice:
        slice['session_id'] = session_json['session_id']
    return session_slice

# 并发得到全部session detail的slice
def _get_slices():
    session_ids = _get_session_detail_ids()
    with ThreadPoolExecutor(max_workers=5) as tp:
        get_slice_queue = {
            tp.submit(_get_slice,SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json'):session_id for session_id in session_ids
        }
        slice_results = []
        for thread in as_completed(get_slice_queue):
            slice_results += thread.result()
    return slice_results


@register_tool(tool_name='memory_recall',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='basic_tool')
def memory_recall(key_words:list[str],search_target:str,top_k:int):

    # 拼接输入的keywords和search target 并得到向量值
    target_text = f"{' '.join(key_words)}  {search_target}"
    target_vec = _get_embedding_model().encode([target_text])[0]

    # 得到slices并对每一个slice的embedding和target_embedding计算余弦相似度
    slices = _get_slices()
    for slice in slices:
        slice_vec = embedding_from_b64(slice['slice_embedding'])
        # 点积后除以长度积 转float类型数值保存 A·B = |A| × |B| × cos(θ)
        slice['score'] = float(np.dot(slice_vec,target_vec)/(np.linalg.norm(target_vec) * np.linalg.norm(slice_vec)))
    
    # 对slices按照score进行排序，得到top-k的结果并返回，同时对slice进行处理
    slices.sort(key=lambda x:x['score'],reverse=True)
    slices_results = []
    for slice in slices:
        slices_results.append({
            "session_id":slice['session_id'],
            "topic":slice['topic'],
            "start_round":slice['start_round'],
            "end_round":slice['end_round'],
            "key_words":slice['key_words'],
            "summary_detail":slice['summary_detail'],
            "score":slice['score']
        })


    return json.dumps(slices_results[:top_k],ensure_ascii=False)