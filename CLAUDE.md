# CLAUDE.md

## 项目概述

Alear030 — 从零自研的 Python Agent Harness。核心思想：**Model + Harness = Agent**。处理工具编排、多 Agent 路由、会话生命周期、事件驱动 Hook、跨会话记忆召回。

## 运行与验证

所有命令从仓库根目录执行：

```bash
python main.py    # 交互式 REPL；Ctrl+C 触发有序收尾
```

依赖根目录 `.env` 中的三级模型配置（`max_level` / `medium_level` / `low_level`），由 `config.py` 读取。当前 `pyproject.toml` 尚未声明完整运行依赖，也没有锁文件，不能把 `pip install -e .` 等命令当成可复现的完整安装方案。

验证改动是否可用时用 `alear030-verify` 技能——这个项目的验证方式有几个反直觉的坑（`python main.py` 有真实副作用、验证脚本必须用 `python -m` 点号路径调用、`unittest discover` 不能带 `-s test`），别凭经验直接套用通用 Python 项目的验证套路。

## 协作方式

本项目不走“用户给需求 → Claude 闷头执行”的单向模式。默认节奏是**探索 → 规划 → 执行 → 验收**；一句话能描述清 diff 的小改（改错字、加日志、重命名）可直接做。

1. **探索** — 先读相关代码/资料搞清现状，不改任何东西；产出“现状是 X”
2. **规划** — 提方案并主动点出取舍与风险；较大特性可用 `AskUserQuestion` 反向采访；产出用户能修改、能拍板的计划
3. **执行** — 用户拍板后才动手
4. **验收** — 提供测试输出或跑通结果，不靠“做好了”这句断言

**分工边界**：用户拥有方向、品味、北极星判断和“什么算够好”的最终拍板；Claude 负责读代码、查资料、铺上下文、起草方案、实现、验证并主动指出选项和风险。用户在监督位，Claude 在执行位。

**反馈文化**：

- 用户随时可以打断纠偏，越早越好
- 同一问题纠正超过两次 → 停下重开，换根本思路或把已知信息重写成更清楚的需求，不继续叠补丁
- 模糊提问是合法且鼓励的；开放问题用于共创，不要求用户每次先给出成型需求

**代码里的 `@claude` 任务标记**：

- SessionStart hook（`.claude/settings.json`）每次会话开始扫描仓库并注入待办标记
- 完成标记后将原行改写成 `# done(@claude): <做了什么>`，保留痕迹且避免下次重复扫描
- `# @claude(ignore) ...` 是用户自己的备注，不是 Claude 任务，不要修改

**协作经验落盘**：协作中形成的长期工作方式写入用户 memory（feedback 类），不要让它随会话消失。

**Claude Code 执行子代理**：仅在当前会话实际提供 `alear-executor` 类型时可用。它用 Sonnet 承接上下文可自包含、会产生大量一次性噪音的执行任务。节奏是 **Opus 主对话规划与拍板 → 主动推荐派发 → 用户拍板 → Sonnet 执行**；不得自动委派。派发指令必须自包含，它不适合需要边写边理解模块耦合的模糊实现。

项目中有三套不同的 Agent 概念，不能混用：

- `agent/agents.yaml`：项目进程内的 5 个常驻配置 Agent（main/slice/summary/plan/memory）
- `subagent_create`：项目运行时按任务临时构造的无持久化 Subagent
- `alear-executor`：Claude Code 层面的执行子代理；仅当前会话提供时可用

## 稳定模块地图

| 路径 | 职责 |
|------|------|
| `main.py` | 进程入口、高层对象装配、顶层交互循环与退出收尾 |
| `config.py` | 模型级别、数据路径及运行常量 |
| `loop/` | ReAct `Loop` 与独立的 plan 编排器 `PlanRunner` |
| `agent/` | YAML 常驻 Agent 定义、实例化与工具授权 |
| `prompt/` | Prompt 分块注册、组合与启动时上下文快照 |
| `tool/` | 工具注册、schema、授权和具体工具实现 |
| `hook/` | Hook 注册、发现及同步/后台调度 |
| `session/` | 当前 session 的消息、切片、摘要、压缩和 plan 状态 |
| `memory/` | 跨 session 的切片分类、去重、用户画像与持久化 |
| `local_model/` | 本地 embedding 代码与已跟踪模型资产 |
| `skill/` | 项目运行时技能资源 |

