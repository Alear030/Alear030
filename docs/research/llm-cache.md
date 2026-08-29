# LLM Cache 方向研究&现象观察

**中文** · English（暂缺）

← [返回 README](../../README.md) · [文档目录](../index.md)

> **状态：进行中。** 已定位一个主因并验证，撤回过一条错误结论，仍有开放问题未解。
> 对应 issue：[#38](https://github.com/Alear030/Alear030/issues/38)（跨 session 复用）· [#39](https://github.com/Alear030/Alear030/issues/39)（多 Agent 并发）· [#40](https://github.com/Alear030/Alear030/issues/40)（memory agent 模板）

main agent 单轮 `prompt_tokens` 动辄一万五，其中 system prompt 和工具 schema 占绝对大头。这部分是每轮都要重发的固定成本，能不能被 provider 的缓存摊掉，直接决定这个项目跑起来贵不贵。

这篇是 LLM 缓存这个方向下的**累积式记录**：查到什么写什么，随时追加。目前的主线是 prompt cache 的跨 session 复用——中途推翻了自己最初的假设，也撤回过一条基于错误计量方式得出的结论。**推翻和撤回的过程都留在文里**，因为一条结论怎么来的，和结论本身一样重要。

文末[仍然开放的问题](#仍然开放的问题)列的是还没查的，后续实测出结果会接着往这篇里加。

---

## 目录

- [先有测量能力](#先有测量能力)
- [观察到的现象](#观察到的现象)
- [假设一：是 timeline/memory_prompt 吗——证伪](#假设一是-timelinememory_prompt-吗证伪)
- [真正的发现：12.7K 的工具 schema 全量 miss](#真正的发现127k-的工具-schema-全量-miss)
- [一次自我更正：撤回「400 token 缺口」](#一次自我更正撤回400-token-缺口)
- [连带发现：memory agent 的模板结构性对抗缓存](#连带发现memory-agent-的模板结构性对抗缓存)
- [仍然开放的问题](#仍然开放的问题)

---

## 先有测量能力

在能测之前，一切关于缓存的讨论都是猜。

第一步是给 `Loop._chat` 的流式请求补上 `stream_options={"include_usage": True}`，迭代 chunk 时接住 `chunk.usage`，拼回非流式同构消息时挂到 `complete_message.usage`；再由 `session_message_insert` 把它 `model_dump()` 落到每条 assistant 消息的 `message_usage` 字段。

这样每一次模型调用的原始 usage（含 `cached_tokens` 这类 provider 专属字段）都逐条落在磁盘上，可以按 `message_round` 聚合。这个埋点同时也是后续 eval token 用量追踪的数据来源。

值得强调的一点：**落盘的是 provider 返回的原始对象，不做任何归一化**。不同 provider 的 usage 字段名和口径都不一样（`cached_tokens` / `prompt_cache_hit_tokens` / ...），现在就统一反而会丢信息。这个决定在后面「自我更正」那一节救了一次场。

## 观察到的现象

一段真实多轮对话的实测：

| 轮次 | `prompt_tokens` | `cached_tokens` | 命中率 |
|---|---|---|---|
| round 1（session 刚开） | 15296 | 2176 | ~14% |
| round 2 | 15374 | 15360 | ~99.9% |
| round 3（第一次） | 15546 | 15488 | ~99.6% |
| round 3（工具调用后第二次） | 19795 | 15744 | ~79.5% |
| round 4 | 20930 | 20864 | ~99.7% |

> 这张表和下文拆解用的是**两次不同的 session**，round 1 的 `prompt_tokens` 分别是 15296 和 15295，差 1 个 token。两次的时间戳文本不同，在 provider 自己的分词器下切出来差一个 token 是说得通的——未专门验证，也不影响结论：下文的拆解全部在同一次请求内部做整数运算，不跨请求相减。

**session 内的规律很干净**：新内容出现过一次就会被缓存，下一轮几乎全命中；工具结果这类大段新内容注入会让命中率短暂下跌，随后立刻恢复。这部分健康，不是问题。

问题在 round 1：**全新 session 的第一次请求，命中率只有 14%**。上万字的 system prompt——persona、工具列表、技能列表、底层架构提示词——绝大部分没能复用上一个 session 已经算过的结果。

## 假设一：是 timeline/memory_prompt 吗——证伪

最初的怀疑落在 prompt 分块的注册顺序上：

```text
system_prompt(0) → attachment_prompt(5) → tool_prompt(10) → skill_prompt(20)
  → timeline(30) → memory_prompt(35) → agent_prompt(40) → basic_prompt(50, 时间戳)
```

前缀缓存只在**第一个字节分叉点之后**失效，所以必然变化的内容应该尽量往后放。`basic_prompt` 渲染当前系统时间、`order=50` 全场最大——这个位置选得对。

但 `timeline`（30）和 `memory_prompt`（35）排在它前面，而这两块读的 `timeline.json` / `user_info` 会被 `session_timeline` / `memory_pipeline` 两个后台 hook 持续写入。推论看起来很顺：只要上一个 session 结束时这两条管线写过东西，下一个 session 的分叉点就卡在 order=30/35，根本轮不到时间戳来决定命不命中。

**这个推论是错的。** 拿两次真实新 session（间隔约 49 分钟）的完整 system prompt 做字节级 diff：

- 前 4333 个字符**逐字节完全一致**
- 从第 4334 个字符起才出现差异，差异内容就是结尾的那句时间戳

因为测试时 `MEMORY_PIPELINE_ENABLED=False`，这两条管线根本没写入，`timeline_prompt` / `memory_prompt` 在这次测试条件下压根没变。「分叉点可能在 skill_prompt 中间」的猜测也一并被 diff 证伪。

顺带排除了另一个替代解释：怀疑技能列表的遍历顺序不稳定，用 `Path.rglob('skill.md')` 连续跑两次独立进程验证，顺序完全一致。

于是问题变成：**system prompt 除了最后一句时间戳逐字节相同，为什么命中率还是只有 14%？**

## 真正的发现：12.7K 的工具 schema 全量 miss

把其中一次 session 的 round 1 拆开算，账对得非常干净：

```text
prompt_tokens  = 15295
system prompt  =  2586   ← 其中 2176 命中
tools schema   = 12709   ← 全量 miss，一个 token 都没命中
                 ------
miss 总量      = 13119 = (2586 - 2176) + 12709
```

**工具 schema 占了整个请求的 83%，且在新 session 首次请求时是 100% miss。** 这个体量是 system prompt 本身的五倍，是当时发现的最大复用缺口。

根因不是它自己变了。检查工具发现机制：

```python
for d in sorted(tools_dir.iterdir()):   # 显式 sorted，不依赖文件系统枚举顺序
    if d.is_dir() and ...:
        importlib.import_module(f'tool.tools.{d.name}')
```

导入顺序显式 `sorted()`，每个工具的 `description` 来自静态的 `tool_prompt.md`、`parameters` 由 `inspect.signature` 推导，都不含时间戳、UUID 或任何运行时状态。代码不变的前提下，`tools` 参数跨进程重启必然逐字节相同。

**那就只剩一种解释：它被排在它前面的时间戳连累了。** 时间戳每次新 session（进程启动）重新生成一次，一变，它之后的整段请求字节流一并作废——包括那 12709 token 的工具 schema。

这把最初被当成「结尾一句话、无关痛痒」的时间戳，升级成了**跨 session 缓存复用的唯一关键阀门**。理论上可复用的范围是 persona + tools schema 合计约 15288 token；只要时间戳还在工具 schema 前面且每次新 session 都变，这一整块就复用不了——`timeline_prompt` / `memory_prompt` 那两块是不是稳定，在这个前提下根本轮不到它们说话。

同时这也纠正了一处最初的表述偏差：时间戳不是「一直在变」，而是**每次新 session 启动各生成一次，session 生命周期内固定**。这正好解释了为什么 session 内 round 2 之后能有 99.9% 的命中率。

> **这条结论的置信边界**：根因是从 provider 上报的 token 整数关系反推出来的，不是来自 provider 关于「请求各部分如何参与缓存前缀哈希」的官方说明。算术三处独立对齐（`2586+12709=15295`、`15295-2176=13119`、`(2586-2176)+12709=13119`），且排除了工具 schema 自身不稳定这个替代解释，但严格说仍是推断而非厂商确认。

## 一次自我更正：撤回「400 token 缺口」

排查中途得出过一条结论，后来撤回了，记在这里。

当时用 `tiktoken`（gpt-4o 编码，和 `session_core.py` 里统计 session token 用的是同一套）量了那段「逐字节相同」的共享前缀，得到约 2579 token；而 provider 实际只报了 2176 命中。差了约 400 token（~15%），发生在内容确认完全相同的区间里，看起来像是一个真实存在的、需要解释的缓存现象——怀疑过 TTL 部分衰减、缓存分块粒度取整、路由到不同后端副本。

**问题是：这两个数字从来不是同一套计量单位。** `2579` 是 tiktoken 数的，`2176` 是 provider 自己的分词器数的。拿一把尺子的读数去减另一把尺子的读数，差值没有意义。

用两段 provider 自己报过 `completion_tokens` 的真实回复文本反过来校验这把尺子：

| 样本 | tiktoken 算出来 | provider 自己报的 | 偏差 |
|---|---|---|---|
| round 1 | 88 | 69 | tiktoken 多算 27% |
| round 3 | 177 | 250 | tiktoken 少算 29% |

两个样本**偏差方向相反**——一个多算一个少算，说明两个分词器对中文的切分逻辑完全不是一回事，不存在固定换算系数可以修正。±30% 的偏差幅度远大于那个「缺口」占的 15%，足以完全解释掉它。

**结论：那 400 token 是测量误差，不是缓存现象。** 从待研究问题里划掉。

值得注意的是这次更正**没有波及**工具 schema 那条结论——因为它全程只用 provider 自己上报的 `prompt_tokens` / `cached_tokens` 做整数运算，同一次请求、同一套统计口径，没有引入外部估算工具。

教训很直白：**跨分词器比较 token 数是无效的**。后续要量化「理论上能省多少」，必须用这家 provider 自己的 tokenizer 或计数接口，不能拿 tiktoken 顶替。

## 连带发现：memory agent 的模板结构性对抗缓存

排查过程中顺手核对了 memory agent 的五种任务模式，发现一个独立问题。

这五种模式的 system prompt 由 `memory/memory_prompt/memory_prompts_core.py` 的模板函数生成，`_switch_prompt` 在每次任务调用前重新构造。逐个核对下来：

| 模式 | 每次调用嵌入的内容 | 逐次调用是否会变 |
|---|---|---|
| `memory_type` | `memory_type` + `user_info` 配置，**每次现读磁盘** | 会变——分类完一个 slice 可能就往配置里追加新特征并落盘 |
| `user_info` | `user_info` 配置 + `user` 画像存储，现读磁盘 | 会变，机制同上 |
| `advanced_task` | `advanced_task_node` 存储，现读磁盘 | 会变 |
| `normal_task` | 现算候选池，且带 `exclude_key` 排除「当前正在判断的这个 slice 自己」 | **保证每次都不一样**——哪怕底层数据没变，`exclude_key` 逐 slice 不同 |
| `session_timeline` | 无占位符，纯静态 | 不变——五个里唯一稳定的 |

**4/5 的模式，模板本身就设计成「每次调用都塞入最新磁盘状态」。** 即便停留在同一个模式里连续处理好几个 slice，system prompt 内容也大概率逐次不同——不是切换模式这个动作导致的，是这些模板结构性地对抗缓存复用。

这里也纠正过一版更早的错误推理：最初认为「`_switch_prompt` 把 `message_list` 整体重新赋值，所以切换模式必然丢缓存」。这个说法混淆了两件事——客户端 Python 对象有没有被重置，和这次实际传输的字节内容是否匹配之前缓存过的前缀。provider 只看传输内容，不知道也不关心 `message_list` 在客户端是不是一个新对象。**判断缓存是否复用的唯一依据是内容是否等价。**

修正方向记在 [#40](https://github.com/Alear030/Alear030/issues/40)，需要权衡的问题是：把这些易变数据从 system prompt 挪到普通 message 里，会不会降低模型对它的遵从度——尤其 `advanced_task_node_judge` / `user_info_extract` 走的是完整 ReAct 多轮循环，本身就有注意力稀释风险，和 `memory_type` / `normal_task` 那种单次分类调用可能得区别对待。

## 仍然开放的问题

1. **provider 的缓存匹配粒度和过期策略是什么？** 精确字节前缀还是分块粒度？TTL 多长？同一前缀间隔多久重发会开始衰减？这决定了「把时间戳挪到最后」能拿回多少收益。
2. **能不能让时间戳彻底不进 system prompt？** 如果它的作用只是让模型知道「现在几点」，或许该改成工具调用按需获取，而不是固定占据一个必然变化的位置。这需要评估对模型时间感知的影响，属于改动型议题，不在这条研究里落地。
3. **MCP 工具运行期动态刷新会不会砍断缓存链条？** `Agents.refresh_all_tool_list()` 会在 session 中途改变 `tools` 参数。实测方式：session 中途连一个 MCP server，对比连接前后几轮的 `cached_tokens` 是否断崖下跌。
4. **多 Agent 并发时缓存怎么算、怎么隔离？** main、subagent、memory 各自的 Loop 可能同时发请求。缓存池是按 API key 还是按账号隔离？容量上限和淘汰策略是什么？更多互不相同的前缀同时挤进来，会不会让 main 那条体积最大的缓存更快被挤出去？这条独立立项在 [#39](https://github.com/Alear030/Alear030/issues/39)。
5. **跨 Agent 缓存共享有没有可能？** 目前 `attachment_prompt` / `timeline` / `memory_prompt` 都用 `condition=lambda agent: agent.agent_name == 'main'` 锁死只给 main，subagent 和 memory 的 system prompt 结构上就不同，前缀从一开始就分叉。如果刻意让一部分静态内容在各 Agent 间共用，能不能实测到跨 Agent 命中？这决定了值不值得为省缓存去统一 prompt 结构。

上面 1、3 需要针对性实验设计，4、5 需要制造可控的并发场景——这些都依赖比「翻 session JSON」更强的观测能力，会和 trace 机制一起推进。
