import json

from hook.hook_core import hooks

from config import SESSION_MEMORTY_DETAIL_PATH


@hooks.register(hook_point='after_session', background=True)
def session_timeline(session=None, memory=None, **kwargs):
    # after_session 后台钩子:会话结束时,把该 session 全部已定型且 worthy_summary 的 slice
    # 提炼成一条跨会话时间线事件。与 final_memory_pipeline 的尾片逻辑独立,此处需要整段会话
    # 的完整 slice 序列(不止尾片),否则叙事线索会缺前面的片段。
    if session is None or memory is None:
        return

    session_detail_file = SESSION_MEMORTY_DETAIL_PATH / f'{session.session_id}.json'
    if not session_detail_file.exists():
        return
    raw = session_detail_file.read_text(encoding='utf-8').strip()
    if not raw:
        return
    session_detail_content = json.loads(raw)

    session_slice = session_detail_content['session_slice']
    if not session_slice:
        return

    worthy_slices = [
        slice for slice in session_slice
        if slice.get('worthy_summary', True)
    ]
    if not worthy_slices:
        return

    memory.session_timeline_extract(slices=worthy_slices, session_id=session.session_id)
