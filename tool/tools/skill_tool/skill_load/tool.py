import yaml

from tool.tool_core import tool,tool_call_processing
from pathlib import Path
from config import ROOT_DIRECTORY

skill_load_desc = "用于加载目标技能"
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt = tool_prompt_file.read_text(encoding='utf-8').strip() or None
else:
    tool_prompt = None

@tool.tool_register(tool_name='skill_load',tool_desc=skill_load_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='skill_tool')
def skill_load(skill_name:str,**kwargs)->str:
    # 执行tool_call_processing
    tool_call_processing(kwargs.get('tcr',None),kwargs.get('emit',None))

    skill_path = ROOT_DIRECTORY/'skill'
    skill_md_list = list(skill_path.rglob(f'{skill_name}/skill.md'))
    if not skill_md_list:
        return f'{skill_name} fail to load'

    skill_text = skill_md_list[0].read_text(encoding='utf-8')
    if not skill_text.startswith('---'):
        return f'{skill_name} fail to load: skill.md 缺少 frontmatter'

    skill_parts = skill_text.split('---', 2)
    if len(skill_parts) < 3:
        return f'{skill_name} fail to load: skill.md frontmatter 未闭合'

    skill_meta = yaml.safe_load(skill_parts[1].strip())
    if not isinstance(skill_meta, dict) or not skill_meta:
        return f'{skill_name} fail to load: skill.md frontmatter 为空或格式不对'
    if skill_meta.get('name') != skill_name:
        return f'{skill_name} fail to load: frontmatter name 与目录名不一致'

    skill_body = skill_parts[2].strip()
    if not skill_body:
        return f'{skill_name} fail to load: skill.md 正文为空'

    return skill_body
