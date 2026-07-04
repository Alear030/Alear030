from hook.hook_core import hooks,HookResult


# 循环工具调用之前，全部注入agents，session，loop,hooks引入一个钩子处理全部tool需要处理四大类的场景
@hooks.register(hook_point='pre_toolUse')
def inject_import_args(tool_args,agents,session,hooks,Loop):
    tool_args['agents'] = agents
    tool_args['session'] = session
    tool_args['hooks'] = hooks
    tool_args['Loop'] = Loop
    return HookResult(modify_input=tool_args)