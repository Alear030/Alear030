import yaml
import json

from pathlib import Path
from datetime import datetime

from config import ROOT_DIRECTORY,SESSION_MEMORTY_DETAIL_PATH
from tool import get_tool_brief

agent_prompt_path = Path(__file__).parent/'agent_prompt'
tool_prompt_path = Path(__file__).parent/'tool_prompt'
skill_prompt_path = Path(__file__).parent/'skill_prompt'

class Prompt:

    def __init__(self,agent):
        self.agent_name:str = agent.agent_name
        self.tool_autho = agent.tool_autho

        self.prompt_content:str = self._prompt_init()

    # 按固定顺序拼接各个分块，组装出完整的system prompt
    def _prompt_init(self)->str:
        return self._system_prompt() +'\n\n' + self._tool_prompt() + '\n\n' + self._skill_prompt() + '\n\n' + self._session_recent() + '\n\n' + self._agent_prompt() + '\n\n' + self._basic_prompt()


    # 系统基础提示，注入当前系统时间
    def _basic_prompt(self)->str:
        time_now = datetime.now()
        return '#系统基础提示' + '\n\n' + f'当前系统时间为:{time_now}'


    # 底层核心架构prompt，仅main agent注入
    def _system_prompt(self)->str:
        system_prompt_file = agent_prompt_path/'system_prompt.md'
        system_prompt_content = ''
        
        if self.agent_name == 'main' and system_prompt_file.exists():
            system_prompt_content = system_prompt_file.read_text(encoding='utf-8').strip() if system_prompt_file.read_text(encoding='utf-8').strip() else ''
        
        return system_prompt_content
    

    # agent自身身份/职责设定，读取agent_prompt/agents/{agent_name}_agent.md
    def _agent_prompt(self)->str:
        agent_prompt_file = agent_prompt_path/'agents'/f'{self.agent_name}_agent.md'
        agent_prompt_content = ''
        if agent_prompt_file.exists():
            agent_prompt_content = agent_prompt_file.read_text(encoding='utf-8').strip() if agent_prompt_file.read_text(encoding='utf-8').strip() else ''
        return agent_prompt_content


    # 工具使用原则 + agent自身持有的每个工具的名称和简短说明（完整tool_prompt已在function-calling schema中传给模型，这里不重复）
    def _tool_prompt(self,)->str:
        tools_prompt = ''
        tool_briefs = get_tool_brief(self.tool_autho)
        if tool_briefs:
            tool_prompt_file = tool_prompt_path/'tool_prompt.md'
            if tool_prompt_file.exists():
                tools_prompt = tool_prompt_file.read_text(encoding='utf-8').strip() + '\n\n' if tool_prompt_file.read_text(encoding='utf-8').strip() else ''
            for tool in tool_briefs:
                tools_prompt += f'工具名称:{tool["name"]}  工具说明:{tool["description"]}' + '\n\n'
        return tools_prompt


    # 技能使用原则 + 全部已注册技能的名称和描述，仅持有skill_tool权限的agent注入
    def _skill_prompt(self)->str:
        skill_prompt = ''
        if 'skill_tool' in self.tool_autho:
            skill_prompt_file = skill_prompt_path/'skill_prompt.md'
            if skill_prompt_file.exists():
                skill_prompt = skill_prompt_file.read_text(encoding='utf-8') + '\n\n' if skill_prompt_file.read_text(encoding='utf-8') else ''

            skill_path = ROOT_DIRECTORY/'skill'
            skill_list = list(skill_path.rglob('skill.md'))
            for skill_file in skill_list:
                skill_content = skill_file.read_text(encoding='utf-8')
                if not skill_content.startswith('---'):
                    continue
                skill_file_parts = skill_content.split('---')
                skill_yaml = skill_file_parts[1].strip()
                skill_metadata = yaml.safe_load(skill_yaml)
                skill_name = skill_metadata.get('name')
                skill_desc = skill_metadata.get('description')
                skill_prompt += f'技能名称:{skill_name}  技能描述:{skill_desc}' + '\n\n'
        return skill_prompt


    # 最近3轮历史session的切片摘要，用于跨session的短期记忆
    def _session_recent(self)->str:
        session_recent_ids = sorted(file.stem for file in Path(SESSION_MEMORTY_DETAIL_PATH).glob("*.json"))[-3:]
        session_prompt = f"# 最近{len(session_recent_ids)}轮对话信息" + '\n\n' if session_recent_ids else ''
        
        for id in session_recent_ids:
            session_prompt += f'## session{id}对话内容摘要' + '\n\n'
            session_json = json.loads((SESSION_MEMORTY_DETAIL_PATH/f'{id}.json').read_text(encoding='utf-8'))
            session_slices = session_json['session_slice']
            for slice in session_slices:
                session_prompt += f'片段所属session_id:{id}  片段主题:{slice["topic"]} 片段详情:{slice["summary_detail"]} 片段开始round:{slice["start_round"]} 片段结束round:{slice["end_round"]}' + '\n\n'
        
        return session_prompt

            
            
