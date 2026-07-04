import yaml

from pathlib import Path

from prompt.prompt_register import register_prompt
from config import ROOT_DIRECTORY

PROMPT_DIR = Path(__file__).parent


# 技能使用原则 + 全部已注册技能的名称和描述，仅持有skill_tool权限的agent注入
@register_prompt(prompt_name='skill_prompt',order=20,condition=lambda agent: 'skill_tool' in agent.tool_autho)
def build(agent)->str:
    skill_prompt = ''
    skill_prompt_file = PROMPT_DIR/'skill_prompt.md'
    if skill_prompt_file.exists():
        text = skill_prompt_file.read_text(encoding='utf-8')
        skill_prompt = text + '\n\n' if text else ''

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