`workspace/`、`z_ccstudy/`、`z_old_code/` 不参与主项目分析。

`.cc_file/`（已 `.gitignore`）是非项目内容的存放位置（笔记、复盘、外部材料等），不参与项目代码分析，不受"外科手术式改动"等代码规范约束。

## 核心运行数据流

### 启动、顶层轮次与退出

```text
启动：构造 YAML Agents
  → Session(slice_agent, summary_agent, main system prompt)
  → 主 Loop(agents, session, hooks)
  → Memory(memory agent, 独立 Loop())
  → trigger('before_session')
  -> 进入输入循环

一次用户输入：loop.loop_run('main', message)
  → run_turn()
  → PlanRunner.run()（仅 plan 模式执行，可能再调用多个 run_turn）
  → loop_run 返回
  → main.py 触发一次 after_round

退出（finally）：trigger('after_session')
  → wait_all()
  → shutdown()
```

`session.round` 在每次带 session 的 `run_turn()` 收尾时增长；`after_round` 则由 `main.py` 在整个顶层 `loop_run()` 返回后触发一次。一个用户输入进入 plan 编排时可能包含多个 round，两者不是一一对应。`HookManager.collect()` 当前没有接入主循环，不要把它写入实际生命周期。session 切片如何流入 Memory，见"架构核心 > Session 与 Memory"。

### Prompt 快照、派生存储与主动召回

这三条路径职责不同：

- `session_recent`、`memory_prompt`、`timeline_prompt` 在 Agent 初始化时读取磁盘并组成 main system prompt，是**启动快照**；同一进程中后续写入不会自动刷新该 prompt。`timeline_prompt` 读 `timeline.json` 做近/远分层渲染(近段含叙事线索,远段仅关键词+摘要),是 `after_session` 的 `session_timeline` hook 的唯一消费者，替代了原先经 `before_session` hook 走 attachment 注入的旧路径
- 后台 Memory 管线将定型 slice 分类、去重并写入 `slice_node.json`，命中 `user_info` 时提炼和更新用户画像
- `memory_recall` 主动检索历史 `session/session_detail/*.json` 中的 slice embedding，当前不以 `slice_node.json` 为检索源

## 架构核心

### Loop 与 PlanRunner

`loop/loop_core.py` 的 `Loop` 是 main 和项目临时 Subagent 共用的纯 ReAct 引擎；不传 `session`/`hooks` 时为无持久化模式。Plan 编排位于 `loop/orchestrator.py`，不应回塞进 Loop。

四个非显而易见的设计决策：

- **强制收尾靠物理断供而非提示词**：`_force_final_reply` 不传 tools，让模型只能输出文本
- **mode 切换靠 diff 而非信任模型自觉**：工具批次执行前后比较 `session.mode`，一旦切换便停止同批剩余工具并补齐 tool results
- **模型 API 失败靠统一错误边界而非层层 try/except**：三处 `chat.completions.create` 共用的 `_chat` 把裸异常翻译成 `LoopAPIError`，`loop_run` 顶层统一兜底返回错误字符串，不炸穿 `main.py`；`_tool_calls_api` 的参数解析和 `match_tool` 的工具内部异常仍未纳入此边界（20260702 方案 `polished-wondering-cook.md` 的另外两部分，暂缓）
- **thinking 与 tools 强绑定**：`_chat` 里 `with_tools=True` 时 `extra_body` 固定带 `thinking:enabled`，两者没有拆开的独立开关；想单独关某次调用的 thinking（如高频调用的性能优化）又要保留 tools，需要先解耦这个方法，会影响 main agent 真实运行时行为——不带 tools 的独立直调（如 `session_core.py::_session_slice`、`memory_core.py::slice_type_define`）可以各自直接传 `extra_body` 关闭，不受此绑定影响

