import json

from openai.types.chat import ChatCompletionMessage


from rich_output import rich_print
from session import Session


class Loop:

    # 初始化loop
    def __init__(self,agents=None,session:Session=None,hooks=None):
        # 基础三要素
        self.agents = agents
        self.session = session
        self.hooks = hooks

        # 其余信息
        self.tool_call = 0


    # 从agents中抽离agent
    def _get_agent(self,agent_name:str):
        return self.agents.agents[agent_name]


    # 兼容不同provider/调用路径下 reasoning_content 字段可能不存在的情况
    def _get_reasoning(self,message:ChatCompletionMessage)->str:
        return getattr(message,'reasoning_content',None) or ''
    

    # pre_toolUse hooks 处理
    def _pre_tool_use_hooks(self,tool_name:str,tool_args:dict)->dict:
        extra_args = {}

        if not self.hooks:
            return extra_args

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

        return extra_args


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
                self.session.session_message_insert(role='assistant',content=self._get_reasoning(agent_rq))
                self.session.session_message_insert(role='tool_calls',content=json.dumps([tool_call.model_dump() for tool_call in agent_rq.tool_calls],ensure_ascii=False))
            else:
                self.session.session_message_insert(role='assistant',content=agent_rq.content)
        return agent_rq


    # 处理toolcalls
    # 之前 plan_mode_on/off 切换后能不能停下来全靠 tool_prompt 里那句"调用后请立即结束本轮"，
    # agent 不听就没辙（实测过 agent 调完 plan_mode_on 还接着调 web_search 的情况）
    # 现在改成看 session.mode 有没有真的变化来判断，不再信任提示词自觉性
    # 返回值 mode_switched：本批次里是否发生了切换，_loop_enter 靠这个决定要不要提前收尾
    def _tool_calls_api(self,agent,tool_calls):
        mode_switched = False

        # 遍历toolcalls 处理pre_toolUse hooks → 调用工具 → 写入session
        for func in tool_calls:

            # 一次模型回复可能带多个并行 tool_calls，如果前面已经切换了 mode，
            # 后面几个就不能再真的执行了（比如切完 plan 又去跑 command）
            # 但 openai 接口要求每个 tool_call_id 都必须对应一条 tool 消息，不能直接跳过不回复，
            # 所以这里给个占位的 skipped 结果糊过去
            if mode_switched:
                tool_result = {
                    'role':'tool',
                    'tool_call_id':func.id,
                    'content':json.dumps({'skipped':'plan 模式已在本轮切换，系统跳过本轮其余工具调用'},ensure_ascii=False)
                }
            else:
                # 获取每个func的基础信息
                tool_name = func.function.name
                tool_args = json.loads(func.function.arguments)

                # pre_toolUse hooks 处理
                extra_args = self._pre_tool_use_hooks(tool_name, tool_args)
                func.function.arguments = json.dumps(tool_args,ensure_ascii=False)

                # 调用前先记一下 mode，调用后对比，判断这次调用是不是 plan_mode_on/off
                mode_before = self.session.mode if self.session else None

                # 得到一个tool的调用结果，拼入messagelist和sessiondetail
                tool_result = agent.match_tool(func,**extra_args)

                if self.session and self.session.mode != mode_before:
                    mode_switched = True

            agent.message_list.append(tool_result)

            # 判断是否传入session
            if self.session:
                self.session.session_message_insert(
                    role='tool_result',
                    content=json.dumps(tool_result,ensure_ascii=False)
                )

        return mode_switched


    # mode 切换后的强制收尾
    # 跟 _handle_overrun 的做法一样：不传 tools 参数，模型这轮物理上拿不到任何工具，
    # 只能吐文本回复，不会出现"又想调工具"的情况
    def _finalize_after_mode_switch(self,agent):
        agent.message_list.append({'role':'user','content':'系统提示：plan 模式已切换，本轮对话到此结束，请直接回复，不要调用任何工具'})

        final_agent_rq = agent.agent_ai.chat.completions.create(
            model=agent.model_name,
            messages=agent.message_list
        ).choices[0].message
        agent.message_list.append(final_agent_rq)

        if self.session:
            rich_print(message=self._get_reasoning(final_agent_rq),type='agent_thinking')
            self.session.session_message_insert(role='assistant',content=final_agent_rq.content or '')

        return final_agent_rq.content


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
            rich_print(message=self._get_reasoning(final_agent_rq),type='agent_thinking')
            self.session.session_message_insert(role='assistant',content=final_agent_rq.content or '')

        return final_agent_rq.content


    # Plan 模式：分步执行循环
    def _plan_loop(self,agent = None)->str:
        last_result = ""
        while True:
            # 防呆：如果 plan 被提前清空（如 agent 在 step 内提前调了 plan_mode_off），直接退出
            if not self.session or not self.session.plan:
                break
            # 刷新 plan 状态（plan_update 落盘后重新读取）
            self.session.plan._refresh()
            step = self.session.plan.first_step
            if step is None:
                # 所有 step 已执行完毕
                break

            # 锁定本轮唯一能被 plan_update 更新的 step
            # 之前没这个锁的时候，agent 有能力一轮里连续调 plan_update 把后面几个 step 一起标 done，等于跳过没执行
            self.session.plan.active_step_number = step.step_number

            user_msg = (
                f"系统提示：当前需要执行Plan Step {step.step_number}\n\n"
                f"{step.description}\n\n"
                f"验收标准：{step.acceptance_criteria}\n\n"
                f"产出物请放置于：{self.session.plan.output_file}\n\n"
                f"当前处于 plan 执行阶段。请执行此 step，完成后使用 plan_update 工具更新状态为 done 并记录结果。"
                f"注意：请勿自行调用 plan_mode_off，等待所有 step 执行完毕后系统会自动提示使用此工具。"
                f"注意：本轮循环使用plan_update需要严格执行仅更新本轮系统提示step，不可连续调用更新其他非本轮系统提示step\n\n"
                f"提示：如果本 step 可拆解为多个互相独立、不依赖彼此结果的子任务，可考虑使用 subagent_create 并行处理；否则直接执行，无需强行拆分。"
            )
            last_result = self._loop_enter(agent=agent,message=user_msg)

        # 全部完成→提示 agent 调用 plan_mode_off 收尾
        if self.session and self.session.plan:
            final_msg = "系统提示：所有 Plan Step 已执行完毕，请调用 plan_mode_off 结束 plan 模式。"
            result = self._loop_enter(agent=agent,message=final_msg)
            return result
        return last_result


    # loop入口
    def _loop_enter(self,agent:str,message:str=None):
        # 取出agent
        agent = agent

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
                rich_print(message=self._get_reasoning(agent_rq),type='agent_thinking' if agent.agent_name=='main' else 'subagent_thinking')
                return agent_rq.content

            # 循环未超出maxtoolcall，同时信息有toolcall，进行处理
            if agent_rq.tool_calls:
                self.tool_call += 1
                rich_print(message=self._get_reasoning(agent_rq),type='agent_thinking' if agent.agent_name=='main' else 'subagent_thinking')
                mode_switched = self._tool_calls_api(agent=agent,tool_calls=agent_rq.tool_calls)

                # plan_mode_on/off 生效后，代码层强制结束本轮，不再给模型可调用工具的机会
                if mode_switched:
                    self.tool_call = 0
                    if self.session:
                        self.session.round += 1
                    return self._finalize_after_mode_switch(agent=agent)

                agent_rq = self._sent_message_api(agent=agent)

        # 循环超出maxtoolcall处理
        if self.tool_call >= agent.max_toolcalls:

            # 重置toolcall 增加session_round
            self.tool_call = 0

            if self.session:
                self.session.round += 1

            final_rq = self._handle_overrun(agent=agent,last_rq=agent_rq)
            return final_rq

    def loop_run(self,agent = None,agent_name:str=None,message:str=None):

        agent = agent if not agent_name else self._get_agent(agent_name=agent_name)
        result = self._loop_enter(agent=agent,message=message)

        # Plan 模式：主循环结束后进入 step 分步执行循环
        if self.session and self.session.mode == 'plan' and self.session.plan:
            result = self._plan_loop(agent=agent)

        if self.hooks:
            self.hooks.trigger(hook_point='after_round',session=self.session,agents=self.agents)
            self.hooks.collect()

        if self.session:
            rich_print(message=result,type='agent_content')

        return result
