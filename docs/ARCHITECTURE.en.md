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
├── main.py                     # entry: assemble Session/Loop/Memory, prewarm, enter TUI, exit teardown
├── config.py                   # central config (MODEL_LEVEL / paths / runtime constants)
├── pyproject.toml              # project metadata and pinned direct dependencies
├── .env                        # API key & three-tier model config (not version-controlled)
│
├── loop/                       # ReAct reasoning loop
│   ├── loop_core.py            # Loop class — pure ReAct engine (shared by main/subagent; zero awareness of plan orchestration)
│   └── orchestrator.py         # PlanRunner — stepwise plan orchestrator, independent of Loop (includes stall circuit-breaker)
│
├── agent/                      # Agent cluster
│   ├── agent_core.py           # Agent class + Agents container (YAML-driven)
│   └── agents.yaml             # 5 resident Agents: main/slice/summary/plan/memory
│
├── prompt/                     # layered Prompt composition (decorator + directory auto-discovery registration)
│   ├── prompt_core.py          # Prompt class: thin wrapper calling build_prompt(agent)
│   ├── prompt_register.py      # @register_prompt + build_prompt (order sort / condition filter / enabled switch)
│   ├── __init__.py             # auto-discover and import prompt/prompts/*/prompt.py
│   └── prompts/                # each block registers independently; concatenated by order
│       ├── system_prompt/      # cognitive architecture (order 0, main only)
│       ├── attachment_prompt/  # runtime notice/interrupt handling protocol (order 5, main only)
│       ├── tool_prompt/        # tool-use principles + name and short desc of held tools (order 10)
│       ├── skill_prompt/       # skill principles + registered skill list (order 20, skill_tool auth only)
│       ├── session_recent/     # slice summaries of last 3 sessions (order 30, main only, currently enabled=False)
│       ├── timeline_prompt/    # cross-session timeline; reads timeline.json for near/far layering (order 30, main only)
│       ├── memory_prompt/      # user-profile injection; reads user.json (order 35, main only)
│       ├── agent_prompt/       # {agent_name}_agent.md identity (order 40, covers main/slice/summary/plan)
│       └── basic_prompt/       # current timestamp (order 50)
│
├── session/                    # session lifecycle
│   ├── session_core.py         # Session class (persist / slice / summary / compress / rebuild message_list)
│   ├── attachment_core.py      # pure in-memory runtime notice/interrupt implementation
│   ├── session_plan.py         # Plan / Plan_step classes (read and advance plan state)
│   ├── session_detail/         # full JSON per session: slices + message stream (not version-controlled)
│   └── session_plan/           # plan files written by plan_design (not version-controlled)
│
├── hook/                       # event-driven Hook system
│   ├── hook_core.py            # HookManager: register / trigger / match filter / background thread pool
│   ├── __init__.py             # recursively discover hook/hooks/**/hook.py
│   └── hooks/                  # layered by hook point
│       ├── pre_toolUse/
│       │   └── inject_import_args/    # sync: inject agents/session/hooks/Loop/memory into all tools
│       ├── after_round/
│       │   ├── memory_pipeline/       # background: slice + summary; hand worthy slices to Memory
│       │   └── session_compress/      # sync: compress session when tokens exceed limit
│       └── after_session/
│           ├── final_memory_pipeline/ # background: handle final settled trailing slice on session exit
│           └── session_timeline/      # background: distill worthy slices into a cross-session timeline event
│
├── tool/                       # tool system
│   ├── tool_core.py            # tool registration / schema derivation / match_tool / pre_toolUse trigger
│   ├── __init__.py             # import only first-level packages under tool/tools/
│   └── tools/
│       ├── command/            # command execution + security.py gate (see end of design decisions)
│       ├── file_tool/          # file-tool cluster
│       │   ├── file_read/      # read (with line numbers; triple output caps)
│       │   ├── file_write/     # write/create (full overwrite)
│       │   ├── file_edit/      # local edit (unique string replace)
│       │   ├── file_glob/      # glob by filename
│       │   └── file_grep/      # search content by regex
│       ├── web_search/         # DuckDuckGo search
│       ├── web_fetch/          # web fetch (thread-pool parallel multi-URL)
│       ├── memory_recall/      # semantic search over historical session slices
│       ├── session_slice/      # read a specific session raw text
│       ├── plan_tool/          # plan cluster (internally calls Loop to run plan_agent)
│       │   ├── plan_design/    # create/modify stepwise plan
│       │   ├── plan_update/    # update status and result of a given step
│       │   ├── plan_mode_on/   # activate plan execution mode
│       │   └── plan_mode_off/  # end plan execution mode
│       ├── subagent_tool/
│       │   └── subagent_create/# create and run multiple temporary subagents in parallel (default read-only auth; overridable via tool_autho)
│       ├── skill_tool/         # skill cluster
│       │   ├── skill_list/     # scan on-disk skill list (currently disabled)
│       │   ├── skill_load/     # load skill.md body by directory name
│       │   └── skill_finish/   # skill-creation finish: write back skill_info after confirmation
│       ├── user_intention/     # user-intention recognition (currently disabled)
│       └── interaction/
│           └── askUserQuestion/# ask back / clarify
│
├── mcp_client/                 # MCP client (directory must not be named mcp — would shadow the pip package)
│   ├── mcp_core.py             # public facade: prewarm_mcp_servers / shutdown_mcp_servers
│   ├── mcp_config.py           # read mcp.json, expand ${VAR} placeholders, filter by enabled
│   ├── mcp_supervisor.py       # asyncio isolation: daemon thread + single resident supervisor task
│   ├── mcp_bridge.py           # runtime register_tool / unregister_tool for remote tools
│   ├── mcp.json.example        # config template
│   └── mcp.json                # local actual config (not version-controlled)
│
├── memory/                     # cross-session memory
│   ├── memory_core.py          # main line: slice classify, dedupe, slice_node ingest, user_info profile extraction
│   ├── memory_storage/         # derived storage (slice_node / user / timeline / advanced_task_node)
│   ├── memory_config/          # runtime config such as profile-dimension templates
│   ├── memory_prompt/          # source of memory agent system prompt, one file per type
│   └── memory_log/             # failure diagnostics and evaluation logs
│
├── local_model/                # local Chinese embedding model (GTE)
│                               # weights not version-controlled; first run auto-downloads from ModelScope (~195MB)
│
├── tui/                        # Textual TUI
│   ├── tui_core.py             # entry: App assembly, do_work worker thread, _run_round
│   ├── tui_style.tcss          # global styles
│   ├── tui_channel/
│   │   └── tui_channel_core.py # channel routed by agent_name: append_stream / build_widget
│   └── tui_widget/
│       ├── tui_widgets_core.py # @widget_register registration + build_widget construct by type
│       └── tui_widgets/        # one directory per widget (widget_core.py + widget_css.tcss)
│           ├── UserInput/ UserContent/
│           ├── AssistantContent/ AssistantThinking/ AssistantToolCall/
│           ├── AskUserQuestion/ SystemError/
│           └── BottomBar/ BottomThinkTip/ StateBar/
│
├── skill/                      # skill system: one directory per skill containing skill.md (YAML frontmatter + body)
│
└── workspace/                  # workspace (not part of project code)
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
