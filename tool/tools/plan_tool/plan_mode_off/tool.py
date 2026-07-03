import json

from pathlib import Path
from datetime import datetime

from config import SESSION_PLAN_FILE_PATH
from tool.tool_core import register_tool


tool_desc = '结束 plan 执行模式。所有 plan step 已执行完毕后调用，将 plan_status 改为 done，切换 session 回普通模式。'
tool_prompt_file = Path(__file__).parent / 'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt = tool_prompt_file.read_text(encoding='utf-8').strip()
else:
    tool_prompt = None


@register_tool(tool_name='plan_mode_off', tool_desc=tool_desc, tool_prompt=tool_prompt, tool_enabled=True, tool_autho='plan_tool')
def plan_mode_off(plan_file: str, session=None):
    plan_path: Path = SESSION_PLAN_FILE_PATH / f'{plan_file}.json'

    if not plan_path.exists():
        return json.dumps({"error": f"plan 文件不存在: {plan_path}"}, ensure_ascii=False)

    try:
        plan_data = json.loads(plan_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return json.dumps({"error": "plan 文件格式错误"}, ensure_ascii=False)

    if plan_data.get('plan_status') != 'in_progress':
        return json.dumps({
            "error": f"plan 当前状态为 '{plan_data.get('plan_status')}'，仅 'in_progress' 状态可结束"
        }, ensure_ascii=False)

    # 检查是否所有 step 都已执行完毕
    all_done = all(step.get('status') == 'done' for step in plan_data.get('plan_steps', []))
    if not all_done:
        return json.dumps({
            "error": "存在未完成的 step，请先通过 plan_update 将全部 step 状态更新为 done 后再调用 plan_mode_off"
        }, ensure_ascii=False)

    # 更新文件状态
    plan_data['plan_status'] = 'done'
    plan_data['update_time'] = datetime.now().strftime('%Y%m%d_%H%M%S')
    plan_path.write_text(
        json.dumps(plan_data, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    # 切换 session 回普通模式
    if session:
        session.mode = 'auto'
        session.plan = None

    return json.dumps({
        "result": f"plan '{plan_data['plan_title']}' 已执行完毕",
        "plan_title": plan_data['plan_title'],
        "plan_status": "done"
    }, ensure_ascii=False)
