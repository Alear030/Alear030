import json
import inspect
import typing

from rich_output import rich_print

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
            if name == 'self' or name == 'agents' or name == 'session':
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
    
    def match_tool(self,tool_call,**extra)->dict:
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)

        if tool_name not in self.tool_list:
            rich_print(message=f'{tool_name} doesnt exist...',type='system_error')
            return {'role':'tool','tool_call_id':tool_call.id,'content':'错误工具不存在'}
        
        rich_print(message=f'{tool_name}...',type='tool_call')

        tool_func = self.tool_list[tool_name]['function']
        tool_result = tool_func(**tool_args,**extra)

        return {'role':'tool','tool_call_id':tool_call.id,'content':str(tool_result)}


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
    
_register = _ToolRegister()

register_tool = _register.tool_register
get_tool = _register.get_tools
match_tool = _register.match_tool
