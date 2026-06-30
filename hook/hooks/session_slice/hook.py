from hook.hook_core import hooks

@hooks.register(hook_point="round_finished",background=True)
def session_slice(session=None,**kwrags):
    if session is None:
        return
    session._session_slice()