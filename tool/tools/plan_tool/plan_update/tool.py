import json

from pathlib import Path
from datetime import datetime

from config import SESSION_PLAN_FILE_PATH
from tool.tool_core import register_tool


tool_desc = '更新 plan 中指定 step 的执行状态和结果。执行完一个 step 后调用，记录该 step 的状态变更'
tool_prompt_file = Path(__file__).parent / 'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt = tool_prompt_file.read_text(encoding='utf-8').strip()
else:
    tool_prompt = None


@register_tool(tool_name='plan_update', tool_desc=tool_desc, tool_prompt=tool_prompt, tool_enabled=True, tool_autho='plan_tool')
def plan_update(plan_file: str, step_number: int, status: str = None, result: str = None, session=None):
    # 之前只在 system prompt 里口头约束"一轮只能更新当前 step"，agent 不听话就没辙
    # 这里换成硬校验：step_number 必须等于 plan_loop 锁定的 active_step_number，否则直接拒绝、不写盘
    if session and session.plan:
        active = session.plan.active_step_number
        if active is not None and step_number != active:
            return json.dumps({
                "error": f"当前只能更新 step {active}，不可跳步或提前更新 step {step_number}"
            }, ensure_ascii=False)

    plan_path: Path = SESSION_PLAN_FILE_PATH / f'{plan_file}.json'

    if not plan_path.exists():
        return json.dumps({"error": f"plan 文件不存在: {plan_path}"}, ensure_ascii=False)

    try:
        plan_data = json.loads(plan_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return json.dumps({"error": "plan 文件格式错误"}, ensure_ascii=False)

    # 找到对应 step
    for step in plan_data['plan_steps']:
        if step['step_number'] == step_number:
            if status is not None:
                step['status'] = status
            if result is not None:
                step['result'] = result
            break
    else:
        return json.dumps({"error": f"step_number {step_number} 不存在"}, ensure_ascii=False)

    # 更新顶层 update_time
    plan_data['update_time'] = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 写回文件
    plan_path.write_text(
        json.dumps(plan_data, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    updated_fields = []
    if status is not None:
        updated_fields.append(f"status → {status}")
    if result is not None:
        updated_fields.append("result 已更新")

    return json.dumps({
        "result": f"plan '{plan_file}' step {step_number} 已更新: {', '.join(updated_fields)}"
    }, ensure_ascii=False)
