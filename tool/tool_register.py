import json
import inspect

from core import *

class ToolRegister:

    #初始化ToolRegister类的技能列表，后续需要增加role、subagent区分
    def __init__(self):
        self.tool_list = {}

    #技能注册装饰器，后续需增加role，subagent区分
    def tool_register(self,tool_name:str=None,tool_desc:str='',tool_enabled:bool=True,sub_enabled:bool=True):
        if tool_name:
            rich_print(f'{tool_name} does not exist......')
        def get_element(func):

            self.tool_list[tool_name] = {
                'name':tool_name,
                'description':tool_desc,
                'tool_def':func,
                'parmeters':self._make_parmeters(func),
                'enabled':tool_enabled,
                'sub_enabled':sub_enabled
            }
            return func
        
        return get_element
    
    
    # def _make_parmeters(self,func):
        
    

