from hook.hook_core import hooks

@hooks.register(hook_point="after_round",background=True)
def session_slice(session=None,**kwrags):
    if session is None:
        return
    session._session_slice()
    session._session_summary()