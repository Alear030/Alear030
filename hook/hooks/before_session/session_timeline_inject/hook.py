import tiktoken

from hook.hook_core import hooks


# timeline attachment token 预算:RECENT 预算内(或最近 MIN_FULL 条)用 full(含叙事线索 thread);
# 超出预算的远段统一 keywords+summary,不再细分中段(原 half/less 输出相同,MIDEL 档失效)
RECENT_TIMELINE = int(2048)
# 最近 N 条强制 full(不受预算挤压),保证最近 session 全字段覆盖
MIN_FULL_TIMELINE = int(3)

# done(@claude): 补全 count_token,用 tiktoken gpt-4o 编码器算单段文本 token 数
# 与 session_core._session_count_tokens 同一 gpt-4o 编码器;模块级缓存避免 timeline 循环里重复构建
_TOKEN_ENCODING = tiktoken.encoding_for_model(model_name='gpt-4o')


def count_token(text: str) -> int:
    # 纯文本 token 数,不含消息列表 per-message 开销(那部分由 _session_count_tokens 按需 +4)
    return len(_TOKEN_ENCODING.encode(text))

# 根据 token 预算返回 timeline content:RECENT 预算内(或最近 MIN_FULL 条)用 full(含叙事线索);
# 超出预算的远段统一 keywords+summary。远段不能只留 keywords--summary 是 agent 圈定
# memory_recall session_ids 候选范围的关键语义线索,只给 keywords 会被当次主题稀释导致漏选
# (20260622_142346「存在与自发性」即因此被漏),故远段也保留 summary,不再与中段区分
def timeline_content(timeline,timeline_token,timeline_index):
    sid = timeline['session_id']
    keywords = '、'.join(timeline['keywords'])
    # summary 容错:降级条目(source=fallback)summary 留空,省略"本轮主要讲了"段避免空句;
    # 其远段圈定靠 keywords(去重不截断、词多覆盖广)兜住。LLM 条目 summary 非空照常渲染
    summary = timeline.get('summary','')
    summary_seg = f"。本轮主要讲了{summary}" if (isinstance(summary,str) and summary.strip()) else ""
    if timeline_index < MIN_FULL_TIMELINE or timeline_token < RECENT_TIMELINE:
        thread = '；'.join(timeline['thread'])
        return f"session:{sid}:关键词:{keywords}{summary_seg}。叙事线索:{thread}"
    return f"session{sid}:关键词:{keywords}{summary_seg}"


@hooks.register(hook_point='before_session')
def session_timeline_inject(session=None, memory=None, **kwargs):
    # before_session 同步钩子:session 构造完成、进入主循环前,把历史时间线(排除最近 3 条,
    # 因为那 3 条已被 session_recent 快照覆盖)通过 attachment 注入。Loop._sent_message_api
    # 会在本 session 第一次发出用户消息时自动把 attachment 拼进去并清空,不需要额外的
    # before_round + round==1 特判。对 timeline 存储的读取统一走 memory 对象,不直接 import
    # memory_storage,避免 hook 侧开出一条不受 Memory 类管控的平行读取路径。
    if session is None or memory is None:
        return

    historical_timeline = memory.get_historical_timeline(exclude_recent=3)
    if not historical_timeline:
        return
    else:historical_timeline.reverse()

    timeline_token = 0
    timeline_info = None

    for timeline_index,timeline in enumerate(historical_timeline):
        tl_content = timeline_content(timeline=timeline,timeline_token=timeline_token,timeline_index=timeline_index)
        timeline_info = timeline_info + '\n\n' + tl_content if timeline_info else tl_content
        timeline_token+=count_token(text=tl_content)


    session.attachment.attachment_add(
        attachment_type='notification',
        attachment_source='session_timeline',
        attachment_content=(
            "以下是历史会话的时间线概览(按发生顺序,近段最详含叙事线索、远段保留关键词与一句话概括锚定 session_id,"
            "配合 memory_recall 的 session_ids 参数圈定候选范围以提升召回准确率):\n"
            + timeline_info
        )
    )
