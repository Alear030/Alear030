# Loop 的想法&取舍

**中文** · English（暂缺）

← [返回 README](../../README.md) · [文档目录](../index.md)

`loop/loop_core.py` 的 `Loop` 是这个项目的执行引擎——**一个纯 ReAct 循环**，main agent 和运行时临时构造的 subagent 共用同一份实现。

这篇讲**为什么长成这样**。当前实现是什么样见 [架构文档](../ARCHITECTURE.md)；机制细节以代码为准。

---

## 目录

- [一条被撤销的边界：plan 编排曾经在这里](#一条被撤销的边界plan-编排曾经在这里)
- [跟着一起走的那个机制](#跟着一起走的那个机制)
- [三个不显然的决定](#三个不显然的决定)
- [一条尚未拆开的耦合](#一条尚未拆开的耦合)

---

## 一条被撤销的边界：plan 编排曾经在这里

Plan 曾经是这个项目里唯一的多轮编排机制，而它**不在 Loop 里**——`loop/orchestrator.py`（已随本次下线删除）的 `PlanRunner` 是独立的一层。

分开的理由不是洁癖，是**演进方向**：未来的 `GoalRunner` 可以在 `run()` 外层再包一圈——检查产出、不合格就重新规划、再跑一遍——**而不需要改 Loop 一行**。如果 plan 的控制流塞进 Loop，每加一层编排就要动引擎。

代价是 `run_loop` 里有一次无条件调用：

```python
plan_result = PlanRunner(loop=self, session=self.session).run(agent=agent)
```

**决策收在 `PlanRunner.run()` 内部**——非 plan 模式直接返回 `None`，调用方无条件调即可，不必在 Loop 里写 `if session.mode == 'plan'`。用一次空调用换 Loop 对 plan 的零感知。

`PlanRunner` 自己还有两道卡控。一是**无进展熔断**：连续 `PLAN_STALL_LIMIT` 轮拿到同一个 `step_number`，说明模型没把 step 标 done，直接退出——不做这件事，一个不肯收尾的模型能把 plan 跑成死循环。二是 `Plan.advance()` 把当前 step 记进 `active_step_number`，**限制本轮唯一允许更新的 step**，否则模型可以在一轮里连续调 `plan_update` 把后面几个 step 一起标成 done，计划就成了摆设。两者是同一个判断的两个方向：**step 的推进权归代码，不归模型。**

### 为什么整体下线

这条边界画得没错。错的是被它围起来的那个东西。

上面每一条卡控读起来都成立，但它们共享同一个前提：**编排的正确形态是「代码驱动模型」**——代码决定下一步是什么，代码决定哪一步可以被标完成，代码在模型不往前走时熔断。整套机制是这个前提的忠实实现，所以它内部越自洽，就越把这个前提锁得越死。

随着对「harness 该以多大力度分控与管控模型」的认识变化，这个前提本身变成了需要被检验的对象，检验的结论是它不成立。一个计划文件加一个更新工具，把编排以「可读可写的状态」暴露给模型自己驱动，能覆盖的场景更多，中途出错时的退路也更宽——而状态机形态下，模型每偏离一次，代码就得多加一道卡控去接住它，卡控本身会持续增殖。

所以 plan 不是被搬到别处，是被判定为方向性错误之后整体下线的：四个工具、plan agent、`PlanRunner`、`Plan` 类与 `session.mode` 一次性从运行链路移除，代码交给 git 历史。这篇留下的是它存在过的形状，和它被撤销的理由。

> 顺带记一条同源的取舍，它没有随 plan 走：**`session` 和 `hooks` 对 Loop 都是可选的**。不传就是无持久化模式——不落盘、不触发生命周期钩子，但 ReAct 循环照跑。代码里十余处 `if self.session:` 判空守卫就是这条的代价，收益是 memory 管线与 subagent 能复用同一个 `Loop` 跑后台任务而不污染真实会话，测试也能不带 session 直接构造。

---

## 跟着一起走的那个机制

有一个机制值得单独记，因为**它被撤销的理由和 plan 不同**：它本身是对的，只是没有服务对象了。

`plan_mode_on` / `plan_mode_off` 是工具。模型在一个批次里可能调了 `plan_mode_off`，后面还跟着三个别的工具调用。如果相信「模型知道自己切了模式就该停」，那三个工具会在**已经切换后的模式下**继续执行。

`_tool_calls_api` 的做法是每个工具调用前后 diff `session.mode`：

```python
mode_before = self.session.mode if self.session else None
tcr = agent.match_tool(...)
if self.session and self.session.mode != mode_before:
    mode_switched = True
```

一旦发现切换，**停止执行同批剩余工具并补齐 tool results**（协议要求每个 tool_call 都得有对应结果），然后强制收尾。**判断依据是状态的实际变化，不是模型声称做了什么。**

这条随 plan 一起下线了，因为它唯一的触发源就是那两个工具。但它保护的性质是真的：**一个工具改变了本轮的前提之后，同批剩余的调用不该继续跑。** 记在这里是为了将来重建它时不重犯同一个错——不该再由引擎伸进 `session` 去嗅一个业务字段，而应该让工具自己声明「我改变了本轮前提」，引擎只对声明作反应。那样引擎不需要知道任何具体业务，新工具想要同样的保护也不必改引擎。

`session.mode` 本身也在这次一并清掉。它描述的是「模型此刻被允许做什么」，属于对 agent 行为的控制；挂在 `Session` 上，等于把「这次会话是什么」和「模型此刻被允许做什么」混成了同一个字段。plan 走后它只剩一个取值，留着就是一个迟早会长回来的空位。

---

## 三个不显然的决定

### 1. 强制收尾靠物理断供，不靠提示词

工具调用次数达到上限时，必须让模型停下来。

朴素做法是发一句「请直接回复，不要调用任何工具」。**但提示词不是约束，是建议**——模型完全可以无视它继续调工具。

`_force_final_reply` 的做法是 `self._chat(agent, with_tools=False, stream_key=stream_key)`：**这次请求根本不带 `tools` 参数**。模型不是被劝住的，是没有工具可调。提示词照发，但它只负责解释原因，不负责生效。

这条决定的连带处理：达上限那条路径要 `drop_last_toolcalls`——把最后一条带 `tool_calls` 的 assistant 消息弹掉，否则历史里挂着一批没有对应 tool result 的调用，协议不完整。

### 2. 模型 API 失败靠统一错误边界，不靠层层 try/except

流式调用会在很多地方失败：建连失败、中途断流、provider 返回异常。如果每个调用点各自 `try/except`，错误处理会散得到处都是，而且很容易漏一个直接炸穿 `main.py`。

做法是**一个翻译点 + 一个兜底点**：

- `_chat` 把所有裸异常翻译成 `LoopAPIError`（`except LoopAPIError: raise` 放在 `except Exception` 前面，防止二次包装）
- `run_loop` 顶层捕获 `LoopAPIError`，返回一个错误字符串，同时 `emit` 一条 `SystemError` 给 TUI

建连失败和流式中途失败时都会**补发 `StreamEnd`**——避免 TUI 侧已创建的流悬挂、widget 无法 finalize。建连失败时若尚未创建对应 widget，TUI 收尾为空操作。

**这条边界目前没有覆盖全部路径**：`_tool_calls_api` 的参数解析、`match_tool` 内部的工具异常，以及工具内绕开 `Loop` 直调模型的情况，仍在边界之外。这是 20260702 那版方案里暂缓的两部分，不是遗漏。

### 3. 流式累积替代整块返回

`_chat` 用 `stream=True` 逐 chunk 累积 `content` / `thinking` / `tool_calls`，再拼回一个和非流式**同构**的消息对象。

`tool_calls` 的累积是这里最麻烦的一段：流式返回的 tool_call 是按 `index` 分片到达的，参数 JSON 被切成任意片段，必须按 index 占位再拼回完整 JSON。

为什么值得这么麻烦：**没有流式就没有 TUI 的逐字渲染**，而逐字渲染是这个项目终端体验的主要部分。拼回同构消息则是为了让下游（落盘、message_list、工具分发）完全不必知道这次是流式还是整块。

一个连带的取舍写在 `_sent_message_api` 上：**attachment 只拼进模型可见的 `message_list`，不落盘、不事后还原**。理由是 provider 的 prompt cache 按前缀匹配——**已经发出去的历史字节一旦改动，缓存前缀就断了**。宁可让 attachment 留在历史里显得冗余，也不事后改写。（这条与 [LLM Cache 研究](../research/llm-cache.md) 是同一条线上的考虑。）

---

## 一条尚未拆开的耦合

`_chat` 里 thinking 和 tools 是**绑死**的：

```python
if with_tools:
    params['tools'] = ...
    params['extra_body'] = {'thinking':{'type':'enabled'}}
```

两者没有独立开关。想单独关掉某次调用的 thinking（比如高频调用的性能优化）又要保留 tools，必须先解耦这个方法——而那会影响 main agent 的真实运行时行为。

**不带 tools 的独立直调不受这条约束**，各自直接传 `extra_body` 即可：`session/session_core.py::_structured_chat` 已经固定传 `disabled`（`_session_slice` 与 `_session_summary` 都经它发起，本身不碰 `extra_body`）；`memory/memory_core.py::slice_type_define` 目前仍传 `enabled`，等待收进结构化直调的统一边界。

这条留在这里不是因为想不清楚，是因为改它的收益（省一点 thinking token）和风险（动 main agent 的运行时行为）目前不成比例。
