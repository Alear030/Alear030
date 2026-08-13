from tool.tool_core import register_tool,tool_call_processing
from pathlib import Path
from config import ROOT_DIRECTORY

skill_load_desc = "用于加载目标技能"
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt = tool_prompt_file.read_text(encoding='utf-8').strip() or None
else:
    tool_prompt = None

@register_tool(tool_name='skill_load',tool_desc=skill_load_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='skill_tool')
def skill_load(skill_name:str,**kwargs)->str:
    # 执行tool_call_processing
    tool_call_processing(kwargs.get('tcr',None),kwargs.get('emit',None))

    skill_path = ROOT_DIRECTORY/'skill'
    skill_md_list = list(skill_path.rglob(f'{skill_name}/skill.md'))
    if not skill_md_list:
        return f'{skill_name} fail to load'
    skill_text = skill_md_list[0].read_text(encoding='utf-8')
    skill_parts = skill_text.split('---')
    skill_body = '---'.join(skill_parts[2:]).strip()

    return skill_body
