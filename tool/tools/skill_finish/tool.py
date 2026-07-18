import yaml

from pathlib import Path

from config import ROOT_DIRECTORY
from tool.tool_core import register_tool

tool_desc = '用于经由系统提示创建技能，并成功将技能文件落盘后，对整个技能创建过程进行收尾结束工作'
tool_prompt_file = Path(__file__).parent/"tool_prompt.md"
if tool_prompt_file.exists():
    tool_prompt = tool_prompt_file.read_text(encoding='utf-8').strip()
else:
    tool_prompt = None


# skill_create 之后收尾:从 skill.md frontmatter 读 description 作为 skill_desc,
# 写回 advanced_task_node 给对应 task_id 的 node 打 skill_info 标记,避免重复提示创建技能
@register_tool(tool_name='skill_finish',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='skill_tool')
def skill_finish(task_id:int,skill_name:str,**kwargs):
    memory = kwargs.get('memory')
    if memory is None:
        return 'skill_finish 失败:未注入 memory 实例'

    # skill_desc 从 skill.md frontmatter 读(与 skill_list 解析方式一致,单一真相源不另开解析路径)
    skill_md_list = list((ROOT_DIRECTORY/'skill').rglob(f'{skill_name}/skill.md'))
    if not skill_md_list:
        return f'skill_finish 失败:未找到 skill/{skill_name}/skill.md'
    skill_raw = skill_md_list[0].read_text(encoding='utf-8')
    if not skill_raw.startswith('---'):
        return f'skill_finish 失败:{skill_name}/skill.md 缺少 frontmatter'
    skill_desc = (yaml.safe_load(skill_raw.split('---')[1].strip()) or {}).get('description')
    if not skill_desc:
        return f'skill_finish 失败:{skill_name}/skill.md frontmatter 缺少 description'

    ok = memory.advanced_nodes_skillInfo(task_id=task_id, skill_name=skill_name, skill_desc=skill_desc)
    return f'skill_finish 完成:task_id={task_id} skill_name={skill_name}' if ok else f'skill_finish 失败:advanced_task_node 中无 task_id={task_id}'
