import json

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed


from ..subagent_core import Subagent
from tool.tool_core import register_tool


# tool描述信息
tool_desc = '用于并行创建并运行多个 subagent，每个 subagent 独立执行指定任务并按验收标准自查，适合可拆分为多条独立任务并行处理的场景'
tool_prompt_file = Path(__file__).parent / 'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8').strip()
    tool_prompt = tool_prompt_content if tool_prompt_content else None
else:
    tool_prompt = None


@register_tool(tool_name='subagent_create',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='subagent_tool')
def subagent_create(subagent_files:list[dict],max_subagent:int = 5,**kwargs)->str:
    if len(subagent_files) > max_subagent:
        return json.dumps({"error": f"subagent 数量({len(subagent_files)})超出上限 max_subagent={max_subagent}"}, ensure_ascii=False)

    subagent_group = []
    for file in subagent_files:
        subagent_group.append(Subagent(subagent_file=file))

    with ThreadPoolExecutor(max_workers=max_subagent) as tp:
        subagent_queue = {
            tp.submit(subagent.subagent_run):subagent for subagent in subagent_group
        }
        results = []

        for thread in as_completed(subagent_queue):
            result = thread.result()
            results.append(result)
        
    results.sort(key=lambda x:x['subagent_id'])

    return json.dumps(results,ensure_ascii=False)