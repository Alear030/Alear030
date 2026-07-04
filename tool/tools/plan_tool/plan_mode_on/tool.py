import json

from pathlib import Path
from datetime import datetime

from config import SESSION_PLAN_FILE_PATH
from tool.tool_core import register_tool


tool_desc = '激活指定 plan 进入执行模式。用户确认计划后调用，将 plan_status 改为 in_progress，表示开始执行该计划。'
tool_prompt_file = Path(__file__).parent / 'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt = tool_prompt_file.read_text(encoding='utf-8').strip()
else:
    tool_prompt = None


@register_tool(tool_name='plan_mode_on', tool_desc=tool_desc, tool_prompt=tool_prompt, tool_enabled=True, tool_autho='plan_tool')
def plan_mode_on(plan_file: str, session=None, **kwargs):
    plan_path: Path = SESSION_PLAN_FILE_PATH / f'{plan_file}.json'

    if not plan_path.exists():
        return json.dumps({"error": f"plan 文件不存在: {plan_path}"}, ensure_ascii=False)

    try:
        plan_data = json.loads(plan_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return json.dumps({"error": "plan 文件格式错误"}, ensure_ascii=False)

    if plan_data.get('plan_status') != 'pending':
        return json.dumps({
            "error": f"plan 当前状态为 '{plan_data.get('plan_status')}'，仅 'pending' 状态可激活"
        }, ensure_ascii=False)

    # 更新文件状态
    plan_data['plan_status'] = 'in_progress'
    plan_data['update_time'] = datetime.now().strftime('%Y%m%d_%H%M%S')
    plan_path.write_text(
        json.dumps(plan_data, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    # 初始化 session 中的 Plan 对象并切换 mode
    if session:
        session._plan_init(plan_file)

    return json.dumps({
        "result": f"plan '{plan_data['plan_title']}' 已进入执行模式",
        "plan_title": plan_data['plan_title'],
        "plan_status": "in_progress",
        "system_prompt": "plan 已激活，请结束本轮对话。系统将自动读取 plan 的下一个 step 并继续执行。"
    }, ensure_ascii=False)
