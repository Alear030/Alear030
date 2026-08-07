import json
import inspect
import typing

from dataclasses import dataclass,field,asdict
from rich_output import rich_print

@dataclass
class ToolCallResult:
    tool_call_id:str = ""                       # 路由键，match_tool 从 func 填，channel 据此找 widget
    tool_name:str = ""                          # 信息性，TUI 路由不依赖
    tool_call_result:dict = field(default_factory=dict)   # {"role","tool_call_id","content"} 协议消息，loop 落盘/回模型
    tool_call_state:dict = field(default_factory=dict)    # {"tool_call_state","tool_call_state_message"} TUI 态
    tool_call_extra_info:dict = field(default_factory=dict)  # 未来 TUI 新建结果widget 路由


class _ToolRegister:

    #初始化ToolRegister类的技能列表，后续需要增加role、subagent区分
    def __init__(self,role:str='main'):
        self.tool_list = {}

    #技能注册装饰器，后续需增加role，subagent区分
    def tool_register(self,tool_name:str=None,tool_desc:str='',tool_prompt:str='',tool_enabled:bool=True,tool_autho:str='basic_tool'):
        if not tool_name:
            rich_print(f'tool {tool_name} does not exist......',type='system_error')
        rich_print(f'tool {tool_name} loaded...',type='system_message')

        def add_tool(func):
            self.tool_list[tool_name] = {
                'name':tool_name,
                'description':tool_desc,
                'function':func,
                'parameters':self._make_parmeters(func),
                'prompt':tool_prompt,
                'enabled':tool_enabled,
                'tool_autho':tool_autho
            }
            return func
        
        return add_tool
    
    
    def _make_parmeters(self,func)->dict:

        ## 后续补充全部变量类型映射关系
        type_map = {int:'integer',str:'string',bool:'boolean',float:'number'}
        func_sig = inspect.signature(func)

        func_properties = {}
        func_required = []

        for name,arg in func_sig.parameters.items():
            # memory 与 agents/session 一样是 pre_toolUse 注入的运行时对象，模型无法构造，必须从可见 schema 排除
            if name in ('self','agents','session','memory','tool_call_tui_emit','tcr') or arg.kind == inspect.Parameter.VAR_KEYWORD:
                continue

            if arg.default is inspect.Parameter.empty:
                func_required.append(name)

            arg_type = arg.annotation if arg.annotation is not inspect.Parameter.empty else str
            func_properties[name] = {
                **self._make_type_schema(arg_type,type_map),
                'description':f'参数{name}'
            }
        return {'type':'object','properties':func_properties,'required':func_required}


    # 处理list[X]/dict等复合类型标注，映射为JSON Schema的array/object，避免被兜底成string
    def _make_type_schema(self,arg_type,type_map:dict)->dict:
        origin = typing.get_origin(arg_type)

        if origin is list:
            item_args = typing.get_args(arg_type)
            item_type = item_args[0] if item_args else str
            return {'type':'array','items':self._make_type_schema(item_type,type_map)}

        if origin is dict or arg_type is dict:
            return {'type':'object'}

        return {'type':type_map.get(arg_type,'string')}
    
    # verbose 单独接收，不并入 extra：extra 会原样透传进 tool_func(**tool_args,**extra)，
    # 混进去会污染工具实际收到的参数
    # 工具调用唯一入口：mode 旁路→参数解析/校验→pre_toolUse hooks→执行→异常兜底，统一返回 ToolCallResult
    # 生命周期触发：processing 跑工具前发、error 兜底路径发、success 由工具自己经 emit 发
    # runtime 是 loop 传入的运行时对象（session/agents/hooks/memory/Loop），只供 hook 触发，不落进工具参数
    def match_tool(self,tool_call,mode_switched:bool=False,verbose:bool=True,runtime:dict=None,emit=None,**extra)->ToolCallResult:
        tool_name = tool_call.function.name
        tool_call_id = tool_call.id

        # 创建本次match_tool的ToolCallResult dataclass用于后续状态数据流转
        tcr:ToolCallResult = ToolCallResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name
        )

        # mode 已切换后剩余并行调用不再执行，但 openai 要求每个 tool_call_id 都有 tool 回复
        if mode_switched:
            return self._error_result(tcr,'plan_mode_switched','plan 模式已在本轮切换，系统跳过本轮其余工具调用',emit)

        # 工具没注册过：不给模型空转的机会，直接回一句"不存在"
        if tool_name not in self.tool_list:
            rich_print(message=f'{tool_name} doesnt exist...',type='system_error')
            return self._error_result(tcr,'tool_not_found','工具不存在',emit)

        if verbose:
            rich_print(message=f'{tool_name}...',type='tool_call')

        # 参数解析 + 校验：失败不能伪装成空参数继续执行工具
        try:
            tool_args = json.loads(tool_call.function.arguments)
        except (json.JSONDecodeError, TypeError) as ee:
            return self._error_result(tcr,'invalid_tool_arguments',f'工具参数不是合法 JSON：{ee}。请修正参数后重新调用。',emit)
        if not isinstance(tool_args,dict):
            return self._error_result(tcr,'invalid_tool_arguments','工具参数必须是 JSON object，请修正参数后重新调用。',emit)

        # pre_toolUse hooks：可改写 tool_args 或注入运行时对象；hook 异常按工具失败兜底
        try:
            hook_extra = _pre_tool_use_hooks(tool_name, tool_args, runtime or {})
        except Exception as ee:
            return self._error_result(tcr,'tool_execution_error',f'pre_toolUse hook 执行失败：{type(ee).__name__}: {ee}。',emit)

        # 组装注入：extra=loop 直传；tcr=工具可改的结果载体；emit（已绑 Update）注入成 tool_call_tui_emit 供工具触发 success/进度
        inject = dict(extra)
        inject["tcr"] = tcr
        if emit:
            inject["tool_call_tui_emit"] = emit
        inject.update(hook_extra)

        # 触发 processing：工具真正开跑
        if emit:
            tcr.tool_call_state = {'tool_call_state':'processing'}
            emit(content=asdict(tcr))

        # 从注册表取出真正要执行的函数，展开调用；工具内部异常收口成 error，不炸穿 ReAct 循环
        tool_func = self.tool_list[tool_name]['function']
        try:
            tool_call_return = tool_func(**tool_args,**inject)
        except Exception as ee:
            return self._error_result(tcr,'tool_execution_error',f'工具执行失败：{type(ee).__name__}: {ee}。请根据错误修正后重试。',emit)

        # 统一终态：工具返回 dataclass 直接用；字符串/其他自动包一层 finished（中性态，未适配 success 样式的工具用）
        # success 由工具自己经 emit 触发，match_tool 只兜底发 finished
        if not isinstance(tool_call_return,ToolCallResult):
            tcr.tool_call_id = tool_call_id
            tcr.tool_name = tool_name
            tcr.tool_call_state = {'tool_call_state':'finished'}
            tcr.tool_call_result = {'role':'tool','tool_call_id':tool_call_id,'content':str(tool_call_return)}
            if emit:
                emit(content=asdict(tcr))
        else:
            tcr = tool_call_return
            # 工具返回新 dataclass 时，路由键/工具名以 func 为准兜底，协议消息 id 补上
            tcr.tool_call_id = tool_call_id
            tcr.tool_name = tool_name
            tcr.tool_call_result.setdefault('tool_call_id',tool_call_id)

        return tcr


    # 失败结果统一构造：协议消息带结构化错误，TUI 态落 error 并 emit
    def _error_result(self,tcr:ToolCallResult,error_key:str,message:str,emit=None)->ToolCallResult:
        tcr.tool_call_result = {'role':'tool','tool_call_id':tcr.tool_call_id,'content':json.dumps({'error':error_key,'message':message},ensure_ascii=False)}
        tcr.tool_call_state = {'tool_call_state':'basic_error','tool_call_state_message':message}
        if emit:
            emit(content=asdict(tcr))
        return tcr


    def get_tools(self,tool_autho:list=None)->list:
        tools = []

        for tool in self.tool_list.values():
            if not tool['enabled']:
                continue

            if tool['tool_autho'] in tool_autho:
                tools.append({
                    'type':'function',
                    'function':{
                        'description':tool['description']+'\n\n'+(tool['prompt']or''),
                        'name':tool['name'],
                        'parameters':tool['parameters']
                    }
                })

        return tools


    # 只返回name+简短description，不含tool_prompt全文，用于system prompt里罗列工具时避免和function-calling schema里的完整description重复
    def get_tool_briefs(self,tool_autho:list=None)->list:
        briefs = []

        for tool in self.tool_list.values():
            if not tool['enabled']:
                continue

            if tool['tool_autho'] in tool_autho:
                briefs.append({'name':tool['name'],'description':tool['description']})

        return briefs

# pre_toolUse hooks 触发：运行时对象从 runtime dict 取，返回需透传给工具的非 JSON 参数
# @claude 后续钩子需要都合并到hooks下进行解耦，先记录
def _pre_tool_use_hooks(tool_name:str,tool_args:dict,runtime:dict)->dict:
    extra_args = {}
    hooks = runtime.get('hooks')
    if not hooks:
        return extra_args

    results = hooks.trigger(
        hook_point='pre_toolUse',
        match_ctx={'tool':tool_name},
        session = runtime.get('session'),
        agents = runtime.get('agents'),
        hooks = hooks,
        Loop = runtime.get('Loop'),
        memory = runtime.get('memory'),
        tool_args = dict(tool_args)
    )

    for hr in results:
        if hr.block:
            continue
        if hr.modify_input:
            # 可 JSON 序列化的值改写 tool_args，其余走 extra_args 直传工具
            for k,v in hr.modify_input.items():
                if isinstance(v, (str, int, float, bool, list, dict, type(None))):
                    tool_args[k] = v
                else:
                    extra_args[k] = v

    return extra_args


_register = _ToolRegister()

register_tool = _register.tool_register
get_tool = _register.get_tools
get_tool_brief = _register.get_tool_briefs
match_tool = _register.match_tool
