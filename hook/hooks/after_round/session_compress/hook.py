from hook.hook_core import hooks

@hooks.register(hook_point='after_round',background=False)
def session_compress(session=None,agents=None,**kwargs):
    if session is None:
        return
    session.session_compress(agent = agents.agents['main'])
