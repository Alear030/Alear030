# Loop 的想法&取舍

**中文** · English（暂缺）

← [返回 README](../../README.md) · [文档目录](../index.md)

`loop/loop_core.py` 的 `Loop` 是这个项目的执行引擎——**一个纯 ReAct 循环**，main agent 和运行时临时构造的 subagent 共用同一份实现。

这篇讲**为什么长成这样**。当前实现是什么样见 [架构文档](../ARCHITECTURE.md)；机制细节以代码为准。

---

## 目录

- [一条边界：Loop 不知道 plan 存在](#一条边界loop-不知道-plan-存在)
- [四个不显然的决定](#四个不显然的决定)
- [一条尚未拆开的耦合](#一条尚未拆开的耦合)

---

## 一条边界：Loop 不知道 plan 存在

Plan 是这个项目里唯一的多轮编排机制，但它**不在 Loop 里**——`loop/orchestrator.py` 的 `PlanRunner` 是独立的一层。

分开的理由不是洁癖，是**演进方向**。`PlanRunner` 顶部的注释写着：未来的 `GoalRunner` 可以在 `run()` 外层再包一圈——检查产出、不合格就重新规划、再跑一遍——**而不需要改 Loop 一行**。如果 plan 的控制流塞进 Loop，每加一层编排就要动引擎。

代价是 `loop_run` 里有一次无条件调用：

```python
plan_result = PlanRunner(loop=self, session=self.session).run(agent=agent)
```

**决策收在 `PlanRunner.run()` 内部**——非 plan 模式直接返回 `None`，调用方无条件调即可，不必在 Loop 里写 `if session.mode == 'plan'`。用一次空调用换 Loop 对 plan 的零感知。

同一条思路还体现在依赖上：**`session` 和 `hooks` 都是可选的**。不传就是无持久化模式——不落盘、不触发生命周期钩子，但 ReAct 循环照跑。代码里十余处 `if self.session:` 判空守卫就是这条的代价。收益是 memory 管线能复用同一个 `Loop` 跑后台任务而不污染真实会话，测试也能不带 session 直接构造。

`PlanRunner` 自己也做了一个取舍：**无进展熔断**。连续 `PLAN_STALL_LIMIT` 轮拿到同一个 `step_number`，说明模型没把 step 标 done，直接退出循环。不做这件事的话，一个不肯收尾的模型能把 plan 跑成死循环。

熔断挡的是「不往前走」，另一头「一次往前走太多」由 `Plan.advance()` 挡：它把当前 step 记进 `active_step_number`，**限制本轮唯一允许更新的 step**。没有这条，模型可以在一轮里连续调 `plan_update` 把后面几个 step 一起标成 done——计划就成了摆设。两者是同一个判断的两个方向：**step 的推进权归代码，不归模型。**

---

## 四个不显然的决定

### 1. 强制收尾靠物理断供，不靠提示词

有两种情况必须让模型停下来：plan 模式刚切换、工具调用次数达到上限。

朴素做法是发一句「请直接回复，不要调用任何工具」。**但提示词不是约束，是建议**——模型完全可以无视它继续调工具。

`_force_final_reply` 的做法是 `self._chat(agent, with_tools=False)`：**这次请求根本不带 `tools` 参数**。模型不是被劝住的，是没有工具可调。提示词照发，但它只负责解释原因，不负责生效。

这条决定的连带处理：达上限那条路径要 `drop_last_toolcalls`——把最后一条带 `tool_calls` 的 assistant 消息弹掉，否则历史里挂着一批没有对应 tool result 的调用，协议不完整。

### 2. mode 切换靠 diff，不信任模型自觉

`plan_mode_on` / `plan_mode_off` 是工具。模型在一个批次里可能调了 `plan_mode_off`，后面还跟着三个别的工具调用。

如果相信「模型知道自己切了模式就该停」，那三个工具会在**已经切换后的模式下**继续执行。

`_tool_calls_api` 的做法是每个工具调用前后 diff `session.mode`：

```python
mode_before = self.session.mode if self.session else None
tcr = agent.match_tool(...)
if self.session and self.session.mode != mode_before:
    mode_switched = True
```

一旦发现切换，**停止执行同批剩余工具并补齐 tool results**（协议要求每个 tool_call 都得有对应结果），然后走 `_force_final_reply` 强制收尾。

判断依据是**状态的实际变化**，不是模型声称做了什么。

### 3. 模型 API 失败靠统一错误边界，不靠层层 try/except

流式调用会在很多地方失败：建连失败、中途断流、provider 返回异常。如果每个调用点各自 `try/except`，错误处理会散得到处都是，而且很容易漏一个直接炸穿 `main.py`。

做法是**一个翻译点 + 一个兜底点**：

- `_chat` 把所有裸异常翻译成 `LoopAPIError`（`except LoopAPIError: raise` 放在 `except Exception` 前面，防止二次包装）
- `loop_run` 顶层捕获 `LoopAPIError`，返回一个错误字符串，同时 `emit` 一条 `SystemError` 给 TUI

流式中途失败时还要**补发 `StreamEnd`**——否则 TUI 侧那条流永远悬挂着，widget 不会 finalize。建连失败还没开流，则跳过这一步。

**这条边界目前没有覆盖全部路径**：`_tool_calls_api` 的参数解析、`match_tool` 内部的工具异常，以及工具内绕开 `Loop` 直调模型的情况，仍在边界之外。这是 20260702 那版方案里暂缓的两部分，不是遗漏。

### 4. 流式累积替代整块返回

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
