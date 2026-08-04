import json

from hook.hook_core import hooks

from config import SESSION_MEMORTY_DETAIL_PATH


@hooks.register(hook_point='after_session', background=True)
def final_memory_pipeline(session=None, memory=None, **kwargs):
    # after_session 后台钩子:处理 after_round 每轮砍尾留下的最后一个尾片(此时会话已结束,末片已定型)。
    # 切片+summary 在每轮 after_round 已完成,这里只读 JSON 把尾片喂给 memory 管线。
    if session is None:
        return

    # memory 未注入(如无记忆的纯推理模式)或 pipeline_enabled 为 False→ 切片已落地,pipeline 阶段跳过
    if memory is None or not memory.pipeline_enabled:
        return

    # 读取刚写好的持久化 JSON;文件不存在或为空则跳过
    session_detail_file = SESSION_MEMORTY_DETAIL_PATH / f'{session.session_id}.json'
    if not session_detail_file.exists():
        return
    raw = session_detail_file.read_text(encoding='utf-8').strip()
    if not raw:
        return
    session_detail_content = json.loads(raw)

    # 空切片兜底(after_session 时末片已定型)
    session_slice = session_detail_content['session_slice']
    if not session_slice:
        return

    worthy_slices = [
        slice for slice in [session_slice[-1]]
        if slice.get('worthy_summary', True)
    ]
    if not worthy_slices:
        return

    memory.slices_pipeline(
        slices=worthy_slices,
        messages=session_detail_content['session_messages'][1:],
        session=session,
    )
