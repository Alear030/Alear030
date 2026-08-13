import yaml

from tool.tool_core import register_tool,tool_call_processing
from pathlib import Path
from config import ROOT_DIRECTORY

skill_list_desc = "用于查询当前可用技能"
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt = tool_prompt_file.read_text(encoding='utf-8').strip() or None
else:
    tool_prompt = None

@register_tool(tool_name='skill_list',tool_desc=skill_list_desc,tool_prompt=tool_prompt,tool_enabled=False,tool_autho='skill_tool')
def skill_list(**kwargs)->list:
    # 执行tool_call_processing
    tool_call_processing(kwargs.get('tcr',None),kwargs.get('emit',None))

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
