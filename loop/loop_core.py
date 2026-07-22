import json

from openai.types.chat import ChatCompletionMessage


from rich_output import rich_print
from .orchestrator import PlanRunner


# 模型 API 调用失败（网络、限流、余额不足等），由 loop_run 统一兜底，不炸穿 main.py
class LoopAPIError(Exception):
    pass


# 纯 ReAct 推理引擎：main agent 与 subagent 共用，对 plan 编排零感知
class Loop:

    def __init__(self,agents=None,session=None,hooks=None,verbose:bool=True,memory=None):
        self.agents = agents
        self.session = session
        self.hooks = hooks
        self.memory = memory
        # 控制 thinking 类内容是否打印到终端；memory 等后台管线复用的 Loop 可传 False 静音
        self.verbose = verbose


    # 从 agents 容器中取出指定 agent
    def _get_agent(self,agent_name:str):
        return self.agents.agents[agent_name]


    # 兼容不同 provider 下 reasoning_content 字段可能不存在的情况
    def _get_reasoning(self,message:ChatCompletionMessage)->str:
        return getattr(message,'reasoning_content',None) or ''


    # 统一 LLM 调用：with_tools 决定是否携带 tools 与 thinking
    # API 调用失败（余额不足/网络/限流等）在此翻译成 LoopAPIError，由 loop_run 统一兜底
    def _chat(self,agent,with_tools:bool)->ChatCompletionMessage:
        params = {'model':agent.model_name,'messages':agent.message_list}
        if with_tools:
            params['tools'] = agent.tool_list
            params['tool_choice'] = 'auto'
            params['extra_body'] = {'thinking':{'type':'enabled'}}
        try:
            return agent.agent_ai.chat.completions.create(**params).choices[0].message
        except Exception as ee:
            rich_print(message=f'模型调用失败：{ee}',type='system_error')
            raise LoopAPIError(str(ee)) from ee


    # pre_toolUse hooks 处理，返回需透传给工具的非 JSON 参数
    # @claude 后续钩子需要都合并到hooks下进行解耦，先记录
    def _pre_tool_use_hooks(self,tool_name:str,tool_args:dict)->dict:
        extra_args = {}
        if not self.hooks:
            return extra_args

        results = self.hooks.trigger(
            hook_point='pre_toolUse',
            match_ctx={'tool':tool_name},
            session = self.session,
            agents = self.agents,
            hooks = self.hooks,
            Loop = Loop,
            memory = self.memory,
            tool_args = dict(tool_args)
        )

        for hr in results:
            if hr.block:
                continue
            if hr.modify_input:
                # 可 JSON 序列化的值改写 tool_args，其余走 extra_args 直传工具
                for k,v in hr.modify_input.items():
                    if isinstance(v, (str, int, float, bool, list, dict, type(None))):
                        tool_args[k] = v
                    else:
                        extra_args[k] = v

        return extra_args


    # 发送消息：拼 user 消息→调 LLM→写回 message_list→按需写 session
    # attachment 只拼进模型可见的 message_list，不落盘、不还原：一旦发出去的历史字节
    # 改动会破坏 provider 的 prompt cache 前缀，所以宁可让它留在历史里，也不事后改写
    def _sent_message_api(self,agent,message_content:str=None)->ChatCompletionMessage:
        if message_content:
            model_content = message_content
            if self.session and self.session.attachment.attachment_list:
                model_content = f'{self.session.attachment.attachment_render()}\n\n{message_content}'
                self.session.attachment.attachment_clear()

            agent.message_list.append({'role':'user','content':model_content})
            if self.session:
                self.session.session_message_insert(role='user',content=message_content)

        try:
            agent_rq = self._chat(agent,with_tools=True)
        except LoopAPIError:
            # 失败时弹出刚 append 的 user 消息，避免下一轮出现连续两条 user 消息
            if message_content:
                agent.message_list.pop()
            raise
        agent.message_list.append(agent_rq)

        if self.session:
            if agent_rq.tool_calls:
                self.session.session_message_insert(role='assistant',content=self._get_reasoning(agent_rq))
                self.session.session_message_insert(role='tool_calls',content=json.dumps([tc.model_dump() for tc in agent_rq.tool_calls],ensure_ascii=False))
            else:
                self.session.session_message_insert(role='assistant',content=agent_rq.content)
        return agent_rq


    # 处理一批 tool_calls：解析参数→pre hook→调工具→写 session；返回本批是否发生 mode 切换
    # 不信任提示词自觉性，靠 diff session.mode 判断 plan_mode_on/off 是否真的生效
    def _tool_calls_api(self,agent,tool_calls)->bool:
        mode_switched = False

        for func in tool_calls:
            # mode 已切换后剩余并行调用不再执行，但 openai 要求每个 tool_call_id 都有 tool 回复
            if mode_switched:
                tool_result = {
                    'role':'tool',
                    'tool_call_id':func.id,
                    'content':json.dumps({'skipped':'plan 模式已在本轮切换，系统跳过本轮其余工具调用'},ensure_ascii=False)
                }
            else:
                tool_name = func.function.name
                # 参数必须先还原为 JSON object；解析失败不能伪装成空参数继续执行工具
                try:
                    tool_args = json.loads(func.function.arguments)
                except (json.JSONDecodeError, TypeError) as ee:
                    tool_result = {
                        'role':'tool',
                        'tool_call_id':func.id,
                        'content':json.dumps({
                            'error':'invalid_tool_arguments',
                            'message':f'工具参数不是合法 JSON：{ee}。请修正参数后重新调用。'
                        },ensure_ascii=False)
                    }
                else:
                    # null、数组、字符串等合法 JSON 值也不能作为函数参数映射
                    if not isinstance(tool_args,dict):
                        tool_result = {
                            'role':'tool',
                            'tool_call_id':func.id,
                            'content':json.dumps({
                                'error':'invalid_tool_arguments',
                                'message':'工具参数必须是 JSON object，请修正参数后重新调用。'
                            },ensure_ascii=False)
                        }
                    else:
                        try:
                            extra_args = self._pre_tool_use_hooks(tool_name, tool_args)
                            func.function.arguments = json.dumps(tool_args,ensure_ascii=False)

                            # 调用前后 diff mode，判断此次调用是否为 plan_mode_on/off
                            mode_before = self.session.mode if self.session else None
                            tool_result = agent.match_tool(func,verbose=self.verbose,**extra_args)
                            if self.session and self.session.mode != mode_before:
                                mode_switched = True
                        except Exception as ee:
                            # 单个工具失败仍返回同一 tool_call_id，避免异常打断整批调用和后续重试
                            tool_result = {
                                'role':'tool',
                                'tool_call_id':func.id,
                                'content':json.dumps({
                                    'error':'tool_execution_error',
                                    'message':f'工具执行失败：{type(ee).__name__}: {ee}。请根据错误修正后重试。'
                                },ensure_ascii=False)
                            }

            agent.message_list.append(tool_result)
            if self.session:
                self.session.session_message_insert(role='tool_result',content=json.dumps(tool_result,ensure_ascii=False))

        return mode_switched


    # 强制收尾：不传 tools，模型物理上拿不到工具，只能吐文本；可选先弹出末尾 tool_calls
    def _force_final_reply(self,agent,notice:str,drop_last_toolcalls:bool=False)->str:
        if drop_last_toolcalls and agent.message_list and getattr(agent.message_list[-1],'tool_calls',None):
            agent.message_list.pop()

        agent.message_list.append({'role':'user','content':notice})
        if self.session:
            self.session.session_message_insert(role='user',content=notice)
        try:
            final_rq = self._chat(agent,with_tools=False)
        except LoopAPIError:
            # 失败时弹出刚 append 的 notice 消息，避免下一轮出现连续两条 user 消息
            agent.message_list.pop()
            raise
        agent.message_list.append(final_rq)

        if self.session:
            if self.verbose:
                rich_print(message=self._get_reasoning(final_rq),type='agent_thinking')
            self.session.session_message_insert(role='assistant',content=final_rq.content or '')
        return final_rq.content


    # 结束一轮：重置计数并递增 session.round
    def _close_round(self):
        if self.session:
            self.session.round += 1


    # 引擎入口：发首条消息，进入 ReAct 工具循环直到出结果或达上限
    def run_turn(self,agent,message:str=None)->str:
        agent_rq = self._sent_message_api(agent=agent,message_content=message)
        tool_call = 0

        while tool_call < agent.max_toolcalls:
            think_type = 'agent_thinking' if agent.agent_name=='main' else 'subagent_thinking'

            # 无 tool_calls 即本轮收尾：有内容返回内容，无内容返回空串（不再空转死循环）
            if not agent_rq.tool_calls:
                if self.verbose:
                    rich_print(message=self._get_reasoning(agent_rq),type=think_type)
                self._close_round()
                return agent_rq.content or ''

            tool_call += 1
            if self.verbose:
                rich_print(message=self._get_reasoning(agent_rq),type=think_type)

            # 执行工具调用 + 通过 diff session.mode 检测模式是否真的切换（不信任提示词自觉性）
            mode_switched = self._tool_calls_api(agent=agent,tool_calls=agent_rq.tool_calls)

            # plan_mode_on/off 生效后代码层强制结束本轮，不再给模型可调工具的机会
            if mode_switched:
                self._close_round()
                return self._force_final_reply(agent=agent,notice='系统提示：plan 模式已切换，本轮对话到此结束，请直接回复，不要调用任何工具')

            agent_rq = self._sent_message_api(agent=agent)

        # 达到工具调用上限，强制无 tools 收尾
        rich_print(message='tool_call over max...', type='system_message')
        self._close_round()
        return self._force_final_reply(agent=agent,notice='系统提示：已达到工具调用次数上限，请根据已有信息进行回复',drop_last_toolcalls=True)


    # 对外入口：解析 agent（agent 实例或 agent_name 二选一）→跑一轮→plan 编排→触发 after_round hook
    # 模型 API 失败在此统一兜底：本轮提前结束，不炸穿 main.py 的顶层循环
    def loop_run(self,agent = None,agent_name:str=None,message:str=None):
        agent = agent if not agent_name else self._get_agent(agent_name=agent_name)
        try:
            result = self.run_turn(agent=agent,message=message)

            # plan 模式则进入分步编排，是否真跑由 PlanRunner 内部判断；after_round 之前完成以保原切片时机
            plan_result = PlanRunner(loop=self,session=self.session).run(agent=agent)
            if plan_result is not None:
                result = plan_result
        except LoopAPIError as ee:
            result = f'[系统错误] 模型调用失败，本轮未完成：{ee}'
            if self.session:
                self.session.round += 1

        # @claude bug:loop_run 用 if self.session 当打印 agent_content 的条件不精确
        # memory agent 复用全局 loop 也带 session,后台记忆提炼 JSON 被误打印成主回复干扰用户
        # plan/subagent 仅因用无 session 新 Loop 巧合未暴露;修复:条件改为 agent.agent_name=='main'
        # 测试阶段暂不修--需要观察各 subagent 产出,测试结束再收口
        if self.session:
            rich_print(message=result,type='agent_content')

        return result
