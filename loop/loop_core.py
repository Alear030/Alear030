import json

from time import perf_counter

from openai.types.chat import ChatCompletionMessage

from .orchestrator import PlanRunner


# 模型 API 调用失败（网络、限流、余额不足等），由 loop_run 统一兜底，不炸穿 main.py
class LoopAPIError(Exception):
    pass


# 纯 ReAct 推理引擎：main agent 与 subagent 共用，对 plan 编排零感知
class Loop:

    def __init__(self,agents=None,session=None,hooks=None,verbose:bool=True,memory=None,emit=None,trace=None):
        self.agents = agents
        self.session = session
        self.hooks = hooks
        self.memory = memory
        # eval 观测实例：attachment 这类没有独立存在理由的点位在 Loop 内直调它，不为观测另开 hook 点
        self.trace = trace
        # 控制 thinking 类内容是否打印到终端；memory 等后台管线复用的 Loop 可传 False 静音
        self.verbose = verbose

        self.stream_id = 0
        # 唯一外发口：TUI 挂载 handle_loop_event；loop 内部统一 emit(event,content,stream_id,agent_name) 外发，事件名语义化不感知渲染层
        self.emit = emit
        self.length_end = False# @claude 后续需要添加流式长度，截断工具执行的逻辑


    # 从 agents 容器中取出指定 agent
    def _get_agent(self,agent_name:str):
        return self.agents.agents[agent_name]


    # 兼容不同 provider 下 reasoning_content 字段可能不存在的情况
    def _get_reasoning(self,message:ChatCompletionMessage)->str:
        return getattr(message,'reasoning_content',None) or ''


    # 统一 LLM 调用：with_tools 决定是否携带 tools 与 thinking
    # 建连失败与流式中途异常都在此翻译成 LoopAPIError，由 loop_run 统一兜底
    def _chat(self,agent,with_tools:bool):

        # 组装请求参数：with_tools 时带 tools 与 thinking
        params = {'model':agent.model_name,'messages':agent.message_list}
        if with_tools:
            params['tools'] = agent.tool_list
            params['tool_choice'] = 'auto'
            params['extra_body'] = {'thinking':{'type':'enabled'}}
            tui_thinking_enabled = True # 标记TUI是否开启ThinkingWidget
        else:
            tui_thinking_enabled = False # 标记TUI是否开启ThinkingWidget
        # 打开流式：create 返回 stream，chunk 逐个到
        params["stream"] = True
        params["stream_options"] = {"include_usage":True}

        # 本次调用的流序号，TUI 用它区分流；建连失败时未赋值，异常路径据此跳过 end 信号
        stream_key = None
        try:
            # 流号前置分配，先发 Thinking 骨架事件，input 即显示
            self.stream_id += 1
            stream_key = f'{agent.agent_name}_{self.stream_id}'

            # 发起请求，拿回 stream 对象
            stream = agent.agent_ai.chat.completions.create(**params)

            # 累积变量：流式 content 全量在这攒
            AssistantMessage = ''
            AssistantThinking = ''
            AssistantThinkingStreamEndFlag = False
            AssistantToolCalls = []
            AssistantUsage = None
            
            # 迭代 stream：空 choices 跳过，中途异常与建连失败同款兜底
            for chunk in stream:
                # 接取usage token消耗字段位置，ps：这里后续可能得跟多provider结合，不同provider适配返回的usage不同
                if getattr(chunk,"usage",None):
                    AssistantUsage = chunk.usage

                # 部分 provider 会夹空 choices 心跳包，跳过避免 IndexError
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # 处理thinking信息
                if getattr(delta,'reasoning_content',None):
                    # 发 thinking 骨架事件
                    if self.emit and tui_thinking_enabled and not AssistantThinkingStreamEndFlag:
                        self.emit(event='AssistantThinking',content={},stream_id=stream_key,agent_name=agent.agent_name)
                    # 标记thinking流已经开始
                    AssistantThinkingStreamEndFlag = True
                    # 累积thinking内容
                    AssistantThinking += delta.reasoning_content
                    # 发 thinking 内容增量
                    if self.emit and tui_thinking_enabled:
                        self.emit(event='AssistantThinking',content={'reasoning_delta':delta.reasoning_content},stream_id=stream_key,agent_name=agent.agent_name)

                # 处理content信息
                if getattr(delta,'content',None):
                    
                    # content 开始说明 thinking 已结束：标志置 False，触发 StreamEnd 收尾事件
                    if self.emit and tui_thinking_enabled and AssistantThinkingStreamEndFlag:
                        AssistantThinkingStreamEndFlag = False
                        self.emit(event='AssistantThinkingStreamEnd',content={},stream_id=stream_key,agent_name=agent.agent_name)
                    
                    # 发 delta 增量给 TUI，widget 内部走 MarkdownStream 累积
                    AssistantMessage += delta.content
                    if self.emit:
                        self.emit(event='AssistantContent',content={'message_delta':delta.content},stream_id=stream_key,agent_name=agent.agent_name)

                # 处理ToolCalls信息：分片到，按 index 拼回完整调用
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        # 并行调用时 index 不保证有序，列表不够长先占位
                        while len(AssistantToolCalls) <= tc.index:
                            AssistantToolCalls.append({"id":"","type":"function","function":{"name":"","arguments":""}})

                        # 首片才有 id，其余片这里跳过保留空串
                        if tc.id:
                            AssistantToolCalls[tc.index]["id"] = tc.id
                        if tc.function:
                            # arguments 是增量，逐片 += 拼回完整 JSON
                            if tc.function.name:
                                AssistantToolCalls[tc.index]["function"]["name"] += tc.function.name
                            if tc.function.arguments:
                                AssistantToolCalls[tc.index]["function"]["arguments"] += tc.function.arguments
                
                # 处理thinking流结束信息
                if AssistantThinkingStreamEndFlag and not getattr(delta,"reasoning_content",None):
                    # 发 thinking 流结束事件
                    AssistantThinkingStreamEndFlag = False
                    if self.emit and tui_thinking_enabled:
                        self.emit(event='AssistantThinkingStreamEnd',content={},stream_id=stream_key,agent_name=agent.agent_name)
                
                # 处理finish_reason信息
                if chunk.choices[0].finish_reason == "length":
                    self.length_end = True
                
            # 流正常收尾：发 stream_end，TUI 据此停 MarkdownStream 并回收该流
            if self.emit:
                self.emit(event='StreamEnd',content={},stream_id=stream_key,agent_name=agent.agent_name)

            # 拼接完整用于 return 的message：和原非流式返回结构一致
            complete_message = ChatCompletionMessage(
                role = 'assistant',
                content=AssistantMessage or None,
                tool_calls=AssistantToolCalls or None
            )
            if AssistantThinking:# 判断是否返回Thinking数据
                complete_message.reasoning_content = AssistantThinking.rstrip('\n')
            if AssistantUsage is not None:#判断是否返回了CompletionUsage pydantic 对象
                complete_message.usage = AssistantUsage

            # 一次调用记一条：thinking/content/tool_calls/usage 同源同时刻,拆开就得靠伪造时间戳才关联得回来
            # tool_calls 原样存不 parse：arguments 是模型吐的 JSON 字符串,畸形参数本身就是 eval 要看的证据
            if self.trace:
                loop_round=self.session.round if self.session else ''
                self.trace.trace_record(
                    trace_type="assistant_output",
                    source=agent.agent_name,
                    loop_round=loop_round,
                    stream_key=stream_key,
                    trace_detail={
                        "assistant_reasoning":AssistantThinking or None,
                        "assistant_content":AssistantMessage or None,
                        "assistant_toolcalls":AssistantToolCalls or None,
                        "assistant_usage":AssistantUsage.model_dump() if AssistantUsage is not None else None
                    }
                )

            return complete_message

        except LoopAPIError:
            # LoopAPIError 别进 except Exception，原样上抛防二次包装
            raise

        except Exception as ee:
            # 建连失败 / 流式中途断流：同款翻译，已 emit 不回滚
            # 流中断也发 stream_end 防 TUI 侧 stream 悬挂；建连失败未开流则跳过
            if self.emit and stream_key:
                self.emit(event='StreamEnd',content={},stream_id=stream_key,agent_name=agent.agent_name)
            raise LoopAPIError(str(ee)) from ee



    # 发送消息：拼 user 消息→调 LLM→写回 message_list→按需写 session
    # attachment 只拼进模型可见的 message_list，不落盘、不还原：一旦发出去的历史字节
    # 改动会破坏 provider 的 prompt cache 前缀，所以宁可让它留在历史里，也不事后改写
    def _sent_message_api(self,agent,message_content:str=None,source:str='user')->ChatCompletionMessage:
        if message_content:
            model_content = message_content
            attachment_content = ''
            if self.session and self.session.attachment.attachment_list:
                # 渲染结果先接成变量：clear 之后取不到，且拼接与 trace 两个消费者不该各渲染一次
                attachment_content = self.session.attachment.attachment_render()
                model_content = f'{attachment_content}\n\n{message_content}'
                self.session.attachment.attachment_clear()

            agent.message_list.append({'role':'user','content':model_content})

            # trace_record 集中记录每轮给模型的输入；attachment 在 model_content 里排在正文之前，
            # 故先记 attachment 再记正文——行序即拼接序，读 jsonl 能还原出模型实际看到的完整消息
            # round 是借 session 的,trace 自己没有轮次概念,只拿它当对回 session JSON 的关联键
            if self.trace:
                session_round = self.session.round if self.session else ''
                if attachment_content:
                    self.trace.trace_record(trace_type="input",source="attachment",loop_round=session_round,trace_detail={"input_message":attachment_content})
                self.trace.trace_record(trace_type="input",source=source,loop_round=session_round,trace_detail={"input_message":message_content})

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
            # assistant 落盘直接交完整对象,正文/thinking/tool_calls 由 session_message_insert 按 role 分类拆字段
            self.session.session_message_insert(role='assistant',content=agent_rq)
        return agent_rq


    # 处理一批 tool_calls：match_tool→分发；返回本批是否发生 mode 切换
    # 不信任提示词自觉性，靠 diff session.mode 判断 plan_mode_on/off 是否真的生效
    # 工具调用全生命周期（processing/error/success 触发）收口在 match_tool，这里只做 mode diff 与结果分发
    def _tool_calls_api(self,agent,tool_calls)->bool:
        mode_switched = False

        # emit 包装提前抽取，两阶段复用；事件名默认 AssistantToolCallUpdate，工具可覆盖
        def _emit_wrapper(content,event="AssistantToolCallUpdate"):
            if self.emit:
                self.emit(event=event,content=content,agent_name=agent.agent_name)
        # self.emit 为空则不发，保持无 TUI 时 match_tool 照常可用
        emit_wrapper = _emit_wrapper if self.emit else None
        if emit_wrapper:
            for func in tool_calls:
                wait_tcr = {
                    "tool_call_id":func.id,
                    "tool_call_name":func.function.name,
                    "tool_call_state":{"tool_call_state":"waiting"}
                }
                emit_wrapper(content=wait_tcr)
        
        for func in tool_calls:
            # 调用前记 mode，回来 diff 是否真的切换（不信任提示词自觉性）
            mode_before = self.session.mode if self.session else None
            # 耗时从外面量：match_tool 永不抛异常,成败全收敛进 tcr,出参就够观测,不必让 trace 渗进工具层
            tool_call_start = perf_counter()
            # match_tool 接管 mode 旁路、参数解析/校验、hooks、执行、异常、生命周期 emit
            tcr = agent.match_tool(func,verbose=self.verbose,mode_switched=mode_switched,
                                   runtime={'session':self.session,'agents':self.agents,'hooks':self.hooks,'memory':self.memory,'Loop':Loop},
                                   emit=emit_wrapper)
            tool_call_duration = perf_counter() - tool_call_start
            if self.session and self.session.mode != mode_before:
                mode_switched = True

            # args/return 存原样不 parse：invalid_tool_arguments 那条路径上参数本就不是合法 JSON,
            # 解析一道要么让 trace 自己成崩溃点,要么把畸形证据抹掉
            # 挑字段不用 asdict(tcr)：tool_call_extra_info 是 TUI 渲染树,展示层结构不进 eval 数据
            # 不带 stream_key,靠 tool_call_id 对回 assistant_output 里的 assistant_toolcalls
            if self.trace:
                self.trace.trace_record(
                    trace_type="tool_call",
                    source=agent.agent_name,
                    loop_round=self.session.round if self.session else '',
                    trace_detail={
                        "tool_call_id":func.id,
                        "tool_call_name":func.function.name,
                        "tool_call_args":func.function.arguments,
                        "tool_call_state":tcr.tool_call_state.get('tool_call_state'),
                        "tool_call_error":tcr.tool_call_error or None,
                        "tool_call_return":tcr.tool_call_result.get('content'),
                        # duration_ms 是 match_tool 整段,tool_func_ms 是工具本体；相减即 harness 开销
                        # 只存两个事实不存差值：派生量交给读的人算,免得三个数长成两个真相
                        "duration_ms":round(tool_call_duration*1000,3),
                        "tool_func_ms":tcr.tool_call_duration_ms
                    }
                )

            # 分发：协议消息 + 落盘
            agent.message_list.append(tcr.tool_call_result)
            if self.session:
                self.session.session_message_insert(role='tool_result',content=json.dumps(tcr.tool_call_result,ensure_ascii=False))
        return mode_switched


    # 强制收尾：不传 tools，模型物理上拿不到工具，只能吐文本；可选先弹出末尾 tool_calls
    def _force_final_reply(self,agent,notice:str,drop_last_toolcalls:bool=False)->str:
        if drop_last_toolcalls and agent.message_list and getattr(agent.message_list[-1],'tool_calls',None):
            agent.message_list.pop()

        agent.message_list.append({'role':'user','content':notice})

        # 强制收尾的提示不经 _sent_message_api,单独记：否则 trace 里会出现一条没有输入的模型回复
        # source 用 attachment 不用 system：system 已归 trace 设施自身的生命周期,
        # 而这条和 attachment 同类——都是系统注入进模型可见消息流的内容,只是投递方式不同
        if self.trace:
            self.trace.trace_record(trace_type="input",source="attachment",loop_round=self.session.round if self.session else '',trace_detail={"input_message":notice})

        if self.session:
            self.session.session_message_insert(role='user',content=notice)
        try:
            final_rq = self._chat(agent,with_tools=False)
        except LoopAPIError:
            # 失败时弹出刚 append 的 notice 消息，避免下一轮出现连续两条 user 消息 @claude实际上后续应该想办法将error变成类似attachment的内容和下一轮user消息拼接在一起，避免丢失上下文
            agent.message_list.pop()
            raise
        agent.message_list.append(final_rq)

        if self.session:
            self.session.session_message_insert(role='assistant',content=final_rq)
        return final_rq.content


    # 结束一轮：重置计数并递增 session.round
    def _close_round(self):
        if self.session:
            self.session.round += 1


    # 引擎入口：发首条消息，进入 ReAct 工具循环直到出结果或达上限
    # source 只随首条消息下传给 trace；循环里那次 _sent_message_api 无 message_content,不产生记录
    def run_turn(self,agent,message:str=None,source:str='user')->str:
        agent_rq = self._sent_message_api(agent=agent,message_content=message,source=source)
        tool_call = 0

        while tool_call < agent.max_toolcalls:
            # 无 tool_calls 即本轮收尾：有内容返回内容，无内容返回空串（不再空转死循环）
            if not agent_rq.tool_calls:
                self._close_round()
                return agent_rq.content or ''

            tool_call += 1

            # 执行工具调用 + 通过 diff session.mode 检测模式是否真的切换（不信任提示词自觉性）
            mode_switched = self._tool_calls_api(agent=agent,tool_calls=agent_rq.tool_calls)

            # plan_mode_on/off 生效后代码层强制结束本轮，不再给模型可调工具的机会
            if mode_switched:
                self._close_round()
                return self._force_final_reply(agent=agent,notice='系统提示：plan 模式已切换，本轮对话到此结束，请直接回复，不要调用任何工具')

            agent_rq = self._sent_message_api(agent=agent)

        # 达到工具调用上限，强制无 tools 收尾
        if self.emit:
            self.emit(event='SystemError',content={'message':'已达到工具调用次数上限'},agent_name=agent.agent_name)
        self._close_round()
        return self._force_final_reply(agent=agent,notice='系统提示：已达到工具调用次数上限，请根据已有信息进行回复',drop_last_toolcalls=True)


    # 跑一次 agent 会话：解析 agent（agent 实例或 agent_name 二选一）→跑一轮→plan 编排
    # memory 管线、subagent、plan_design 都直调这里，不带 hook；顶层轮次的 hook 边界在 run_loop
    # 模型 API 失败在此统一兜底：本轮提前结束，不炸穿 main.py 的顶层循环
    def loop_run(self,agent = None,agent_name:str=None,message:str=None,source:str='user'):
        agent = agent if not agent_name else self._get_agent(agent_name=agent_name)

        try:
            if self.emit:
                self.emit(event='LoopStart',agent_name=agent.agent_name)
            result = self.run_turn(agent=agent,message=message,source=source)
            # plan 模式则进入分步编排，是否真跑由 PlanRunner 内部判断；after_loop 之前完成以保原切片时机
            plan_result = PlanRunner(loop=self,session=self.session).run(agent=agent)
            if plan_result is not None:
                result = plan_result
        
        except LoopAPIError as ee:
            result = f'[系统错误] 模型调用失败，本轮未完成：{ee}'
            if self.session:
                self.session.round += 1
            if self.emit:
                self.emit(event='SystemError',content={'message':result},agent_name=agent.agent_name)

        # 收尾：发 LoopEnd 事件
        finally:
            if self.emit:
                self.emit(event='LoopEnd',content={},agent_name=agent.agent_name)

        return result


    # 顶层入口：一次外部输入的完整轮次，hook 边界收在这里；loop_run 只管跑一次 agent 会话
    # source 记谁把消息送进来的（user/attachment/各agent名），与 trace 的 source 同一套词汇，A2A 时原样可用
    # try/finally：异常路径也跑 after_loop。工具内部异常已被 match_tool 收口成 _error_result、
    # 模型 API 异常已被 loop_run 的 LoopAPIError 分支吃掉，真正能穿透到这里的是
    # Plan.advance() 的 ValueError（此时本轮消息完整，该跑）与 session 落盘失败（此时磁盘已不可信，跳过也挽回不了）
    def run_loop(self,source:str,message:str=None,agent_name:str=None):
        if not message:
            return

        # 无 hooks 的 Loop（memory 管线、subagent、plan_design）直调 loop_run，走不到这里，判空仍保留兜底
        if self.hooks:
            self.hooks.trigger(hook_point='before_loop',session=self.session,agents=self.agents,
                               memory=self.memory,hooks=self.hooks,
                               source=source,user_message=message)
        try:
            return self.loop_run(agent_name=agent_name,message=message,source=source)
        finally:
            # 入库开关收拢在 memory.pipeline_enabled(创建时统一设置)，触发时不再传
            if self.hooks:
                self.hooks.trigger(hook_point='after_loop',session=self.session,agents=self.agents,
                                   memory=self.memory,hooks=self.hooks)
