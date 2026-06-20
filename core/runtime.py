from .agent import Agent,main_agent,main_agent_ai
from openai import OpenAI
from .rich_output import rich_print
from openai.types.chat import ChatCompletionMessage

def _sent_message_api(agent:Agent,agent_ai:OpenAI,message_content:str)->ChatCompletionMessage:
    agent.message_list.append({'role':'user','content':message_content})

    agent_rq = agent_ai.chat.completions.create(
        model=agent.model_name,
        messages=agent.message_list,
        tools=agent.tool_list,
        tool_choice='auto',
        extra_body={'thinking':{'type':'enabled'}}
    ).choices[0].message
    main_agent.message_list.append(agent_rq)
    return agent_rq

def _tool_call_api(agent:Agent,message:ChatCompletionMessage):
    for func in message:
        tool_result = agent.match_tool(func)
        agent.message_list.append(tool_result)

def loop():
    tool_call_max = 10
    tool_call = 1
    user_message = input('please enter your message: ')

    while tool_call < tool_call_max:

        rq = _sent_message_api(agent=main_agent,agent_ai=main_agent_ai,message_content=user_message)

        if rq.content and not rq.tool_calls:
            rich_print(message=rq.reasoning_content,type='agent_thinking')
            rich_print(message=rq.content,type='agent_content')
            return
        
        if rq.tool_calls:
            tool_call += 1
            rich_print(message=rq.reasoning_content,type='agent_thinking')
            _tool_call_api(agent=main_agent,message=rq.tool_calls)
    
    if tool_call >= tool_call_max:
        rich_print(message='tool_call over max...',type='system_message')
        final_rq = _sent_message_api(agent=main_agent,agent_ai=main_agent_ai,message_content='系统提示：请根据已有信息进行回复')
        rich_print(message=final_rq.reasoning_content,type='agent_thinking')
        rich_print(message=final_rq.content,type='agent_content')
        return







