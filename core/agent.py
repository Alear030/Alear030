import os

from tools import *
from .rich_output import rich_print
from dotenv import load_dotenv
from openai import OpenAI

from .prompt_structor import get_prompt

load_dotenv()

class Agent:

    ## 后续补充关于agent_mode的内容，暂定auto、plan、goal
    def __init__(self,agnet_id:int,agent_name:str,agent_role:str,agent_mode:str='auto'):
        
        self.agent_id = agnet_id
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

        system_prompt = get_prompt(type='agent',role=self.agent_role)


        return [{'role':'system','content':system_prompt}]


main_agent = Agent(agnet_id=int(000),agent_name='main',agent_role='main',agent_mode='auto')
main_agent_ai = OpenAI(base_url=main_agent.base_url,api_key=main_agent.api_key)
rich_print(message='main_agent created...',type='system_message')