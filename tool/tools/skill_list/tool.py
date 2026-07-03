import yaml

from tool.tool_core import register_tool
from pathlib import Path
from config import ROOT_DIRECTORY

skill_list_desc = "用于查询当前可用技能"
skill_list_prompt_file = Path(__file__).parent/'tool_prompt.md'
if skill_list_prompt_file.exists():
    skill_list_content = skill_list_prompt_file.read_text(encoding='utf-8').strip()
    skill_list_prompt = skill_list_content if skill_list_content else None
else:
    skill_list_prompt = None

@register_tool(tool_name='skill_list',tool_desc=skill_list_desc,tool_prompt=skill_list_prompt,tool_enabled=False,tool_autho='skill_tool')
def skill_list()->list:
    skill_path = ROOT_DIRECTORY/'skill'
    skill_list = list(skill_path.rglob('skill.md'))
    skill_data = []

    for skill_file in skill_list:
        skill_raw = skill_file.read_text(encoding='utf-8')
        if not skill_raw.startswith('---'):
            continue
        skillFile_parts = skill_raw.split('---')
        skill_yaml = skillFile_parts[1].strip()
        skill_metadata = yaml.safe_load(skill_yaml)
        skill_info = {'skill_name':skill_metadata.get('name'),'skill_description':skill_metadata.get('description')}
        skill_data.append(skill_info)
    
    return skill_data

skill_list_desc = "用于加载目标技能"

@register_tool(tool_name='skill_load',tool_desc=skill_list_desc,tool_enabled=True,tool_autho='skill_tool')
def skill_load(skill_name:str)->str:
    skill_path = ROOT_DIRECTORY/'skill'
    skill_md_list = list(skill_path.rglob(f'{skill_name}/skill.md'))
    if not skill_md_list:
        return f'{skill_name} fail to load'
    skill_text = skill_md_list[0].read_text(encoding='utf-8')
    skill_parts = skill_text.split('---')
    skill_body = '---'.join(skill_parts[2:]).strip()

    return skill_body