`PlanRunner.run()` 在非 plan 模式下直接返回；plan 模式通过 `session.plan.advance()` 取得当前 step，按连续重复的 `step_number` 和 `PLAN_STALL_LIMIT` 检测无进展。未来 GoalRunner 可在其外层做目标验收与重新规划，无需修改 Loop。

### Agent、Prompt 与 Tool

5 个常驻 Agent 的名称、模型级别和工具授权以 `agent/agents.yaml` 为准。`Agent` 构造时通过 `Prompt(agent)` 生成 system prompt。

`@register_prompt(prompt_name, order, condition, enabled)` 注册 Prompt 分块；`build_prompt(agent)` 按 `order` 排序并过滤禁用项和不满足的条件。

Tool schema 由 `inspect.signature` 生成，当前排除 `self`、`agents`、`session` 和 `**kwargs`。函数签名是模型可见参数契约的唯一真相源；运行时校验处理边界输入，不为单个 Tool 另维护平行 schema。确实无法表达的类型约束，应统一扩展推导机制并验证生成结果与 Agent 授权，而不是局部绕开。所有工具函数统一保留 `**kwargs`，用于吞掉 `pre_toolUse` 无条件注入（见"Hook 系统"表）但本工具不使用的 `agents/session/hooks/Loop`；工具类别授权仍以 `agents.yaml` 为准。

### 三套自动发现规则

三者都依赖“import 执行装饰器注册”的副作用，但发现深度不同：

| 系统 | 当前发现规则 | 新增模块要求 |
|------|--------------|--------------|
| Hook | `hook/__init__.py` 递归发现 `hook/hooks/**/hook.py` | 放在对应 hook point 下并使用 `@hooks.register`；路径中的下划线目录会被跳过 |
| Prompt | `prompt/__init__.py` 扫描 `prompt/prompts/` 一级目录并加载固定 `prompt.py` | 使用 `prompt/prompts/<name>/prompt.py` + `@register_prompt`，不支持任意深度递归 |
| Tool | `tool/__init__.py` 只导入 `tool/tools/` 下的一级 package | package 的 `__init__.py` 必须显式 import 具体实现；嵌套 `tool.py` 不会仅因文件存在而注册 |

### Hook 系统

| Hook | hook point | 模式 | 职责 |
|------|------------|------|------|
| `inject_import_args` | `pre_toolUse` | 同步 | 给工具调用注入 `agents/session/hooks/Loop` |
| `memory_pipeline` | `after_round` | 后台 | 切片、摘要并把已定型且 worthy 的 slices 交给 Memory |
| `session_compress` | `after_round` | 同步 | Token 超限时执行 session 压缩 |
| `final_memory_pipeline` | `after_session` | 后台 | 会话退出时处理最终定型尾片 |
| `session_timeline` | `after_session` | 后台 | 会话结束时把全部 worthy slice 提炼成一条跨会话时间线事件,写 `timeline.json` |

`after_round` 参数由 `main.py` 在 `hooks.trigger(...)` 时显式传入；工具运行时对象则由上表的 `inject_import_args`（`pre_toolUse`）注入，这两条注入路径不要混淆。

### Session 与 Memory

`Session` 构造即创建当前 session JSON，使用 `threading.Lock` 保护读改写。原始消息与 `session_slice` 是会话事实源；`slice_node` 是可追溯的派生存储，不应反写或替代原始 slices。Slice 的稳定分层是范围元数据（如 `start_round/end_round`）、`slice_anchor` 内容锚点和 `slice_embedding` 派生向量。

`session/session_plan.py` 的 `Plan.advance()` 是 step 推进的公开入口：刷新磁盘状态、取得首个未完成 step、写入 `active_step_number` 后返回该 step，全部完成时返回 `None`。`active_step_number` 限制本轮唯一允许更新的 step，防止跳步或一次连续完成多个 step。

