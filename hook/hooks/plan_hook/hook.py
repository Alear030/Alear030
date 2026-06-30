from hook.hook_core import hooks,HookResult

# 循环中调用工具时注入 agents 容器，供所有工具按需使用
@hooks.register(hook_point='pre_toolUse', match={'tool':'plan_create'})
def inject_agents(agents, tool_args, **_):
    tool_args['agents'] = agents
    return HookResult(modify_input=tool_args)