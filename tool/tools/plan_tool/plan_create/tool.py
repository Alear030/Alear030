import json

from pathlib import Path
from datetime import datetime


from config import SESSION_PLAN_FILE_PATH
from tool.tool_core import register_tool
from loop import Loop


# 设置tool的基本描述和prompt信息
tool_desc = '用于制定分步执行计划，将复杂任务拆解为可执行的步骤序列。调用前必须先收集信息、对齐目标、获得用户确认。'
tool_prompt_file = Path(__file__).parent / 'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt = tool_prompt_file.read_text(encoding='utf-8').strip()
else:
    tool_prompt = None


@register_tool(tool_name='plan_create',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='advance_tool')
def plan_create(plan_title:str,task_description:str,agents=None):

    # 判断hook是否成功注入agents
    if agents is None:
        return json.dumps({"error":"plan_create tool调用失败:agents未被hook注入"},ensure_ascii=False)
    plan_agent = agents.agents['plan']

    # plan_agent生成plan
    try:
        # 重置plan_agent的message_list，保留 system prompt，message 交给 Loop 拼接
        plan_agent.message_list = [plan_agent.message_list[0]]
        user_content = json.dumps(
            {"plan_title": plan_title, "plan_background": task_description},
            ensure_ascii=False
        )

        # 用 Loop 跑 plan_agent 的 ReAct 循环
        loop = Loop(agents=agents)
        plan_content = loop.loop_run(agent_name='plan', message=user_content)

        # 解析plan_content 是否为JSON格式
        def _extract_json(text):
            """从 markdown 代码块或纯文本中提取 JSON"""
            import re
            text = text.strip()
            m = re.match(r'^```(?:json)?\s*\n(.*?)\n```$', text, re.DOTALL)
            if m:
                return m.group(1).strip()
            # 尝试从文本中找到第一个 [ 到最后一个 ]
            start = text.find('[')
            end = text.rfind(']')
            if start != -1 and end != -1 and end > start:
                return text[start:end + 1]
            return text

        plan_content_stripped = _extract_json(plan_content)
        try:
            plan_json = json.loads(plan_content_stripped)
        except json.JSONDecodeError:
            return plan_content
        
    except Exception as ee:
        return json.dumps({"error":f"plan_create tool调用失败:{ee}"},ensure_ascii=False)
    
    # 确保session_plan文件夹存在
    SESSION_PLAN_FILE_PATH.mkdir(parents=True,exist_ok=True)

    # 解析plan_content
    plan_detail = {
        "plan_title":plan_title,
        "plan_status":"pending",
        "created_time":datetime.now().strftime('%Y%m%d_%H%M%S'),
        "update_time":datetime.now().strftime('%Y%m%d_%H%M%S'),
        "plan_steps":[
            {
                "step_number": s.get("step_number", i + 1),
                "description": s.get("description", ""),
                "acceptance_criteria": s.get("acceptance_criteria", ""),
                "status": "pending",
                "result": ""
            } for i,s in enumerate(plan_json)
        ]
    }

    # 将plan_detail写入session_plan中
    plan_file = SESSION_PLAN_FILE_PATH/f"{plan_detail['created_time']}.json"
    plan_file.write_text(
        json.dumps(plan_detail,ensure_ascii=False,indent=2),
        encoding='utf-8'
    )

    # 返回最终plan_create的结果
    tool_result = json.dumps({"result":f"计划创建成功，已写入{plan_file}文件"})
    return tool_result