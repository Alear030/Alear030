# Alear030 Architecture

[中文](ARCHITECTURE.md) · **English**

← [Back to README](../README.en.md)

This document is the authoritative source of architecture facts for Alear030, written for someone reading the project for the first time. For a deeper look at the memory pipeline see [Memory System](modules/memory.en.md); to extend the system see [Extending](EXTENDING.en.md); to get it running see [Configuration](CONFIGURATION.en.md).

Alear030 is not a "Python Agent framework". It is a complete Agent infrastructure (Harness) — handling tool orchestration, multi-agent routing, session lifecycle, event-driven Hooks, and cross-session memory recall. The model does the reasoning; every other layer lives in this repository.

---

## Table of Contents

- [Runtime Data Flow](#runtime-data-flow)
- [Directory Structure](#directory-structure)
- [Core Design Decisions](#core-design-decisions)
- [Three Auto-Discovery Rules](#three-auto-discovery-rules)
- [Data and Persistence](#data-and-persistence)

---

## Runtime Data Flow

### Startup

`main.py` does one thing: assemble high-level objects in dependency order, then hand control to the TUI.

```text
prewarm_embedding_model()        # spawn independent worker to load embedding; does not block TUI startup
  → prewarm_mcp_servers(agents)  # background thread connects MCP servers one by one; single failure is logged only
  → Memory(memory agent, independent Loop())
  → Session(slice_agent, summary_agent, main system prompt)
  → Loop(agents, session, hooks, memory)
  → Alear030TUI assembly (TUI hangs its receive_loop_emit on loop.emit)
  → hooks.trigger('before_session')
  → AlearTui.run()               # enter Textual event loop
```

The embedding model is prewarmed in a separate process because loading is slow (on first run it also downloads ~195MB of weights from ModelScope); putting that in the main process would delay TUI startup. MCP servers follow the same idea via a background thread: once a server connects, its tools are registered into the tool table and each agent's `tool_list` is refreshed.

### One User Input

```text
Input.Submitted
  → do_work thread → _run_round()
  → hooks.trigger('before_round')
  → loop.loop_run('main', message)
      → run_turn()                  # ReAct: model → tools → model → …
      → PlanRunner.run()            # plan mode only; may call run_turn multiple times inside
  → hooks.trigger('after_round')
  → finally unlock input
```

`session.round` increments at the end of every `run_turn()` that has a session; `after_round` is triggered **once** by the TUI's `_run_round()` after the entire top-level `loop_run()` returns. When a user input enters plan orchestration it may contain multiple rounds — the two are not one-to-one.

While reasoning runs, streaming events are emitted back to the TUI:

```text
loop.emit(event, content, stream_id, agent_name)
  → TUI finds TuiChannel by agent_name
  → call_from_thread back to UI thread
  → channel.append_stream
  → tuiwidgets.build_widget renders
```

User-visible harness errors go through `Loop.emit(event='SystemError')`; tool-own errors go through `_error_result` / `tool_call_extra_info` — there is no separate notification bus.

### Shutdown

```text
finally:
  signal.signal(SIGINT, SIG_IGN)   # ignore Ctrl+C during teardown so join is not interrupted by a second press
  → hooks.trigger('after_session')
  → hooks.wait_all()
  → hooks.shutdown()
  → shutdown_mcp_servers()
  → shutdown_embedding_worker()
```

---

## Directory Structure

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

## Core Design Decisions

### 1. Multi-Agent cluster, not a single-Agent function call

Five resident Agents each have their own identity and tool authorization, defined in `agent/agents.yaml`. They are not functions of main — they share a memory space and reason independently.

Model levels split into two tiers: main / slice / summary / plan use `medium_level`; memory uses `low_level`.

Tool authorization is clearly differentiated:

| Agent | Authorization |
|---|---|
| `main` | All on |
| `plan` | basic / file_read / memory / subagent / web / skill / mcp |
| `memory` | memory_tool only |
| `slice`, `summary` | All off (they only do structured extraction and need no tools) |

The yaml has 13 authorization-category keys, but `advance_tool` and `config_tool` are currently **placeholders with no tools attached**; 10 categories actually have concrete tools, plus runtime-registered `mcp_tool` for 11 in total.

Besides the five resident Agents, `subagent_create` can construct temporary Subagents at runtime per task (random unique name `subagent_{uuid8}`) and register them into the agents container for name-based routing.

### 2. Session slicing + embedding recall, not RAG

Each conversation turn has topic boundaries cut by an LLM → local GTE model computes embeddings → cosine-similarity search. This is not "search documents"; it is "recall experience".

Settled slices then go through the background Memory pipeline for classification, dedup by `(session_id, start_round, end_round)`, and extraction of user profile plus cross-session timeline. The whole chain depends on no external vector database.

### 3. Event-driven Hook system

Hook auto-discovery → registration → multi-event-point triggering → sync/async execution → match-condition filtering. Extending a Hook only requires a new `hook.py` under the corresponding hook-point directory.

Five are currently registered:

| Hook | hook point | Mode | Role |
|---|---|---|---|
| `inject_import_args` | `pre_toolUse` | sync | Inject `agents`/`session`/`hooks`/`Loop`/`memory` into **all** tools uniformly; each tool decides whether to use them — no per-tool-name registration matching |
| `memory_pipeline` | `after_round` | background | Slice + summary; hand settled and worthy slices to Memory |
| `session_compress` | `after_round` | sync | Compress session when tokens exceed the limit |
| `final_memory_pipeline` | `after_session` | background | Handle the final settled trailing slice on session exit |
| `session_timeline` | `after_session` | background | Distill worthy slices into one cross-session timeline event |

The master gate for Memory ingestion is `Memory.pipeline_enabled` (passed once when `main.py` constructs Memory; hooks do not each take their own parameter). Note that the null check is **before slicing**: when `pipeline_enabled=False`, slicing and summary short-circuit together, not only persistence.

### 4. Tool registration + automatic OpenAI Schema generation

Decorator `@register_tool` + `inspect.signature` → automatically generate function-calling parameter schemas; adding a tool needs zero boilerplate.

The function signature is the **sole source of truth** for the model-visible parameter contract. Schema derivation excludes `self`, `agents`, `session`, `memory`, and `**kwargs`; every tool function uniformly keeps `**kwargs` to absorb runtime objects that `pre_toolUse` injects unconditionally but this tool does not use.

MCP tools are the only exception: the remote server's self-reported `inputSchema` is already JSON Schema and is adopted directly, without signature derivation — the closure signature is `**kwargs` and yields no contract.

### 5. Layered Prompt composition

Each block under `prompt/prompts/` registers independently with `@register_prompt(order, condition, enabled)`; `build_prompt(agent)` sorts by order, filters by condition / enabled, then concatenates into the final system prompt. Adding a block only requires creating a directory and writing `prompt.py` — auto-discovered and registered, without editing other blocks.

Order and conditions for the current nine blocks are in the directory structure above. A few notable points:

- **`session_recent` / `memory_prompt` / `timeline_prompt` are startup snapshots** — read from disk at Agent init; later writes in the same process do not automatically refresh the system prompt
- **`timeline_prompt`'s registration name is `timeline` (different from the directory name); enabled is decided at import time by whether `timeline.json` exists**, so a fresh clone has it disabled
- **memory agent does not use `agent_prompt`** — its system prompt is replaced directly on `message_list[0]` by `memory_core` via `memory_prompts.get_memory_type_prompt()`
- **MCP tools do not enter `tool_prompt`** — the system prompt is a startup snapshot and does not refresh; MCP tools are visible only in the function-calling schema

### 6. Module decoupling

Modules such as agent, session, tool, and hook do not reference each other directly; they are wired through assembly in `main.py` and interact via hook injection in the loop. This avoids unnecessary circular imports as the framework grows, and avoids awkward lazy-import workarounds scattered across subfiles.

Lower-level registry, types, config, and storage components may be imported directly — the goal is to avoid instance-level global coupling, not absolute zero imports between modules.

### On file_tool read/write asymmetry

Write paths for `file_write` and `file_edit` are restricted to `workspace/` and skill directories, but `file_read`, `file_grep`, and `file_glob` **can read any absolute path on disk**. This is an intentional tradeoff (read and write have different risk levels); do not assume the entire file_tool cluster is sandboxed.

Separately, `web_fetch` hard-truncates output at 5000 characters and has **no continuation protocol** — it is the only tool that truncates without telling the model how to get the remainder, inconsistent with `file_read`'s offset continuation and `command`'s head-and-tail truncation. Known issue to fix.

### On the command tool security gate

`tool/tools/command/security.py` deserves a separate note because its design once reversed direction:

- **The gate is destructive interception, not whitelist admission**. Early versions required commands to be on a whitelist to pass; false-positive rate was too high in practice (`git -C`, `npm --prefix`, `netstat -ano` were all rejected). `COMMAND_WHITELIST` is now demoted to a classification table; unlisted commands are marked unknown and still allowed — what is actually blocked are destructive operations and dangerous paths
- **Validate segment by segment on separators**. `&&`, `||`, `&`, `;`, and `|` all split; each segment goes through the gate independently — previously only the first segment was checked, and commands after separators were never inspected
- **On Windows, backslashes are not treated as escape characters**, or absolute paths would be shattered into illegal command names
- **Redirects allow the operator and validate the target path as a write**, rather than hard-rejecting wholesale
- **`additional_check` returns a rejection-reason string rather than a bool**, so the model can try another formulation instead of spinning on "failed additional security check"
- **Interpreter payloads are recursively gated**. `bash -c "rm -rf x"` and `rm -rf x` are the same operation, but the former once escaped inspection entirely — `bash` was neither in the classification table nor the hard-reject table, and the whole command after `-c` was just one parameter token. Now `-c`/`-e` values for `bash`/`sh`/`zsh`/`python`/`node`/`powershell` are extracted and re-run through the full gate as ordinary commands, with a nesting-depth limit

**This layer's threat model is "prevent model slips", not a sandbox.** It blocks irreversible operations the model casually writes during normal tasks; it does not assume an adversary will deliberately craft bypasses. When real isolation is needed, use a container or VM — do not rely on this layer.

---

## Three Auto-Discovery Rules

Hook, Prompt, and Tool all depend on the side effect of "import runs decorator registration", but discovery depth differs:

| System | Discovery rule | Requirements for new modules |
|---|---|---|
| Hook | Recursively discover `hook/hooks/**/hook.py` | Place under the corresponding hook-point directory and use `@hooks.register`; any path segment starting with underscore is skipped |
| Prompt | Scan only **first-level directories** under `prompt/prompts/`, load fixed `prompt.py` | Use `prompt/prompts/<name>/prompt.py` + `@register_prompt`; arbitrary-depth recursion is not supported |
| Tool | Import only **first-level packages** under `tool/tools/` | The package `__init__.py` must explicitly import concrete implementations; a nested `tool.py` is not registered merely because the file exists |

MCP tools **do not use this table**: after a server connects, `mcp_bridge.py` calls `register_tool(...)` at runtime and `unregister_tool(...)` on disconnect — unrelated to import-time auto-discovery.

For how to write them, see [Extending](EXTENDING.en.md).

---

## Data and Persistence

Constructing a `Session` creates the current session's JSON file immediately, protected by `threading.Lock` for read-modify-write.

**Raw messages and `session_slice` are the session source of truth**; `slice_node` is a traceable derived store that neither rewrites nor replaces original slices. A Slice's stable layers are range metadata (`start_round` / `end_round`), the `slice_anchor` content anchor, and the `slice_embedding` derived vector.

Two paths for slices flowing into Memory:

```text
after_round / memory_pipeline (background)
  → session._session_slice()
  → session._session_summary()
  → from settled slices session_slice[:-1], filter worthy_summary
  → Memory.slices_pipeline()

after_session / final_memory_pipeline (background)
  → same filter on the final settled trailing slice
  → Memory.slices_pipeline()
```

`after_round` only temporarily withholds the last slice (which may still grow) from Memory; it does not delete it from the session. `after_session` is responsible for admitting the final trailing slice. Both entry points only filter what is **passed to Memory**; the session JSON always keeps complete, seamless original slices.

The following directories are real runtime data, not disposable temporary files (all gitignored):

- `session/session_detail/`, `session/session_plan/`
- `memory/memory_storage/memory_storages/`, `memory/memory_log/memory_logs/`
- Model weights under `local_model/`
