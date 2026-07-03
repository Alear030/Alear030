import yaml

from pathlib import Path
from openai import OpenAI

from tool import get_tool,match_tool
from config import MAX_TOOLCALLS,MODEL_LEVEL
from prompt.prompt_core import Prompt

# 得到agent_group配置文件
agents_file = Path(__file__).parent/'agents.yaml'
if agents_file.exists():
    agents_text = agents_file.read_text(encoding='utf-8').strip()
    agents_yaml = yaml.safe_load(agents_file.read_text(encoding='utf-8')) if agents_text else None


class Agent:
    def __init__(self,agent_profile:dict):
        # agent 基础信息
        self.agent_id:int = agent_profile['agent_id']
        self.agent_name:str = agent_profile['agent_name']
        self.agent_mode:str = agent_profile['agent_mode']
        self.agent_level:str = agent_profile['agent_level']
        self.agent_priority:int = agent_profile['agent_priority']
        self.agent_desc:str = agent_profile['agent_desc']

        # agent model相关信息 openai实例
        self.base_url = MODEL_LEVEL[agent_profile['agent_level']]['base_url']
        self.api_key = MODEL_LEVEL[agent_profile['agent_level']]['api_key']
        self.model_name = MODEL_LEVEL[agent_profile['agent_level']]['model_name']
        self.agent_ai = OpenAI(base_url=self.base_url,api_key=self.api_key)
        
        # agent tools 信息
        self.tool_autho:list[str] = self._get_tool_autho(agent_tool_autho=agent_profile['agent_tool_autho'])
        self.tool_list:list = get_tool(self.tool_autho)
        self.max_toolcalls = MAX_TOOLCALLS
        self.match_tool = match_tool

        # agent prompt&message_list 信息
        self.prompt:Prompt = Prompt(self)
        self.message_list:list = [{'role':'system','content':self.prompt.prompt_content}]


    # 得到agent的tool_autho
    def _get_tool_autho(self,agent_tool_autho:dict):
        tool_autho_list =[]
        for key,value in agent_tool_autho.items():
            if value:
                tool_autho_list.append(key)
        return tool_autho_list


class Agents:
    def __init__(self,agents_yaml:dict):
        self.agents:dict[str,Agent] = self._agents_init(agents_yaml = agents_yaml['agents'])
    
    # 初始化批量创建agents
    def _agents_init(self,agents_yaml:dict)->dict:
        agents_dict = {}
        for agent in agents_yaml:
            agents_dict[agent['agent_name']] = Agent(agent_profile=agent)
        return agents_dict
    
    # 为后续agent自主创建agent后，更新agents预留
    def _agents_reload(self):
        pass


# 创建全局Agents实例
agents = Agents(agents_yaml=agents_yaml)