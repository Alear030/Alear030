from hook.hook_core import hooks

@hooks.register(hook_point='after_round',background=False)
def session_compress(session=None,agents=None,memory=None,**kwargs):
    if session is None:
        return
    # memory 透传给 session_compress:压缩时需重新注入跨 session timeline(memory.inject_timeline_attachment)
    session.session_compress(agent = agents.agents['main'], memory = memory)