Memory 当前实际主线位于 `memory/memory_core.py`：负责 slice 分类、按 `(session_id, start_round, end_round)` 去重、`slice_node` 入库、`user_info` 提炼以及对应模板更新。两模块（`memory_core`/`memory_storage`）的职责划分以 `memory_core.py` 顶部 `@claude(ignore)` 注释为准。`memory_storage/` 和 `memory_config/` 都可能被运行时更新。

Session 切片流入 Memory 的路径：

```text
after_round / memory_pipeline（后台）
  → session._session_slice()
  → session._session_summary()
  → 从定型片 session_slice[:-1] 中筛选 worthy_summary
  → Memory.slices_pipeline()

after_session / final_memory_pipeline（后台）
  → 对已经定型的最终尾片执行相同筛选
  → Memory.slices_pipeline()
```

`after_round` 只是暂不把仍可能增长的最后一片交给 Memory，并不从 session 中删除它；`after_session` 负责补入最终尾片。两个入口只过滤传给 Memory 的 `worthy_summary=False`，session JSON 仍保留完整、无缝的原始 slices。历史 slice 缺少该字段时用 `slice.get('worthy_summary', True)` 保守兼容。这两个 hook 的触发时机见"Hook 系统"表。

## 数据与版本控制安全

以下内容都不是可随意重建的临时文件：

- `session/session_detail/`、`session/session_plan/`：真实会话与计划运行数据
- `memory/memory_storage/`、`memory/memory_config/`：派生记忆、用户画像及运行时会更新的配置
- `local_model/`：体积较大的已跟踪模型资产；它不是运行时临时下载目录

只有 `session/session_detail/` 和 `session/session_plan/` 当前明确写入 `.gitignore`；不要假定 memory 或 local model 已被忽略。历史 session 文件可能在加入 ignore 规则前已经被 Git 跟踪，ignore 不会取消跟踪，也不意味着删除后一定能完整恢复。

- 未经用户明确授权，禁止删除、清空或批量覆盖上述目录
- 操作前按需检查 `git status`、`git ls-files -- <path>` 和 `git log -- <path>`，不要根据 `.gitignore` 猜测可恢复性
- 需要干净环境验证时使用临时目录或临时 session id，不得清场式测试真实数据
- 不确定某路径是否属于过程数据、派生记忆或模型资产时，先询问用户
- 用真实历史数据重放验证改动（如测试新版 prompt）时，测试前后对相关文件计算 MD5 并比对，用以证明测试脚本未意外写入；测试脚本本身及其输出落在 `test/` 下的临时文件，不落进正式 `memory_storage`/`session_detail`

## 机制演进与收口

对任何承载行为、状态或编排的机制改动，先说明现有权威路径、生产者、消费者与生命周期。语义相同则扩展既有路径；只有职责、生命周期或事实源确实不同才新增路径。

每项关切只保留一个权威表示：其余注册、缓存、派生文件或展示均须能追溯到该来源。存在先后依赖时，由明确调用者编排；不得依赖自动发现顺序、目录顺序或后台队列时序。

本次变更若明确替换或放弃某路径，必须在同次变更中移除本次产生或被替代的旧入口、配置、文档、提示词和无调用脚手架；不顺手清理任务无关的历史代码。

## 开发约定

- **依赖边界**：`main.py` 负责高层运行实例装配，工具所需运行时对象由 `pre_toolUse` 注入（见"Hook 系统"表）；底层 registry、类型、配置和存储组件允许直接 import。新增依赖时优先避免实例级全局耦合与循环引用，不追求模块间绝对零 import
- **新增 Hook/Prompt/Tool**：发现机制与新增要求见"三套自动发现规则"表
- **外科手术式改动**：只触碰任务直接要求的代码；移动功能时不顺手清理相邻逻辑

## 提交规范

生成 commit message 用 `commit-message` 技能——固定格式是 `YYYYMMDD_HHMMSS 当前进度:...;后续计划:...`，只 commit 本次改动直接相关的文件。
