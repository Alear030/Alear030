from hook.hook_core import hooks

@hooks.register(hook_point='round_finished',background=False)
def session_compress(session=None,agents=None,**kwargs):
    if session is None:
        return
    session.session_compress(agent = agents.agents['main'])
