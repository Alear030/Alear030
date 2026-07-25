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

#@claude 这里其实后续应该将搜索的节点转移到memory_storage中的slice_node文件中

# 得到全部的session_detail id 为后续得到slices准备，且排除当前session的id
def _get_session_detail_ids():
    session_detail_ids = sorted(file.stem for file in Path(SESSION_MEMORTY_DETAIL_PATH).glob("*.json"))[:-1]
    return session_detail_ids

# 得到一个session detail中的slice,并注入session_id
def _get_slice(session_file)->list:
    # 得到slice；刚创建还没切片的 session 没有 session_slice 键，用 .get 兜住不让整次召回崩
    session_json = _json_read(file_path=session_file)
    session_slice = session_json.get('session_slice') or []

    # 将session_id注入到每个slice中 并且附上embedding数值
    for slice in session_slice:
        slice['session_id'] = session_json.get('session_id','')
    return session_slice

# 并发得到全部session detail的slice；传入session_ids时收窄到交集,避免全量扫描
def _get_slices(session_ids:list[str]=None):
    all_session_ids = _get_session_detail_ids()
    if session_ids:
        session_ids = [session_id for session_id in session_ids if session_id in all_session_ids]
    else:
        session_ids = all_session_ids
    with ThreadPoolExecutor(max_workers=5) as tp:
        get_slice_queue = {
            tp.submit(_get_slice,SESSION_MEMORTY_DETAIL_PATH/f'{session_id}.json'):session_id for session_id in session_ids
        }
        slice_results = []
        failed = []
        for thread in as_completed(get_slice_queue):
            # 单个 session 文件损坏/结构异常不该毁掉整次召回，跳过并记名字，由调用方报出去
            try:
                slice_results += thread.result()
            except Exception as ee:
                failed.append(f'{get_slice_queue[thread]}({type(ee).__name__})')
    return slice_results,failed


@register_tool(tool_name='memory_recall',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='memory_tool')
def memory_recall(key_words:list[str],search_target:str,top_k:int,session_ids:list[str]=None,**kwargs):

    # 拼接输入的keywords和search target 并得到向量值
    target_text = f"{' '.join(key_words)}  {search_target}"
    target_vec = _get_embedding_model().encode([target_text])[0]

    # 得到slices并对每一个slice的embedding和target_embedding计算余弦相似度；
    # session_ids 非空时收窄扫描范围,为空则维持原有全量扫描行为
    slices,failed_files = _get_slices(session_ids=session_ids)

    # 历史 slice 可能缺 slice_embedding(早期数据没这个字段)，无向量无法算相似度，跳过而非崩掉
    scored_slices = []
    skipped_no_embedding = 0
    for slice in slices:
        embedding_b64 = slice.get('slice_embedding')
        if not embedding_b64:
            skipped_no_embedding += 1
            continue
        slice_vec = embedding_from_b64(embedding_b64)
        # 点积后除以长度积 转float类型数值保存 A·B = |A| × |B| × cos(θ)
        slice['score'] = float(np.dot(slice_vec,target_vec)/(np.linalg.norm(target_vec) * np.linalg.norm(slice_vec)))
        scored_slices.append(slice)

    # 对slices按照score进行排序，得到top-k的结果并返回，同时对slice进行处理
    scored_slices.sort(key=lambda x:x['score'],reverse=True)
    slices_results = []
    for slice in scored_slices[:top_k]:
        anchor = slice.get('slice_anchor') or {}
        slices_results.append({
            "session_id":slice.get('session_id',''),
            "topic":anchor.get('topic',''),
            "start_round":slice.get('start_round'),
            "end_round":slice.get('end_round'),
            "key_words":anchor.get('key_words',[]),
            "summary_detail":anchor.get('summary_detail',''),
            "score":slice['score']
        })

    # 跳过/失败不静默吞掉，否则召回结果变少却看不出原因
    payload = {"results":slices_results}
    if skipped_no_embedding:
        payload["skipped_no_embedding"] = skipped_no_embedding
    if failed_files:
        payload["failed_session_files"] = failed_files

    if skipped_no_embedding or failed_files:
        return json.dumps(payload,ensure_ascii=False)
    return json.dumps(slices_results,ensure_ascii=False)