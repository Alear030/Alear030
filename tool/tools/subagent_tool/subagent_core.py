from openai import OpenAI
from datetime import datetime


from config import MODEL_LEVEL,SUB_MAX_TOOLCALLS
from tool import get_tool,match_tool
from loop import Loop


class Subagent:

    # subagent 初始化，传入系统提示词和任务描述，执行标准
    # subagent_file 需要包含：subagent_id\system_prompt\task_desc\check_standard
    # verbose 控制该 subagent 的 thinking 是否打印到终端，默认开，与 main/memory 用法一致
    def __init__(self,subagent_file:dict = None,verbose:bool=True):
        # subagent 基础信息
        self.agent_id:int = subagent_file['subagent_id']
        self.agent_name:str = 'subagent'
        self.subagent_level:str = 'low_level'
        self.verbose:bool = verbose

        # subagent model openai 相关信息
        self.base_url:str = MODEL_LEVEL[self.subagent_level]['base_url']
        self.api_key:str = MODEL_LEVEL[self.subagent_level]['api_key']
        self.model_name:str = MODEL_LEVEL[self.subagent_level]['model_name']
        self.agent_ai:OpenAI = OpenAI(base_url=self.base_url,api_key=self.api_key)
        
        # subagent tool 相关信息：未显式传入 tool_autho 时保持原有只读四类，传入则按调用方指定类别授权
        self.tool_antho:list = subagent_file.get('tool_autho') or ['basic_tool','file_read_tool','memory_tool','web_tool']
        self.tool_list:list = get_tool(self.tool_antho)
        self.max_toolcalls:int = SUB_MAX_TOOLCALLS
        self.match_tool = match_tool

        # subagent message_list 信息
        # 关于system_prompt的想法：后续其实可以按照不同类型的subagent进行装配，不用mainagent进行输入，比如search_subagent、dig_subagent等，而且其实也可以考虑后续常用的Agent让mainagent自主创建到yaml里面
        current_time = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.message_list:list = [{"role":"system","content":subagent_file['system_prompt'] + f'系统提示：当前时间为:{current_time}'}]
        self.task_message:str = f"请依据验收标准 {subagent_file['check_standard']}  执行任务 {subagent_file['task_desc']}"

    def subagent_run(self):
        subagent_loop = Loop(verbose=self.verbose)
        subagent_rq = subagent_loop.loop_run(agent=self,message=self.task_message)
        subagent_result = {"subagent_id":self.agent_id,"result":subagent_rq}
        return subagent_result





