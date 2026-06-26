import json

from openai import OpenAI
from openai.types.chat import ChatCompletionMessage


from agent import Agent,main_agent,main_agent_ai
from .rich_output import rich_print
from config import MAX_TOOLCALLS
from session import session_message_insert

def _sent_message_api(agent:Agent,agent_ai:OpenAI,message_content:str=None,session_id:str=None,session_round:int=None)->ChatCompletionMessage:
    
    if message_content:
        agent.message_list.append({'role':'user','content':message_content})
        session_message_insert(session_id=session_id,role='user',message=message_content,session_round=session_round)

    agent_rq = agent_ai.chat.completions.create(
        model=agent.model_name,
        messages=agent.message_list,
        tools=agent.tool_list,
        tool_choice='auto',
        extra_body={'thinking':{'type':'enabled'}}
    ).choices[0].message
    main_agent.message_list.append(agent_rq)

    if agent_rq.tool_calls:
        session_message_insert(session_id=session_id,role='assistant',message=agent_rq.reasoning_content,session_round=session_round)
        session_message_insert(session_id=session_id,role='tool_calls',message=json.dumps([tool_call.model_dump() for tool_call in agent_rq.tool_calls],ensure_ascii=False),session_round=session_round)
    else:
        session_message_insert(session_id=session_id,role='assistant',message=agent_rq.content,session_round=session_round)
    
    return agent_rq


def _tool_call_api(agent:Agent,message:ChatCompletionMessage,session_id:str=None,session_round:int=None):

    for func in message:
        tool_result = agent.match_tool(func)
        agent.message_list.append(tool_result)
        session_message_insert(session_id=session_id,role='tool_result',message=json.dumps(tool_result,ensure_ascii=False),session_round=session_round)



def loop(session_id:str='',session_round:int=''):

    if session_round == 0:
        session_message_insert(session_id=session_id,role='system',message=main_agent.message_list[0]['content'],session_round=session_round)

    tool_call_max = MAX_TOOLCALLS
    tool_call = 0
    user_message = input('please enter your message: ')
    
    rq = _sent_message_api(agent=main_agent,agent_ai=main_agent_ai,message_content=user_message,session_id=session_id,session_round=session_round)

    while tool_call < tool_call_max:

        if rq.content and not rq.tool_calls:
            rich_print(message=rq.reasoning_content,type='agent_thinking')
            rich_print(message=rq.content,type='agent_content')
            return
        
        if rq.tool_calls:
            tool_call += 1
            rich_print(message=rq.reasoning_content,type='agent_thinking')
            _tool_call_api(agent=main_agent,message=rq.tool_calls,session_id=session_id,session_round=session_round)
            rq = _sent_message_api(agent=main_agent,agent_ai=main_agent_ai,session_id=session_id,session_round=session_round)
    
    if tool_call >= tool_call_max:
        rich_print(message='tool_call over max...',type='system_message')
        final_rq = _sent_message_api(agent=main_agent,agent_ai=main_agent_ai,message_content='系统提示：请根据已有信息进行回复',session_id=session_id,session_round=session_round)
        rich_print(message=final_rq.reasoning_content,type='agent_thinking')
        rich_print(message=final_rq.content,type='agent_content')
        return
