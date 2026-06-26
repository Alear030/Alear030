import os

from tools import get_tool,match_tool
from core import rich_print
from dotenv import load_dotenv
from openai import OpenAI

from .prompt_structor import prompt_structor

load_dotenv()

class Agent:

    ## 后续补充关于agent_mode的内容，暂定auto、plan、goal
    def __init__(self,agent_id:int,agent_name:str,agent_role:str,agent_mode:str='auto'):
        
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.agent_role = agent_role
        self.agent_mode = agent_mode

        self.base_url = os.getenv(f'{agent_role}_BASE_URL')
        self.api_key = os.getenv(f'{agent_role}_API_KEY')
        self.model_name = os.getenv(f'{agent_role}_MODEL_NAME')

        self.tool_list = get_tool(role=agent_role)
        self.message_list = self._message_init()

        self.match_tool = match_tool

    def _message_init(self)->list:

        system_prompt = ''

        system_prompt = prompt_structor(type='agent',role=self.agent_role)


        return [{'role':'system','content':system_prompt}]

# main agent init
main_agent = Agent(agent_id=int(0),agent_name='main',agent_role='main',agent_mode='auto')
main_agent_ai = OpenAI(base_url=main_agent.base_url,api_key=main_agent.api_key)
rich_print(message='main_agent created...',type='system_message')

slice_agent = Agent(agent_id=int(1),agent_name='slice',agent_role='slice',agent_mode='auto')
slice_agent_ai = OpenAI(base_url=main_agent.base_url,api_key=main_agent.api_key)
rich_print(message='slice_agent created...',type='system_message')

# summary agent init
summary_agent = Agent(agent_id=int(1),agent_name='summary',agent_role='summary',agent_mode='auto')
summary_agent_ai = OpenAI(base_url=main_agent.base_url,api_key=main_agent.api_key)
rich_print(message='summary_agent created...',type='system_message')