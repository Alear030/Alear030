class _PromptRegister:
    def __init__(self):
        self.prompt_list = {}

    # 分块注册装饰器
    # prompt_name: 分块名（唯一）
    # order: 拼接顺序，数值越小越靠前
    # condition: Callable[[agent], bool]，None=总是启用；否则只有返回True才拼入
    # enabled: 整体开关，False时即使condition为真也跳过（对应tool的tool_enabled玩法）
    def register_prompt(self,prompt_name:str=None,order:int=0,condition=None,enabled:bool=True):
        def add_prompt(func):
            self.prompt_list[prompt_name] = {
                'name':prompt_name,
                'order':order,
                'condition':condition,
                'function':func,   # Callable[[agent], str]
                'enabled':enabled,
            }
            return func
        return add_prompt

    # 按order排序，过滤未启用/condition不满足的分块，调用function(agent)取内容，非空才拼入
    def build_prompt(self,agent)->str:
        parts = []
        for item in sorted(self.prompt_list.values(),key=lambda p:p['order']):
            if not item['enabled']:
                continue
            if item['condition'] and not item['condition'](agent):
                continue
            content = item['function'](agent)
            if content:
                parts.append(content)
        return '\n\n'.join(parts)

_register = _PromptRegister()
register_prompt = _register.register_prompt
build_prompt = _register.build_prompt
