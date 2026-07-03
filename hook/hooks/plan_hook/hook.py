from hook.hook_core import hooks,HookResult

# 循环中调用工具时注入 agents 容器，供所有工具按需使用
@hooks.register(hook_point='pre_toolUse', match={'tool':'plan_design'})
def inject_agents(agents, tool_args, **_):
    tool_args['agents'] = agents
    return HookResult(modify_input=tool_args)

# 循环中调用工具时注入 session 容器，供所有工具按需使用
@hooks.register(hook_point='pre_toolUse', match={'tool':'plan_mode_on'})
def inject_session(session, tool_args, **_):
    tool_args['session'] = session
    return HookResult(modify_input=tool_args)

@hooks.register(hook_point='pre_toolUse', match={'tool':'plan_mode_off'})
def inject_session_off(session, tool_args, **_):
    tool_args['session'] = session
    return HookResult(modify_input=tool_args)

# plan_update 需要拿到 session.plan.active_step_number 做跳步校验，所以也要注入 session
@hooks.register(hook_point='pre_toolUse', match={'tool':'plan_update'})
def inject_session_update(session, tool_args, **_):
    tool_args['session'] = session
    return HookResult(modify_input=tool_args)