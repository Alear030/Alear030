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

        # agent model相关信息 openai实例、
        self.agent_level = agent_profile['agent_level']
        self.base_url = MODEL_LEVEL[self.agent_level]['base_url']
        self.api_key = MODEL_LEVEL[self.agent_level]['api_key']
        self.model_name = MODEL_LEVEL[self.agent_level]['model_name']
        self.agent_ai = OpenAI(base_url=self.base_url,api_key=self.api_key)
        
        # agent tools 信息
        self.tool_autho:list[str] = self._get_tool_autho(agent_tool_autho=agent_profile['agent_tool_autho'])
        self.tool_list:list = get_tool(self.tool_autho)
        self.max_toolcalls = MAX_TOOLCALLS
        self.match_tool = match_tool

        # agent prompt&message_list 信息
        self.prompt:Prompt = Prompt(self)
        self.message_list:list = [{'role':'system','content':self.prompt.prompt_content}]


    # 重新按授权取一次工具表：tool_list 是构造期快照，运行时注册的工具（MCP server 连上/断开）
    # 不刷新就永远进不了模型可见的 tools。loop._chat 每次现读 tool_list，故刷新后下一次调用即生效
    def refresh_tool_list(self):
        self.tool_list = get_tool(self.tool_autho)

    # 得到agent的tool_autho
    def _get_tool_autho(self,agent_tool_autho:dict):
        tool_autho_list =[]
        for key,value in agent_tool_autho.items():
            if value:
                tool_autho_list.append(key)
        return tool_autho_list
    
    # 处理agent_level
    def refresh_agent_level(self,agent_level = None):
        agent_level_set = {'max_level','medium_level','low_level'}
        if agent_level is not None and agent_level in agent_level_set:
            self.agent_level = agent_level
        self.base_url = MODEL_LEVEL[self.agent_level]['base_url']
        self.api_key = MODEL_LEVEL[self.agent_level]['api_key']
        self.model_name = MODEL_LEVEL[self.agent_level]['model_name']



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

    # 工具表整体刷新：各 agent 按自身 tool_autho 重取，授权隔离仍然生效
    def refresh_all_tool_list(self):
        for agent in self.agents.values():
            agent.refresh_tool_list()

    # 支持 agents["name"] 字典式访问，替代 agents.agents["name"]
    def __getitem__(self, key: str) -> Agent:
        return self.agents[key]


# 创建全局Agents实例
agents = Agents(agents_yaml=agents_yaml)