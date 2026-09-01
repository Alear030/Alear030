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
        self.system_prompt:Prompt = Prompt(self)
        self.message_list:list = [{'role':'system','content':self.system_prompt.prompt_content}]

        # eval 观测实例，由 main.py 回填：Agent 在模块 import 期就构造完了，那时 session 还不存在，
        # 而 trace 是 per-session 实例，构造期根本拿不到
        self.trace = None
        # profile 快照：构造即建全，之后一律走 agent_profile_update 改，别直接写这个 dict
        # tool_list 只留工具名不留 schema：整棵 JSON Schema 进 diff，MCP 每连上一个 server 就写一大坨
        self.agent_profile = {
            "model_name":self.model_name,
            "agent_level":self.agent_level,
            "tool_autho":self.tool_autho,
            "tool_list":[tool['function']['name'] for tool in self.tool_list],
            "system_prompt":self.system_prompt.prompt_content
        }


    # 重新按授权取一次工具表：tool_list 是构造期快照，运行时注册的工具（MCP server 连上/断开）
    # 不刷新就永远进不了模型可见的 tools。loop._chat 每次现读 tool_list，故刷新后下一次调用即生效
    def refresh_tool_list(self):
        self.tool_list = get_tool(self.tool_autho)
        self.agent_profile_update(target={"tool_list":[tool['function']['name'] for tool in self.tool_list]})

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
        # 一次调用带上两个字段：一次真实变更对应一条记录，拆两次调用会变成两条
        self.agent_profile_update(target={"model_name":self.model_name,"agent_level":self.agent_level})

    # trace 注入后由 main.py 调一次，把当前 profile 全量记下当基线，后续增量才有的比
    # 形状和 update 保持一致（全量塞进 added），读 jsonl 时不用为初始记录另分一支
    def agent_profile_trace_init(self):
        if not self.trace:
            return
        self.trace.trace_record(
            trace_type="agent_profile",
            source=self.agent_name,
            trace_detail={"added":self.agent_profile,"changed":{},"removed":[]}
        )

    # profile 变更唯一入口：变更方法改完自己的属性，把动了的 key/value 交给这里
    # key 不在 profile 里就是新增；在的话值相同不记、不同才记一条——字段因此可以由任意子系统
    # 运行时引入（slash 命令、权限 mode），不必先在某处登记
    # remove 单列不塞进 target：拿 None 表达删除会和「值本身就是 None」撞车
    # 快照无论有没有 trace 都要更新，否则 trace 注入之后基线是错的
    # 未加锁：MCP 后台线程与 hook 后台线程都可能进来，落盘由 Trace 自己的锁保证，
    # 这里只是快照读-比-写可能交错；当前各 agent 是不同对象，无实际竞争
    def agent_profile_update(self,target:dict=None,remove:list=None):
        added = {}
        changed = {}
        removed = []

        for key,value in (target or {}).items():
            if key not in self.agent_profile:
                added[key] = value
            elif self.agent_profile[key] != value:
                changed[key] = {"from":self.agent_profile[key],"to":value}
            self.agent_profile[key] = value

        for key in (remove or []):
            if key in self.agent_profile:
                removed.append(key)
                del self.agent_profile[key]

        # 三项皆空说明这次调用没带来任何变化，不记空记录刷屏
        if not self.trace or (not added and not changed and not removed):
            return

        self.trace.trace_record(
            trace_type="agent_profile",
            source=self.agent_name,
            trace_detail={"added":added,"changed":changed,"removed":removed}
        )


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