from hook.hook_core import hooks


@hooks.register(hook_point='before_session')
def session_timeline_inject(session=None, memory=None, **kwargs):
    # before_session 同步钩子:session 构造完成、进入主循环前,把历史时间线(排除最近 3 条,
    # 因为那 3 条已被 session_recent 快照覆盖)通过 attachment 注入。Loop._sent_message_api
    # 会在本 session 第一次发出用户消息时自动把 attachment 拼进去并清空,不需要额外的
    # before_round + round==1 特判。
    # 注入逻辑(含 token 预算分层)收口到 memory.inject_timeline_attachment,与 session_compress
    # 共用同一实现--compress 清空 message_list 时连带清掉首轮注入的 timeline,需重新注入,
    # 走同一个入口避免分层逻辑双源漂移。对 timeline 存储的读取统一走 memory 对象,不直接
    # import memory_storage,避免 hook 侧开出一条不受 Memory 类管控的平行读取路径。
    if session is None or memory is None:
        return
    memory.inject_timeline_attachment(session)
