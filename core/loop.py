import json

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage

from session import Session
from .rich_output import rich_print

def _sent_message_api(agent,agent_ai:OpenAI,message_content:str=None,session:Session=None)->ChatCompletionMessage:
    
    if message_content:
        agent.message_list.append({'role':'user','content':message_content})
        session.session_message_insert(role='user',content=message_content)
        # session_message_insert(session_id=session_id,role='user',message=message_content,session_round=session_round)

    agent_rq = agent_ai.chat.completions.create(
        model=agent.model_name,
        messages=agent.message_list,
        tools=agent.tool_list,
        tool_choice='auto',
        extra_body={'thinking':{'type':'enabled'}}
    ).choices[0].message
    agent.message_list.append(agent_rq)

    if agent_rq.tool_calls:
        session.session_message_insert(role='assistant',content=agent_rq.reasoning_content)
        session.session_message_insert(role='tool_calls',content=json.dumps([tool_call.model_dump() for tool_call in agent_rq.tool_calls],ensure_ascii=False))
    else:
        session.session_message_insert(role='assistant',content=agent_rq.content)    
    return agent_rq


def _tool_call_api(agent,message:ChatCompletionMessage,session:Session,agents=None,hooks=None):

    for func in message:
        tool_name = func.function.name
        tool_args = json.loads(func.function.arguments)
        extra = {}

        if hooks and agents:
            results = hooks.trigger(
                hook_point = 'pre_toolUse',
                match_ctx = {'tool':tool_name},
                session=session,
                agents=agents,
                tool_args=dict(tool_args)
            )
            for hr in results:
                if hr.block:
                    continue
                if hr.modify_input:
                    for key,value in hr.modify_input.items():
                        if isinstance(value,(str,int,float,bool,list,dict,type(None))):
                            tool_args[key] = value
                        else:
                            extra[key] = value

            func.function.arguments = json.dumps(tool_args,ensure_ascii=False)

        tool_result = agent.match_tool(func,**extra)
        agent.message_list.append(tool_result)
        session.session_message_insert(role='tool_result',content=json.dumps(tool_result,ensure_ascii=False))


def loop(session:Session,user_message:str,agents,hooks):

    # 处理session相关的数据
    session_round = session.round

    # 创建mainagentai
    main_agent = agents.agents['main']
    main_agent_ai = agents.agents['main'].agent_ai

    # 初始化相关的数据
    tool_call = 0

    if session_round == 0:
        session.session_message_insert(role='system',content=main_agent.message_list[0]['content'])

    
    rq = _sent_message_api(agent=main_agent,agent_ai=main_agent_ai,message_content=user_message,session=session)

    while tool_call < main_agent.max_toolcalls:

        if rq.content and not rq.tool_calls:
            rich_print(message=rq.reasoning_content,type='agent_thinking')
            rich_print(message=rq.content,type='agent_content')
            return
        
        if rq.tool_calls:
            tool_call += 1
            rich_print(message=rq.reasoning_content,type='agent_thinking')
            _tool_call_api(agent=main_agent,message=rq.tool_calls,session=session,agents=agents,hooks=hooks)
            rq = _sent_message_api(agent=main_agent,agent_ai=main_agent_ai,session=session)
    
    if tool_call >= main_agent.max_toolcalls:
        rich_print(message='tool_call over max...',type='system_message')
        # 超限后如果最后一条消息还有 tool_calls，pop 掉避免 API 400
        if rq.tool_calls:
            main_agent.message_list.pop()
        # 运行时指令，只写 message_list 不写 session，避免污染对话历史
        main_agent.message_list.append({'role':'user','content':'系统提示：已达到工具调用次数上限，请根据已有信息进行回复'})
        # 不带 tools 调 API，杜绝再次返回 tool_calls
        final_rq = main_agent_ai.chat.completions.create(
            model=main_agent.model_name,
            messages=main_agent.message_list,
        ).choices[0].message
        main_agent.message_list.append(final_rq)
        session.session_message_insert(role='assistant',content=final_rq.content)
        rich_print(message=final_rq.reasoning_content,type='agent_thinking')
        rich_print(message=final_rq.content,type='agent_content')
        return
