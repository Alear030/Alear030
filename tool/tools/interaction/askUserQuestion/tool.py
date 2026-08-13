import json

from pathlib import Path
from dataclasses import asdict
import queue

from tool.tool_core import register_tool,ToolCallResult


tool_prompt_file = Path(__file__).parent / 'tool_prompt.md'
tool_prompt = tool_prompt_file.read_text(encoding='utf-8').strip() if tool_prompt_file.exists() else None

question_excample = [
    {
        "header":"颜色偏好",
        "question":"你喜欢什么颜色？",
        "multi-option":True,
        "options":[
            {"label":"红色","description":"红色是喜庆的颜色"}, 
            {"label":"绿色","description":"绿色是希望的颜色"},
            {"label":"蓝色","description":"蓝色是冷静的颜色"}
        ],
        "answer":{
            "options":[
                {"label":"红色","description":"红色是喜庆的颜色"},
                {"label":"绿色","description":"绿色是希望的颜色"}
            ],
            "user_input":None
        }
    },
    {
        "header":"颜色原因",
        "question":"为什么你必须喜欢一个颜色？",
        "multi-option":False,
        "options":[
            {"label":"红色","description":"红色是喜庆的颜色"}, 
            {"label":"绿色","description":"绿色是希望的颜色"},
            {"label":"蓝色","description":"蓝色是冷静的颜色"}
        ],
        "answer":{
            "options":[
                {"label":"红色","description":"红色是喜庆的颜色"}
            ],
            "user_input":None
        }
    }
]

# 校验失败统一落 error 结果并 emit，返回 False 供调用方短路返回
def _question_error(tcr,error_key:str,message:str)->bool:
    tcr.tool_call_state = {'tool_call_state':'error'}
    tcr.tool_call_result = {'role':'tool','tool_call_id':tcr.tool_call_id,'content':json.dumps({'error':error_key,'message':message},ensure_ascii=False)}
    tcr.tool_call_extra_info = [{
        "id":"tool_call_error_info",
        "type":"Horizontal",
        "content":[
            {"id":"tool_call_error_info_pointer","type":"Static","content":"⎿","css":{"color":"rgba(255,255,255,0.5)","width":"2","height":"auto"}},
            {"id":"tool_call_error_info_message","type":"Static","content":message,"css":{"color":"rgba(255,255,255,0.5)","width":"100%","height":"auto"}}
        ],
        "css":{"width":"100%","height":"auto"}
    }]
    return False


# 校验 question_info：非空 list，每项结构能给 TUI 挂题
# 单/多选只认 multi-option（True=多选；缺省当单选）；user_input 为可选布尔
def _question_check(tcr,emit,question_info)->bool:
    # 空列表没有可展示内容
    if not isinstance(question_info,list) or not question_info:
        return _question_error(tcr,'invalid_question_info','question_info 必须是非空列表。')

    # 逐项：挡坏类型/空题干/错布尔，再强制非空 options
    for index,item in enumerate(question_info):
        if not isinstance(item,dict):
            return _question_error(tcr,'invalid_question_item',f'第{index+1}项必须是 dict 对象。')

        if not isinstance(item.get('question'),str) or not item['question'].strip():
            return _question_error(tcr,'invalid_question_text',f'第{index+1}项 question 必须是非空字符串。')

        # header 给多题 tab 用，缺了 TUI 只剩空 [ ]
        if not isinstance(item.get('header'),str) or not item['header'].strip():
            return _question_error(tcr,'invalid_question_header',f'第{index+1}项 header 必须是非空字符串。')

        # 写了 multi-option 就必须是 bool，避免模型塞字符串
        if 'multi-option' in item and not isinstance(item.get('multi-option'),bool):
            return _question_error(tcr,'invalid_question_multi_option',f'第{index+1}项 multi-option 必须是布尔值。')

        if 'user_input' in item and not isinstance(item['user_input'],bool):
            return _question_error(tcr,'invalid_question_user_input',f'第{index+1}项 user_input 必须是布尔值。')

        # options 是挂选项行的事实源，空则 TUI 无内容可点
        options = item.get('options')
        if not isinstance(options,list) or not options:
            return _question_error(tcr,'invalid_question_options',f'第{index+1}项必须提供非空 options 列表。')
        for option in options:
            if not isinstance(option,dict) or not isinstance(option.get('label'),str) or not option['label'].strip():
                return _question_error(tcr,'invalid_question_options',f'第{index+1}项 options 中每项都必须包含非空字符串 label。')
            if 'value' in option and not isinstance(option['value'],str):
                return _question_error(tcr,'invalid_question_options',f'第{index+1}项 options 中 value 必须是字符串。')

    return True

# done(@claude): 重写 tool_prompt（硬契约+场景教导）并同步 tool_desc 支持多题
@register_tool(
    tool_name='ask_user_question',
    tool_desc='当任务缺少会实质改变后续路径的用户目标、偏好或取舍时，向用户发起一个或多个问题并等待结构化回答。',
    tool_prompt=tool_prompt,
    tool_enabled=True,
    tool_autho='interaction_tool'
)
def ask_user_question(question_info:list[dict],**kwargs)->ToolCallResult:

    emit = kwargs.get('emit',None)
    tcr = kwargs.get('tcr',None)

    if tcr is None:
        return 'ask_user_question 缺少 tcr 注入，请告知Alear030大人进行修复'

    # 对question_info进行校验，失败则返回错误信息
    if not _question_check(tcr,emit,question_info):
        if emit:
            emit(content=asdict(tcr))
        return tcr

    # 创建一个队列，用于TUI和tool之间通信 并发送给TUI 阻塞等待用户回答
    ask_user_question_queue = queue.Queue()
    emit(
        event = "AskUserQuestion",
        content = {
            "question_info":question_info,
            "queue":ask_user_question_queue
        }
    )
    final_answer = ask_user_question_queue.get()

    # 如果用户未回答问题，则返回错误信息
    if not final_answer:
        tcr.tool_call_state = {'tool_call_state':'error'}
        tcr.tool_call_result = {'role':'tool','tool_call_id':tcr.tool_call_id,'content':json.dumps({'error':'no_answer','message':'用户未回答问题'},ensure_ascii=False)}
    else:
        tcr.tool_call_state = {'tool_call_state':'success'}
        tcr.tool_call_result = {'role':'tool','tool_call_id':tcr.tool_call_id,'content':json.dumps(final_answer,ensure_ascii=False)}

    if emit:
        emit(content=asdict(tcr))

    return tcr    