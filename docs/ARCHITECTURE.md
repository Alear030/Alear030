# Alear030 架构

**中文** · [English](ARCHITECTURE.en.md)

← [返回 README](../README.md)

这份文档是 Alear030 架构事实的权威来源，面向第一次读这个项目的人。想深入了解记忆链路看 [记忆系统](modules/memory.md)，想动手扩展看 [扩展指南](EXTENDING.md)，想跑起来看 [配置说明](CONFIGURATION.md)。

Alear030 不是一个「Python Agent 框架」，它是一套完整的 Agent 基础设施（Harness）——处理工具编排、多 Agent 路由、会话生命周期、事件驱动 Hook、跨会话记忆召回。模型负责推理，剩下的每一层都在这个仓库里。

---

## 目录

- [运行时数据流](#运行时数据流)
- [目录结构](#目录结构)
- [核心设计决策](#核心设计决策)
- [三套自动发现规则](#三套自动发现规则)
- [数据与持久化](#数据与持久化)

---

## 运行时数据流

### 启动

`main.py` 只做一件事：按依赖顺序装配高层对象，然后把控制权交给 TUI。

```text
prewarm_embedding_model()        # spawn 独立 worker 进程加载嵌入模型，不阻塞 TUI 启动
  → prewarm_mcp_servers(agents)  # 后台线程逐个连 MCP server，单个失败只记录
  → Memory(memory agent, 独立 Loop())
  → Session(slice_agent, summary_agent, main system prompt)
  → Loop(agents, session, hooks, memory)
  → Alear030TUI 装配（TUI 把自己的 receive_loop_emit 挂到 loop.emit 上）
  → hooks.trigger('before_session')
  → AlearTui.run()               # 进入 Textual 事件循环
```

嵌入模型放在独立进程里预热，是因为它加载慢（首次还要从 ModelScope 下载约 195MB 权重），放主进程会让 TUI 迟迟起不来。MCP server 同理，走后台线程，连上一个就把它的工具注册进工具表并刷新各 agent 的 `tool_list`。

### 一次用户输入

```text
Input.Submitted
  → do_work 线程 → _run_round()
  → hooks.trigger('before_round')
  → loop.loop_run('main', message)
      → run_turn()                  # ReAct：模型 → 工具 → 模型 → …
      → PlanRunner.run()            # 仅 plan 模式执行，内部可能再调多次 run_turn
  → hooks.trigger('after_round')
  → finally 解锁输入
```

`session.round` 在每次带 session 的 `run_turn()` 收尾时增长；`after_round` 由 TUI 的 `_run_round()` 在整个顶层 `loop_run()` 返回后**触发一次**。一个用户输入进入 plan 编排时可能包含多个 round，两者不是一一对应。

推理过程边跑边发流式事件回 TUI：

```text
loop.emit(event, content, stream_id, agent_name)
  → TUI 按 agent_name 找到对应 TuiChannel
  → call_from_thread 送回 UI 线程
  → channel.append_stream
  → tuiwidgets.build_widget 渲染
```

用户可见的 harness 错误走 `Loop.emit(event='SystemError')`；工具自身的错误走 `_error_result` / `tool_call_extra_info`，不另开通知总线。

### 退出

```text
finally:
  signal.signal(SIGINT, SIG_IGN)   # 收尾期间忽略 Ctrl+C，join 不会被第二下打断
  → hooks.trigger('after_session')
  → hooks.wait_all()
  → hooks.shutdown()
  → shutdown_mcp_servers()
  → shutdown_embedding_worker()
```

---

## 目录结构

```text
Alear030/
├── main.py                     # 入口：装配 Session/Loop/Memory、预热后进入 TUI、退出收尾
├── config.py                   # 集中配置（MODEL_LEVEL / 路径 / 运行常量）
├── pyproject.toml              # 项目元数据与钉死的直接依赖
├── .env                        # API key & 三级模型配置（不纳入版本控制）
│
├── loop/                       # ReAct 推理循环
│   ├── loop_core.py            # Loop 类 —— 纯 ReAct 引擎（main/subagent 共用，对 plan 编排零感知）
│   └── orchestrator.py         # PlanRunner —— plan 分步编排器，独立于 Loop（含无进展熔断）
│
├── agent/                      # Agent 集群
│   ├── agent_core.py           # Agent 类 + Agents 容器（YAML 驱动）
│   └── agents.yaml             # 5 个常驻 Agent：main/slice/summary/plan/memory
│
├── prompt/                     # Prompt 分层组合（装饰器 + 目录自动发现注册）
│   ├── prompt_core.py          # Prompt 类：薄封装，调用 build_prompt(agent)
│   ├── prompt_register.py      # @register_prompt + build_prompt（order 排序 / condition 过滤 / enabled 开关）
│   ├── __init__.py             # 自动发现并 import prompt/prompts/*/prompt.py
│   └── prompts/                # 各分块独立注册，按 order 拼接
│       ├── system_prompt/      # 认知架构（order 0，仅 main）
│       ├── attachment_prompt/  # 运行时通知/中断处理协议（order 5，仅 main）
│       ├── tool_prompt/        # 工具使用原则 + 已持有工具的 name 与简短描述（order 10）
│       ├── skill_prompt/       # 技能原则 + 已注册技能列表（order 20，仅 skill_tool 权限）
│       ├── session_recent/     # 最近 3 个 session 的 slice 摘要（order 30，仅 main，当前 enabled=False）
│       ├── timeline_prompt/    # 跨会话时间线，读 timeline.json 做近/远分层（order 30，仅 main）
│       ├── memory_prompt/      # 用户画像注入，读 user.json（order 35，仅 main）
│       ├── agent_prompt/       # {agent_name}_agent.md 身份（order 40，覆盖 main/slice/summary/plan）
│       └── basic_prompt/       # 当前时间戳（order 50）
│
├── session/                    # 会话生命周期
│   ├── session_core.py         # Session 类（持久化 / 切片 / 摘要 / 压缩 / message_list 重建）
│   ├── attachment_core.py      # 运行时通知/中断的纯内存态实现
│   ├── session_plan.py         # Plan / Plan_step 类（读取与推进 plan 状态）
│   ├── session_detail/         # 每个会话的完整 JSON：切片 + 消息流（不纳入版本控制）
│   └── session_plan/           # plan_design 落盘的计划文件（不纳入版本控制）
│
├── hook/                       # 事件驱动 Hook 系统
│   ├── hook_core.py            # HookManager：注册 / 触发 / match 过滤 / 后台线程池
│   ├── __init__.py             # 递归发现 hook/hooks/**/hook.py
│   └── hooks/                  # 按 hook point 分层
│       ├── pre_toolUse/
│       │   └── inject_import_args/    # 同步：给全部工具注入 agents/session/hooks/Loop/memory
│       ├── after_round/
│       │   ├── memory_pipeline/       # 后台：切片 + 摘要，把 worthy slice 交给 Memory
│       │   └── session_compress/      # 同步：Token 超限时压缩 session
│       └── after_session/
│           ├── final_memory_pipeline/ # 后台：会话退出时处理最终定型尾片
│           └── session_timeline/      # 后台：把 worthy slice 提炼成跨会话时间线事件
│
├── tool/                       # 工具系统
│   ├── tool_core.py            # 工具注册 / schema 推导 / match_tool / pre_toolUse 触发
│   ├── __init__.py             # 只导入 tool/tools/ 下的一级 package
│   └── tools/
│       ├── command/            # 命令行执行 + security.py 安全闸门（见设计决策末尾）
│       ├── file_tool/          # 文件工具集群
│       │   ├── file_read/      # 读取（带行号，三重输出上限）
│       │   ├── file_write/     # 写入/新建（整体覆盖）
│       │   ├── file_edit/      # 局部编辑（唯一字符串替换）
│       │   ├── file_glob/      # 按文件名 glob 查找
│       │   └── file_grep/      # 按正则搜索内容
│       ├── web_search/         # DuckDuckGo 搜索
│       ├── web_fetch/          # 网页抓取（线程池并行多 URL）
│       ├── memory_recall/      # 语义搜索历史会话切片
│       ├── session_slice/      # 读取特定会话原文
│       ├── plan_tool/          # plan 集群（内部调用 Loop 跑 plan_agent）
│       │   ├── plan_design/    # 创建/修改分步计划
│       │   ├── plan_update/    # 更新指定 step 的状态与结果
│       │   ├── plan_mode_on/   # 激活 plan 执行模式
│       │   └── plan_mode_off/  # 结束 plan 执行模式
│       ├── subagent_tool/
│       │   └── subagent_create/# 并行创建并运行多个临时 subagent（默认只读授权，可用 tool_autho 覆盖）
│       ├── skill_tool/         # 技能集群
│       │   ├── skill_list/     # 扫描磁盘技能列表（当前禁用）
│       │   ├── skill_load/     # 按目录名加载 skill.md 正文
│       │   └── skill_finish/   # 技能创建收尾：确认后回写 skill_info
│       ├── user_intention/     # 用户意图识别（当前禁用）
│       └── interaction/
│           └── askUserQuestion/# 反向提问 / 澄清
│
├── mcp_client/                 # MCP 客户端（目录不能叫 mcp，会遮蔽同名 pip 包）
│   ├── mcp_core.py             # 对外门面：prewarm_mcp_servers / shutdown_mcp_servers
│   ├── mcp_config.py           # 读 mcp.json、展开 ${VAR} 占位符、按 enabled 过滤
│   ├── mcp_supervisor.py       # asyncio 隔离：daemon 线程 + 单个常驻 supervisor task
│   ├── mcp_bridge.py           # 远端工具运行时 register_tool / unregister_tool
│   ├── mcp.json.example        # 配置模板
│   └── mcp.json                # 本机实际配置（不纳入版本控制）
│
├── memory/                     # 跨会话记忆
│   ├── memory_core.py          # 主线：slice 分类、去重、slice_node 入库、user_info 画像提炼
│   ├── memory_storage/         # 派生存储（slice_node / user / timeline / advanced_task_node）
│   ├── memory_config/          # 画像维度模板等运行时配置
│   ├── memory_prompt/          # memory agent 的 system prompt 来源，按 type 分文件
│   └── memory_log/             # 失败诊断与评估日志
│
├── local_model/                # 本地中文嵌入模型（GTE）
│                               # 权重不纳入版本控制，首次运行自动从 ModelScope 下载（约 195MB）
│
├── tui/                        # Textual TUI
│   ├── tui_core.py             # 入口：App 装配、do_work 工作线程、_run_round
│   ├── tui_style.tcss          # 全局样式
│   ├── tui_channel/
│   │   └── tui_channel_core.py # 按 agent_name 路由的 channel：append_stream / build_widget
│   └── tui_widget/
│       ├── tui_widgets_core.py # @widget_register 注册 + build_widget 按类型构造
│       └── tui_widgets/        # 每个 widget 一个目录（widget_core.py + widget_css.tcss）
│           ├── UserInput/ UserContent/
│           ├── AssistantContent/ AssistantThinking/ AssistantToolCall/
│           ├── AskUserQuestion/ SystemError/
│           └── BottomBar/ BottomThinkTip/ StateBar/
│
├── skill/                      # 技能系统：每个技能一个目录，内含 skill.md（YAML frontmatter + 正文）
│
└── workspace/                  # 工作区（不参与项目代码）
```

---

## 核心设计决策

### 1. Multi-Agent 集群，而非单 Agent 函数调用

5 个常驻 Agent 各有独立身份与工具授权，定义在 `agent/agents.yaml`。它们不是 main 的函数——共享记忆空间，独立推理。

模型等级分两档：main / slice / summary / plan 用 `medium_level`，memory 用 `low_level`。

工具授权分化明显：

| Agent | 授权 |
|---|---|
| `main` | 全开 |
| `plan` | basic / file_read / memory / subagent / web / skill / mcp |
| `memory` | 仅 memory_tool |
| `slice`、`summary` | 全关（它们只做结构化抽取，不需要工具） |

授权类别在 yaml 里有 13 个键，但其中 `advance_tool` 与 `config_tool` 目前是**预留位，没有任何工具挂靠**；真正有实体工具的是 10 类，加上运行时注册的 `mcp_tool` 共 11 类。

除 5 个常驻 Agent 外，`subagent_create` 可以在运行时按任务临时构造 Subagent（随机唯一名 `subagent_{uuid8}`），并注册进 agents 容器供按名路由。

### 2. 会话切片 + 嵌入召回，而非 RAG

每轮对话由 LLM 切话题边界 → 本地 GTE 模型算嵌入 → 余弦相似度搜索。不是「搜文档」，是「唤起经历」。

定型的切片再经后台 Memory 管线做分类、按 `(session_id, start_round, end_round)` 去重、提炼用户画像与跨会话时间线。整条链路不依赖任何外部向量数据库。

### 3. 事件驱动 Hook 系统

Hook 自动发现 → 注册 → 多事件点触发 → 同步/异步执行 → match 条件过滤。扩展一个 Hook 只需在对应 hook point 目录下新建 `hook.py`。

当前注册 5 个：

| Hook | hook point | 模式 | 职责 |
|---|---|---|---|
| `inject_import_args` | `pre_toolUse` | 同步 | 给**全部**工具统一注入 `agents`/`session`/`hooks`/`Loop`/`memory`，工具自己决定用不用，无需按工具名逐一注册匹配 |
| `memory_pipeline` | `after_round` | 后台 | 切片 + 摘要，把已定型且 worthy 的 slice 交给 Memory |
| `session_compress` | `after_round` | 同步 | Token 超限时压缩 session |
| `final_memory_pipeline` | `after_session` | 后台 | 会话退出时处理最终定型尾片 |
| `session_timeline` | `after_session` | 后台 | 把 worthy slice 提炼成一条跨会话时间线事件 |

Memory 入库的总闸是 `Memory.pipeline_enabled`（由 `main.py` 创建时统一传入，hook 不各自传参）。注意它的判空**在切片之前**：`pipeline_enabled=False` 时，切片与摘要也一并短路，不只是落盘短路。

### 4. 工具注册 + OpenAI Schema 自动生成

装饰器 `@register_tool` + `inspect.signature` → 自动生成 function-calling 参数 schema，新增工具零样板代码。

函数签名是模型可见参数契约的**唯一真相源**。schema 推导时排除 `self`、`agents`、`session`、`memory` 和 `**kwargs`；所有工具函数统一保留 `**kwargs`，用来吞掉 `pre_toolUse` 无条件注入但本工具不使用的运行时对象。

MCP 工具是唯一的例外：远端 server 自报的 `inputSchema` 本身就是 JSON Schema，直接采用，不走签名推导——闭包签名是 `**kwargs`，推导不出任何契约。

### 5. Prompt 分层组合

`prompt/prompts/` 下每个分块用 `@register_prompt(order, condition, enabled)` 独立注册，`build_prompt(agent)` 按 order 排序、按 condition / enabled 过滤后拼接成最终 system prompt。新增分块只需建目录写 `prompt.py`，自动发现注册，不改其他分块。

当前 9 个分块的顺序与条件见上文目录结构。几处值得注意的：

- **`session_recent` / `memory_prompt` / `timeline_prompt` 是启动快照**——在 Agent 初始化时读盘，同一进程中后续写入不会自动刷新 system prompt
- **`timeline_prompt` 的注册名是 `timeline`（与目录名不同），enabled 在 import 时由 `timeline.json` 是否存在决定**，全新 clone 上为 disabled
- **memory agent 不走 `agent_prompt`**——它的 system prompt 由 `memory_core` 用 `memory_prompts.get_memory_type_prompt()` 直接替换 `message_list[0]`
- **MCP 工具不进 `tool_prompt`**——system prompt 是启动快照不刷新，MCP 工具只在 function-calling schema 里可见

### 6. 模块解耦

agent、session、tool、hook 等模块彼此之间不直接引用，而是通过 `main.py` 装配链接、通过 hook 在 loop 中的注入进行交互。这样做是为了避免后续框架扩展时产生不必要的循环引用，也避免在各种子文件里写懒引用那种不优雅的绕法。

底层 registry、类型、配置和存储组件允许直接 import——目标是避免实例级全局耦合，不是追求模块间绝对零 import。

### 关于 file_tool 的读写不对称

`file_write` 与 `file_edit` 的写入路径被限制在 `workspace/` 与技能目录内，但 `file_read`、`file_grep`、`file_glob` **可以读磁盘上任意绝对路径**。这是有意的取舍（读写风险等级不同），但别误以为整个 file_tool 集群都在沙箱里。

另外 `web_fetch` 的输出硬截断在 5000 字符且**没有续读协议**——是唯一一个截断后不告诉模型怎么拿剩余部分的工具，与 `file_read` 的 offset 续读、`command` 的首尾保留式截断不一致。已知待修。

### 关于 command 工具的安全闸门

`tool/tools/command/security.py` 值得单独一提，因为它的设计经过一次方向性反转：

- **闸门是破坏性拦截，不是白名单准入**。早期版本要求命令登记在白名单里才放行，实测误伤率过高（`git -C`、`npm --prefix`、`netstat -ano` 全被拒）。现在 `COMMAND_WHITELIST` 降级为分类表，未登记的命令标记为 unknown 照常放行，真正被拦的是破坏性操作与危险路径
- **按分隔符分段逐条校验**。`&&`、`||`、`&`、`;`、`|` 都会切分，每一段独立过闸——此前只校验第一段，分隔符之后的命令从不过检
- **Windows 下反斜杠不当转义符**，否则绝对路径会被打碎成非法命令名
- **重定向放行算子、按写操作校验目标路径**，而不是一刀切硬拒
- **`additional_check` 返回拒绝原因字符串而非 bool**，模型能据此换一种写法，而不是对着「未通过额外安全检查」原地打转
- **解释器载荷递归过闸**。`bash -c "rm -rf x"` 与 `rm -rf x` 是同一个操作，但前者一度完全不过检——`bash` 既不在分类表也不在硬拒表，`-c` 后面整条命令只是它的一个参数 token。现在 `bash`/`sh`/`zsh`/`python`/`node`/`powershell` 的 `-c`/`-e` 取值会被取出来当普通命令重新过一遍完整闸门，并有嵌套深度上限

**这层防护的威胁模型是「防模型手滑」，不是沙箱。** 它拦的是模型在正常任务里顺手写出的不可逆操作，不假设对手会蓄意构造绕过。真正需要隔离时应当用容器或虚拟机，不要指望这一层。

---

## 三套自动发现规则

Hook、Prompt、Tool 都依赖「import 执行装饰器注册」的副作用，但发现深度不同：

| 系统 | 发现规则 | 新增模块的要求 |
|---|---|---|
| Hook | 递归发现 `hook/hooks/**/hook.py` | 放在对应 hook point 目录下并用 `@hooks.register`；路径中任一段以下划线开头会被跳过 |
| Prompt | 只扫 `prompt/prompts/` 的**一级目录**，加载固定的 `prompt.py` | 用 `prompt/prompts/<name>/prompt.py` + `@register_prompt`，不支持任意深度递归 |
| Tool | 只导入 `tool/tools/` 下的**一级 package** | package 的 `__init__.py` 必须显式 import 具体实现；嵌套的 `tool.py` 不会仅因文件存在就被注册 |

MCP 工具**不走这张表**：它们在 server 连上之后由 `mcp_bridge.py` 在运行时调 `register_tool(...)` 注册、断开时调 `unregister_tool(...)` 摘除，与 import 期自动发现无关。

具体怎么写见 [扩展指南](EXTENDING.md)。

---

## 数据与持久化

`Session` 构造即创建当前 session 的 JSON 文件，用 `threading.Lock` 保护读改写。

**原始消息与 `session_slice` 是会话事实源**；`slice_node` 是可追溯的派生存储，不反写也不替代原始 slices。Slice 的稳定分层是范围元数据（`start_round` / `end_round`）、`slice_anchor` 内容锚点和 `slice_embedding` 派生向量。

切片流入 Memory 的两条路径：

```text
after_round / memory_pipeline（后台）
  → session._session_slice()
  → session._session_summary()
  → 从已定型片 session_slice[:-1] 中筛出 worthy_summary
  → Memory.slices_pipeline()

after_session / final_memory_pipeline（后台）
  → 对最终定型的尾片做相同筛选
  → Memory.slices_pipeline()
```

`after_round` 只是暂不把仍可能增长的最后一片交给 Memory，并不从 session 中删除它；`after_session` 负责补入最终尾片。两个入口都只过滤**传给 Memory** 的内容，session JSON 始终保留完整、无缝的原始 slices。

以下目录都是真实运行数据，不是可随意重建的临时文件（均已 gitignore）：

- `session/session_detail/`、`session/session_plan/`
- `memory/memory_storage/memory_storages/`、`memory/memory_log/memory_logs/`
- `local_model/` 下的模型权重
