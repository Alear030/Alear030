import json

from openai.types.chat import ChatCompletionMessage


from rich_output import rich_print


class Loop:

    # 初始化loop
    def __init__(self,agents=None,session=None,hooks=None):
        # 基础三要素
        self.agents = agents
        self.session = session
        self.hooks = hooks

        # 其余信息
        self.tool_call = 0


    # 从agents中抽离agent
    def _get_agent(self,agent_name:str):
        return self.agents.agents[agent_name]
    

    # 发送消息
    def _sent_message_api(self,agent,message_content:str=None)->ChatCompletionMessage:
        # 判断message_content非空 判断agent类型 信息拼入message_list 并判断是否需要插入session_detail
        if message_content:
            agent.message_list.append({'role':'user','content':message_content})
            if self.session:
                self.session.session_message_insert(role='user',content=message_content)
        
        # 发送llm消息请求
        agent_rq = agent.agent_ai.chat.completions.create(
            model=agent.model_name,
            messages=agent.message_list,
            tools=agent.tool_list,
            tool_choice='auto',
            extra_body={'thinking':{'type':'enabled'}}
        ).choices[0].message

        # 将消息拼回message_list
        agent.message_list.append(agent_rq)
        # 将消息插入session
        if self.session != None:
            if agent_rq.tool_calls:
                self.session.session_message_insert(role='assistant',content=agent_rq.reasoning_content)
                self.session.session_message_insert(role='tool_calls',content=json.dumps([tool_call.model_dump() for tool_call in agent_rq.tool_calls],ensure_ascii=False))
            else:
                self.session.session_message_insert(role='assistant',content=agent_rq.content)    
        return agent_rq

    
    # 处理toolcalls
    def _tool_calls_api(self,agent,tool_calls):

        # 遍历toolcalls 处理pre_toolUse hooks → 调用工具 → 写入session
        for func in tool_calls:

            # 获取每个func的基础信息
            tool_name = func.function.name
            tool_args = json.loads(func.function.arguments)
            extra_args = {}

            # pre_toolUse hooks 处理
            if self.hooks:
                results = self.hooks.trigger(
                    hook_point='pre_toolUse',
                    match_ctx={'tool':tool_name},
                    session = self.session,
                    agents = self.agents,
                    tool_args = dict(tool_args)
                )

                # 处理每个hook result 返回的结果
                for hr in results:
                    if hr.block:
                        continue
                    if hr.modify_input:
                        # 判断是否是能够进行json解析的参数类型，如果不能则直传
                        for k,v in hr.modify_input.items():
                            if isinstance(v, (str, int, float, bool, list, dict, type(None))):
                                tool_args[k] = v
                            else:
                                extra_args[k] = v

                # 将得到的结果返回赋值到func的参数上
                func.function.arguments = json.dumps(tool_args,ensure_ascii=False)
            
            # 得到一个tool的调用结果，拼入messagelist和sessiondetail
            tool_result = agent.match_tool(func,**extra_args)
            agent.message_list.append(tool_result)

            # 判断是否传入session
            if self.session:
                self.session.session_message_insert(
                    role='tool_result',
                    content=json.dumps(tool_result,ensure_ascii=False)
                )


    # 处理maxtoolcall超出的情况
    def _handle_overrun(self,agent,last_rq:ChatCompletionMessage):
        rich_print(message='tool_call over max...', type='system_message')

        # 判断最后的一次调用是否存在toolcalls,存在就pop出去
        if last_rq.tool_calls:
            agent.message_list.pop()
        
        # 拼接系统提示进入messagelist
        agent.message_list.append({'role':'user','content':'系统提示：已达到工具调用次数上限，请根据已有信息进行回复'})
        
        # 进行最后的一轮对话，不传入tools，并将message拼入agent的messagelist
        final_agent_rq = agent.agent_ai.chat.completions.create(
            model=agent.model_name,
            messages=agent.message_list
        ).choices[0].message
        agent.message_list.append(final_agent_rq)

        # 判断是否传入session 决定是否insert session 以及输出
        if self.session:
            rich_print(message=final_agent_rq.reasoning_content,type='agent_thinking')
            rich_print(message=final_agent_rq.content,type='agent_content')
            self.session.session_message_insert(role='assistant',content=final_agent_rq.content or '')

        return final_agent_rq.content if agent.agent_name != 'main' else None
    

    # loop入口
    def _normal_loop(self,agent_name:str,message:str=None):
        # 取出agent
        agent = self._get_agent(agent_name=agent_name)

        # 判断是否是第一轮对话，如果是session插入system_prompt信息 并且判断是否传入session
        if self.session and self.session.round == 0:
            self.session.session_message_insert(role='system',content=agent.message_list[0]['content'])

        # 首轮循环发送信息
        agent_rq = self._sent_message_api(agent=agent,message_content=message)

        # 进入toolcalls循环
        while self.tool_call < agent.max_toolcalls:
            
            # 循环未超出maxtoolcall 同时信息没有toolcall
            if not agent_rq.tool_calls and agent_rq.content:
                # 重置toolcall 增加session_round
                self.tool_call = 0
                if self.session:
                    self.session.round += 1

                # 判断是否传入session 如果是则直接对话，如果不是则返回最终结果
                rich_print(message=agent_rq.reasoning_content,type='agent_thinking' if agent.agent_name=='main' else 'subagent_thinking')
                if self.session:
                    rich_print(message=agent_rq.content,type='agent_content')
                    return
                else:
                    return agent_rq.content
                
            # 循环未超出maxtoolcall，同时信息有toolcall，进行处理
            if agent_rq.tool_calls:
                self.tool_call += 1
                rich_print(message=agent_rq.reasoning_content,type='agent_thinking' if agent.agent_name=='main' else 'subagent_thinking')
                self._tool_calls_api(agent=agent,tool_calls=agent_rq.tool_calls)
                agent_rq = self._sent_message_api(agent=agent)

        # 循环超出maxtoolcall处理
        if self.tool_call >= agent.max_toolcalls:

            # 重置toolcall 增加session_round
            self.tool_call = 0

            if self.session:
                self.session.round += 1

            final_rq = self._handle_overrun(agent=agent,last_rq=agent_rq)
            return final_rq
        
    def loop_run(self,agent_name:str,message:str=None):
        
        self._normal_loop(agent_name='main',message=message)

    