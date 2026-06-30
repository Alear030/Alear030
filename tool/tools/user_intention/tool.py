import os
import json

from dotenv import load_dotenv
from rich_output import rich_print
from tool.tool_core import register_tool
from json import JSONDecodeError
from openai import OpenAI
from pathlib import Path

load_dotenv()

rounter_prompt = """
你是一个意图识别器，依据输入的关键词判断用户意图，输出JSON格式内容

## 意图分类 P0 - P1

 ### 意图P1 状态查询

 - 场景：用户询问当前项目、任务的状态、进展  
 - 激活词包含不限于：当前任务怎么样了、做到哪了、什么阶段了  

 ### 意图P2 新任务

 - 场景：用户提出新的需求，设定新的目标  
 - 激活词包含不限于：设计一个新功能、我有一个想法、新任务、我给你一个新任务

 ### 意图P3 继续推进

 - 场景：用户希望继续推进任务进度时  
 - 激活词包含不限于：继续、可以、往下进行、接着弄

 ### 意图P4 修改/纠正

 - 场景：用户对当前产出、交付、结果不满意，要进行调整或者指导  
 - 激活词包含不限于：不行、重新弄、不太好、再来吧

 ### 意图5 直接命令
 - 场景：用户明确说要进行哪个节点的任务，或者进行什么样的流程  
 - 激活词包含不限于：进行节点1、进行节点3、执行节点1、2、3、给我写一个prd

 ### 意图6 无法判断
 - 场景：无法判断用户到底是什么意图，和前序意图都不匹配时

## 原则

 - 判断用户意图不能只参考提供给你的激活词
 - 输出格式严格按照约束输出
 
## 推理步骤
 
 1. 用户说了什么？
 2. 触发了什么激活词？
 3. 如果没触发激活词，展开延伸含义匹配激活词
 4. 是否只含有一个激活词？如果有多个激活词，输出意图优先级：P5 > P1 >其他
 5. 输出

## 示例

 用户：现在进展到哪了？
 输出：{"intent": "P1 状态查询","key_word":'进展', "reason": "用户询问当前进展"}

 用户：分析一下这个页面 https://example.com
 输出：{"intent": "P2 新任务","key_word":'分析新系统',  "reason": "用户提供URL，要求分析新系统"}

 用户：继续吧
 输出：{"intent": "P3 继续推进","key_word":'继续推进',  "reason": "用户要求继续推进"}

 用户：这个不对，颜色换成蓝色  
 输出：{"intent": "P4 修改/纠正","key_word":'修改',  "reason": "用户指出错误并要求修改"}

 用户：帮我写PRD
 输出：{"intent": "P5 直接命令","key_word":'直接执行',  "reason": "用户直接指定节点功能"}

 用户：今天天气怎么样
 输出：{"intent": "P6 无法判断","key_word":None,  "reason": "无法匹配任何意图类型"}

## 输出格式

必须输出JSON格式内容，不可输出其他内容
{"intent":"P1 状态查询","key_word":"什么进展","reason":"用户询问进展，匹配相关激活词"}


"""

tool_desc = '用于对话或是执行任务之间分析用户意图'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8').strip()
    tool_prompt = tool_prompt_content if tool_prompt_content else None
else:
    tool_prompt = None


@register_tool(tool_name='user_intention',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=False,tool_autho='basic_tool')
def user_intention(user_content:str)->dict:
    print('\nuser_intentionsing....\n')
    print('\nuser_intention-s key_word is :'+user_content+'\n')
    user_intentions = []

    intention_ai = OpenAI(base_url=os.getenv('main_BASE_URL'),api_key=os.getenv('main_API_KEY'))
    intention_ai_masseges = []
    intention_ai_masseges.append({'role':'system','content':rounter_prompt})
    intention_ai_masseges.append({'role':'user','content':user_content})

    rq = intention_ai.chat.completions.create(
        model=os.getenv('SUBAGENT_MODEL_NAME'),
        messages=intention_ai_masseges
    )


    try:
        intention_ai_rq = json.loads(rq.choices[0].message.content)
    except JSONDecodeError as JE:
        return f'分析输出格式错误，错误原因:{JE}'
    
    user_intention_result = f'\n--- user intention_tool: 根据关键词{intention_ai_rq["key_word"]}分析，用户的意图是{intention_ai_rq["intent"]},原因是{intention_ai_rq["reason"]}----\n'

    rich_print(message=user_intention_result,type='tool_result')
    return f'根据关键词{intention_ai_rq["key_word"]}分析，用户的意图是{intention_ai_rq["intent"]},原因是{intention_ai_rq["reason"]}'