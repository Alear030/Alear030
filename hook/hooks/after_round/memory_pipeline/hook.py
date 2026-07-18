import json

from hook.hook_core import hooks

from config import SESSION_MEMORTY_DETAIL_PATH


@hooks.register(hook_point='after_round', background=True)
def memory_pipeline(session=None, memory=None, hooks=None,**kwargs):
    # after_round 后台钩子:先切片+summary(session 职责),再把切片喂进 memory 管线(memory 职责)。
    # 合并自原 session_slice 钩子——切片是记忆摄入的第一阶段,生产者(切片)与消费者(管线)
    # 放进同一函数顺序执行,从结构上杜绝原先两个异步钩子靠注册顺序碰巧串行导致的读到旧数据/空列表的 bug。
    if session is None:
        return

    # 切片 + summary 无条件先跑(session 自身职责,不依赖 memory 是否接上)
    session._session_slice()
    session._session_summary()

    # # ________ hook test avoid __________
    # return
    
    # memory 未注入(如无记忆的纯推理模式)→ 切片已落地,pipeline 阶段跳过
    if memory is None:
        return

    # 读取刚写好的持久化 JSON;文件不存在或为空则跳过
    session_detail_file = SESSION_MEMORTY_DETAIL_PATH / f'{session.session_id}.json'
    if not session_detail_file.exists():
        return
    raw = session_detail_file.read_text(encoding='utf-8').strip()
    if not raw:
        return
    session_detail_content = json.loads(raw)

    # 空切片兜底 + 末片 start_round==1(整个会话只有一个从头增长的尾片,未定型)→ 跳过
    session_slice = session_detail_content['session_slice']
    if not session_slice or session_slice[-1]['start_round'] == 1:
        return

    worthy_slices = [
        slice for slice in session_slice[:-1]
        if slice.get('worthy_summary', True)
    ]
    if not worthy_slices:
        return

    memory.slices_pipeline(
        slices=worthy_slices,
        messages=session_detail_content['session_messages'][1:],
        session=session,
    )
