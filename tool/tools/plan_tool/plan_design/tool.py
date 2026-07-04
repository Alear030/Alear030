import json

from pathlib import Path
from datetime import datetime


from config import SESSION_PLAN_FILE_PATH,WORK_SPACE
from tool.tool_core import register_tool
from loop import Loop


# 设置tool的基本描述和prompt信息
tool_desc = '用于制定分步执行计划，将复杂任务拆解为可执行的步骤序列。调用前必须先收集信息、对齐目标、获得用户确认。'
tool_prompt_file = Path(__file__).parent / 'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt = tool_prompt_file.read_text(encoding='utf-8').strip()
else:
    tool_prompt = None


# 写入plan文件方法
def _plan_write(plan_title, plan_json, plan_file: Path, output_file: Path):
    # 确保session_plan文件夹存在
    SESSION_PLAN_FILE_PATH.mkdir(parents=True, exist_ok=True)

    # 确保产出物目录存在
    output_file.mkdir(parents=True, exist_ok=True)

    # 读取现有 created_time（修改模式时保留）
    created_time = datetime.now().strftime('%Y%m%d_%H%M%S')
    if plan_file.exists():
        try:
            existing = json.loads(plan_file.read_text(encoding='utf-8'))
            created_time = existing.get('created_time', created_time)
        except (json.JSONDecodeError, Exception):
            pass

    plan_detail = {
        "plan_title": plan_title,
        "plan_status": "pending",
        "created_time": created_time,
        "update_time": datetime.now().strftime('%Y%m%d_%H%M%S'),
        "output_file": str(output_file),
        "plan_steps": [
            {
                "step_number": s.get("step_number", i + 1),
                "description": s.get("description", ""),
                "acceptance_criteria": s.get("acceptance_criteria", ""),
                "status": "pending",
                "result": ""
            } for i, s in enumerate(plan_json)
        ]
    }

    # 将plan_detail写入session_plan中
    plan_file.write_text(
        json.dumps(plan_detail, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )


# 解析plan_content 是否为JSON格式
def _extract_json(text):
    """从 markdown 代码块或纯文本中提取 JSON，逐级尝试+验证"""
    import re
    text = text.strip()
    # 策略1: re.search 找代码块（不要求全字符串匹配）
    m = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
    if m:
        try:
            json.loads(m.group(1).strip())
            return m.group(1).strip()
        except json.JSONDecodeError:
            pass
    # 策略2: 找第一个 [ 到最后一个 ]
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass
    return text


@register_tool(tool_name='plan_design', tool_desc=tool_desc, tool_prompt=tool_prompt, tool_enabled=True, tool_autho='plan_tool')
def plan_design(plan_title: str, task_description: str, plan_file: str = None, output_file: str = None, agents=None, **kwargs):

    # 判断hook是否成功注入agents
    if agents is None:
        return json.dumps({"error": "plan_design tool调用失败:agents未被hook注入"}, ensure_ascii=False)
    plan_agent = agents.agents['plan']

    # 判断是否传入plan_file，如果没传入则写入新的文件，传了则为更改当前文件
    if plan_file:
        plan_path: Path = SESSION_PLAN_FILE_PATH / f'{plan_file}.json'
    else:
        plan_path: Path = SESSION_PLAN_FILE_PATH / f'{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'

    # plan_agent生成plan
    try:
        # 重置plan_agent的message_list，保留 system prompt，message 交给 Loop 拼接
        plan_agent.message_list = [plan_agent.message_list[0]]

        # 修改模式：读取已有 plan；新建模式：直接生成
        if plan_file:
            plan_content_now = json.loads(plan_path.read_text(encoding='utf-8'))
            user_content = json.dumps({"plan_title": plan_title, "plan_background": task_description, "plan_now": plan_content_now}, ensure_ascii=False)
            # output_file 未显式传入时，修改模式沿用已有产出物目录
            if not output_file:
                output_file = plan_content_now.get('output_file')
        else:
            user_content = json.dumps(
                {"plan_title": plan_title, "plan_description": task_description},
                ensure_ascii=False
            )

        # 未指定 output_file 时，默认落到 workspace/plan/{plan_title} 下
        output_path: Path = Path(output_file) if output_file else WORK_SPACE / 'plan' / plan_title

        # 用 Loop 跑 plan_agent 的 ReAct 循环
        loop = Loop(agents=agents)
        plan_content = loop.loop_run(agent_name='plan', message=user_content)
        plan_content_stripped = _extract_json(plan_content)

        try:
            plan_json = json.loads(plan_content_stripped)
        except json.JSONDecodeError:
            return json.dumps({
                "plan_error": "plan_agent 返回了非 JSON 格式内容，信息不足。请根据以下提示补充。",
                "plan_agent_response": plan_content
            }, ensure_ascii=False)

    except Exception as ee:
        return json.dumps({"error": f"plan_design tool调用失败:{ee}"}, ensure_ascii=False)

    # 写盘
    _plan_write(plan_title=plan_title, plan_json=plan_json, plan_file=plan_path, output_file=output_path)

    # 返回结果，区分新建和修改模式
    if plan_file:
        return json.dumps({"result": f"计划已修改，已写入 {plan_path}文件。产出物目录：{output_path}。请查看更新后的计划内容，确认符合预期后使用 plan_mode_on 工具进入执行模式。"}, ensure_ascii=False)
    else:
        return json.dumps({"result": f"计划已创建，已写入 {plan_path}文件。产出物目录：{output_path}。请查看计划内容并与用户确认，确认后使用 plan_mode_on 工具进入执行模式。"}, ensure_ascii=False)
