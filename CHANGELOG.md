# Changelog

版本号采用语义化风格（`major.minor.patch`）：新增能力/结构性重构记 `minor`，bug 修复/小改进记 `patch`，架构级破坏性里程碑记 `major`（预留）。项目无正式发布流程，版本号仅用于标记改动批次，不对应 tag。

按时间倒序排列，最新改动在最上面。每个版本块是一个主题统一的工作批次（可跨多天），日期取批次的实际时间跨度（单天标 `YYYY-MM-DD`，跨天标 `YYYY-MM-DD ~ YYYY-MM-DD`）。

**变更类型标签**：`[新增]` 新功能/新模块 · `[迭代]` 既有功能改进 · `[修复]` bug 修复 · `[重构]` 结构性重构 · `[收口]` 机制收敛/职责归一 · `[清理]` 版本控制治理/文档同步 · `[删除]` 移除功能。重大改动写「契机」（动机/根因）和「验证」（过程声明），小修省略。每块末尾「对应提交」列出 commit hash + 一句话，保证可回溯。

> 早期若干版本块的「对应提交」只列改动描述、不列 commit hash：那几批提交早于当前的 `YYYYMMDD_HHMMSS` message 前缀约定，无稳定锚点可回溯。之后的版本块都带 hash。

## 2026-08-18 ~ 2026-08-19 · v0.8.0 — command 安全闸门方向性反转 + 面向使用者的文档

契机：`command` 工具的白名单准入模型两头不讨好——真实会话 49 次调用误伤 12 次（`git -C`、`npm --prefix`、`netstat -ano` 全被拒），而 `&` 之后的命令从不经过校验，白名单本身可被绕过。同期项目准备公开，缺一套面向使用者而非维护者的文档。

变更：
- [重构] `security.py` 闸门由白名单准入翻转为破坏性拦截：`COMMAND_WHITELIST` 降级为分类表，未登记命令标 `unknown` 照常放行，真正拦截交给 `DESTRUCTIVE_COMMANDS` 与 `BLOCKING_PATTERNS`；三份重复的引号/转义扫描收口为单一 `scan_command`，并按 `&&`/`||`/`&`/`;`/`|` 分段逐条校验
- [修复] 解释器载荷绕过：`rm -rf /tmp/x` 被拒而 `bash -c "rm -rf /tmp/x"` 放行——`bash`/`sh`/`zsh` 既不在分类表也不在硬拒表，`-c` 后整条命令只是一个参数 token 从不递归校验。新增 `_check_interpreter_payload` 作第 1.5 层（必须排在分类之前），把载荷取出重过完整闸门，`threading.local` 记深度上限一层，`powershell -EncodedCommand` 因无法静态校验整条拒
- [修复] `DANGEROUS_PATHS` 三条 Windows 正则原写法要求路径含两个字面反斜杠故从未命中；`wmic` 的 `/format` 由整条拒绝收窄为按取值判定；重定向由一刀切硬拒改为放行算子、按写操作校验目标路径
- [新增] `file_read` 补 `MAX_TOTAL_CHARS` 总量闸与 `MAX_LINE_CHARS` 单行上限；`command` 补 `MAX_OUTPUT_CHARS` 首尾保留式截断、`cwd` 参数、超时后按进程树清理孙进程
- [收口] memory 管线总闸由 `main.py` 硬编码外露为 `config.MEMORY_PIPELINE_ENABLED`——此前旗舰功能默认关闭且只能改源码
- [新增] 面向使用者的文档：双语 README、`docs/ARCHITECTURE.md`、`docs/CONFIGURATION.md`、`docs/EXTENDING.md`、`docs/MEMORY.md`（机制）与 `docs/MEMORY-DESIGN.md`（设计取舍），以及 `SECURITY.md`、`CONTRIBUTING.md`
- [清理] 工具旧名统一为注册名：`[command_runner]`→`[command]`、`[file_writer]`→`[file_write]`，两份 `tool_prompt.md` 标题同步；项目协作规约与 agent 技能纳入版本控制

验证：command 安全层单测 31→44 条全绿，核心断言是包壳与不包壳结论必须一致；AST 149 文件；工具注册探针确认三个注册名在册且旧名零出现；文档技术断言逐条对着源码复核。

对应提交：`66c7b62`(command 工具全面重构) · `7e24f9d`(file_read 单行上限) · `f47d6cb`(文档与协作规约)

后续计划：prompt 层死代码清理与 `docs/PROMPT.md`。

## 2026-08-16 ~ 2026-08-17 · v0.7.7 — TUI 退出手势收口与底部提示

变更：
- [收口] 退出手势统一：`inherit_bindings=False` 关掉 App 默认 `ctrl+q` 与命令面板；`Ctrl+C` 有选区复制、无选区改为双击确认退出（首次发 `ExitConfirm` 切 StateBar 并 2s 超时还原）；SIGINT 经 `call_later` 走同一动作，避免主线程 `call_from_thread` 报错
- [修复] 消息区鼠标选区补 `screen.get_selected_text`，此前只读 `Input.selected_text` 导致拖选仍进确认
- [新增] `BottomThinkTip`：`loop_run` 以 `LoopStart`/`LoopEnd`（finally 保证成对）驱动底部提示
- [收口] 底栏 `event_stop` 上移到 `ExitConfirm` 前，`AskUserQuestion` 复用同一摘除/回焦路径

对应提交：`466d943`(退出手势) · `4ad299e`(双击确认) · `02dc6c8`(底栏 event 收口) · `7d6630a`(BottomThinkTip)

后续计划：中途退出时 `do_work` 仍在跑与 `wait_all` 无超时另切片。

## 2026-08-15 · v0.7.6 — MCP 客户端接入，旧总线 rich_output 退场

契机：需要接入外部工具生态，但官方 SDK 是纯 asyncio 而项目应用层零 asyncio。

变更：
- [新增] `mcp_client/` 集成官方 `mcp` SDK：asyncio 封死在单个 daemon 线程的事件循环里，循环内只有一个常驻 supervisor task 持有 `ClientSessionGroup`；连接/断开必须排队进该 task（`stdio_client` 内部是 anyio task group，cancel scope 必须同 task 进出），`call_tool` 不涉及 cancel scope 故直派不排队
- [新增] `mcp.json` 驱动 stdio 与 Streamable HTTP 两种传输；凭证只以 `${VAR}` 占位符引用、真值走 `.env`，解析不到即跳过该 server；工具名 `mcp__{server_key}__{tool}` 用配置 key 而非 server 自报名
- [迭代] `tool_core` 加 `tool_parameters`（MCP 的 `inputSchema` 本身即 JSON Schema，不走 `inspect.signature`）与 `tool_unregister`；`agent_core` 加 `refresh_tool_list`——`tool_list` 是构造期快照，不刷新则运行时注册的工具进不了模型可见 tools
- [删除] 收口旧总线：删除 `rich_output.py` 及全部 `rich_print` 调用

验证：GitHub 远程 HTTP 拉到 13 个只读工具并实调返回真实数据；本地 stdio server 连接/调用/断开摘除全通且无 cancel scope 报错。

对应提交：`6f30b51`(MCP 客户端体系) · `97e4619`(收口 rich_output)

后续计划：模型自管 server 的工具组与 `tools/list_changed` 热刷新。

## 2026-08-13 ~ 2026-08-14 · v0.7.5 — TUI 底部栏协议、交互工具收口与错误通道

变更：
- [新增] `BottomBar` 承接底部槽（UserInput + StateBar），`AskUserQuestion` 多题 tab 可辨当前题与已答题，作答后在工具卡片展示逐题问答摘要
- [收口] 分散的 `skill_list`/`skill_load`/`skill_finish` 收拢为 `skill_tool` 集群
- [新增] `SystemError` 错误通道：整轮异常、未知路由与模型调用失败统一走这条，不另开通知总线
- [迭代] embedding 预热改为启动即后台 boot，缺权重时在 worker 内下载，不阻塞 TUI 启动
- [修复] TUI 运行时原文 `Static` 关 Rich markup，避免正文里的方括号被当标记解析

对应提交：`fc0eb94`(底部栏协议) · `3a78053`(AskUserQuestion 交互) · `5d39992`(skill_tool 收拢) · `c9e38ab`(SystemError) · `2079a77`(embedding 后台 boot) · `b26928d`(关 Rich markup)

后续计划：继续 TUI 主线与 channel 轮次记账。

## 2026-08-05 ~ 2026-08-10 · v0.7.4 — 工具调用消费端闭环与 emit 三态协议

变更：
- [新增] `ToolCallResult` 融入工具执行环节：`match_tool` 重写为工具自驱 `error`/`processing`/`success` 三态，`tool_call_processing` helper 给无特化 emit 的工具兜底
- [新增] `tool_widget` 的 `extra_info` 挂载 widget 协议整体落地（框架级），`web_search`/`web_fetch` 按新协议特化渲染
- [收口] `AssistantThinking` 骨架事件后移进首个 `reasoning_content` chunk，消除空骨架倒计时；`AssistantContent` 改 pending/holder/timer 攒字刷新
- [修复] `web_search` 注入参数收口：`tool_call_content` 混进工具 schema 致首次调用 `TypeError`，schema 排除名单补齐
- [清理] 新建 `.gitattributes` 断根仓库级行尾符约定（`* text=auto`），`loop_core.py` 混合换行归一化；删除旧版 TUI 备份文件

对应提交：`a89eb03`(ToolCallResult 融入执行) · `32ca43b`(extra_info 挂载协议) · `13fae95`(thinking 流式收口) · `3328aa3`(web_fetch emit 特化) · `5057327`(web_search 注入收口) · `86b3af0`(.gitattributes)

后续计划：channel 轮次记账重构与 toolcall trace。

## 2026-08-03 · v0.7.3 — memory 入库开关收口 + thinking 与正文分离落盘

变更：
- [收口] memory 管线入库开关收拢为 `Memory.pipeline_enabled` 实例属性：`slices_pipeline` 去掉 `enable` 参数改读 `self.pipeline_enabled`，`__init__` 承接、`main.py` 创建时统一传 `False`；`memory_pipeline`/`final_memory_pipeline` 两 hook 不再各自传参——杜绝原 `after_round` 传 `pipeline_enabled=False` 而 `final_memory_pipeline` 漏传走默认 `True` 的入库不对称（CLAUDE.md 明示 bug 来源）
- [修复] assistant 落盘 thinking 污染 content：`session_message_insert` 改按 role 分类接收 `ChatCompletionMessage` 对象（正文进 `message_content`、thinking 进 `message_thinking`、有 `tool_calls` 追加独立 `tool_calls` 消息），loop 落盘传完整对象——修原 tool_calls 轮把 thinking 塞进 `message_content` 且正文丢失的问题，thinking 不再经 `session_message_reform` 回喂模型
- [清理] `.gitignore` 忽略 `changelog-site/`（codex 产出的独立 git 仓库，防主仓库 `git clean` 误删）

验证：AST + 探针（落盘对象/字符串/None 四路径形状）+ guard 测试 9 用例全绿。

对应提交：`b28abe0`(pipeline_enabled 收拢为 Memory 属性) · `fb5be18`(thinking 与正文分离落盘) · `8f269bc`(gitignore 忽略 changelog-site)

后续计划：推进 TUI 主线——thinking/toolcall 挂载、channel 轮次记账重构、embedding 缺权重启动下载。

## 2026-08-02 · v0.7.2 — TUI 重构为 channel 路由 + widget 注册体系，流式 _chat 与 embedding worker 进程落地

契机：v0.7.0 的 TUI 首版仍是单文件整体，事件经 rich_output 零散接收，无法按 agent 路由、承接不了流式渲染（`_chat` 整块返回，界面只能等整轮结束才看到输出）；`rich_print` 直写终端在 TUI 占终端时撞崩 Windows 控制台；sentence_transformers 在主进程加载拖慢启动，Windows 系统编码还易读坏中文。本批次把 TUI 重构成 channel 路由 + widget 注册体系承接 loop 流式事件，embedding 移入独立 worker 进程隔离重依赖。

变更：
- [重构] TUI 重写为 channel 路由 + widget 注册体系：`tui_core.py` 新版 `Alear030TUI`（原 `tui_main.py` 并入此文件并删除，旧版备份为 `tui_core_backup.py` 与 `tui_style copy.tcss` 入库供合并 master 对照，`__init__` 统一导出）；按 agent_name 建 channel，`emit_stream` 经 `call_from_thread` 送 UI 线程，`do_work` 线程跑 round 且 finally 解锁输入；`tui_style.tcss` 瘦身只留输入框/内容区，消息样式移入各 widget css
- [新增] `TuiChannel`（`append_once`/`append_stream` + `stream_widgets` 缓存）与 `TuiWidgets` 注册体系（`@widget_register` + `build_widget` 按类型构造 + Static 兜底）；落地 `AssistantMessage`（reactive 全量替换不累积）与 `UserMessage` 两 widget；`main.py` 切 `Alear030TUI` 并挂 `loop.emit_stream`
- [新增] `loop._chat` 改流式：`stream=True` 逐 chunk 累积 `content`/`thinking`/`tool_calls`（tool_calls 按 index 拼回完整 JSON），流式中途异常与建连失败统一 `LoopAPIError`
- [新增] embedding 移入独立 worker 进程：新增 `embedding_client`（spawn worker + JSON-lines 协议 + 锁/超时/崩溃重启/atexit）与 `embedding_worker`（唯一允许加载 sentence_transformers 的进程，UTF-8 加固防 Windows gbk 读坏中文）；`local_model_core` 瘦身为 `_EmbeddingProxy` 门面，`shutdown_embedding_worker` 由 main.py finally 收尾
- [迭代] subagent 改随机唯一名 `subagent_{uuid8}` 并注册进 agents 容器（`subagent_create` 从 kwargs 取 agents，未注入报错返回）
- [修复] `rich_print` 恢复 receiver 接收器分发：有接收器则全量转接收器、无接收器才直写终端，修复 TUI 占终端时直写撞崩 Windows 控制台，并预留 `_stream_buffers`
- [清理] hook 导出 `HookManager`；`tool_core` 为 `match_tool` 补流程注释

对应提交：`f5491b7`(TUI channel+widget 重构/流式 _chat/embedding worker/subagent 命名) · `88ff2fd`(rich_print receiver 分发代码补齐)

后续计划：推进 TUI 主线——清理 rich_output 等过时类 TUI 文件、丰富 tui_widget 生态、TUI 接入 thinking（已累积未接，留 @claude 位）与 toolcall/toolresult 展示、优化整体 TUI 体验。

## 2026-07-30 · v0.7.1 — 治理 after_round 切片/摘要阻塞用户输入

契机：TUI 启用后暴露出长期潜伏的锁竞争——`after_round` 后台 `_session_slice`/`_session_summary` 在持有 `json_lock` 期间跑 LLM 与 embedding，用户输入要等几分钟才能落盘；重喂窗口吞下超长 `tool_result`（实证约 51k token）再叠加默认 thinking，API 易挂断或拖成数十分钟。

变更：
- [重构] slice/summary 改为「短锁读快照 → 锁外算 → 短锁写回」，LLM/embedding 不再占 `json_lock`
- [修复] 结构化直调 `_structured_chat`：关 thinking、收紧 timeout/重试（实测开 thinking 会挂断，关掉数秒返回）
- [迭代] 重喂窗口按 `SLICE_TOOL_RESULT_MAX_CHARS` 截断超长 `tool_result`，避免单次切片上下文爆炸
- [迭代] 写回语义：定型前缀必写；若盘上 continuation 的 `end_round` 比本次窗口更远则保留 continuation，避免并发覆盖更长尾片
- [新增] 启动预热 embedding；缺权重/下载进度经 TUI Mount 与 `system_message` 可见

验证：单测覆盖锁外计算、写回合并、tool_result 截断与失败上报；live probe 确认并发 `session_message_insert` 等待降至毫秒级。

对应提交：`fda2f03`(slice/summary 移出锁 + 写回合并 + embedding 预热)

后续计划：修 compress/reform 按开口尾 `end_round` 砍上下文导致丢最新轮；memory 结构化直调收同一 API 边界；slice 失败上报改静默日志。

## 2026-07-28 ~ 2026-07-29 · v0.7.0 — TUI 首版闭环与上下文用量可见

契机：REPL 交互对后台切片延迟不敏感，需要可观测的终端 UI；同时压缩与状态栏都需要与 compress 同源的 token 计数，否则「用了多少上下文」只能猜。

变更：
- [新增] Textual TUI 首版：`main.py` 改由 `Alear030Tui` 驱动，封装 `run_round` 与 hook 链路；`rich_output` 增加输出接收器，把 thinking 等事件推入界面
- [新增] thinking 区块样式与 title/body 成对展开/收起（含 Markdown 文本点击与段落底边距修正）
- [新增] Session 内存态 `ContextTokens`，由 `_session_count_tokens` 与 compress 同源刷新；TUI 状态栏展示 ctx used/max，启动前预刷 system prompt 用量
- [修复] `user_info_extract`/`reform` 落盘前校验 `list[dict]+type_name`，`memory_prompt` 读盘防御非 dict 维度，避免脏 JSON 污染 `user.json` 崩启动
- [迭代] `memory_pipeline` hook 重新启用，经 `main` 显式传 `pipeline_enabled=False` 控制入库静默、切片摘要仍跑
- [清理] TUI 构造去掉未使用的 session/loop 占位入参；gitignore 清过时条目并忽略 `.agents/` 与 `AGENTS.md`；README Known Limitations 改为 roadmap

对应提交：`db30054`(TUI 首版闭环) · `aaf61e7`(清理 TUI 构造参数) · `d4cc774`(ContextTokens + user_info 校验 + pipeline_enabled)

后续计划：深化 TUI toolcall/toolresult 与 plan 展示；为 eval 的 toollog 做准备。

## 2026-07-26 ~ 2026-07-29 · v0.6.7 — 日志开关、全新 clone 可跑、权重改运行时下载

契机：v0.6.4 之后仍有三处挡住首次推送——`pip install -e .` 在 flat layout 下炸、全新 clone 首次写 session 因 gitignore 目录不存在而崩、195MB 权重触 GitHub 单文件硬限制；协作契约（技能、`@claude` 标记）也不应随公开仓库悬空引用。

变更：
- [迭代] `memory_log` 加 `LOG_AGENT_RESPONSE` 默认 False：不删模块，关掉后仍可定位「哪一片在哪个阶段失败」，本地评 prompt 时再打开
- [修复] `pyproject` 补 `[build-system]` 与 `packages=[]`，修 `pip install -e .`；补 `transformers`/`modelscope` 显式依赖
- [修复] `session_core._json_write` 与 `memory_storage_core` 写前 `mkdir`，全新 clone 首次落盘不再 `FileNotFoundError`
- [新增] 本地 embedding 权重改运行时 ModelScope 下载（以权重文件而非目录判据）；gitignore 忽略 `pytorch_model.bin`/`model.safetensors`
- [清理] 195MB 的 `pytorch_model.bin` 不再进版本控制（超 GitHub 单文件限制），改由首次加载时下载；`CLAUDE.md` 暂时取消跟踪（它引用的技能本体当时不上传）；README 大规模事实漂移修正；`session_plan/` 补尾斜杠
- [迭代] `memory_pipeline` 临时 `enabled=False` + `slices_pipeline(enable=…)`（后续 v0.7.0 改为 hook 开、入库静默）

验证：mkdir 与下载逻辑探针、memory_log 开关双向、全量 unittest；真实数据 MD5 前后一致。

对应提交：`fcfb8a0`(pipeline 临时关 + CLAUDE.md 收技能) · `90ce450`(LOG_AGENT_RESPONSE + pyproject) · `71f50bb`(README/mkdir/自动下载权重) · `e56524c`(pytorch_model.bin 改运行时下载)

后续计划：继续 TUI toolcall/toolresult。

## 2026-07-26 · v0.6.6 — 真实 coding 任务暴露的工具层六处修复

契机：用 Alear030 读自身源码写简化版时，观察工具本身是坏的——`command` 固定按系统编码（中文 Windows=GBK）解码，而 Python/git 普遍输出 UTF-8，agent 看到乱码等于蒙眼调试。

变更：
- [修复] `command`：subprocess 取 bytes，新增 `_decode` UTF-8 优先、失败回落系统编码（已知极短 GBK 可能误判为合法 UTF-8，注释接受）
- [修复] `security` 换行检查只查引号外，使 `python -c` 多行可执行、`dir` 换行危险命令仍拒
- [修复] `file_read` 满 2000 行时 header 改为追加并给出续读 offset；`file_glob` 匹配总数在截断前统计
- [修复] `memory_recall` 四处裸下标改 `.get`，单文件失败跳过；`web_fetch` 空 urls 早返回

验证：临时脚本 18 项断言（含 UTF-8/GBK 双向）+ 全量 unittest；session/memory MD5 比对确认测试未写入，脚本已删。

对应提交：工具层六处修复

后续计划：元认知问题（工具在手想不到用、错误诊断不回溯等）根因是陈述性 prompt 扛程序性职责，待定是否先做轮次预算软提示与待办工具。

## 2026-07-26 · v0.6.5 — hook 补齐 enabled 开关，三套注册表范式对齐

契机：tool（`tool_enabled`）和 prompt（`enabled`）两套注册表都带整体开关，只有 hook 缺，想临时停掉某个钩子只能注释整个装饰器或给目录加下划线前缀，粗糙且容易忘记还原。本次不引入新机制，只把已存在的范式补到第三套注册表上。

变更：
- [新增] `HookDef` 加 `enabled: bool = True` 字段，`hooks.register(..., enabled=False)` 声明式禁用；带默认值的字段放在 dataclass 末尾，不打乱现有位置参数构造
- [新增] `trigger()` 循环开头按 `enabled` 过滤，过滤点特意置于 `_match` 与线程池 `submit` 之前——否则 `background=True` 的禁用钩子仍会进 `_pending`，导致 `wait_all()` 退出时白等
- [迭代] `register` 加载日志区分 ` (disabled)` 后缀，启动时一眼看出哪些钩子是关的
- 现有 5 个 hook 全不传参走默认 `True`，行为零变化

验证：临时脚本 4 项断言（默认状态未变、禁用不触发且返回空列表、禁用与 `match` 条件正交、后台禁用不进 `_pending`）+ 全量 `unittest` 10 项通过，脚本验证后删除。

对应提交：`58e2a09`(hook 补齐 enabled 开关)

后续计划：暂不加 `hooks.disable()`/`enable()` 运行时方法（当前无调用方，属投机性控制面），需要在进程运行中切换钩子时再评估。

## 2026-07-26 · v0.6.4 — 文档对齐代码、依赖声明补全与路径校验修复

契机：README 多处描述已与代码实际漂移（agent 数量、prompt 分块数、tool 列表、memory 模块状态），`pyproject.toml` 缺 10 个运行时依赖声明，新用户按文档走不通完整上手流程；同轮排查中发现三处路径校验因 API 误用而形同虚设。

变更：
- [修复] `file_read`/`file_glob`/`file_grep` 三处绝对路径校验误用 `Path.absolute()` 而非 `is_absolute()`——前者对相对路径也返回真值，校验形同虚设
- [新增] `LICENSE`（MIT）与 `.env.example`；后者只列运行必需的三级模型配置，`VOLC_*`/`BENCH_API_KEY` 等历史遗留或 benchmark 专用键不列入，避免误导新用户
- [迭代] `pyproject.toml` 补全 `description` 及此前一直缺失的 10 个运行时依赖声明（openai/pyyaml/tiktoken/rich/sentence-transformers/ddgs/requests/beautifulsoup4/numpy/python-dotenv）
- [清理] README 修正与代码漂移的多处描述：agents.yaml 4→5 个 agent（补 memory）、prompt 分块 6→9 块（补 memory_prompt/timeline_prompt/attachment_prompt）、hook 目录树按 hook point 重排、tool 列表补 skill_finish/interaction 并删已废弃的 user_intention 引用、memory 模块描述从「开发中空白骨架」更正为「分类/去重/画像/时间线主线已跑通」；运行章节补 `git clone`→`pip install`→`cp .env.example .env` 完整上手流程
- [重构] `user_intention` 工具：删调试 print、修拼写错误变量名（masseges→messages、rounter→router），配置读取从 `.env` 里并不存在的 `main_BASE_URL` 等废弃键改为对齐项目统一的 `config.MODEL_LEVEL` 模式（工具本身仍保持 disabled）
- [清理] 移除两处死代码（memory_pipeline hook 里注释掉的测试短路 `return`、session_core 里被 print 替代后遗留的 rich_print 死注释）及 `memory_core.py` 一处写死的本机绝对路径注释；`security.py` 清理内部研究注释，只保留通用设计模型说明；`.gitignore`/CLAUDE.md 补充 `.cc_file/` 目录约定

对应提交：`3a1dd38`(一轮收尾)

后续计划：核实 `skill_finish`/`skill_list` 的 `skill_name` 参数是否需要防路径穿越校验（rglob 实测证明当前不可利用，可标注为已验证无需修改）；推进 README「安全边界」说明段落；决定是否提供 demo 数据。

## 2026-07-22 · v0.6.3 — 模型 API 失败的统一错误边界

契机：模型 API 调用失败（如账户余额不足）会直接崩穿 `main.py` 顶层循环、丢掉整轮对话。落地 20260702 暂缓方案（`polished-wondering-cook.md`）的第一部分，用统一错误边界替代层层 try/except。

变更：
- [修复] 三处 `chat.completions.create` 共用的 `_chat` 统一把裸异常翻译成 `LoopAPIError`（rich_print system_error 面板 + `raise from` 保留异常链）
- [修复] `_sent_message_api`/`_force_final_reply` 失败时回滚多塞进 `message_list` 的那条消息，避免残留连续两条 user 消息
- [修复] `loop_run` 顶层 `except LoopAPIError` 兜底返回错误字符串，并手动补 `session.round += 1`（因该路径跳过了 `_close_round`）

验证：`unittest.mock` 临时探针验证异常翻译、消息回滚、`loop_run` 不崩、round 正确自增共 4 项，验证后删除。

对应提交：`290456f`(统一错误边界)

后续计划：`_tool_calls_api` 的 tool_calls 参数解析（`json.loads`）和 `match_tool` 的工具内部异常两块仍未纳入此边界，留在原方案里，后续需要时再确认范围。

## 2026-07-21 · v0.6.2 — CLAUDE.md 补充验证经验

变更：
- [清理] CLAUDE.md 补两条验证经验：`unittest discover` 出失败时先 `git stash` 回退改动前重跑，区分历史遗留断言漂移与本次改动引入的新问题；Windows 上 `Path.read_text`/`write_text` 读写中文文本必须显式传 `encoding='utf-8'`，否则走系统默认 GBK 码页崩溃

对应提交：`d56cd77`(CLAUDE.md 验证经验)

后续计划：继续观察是否还有其他遗漏 encoding 的读写点。

## 2026-07-21 · v0.6.1 — 提炼类 prompt 中文输出约束与运行时提示措辞收紧

变更：
- [迭代] slice/summary/session_timeline 三份提炼类 prompt 补充中文输出约束：`topic`/`key_words`/`summary_detail`/`thread`/`summary`/`keywords` 统一用中文输出，英文对话也概括成中文（检索向量走中文 embedding 模型，跨语言会抵消召回）
- [迭代] attachment_prompt 措辞收紧：删去「注入后不重复展示」这句与当前实现不符的描述，补充「非必要不向用户提到系统提示存在，默默使用」的隐蔽性要求
- [删除] `session_recent` prompt 分块经 `enabled=False` 禁用（职责已被 timeline system prompt 分块覆盖）
- [修复] `main.py` 退出收尾注释 typo（推出->退出）

对应提交：`f8305de`(中文输出约束+attachment措辞+session_recent禁用+typo)

后续计划：观察中文输出约束落地后 embedding 召回准确率变化。

## 2026-07-21 · v0.6.0 — timeline 注入收口：attachment 路径改为 system prompt 分块

契机：跨会话 timeline 原经 `before_session` hook 走 attachment 注入，与 `session_recent`/`memory_prompt` 的 system prompt 快照是两条并行通路，同一份 `timeline.json` 数据却分两套渲染逻辑。将 timeline 统一为 system prompt 分块，消除双源，并同次收口旧 attachment 路径。

变更：
- [新增] `prompt/prompts/timeline_prompt/prompt.py`：启动时读 `timeline.json` 做近/远分层渲染（近段含叙事线索、远段仅关键词+摘要），与旧 attachment 渲染逻辑等价但独立实现，不 import memory_core
- [收口] 删除 `before_session/session_timeline_inject` 整个 hook，及 `memory_core.py` 的 `inject_timeline_attachment`/`get_historical_timeline` 方法与模块级 `timeline_content`/`count_token`/`RECENT_TIMELINE` 辅助代码；`session_core.session_compress` 与 `after_round/session_compress` hook 调用签名同步去掉 `memory` 参数
- [修复] timeline_prompt 原稿两处必现 bug：`timeline` 变量未定义分支下的 `NameError`、`read_text` 缺 `encoding='utf-8'` 致 Windows 下 GBK 解码中文崩溃
- [清理] CLAUDE.md 同步更新启动流程图、Hook 系统表与 Prompt 快照说明；补齐 `test/memory_pipeline` 两个测试文件的过时断言（`session_timeline_extract` 失败降级为 fallback entry 而非 None、`slice_type_define` 无命中返回新构造对象而非原对象）

验证：AST 全量解析（302 文件）+ import 链路确认 timeline 分块注册、旧 hook 不再加载；`session_compress` 签名探针确认去 memory 依赖；36 项单测全绿；无关历史失败经 git stash 交叉验证排除。

对应提交：`dd116d4`(timeline system prompt 化 + 旧 attachment 路径收口)

后续计划：观察 timeline system prompt 分块在真实会话中的召回效果，评估是否需要运行时刷新机制替代启动快照。

## 2026-07-17 ~ 2026-07-19 · v0.5.0 — 记忆系统闭环：任务经验技能化、跨会话时间线与可恢复压缩

契机：v0.4.0 的 memory 管线已能从 slice 涌现 user_info，但 task 类经验仍随会话消散；旧 compress 几乎不触发（计数只算尾片+system 严重低估），且压缩后丢失首轮注入的 timeline。本版本闭合 task->skill 经验链路，并让 compress 真正可触发、可恢复。

变更：
- [新增] task memory pipeline：定型 slice 按 `user_info`/`task` 分类；task 经 normal/advanced 两级节点聚合，三态契约 `merged`/`no_match`/`failed` 路由，累积达阈值产出 skill candidate
- [新增] Session 归属的纯内存 Attachment：`interrupt`（候选确认）/`notification`（自动注入），渲染后即清空，不写入 session 事实数据
- [新增] skill 创建与更新闭环：`create-skill` 从来源 slice 回溯素材，`skill_finish` 写回 advanced task node（append 不丢旧来源），支持已固化 node 累积新变体后产更新 candidate
- [新增] session timeline：after_session 提炼 worthy slice 为 `thread`/`summary`/`keywords`；before_session 按 token 预算经 attachment 注入，辅助 `memory_recall` 收窄 session_ids
- [新增] timeline fallback：提炼失败以 slice 的 `summary_detail`/`topic`/`key_words` 降级构造可追溯 entry（source=fallback），空 summary 渲染兼容
- [重构] session compress：计数改为 main agent 全量 `message_list`（修旧计数只算尾片致几乎不触发）；超阈值 `250000` 后保留 system+最后切片原始消息，attachment 注入更早切片摘要并恢复跨会话 timeline
- [收口] timeline 渲染与注入统一收口到 `memory.inject_timeline_attachment`，`session_timeline_inject` hook 与 `session_compress` 共用同一入口，消除分层双源漂移
- [修复] `file_edit`/`file_write` 的 `path.absolute()` 误用改为 `is_absolute()`（原写法恒真致路径校验失效）
- [清理] `test/` 与运行时 session/memory 数据纳入 .gitignore；CLAUDE.md 正式纳入版本跟踪（供并行 worktree 共享项目约定）

验证：三轮真实 REPL 确认压缩后可由摘要恢复首轮唯一标记；AST + `_emit`/`_update` 分叉探针确认 skill candidate 产出逻辑。

对应提交：四大模块落地 · skill更新闭环 · compress落地 · `a70b002`(timeline fallback) · `90ab861`(阈值250000) · `9a12cd5`(合并+端到端验证) · CLAUDE.md纳入跟踪 · test纳入gitignore · `4dec39b`(bench_secret)

后续计划：跑通 LongMemEval benchmark basic 四格；观察真实会话 compress 触发频率、压缩后衔接质量与 timeline fallback 召回效果。

## 2026-07-08 ~ 2026-07-14 · v0.4.0 — memory 自涌现管线：从 session slice 到用户画像与可量化召回基线

契机：架构巩固阶段告一段落，正式进入 memory 框架。需要让 session 切片自动流入分类、去重、画像提炼管线，并建立召回质量基线以支撑后续收口验证。

变更：
- [新增] memory pipeline/storage/config/prompt 子模块：after_round 处理已定型 worthy slice（排除尾片），after_session 补入最终尾片；`user_info` 经提取、reform、身份去重后更新用户画像模板
- [新增] recall benchmark 基线：metrics 纯函数、真实 `memory_recall` harness、18 条查询/104 项分级标注，用于后续比较召回质量
- [新增] ask_user_question 交互工具：为后续技能固化确认提供用户闸门
- [重构] Hook 生命周期重组：session slice/compress 归入 `after_round`，新增 `after_session/final_memory_pipeline`，使 session 原始消息与派生 memory 数据职责分离
- [修复] slice 重复：按重喂窗口真实起点归一化 round、校验连续性并砍尾重接，消除 slice agent 重编号造成的重叠堆积

验证：重构前召回基线快照已留存（`20260714_112246_recall_benchmark_before.json`），供收口后对比。

对应提交：slice重复修复 · memory管线主体+benchmark+ask_user_question

后续计划：收口 timeline、task memory 与 skill 生命周期，并用 benchmark 验证记忆链路的召回质量。

## 2026-07-05 ~ 2026-07-06 · v0.3.1 — 切片可靠性与命令白名单修复

变更：
- [重构] slice agent 边界提示词：以“自包含最小单元”同时约束过拆和过合；`key_words` 改为随信息密度自适应
- [修复] 切片 JSON markdown 围栏致解析失败：输出补 markdown 去壳；切片输入保留 `tool_calls`/`tool_result` 供切片及 task 提炼消费
- [修复] Windows 风格 `/` flag 白名单大小写匹配：`/flag` 统一转大写比对；command prompt 从白名单唯一来源动态生成可用命令清单
- [迭代] `_build_step_prompt` 注意事项格式：分行编号避免拼接成一整段

对应提交：`e06fff9`(slice agent重写+去壳) · 命令白名单大小写+动态清单 · `9d0ee73`(step prompt格式)

后续计划：推进 memory 消费端（slice 分类/task 提炼）链路。

## 2026-07-05 · v0.3.0 — slice 结构收敛：topic/key_words/summary_detail 收拢进 slice_anchor

契机：slice 的元数据字段（session_id/time_stamp/start_round/end_round/slice_embedding/worthy_summary）和内容锚点字段（topic/key_words/summary_detail）职责不同，扁平结构混在一起不利于后续 memory 系统给 anchor 扩展字段，先收拢分层。

变更：
- [重构] `_session_slice` 构造 slice_data 时把 `topic`/`key_words`/`summary_detail` 收拢进新的 `slice_anchor` 子字典；`_session_slice_summary` 同步改为读写 `slice_anchor` 路径
- [迭代] 适配两处读取存储态 slice 的下游：`memory_recall` 工具返回结果字段读取、`session_recent` prompt 分块渲染（对外字段形状不变，只改内部读取路径）
- [清理] 一次性脚本迁移历史 34 个 `session_detail/*.json`（33 个含 slice，共 200 条）：旧扁平结构转 `slice_anchor` 嵌套结构，补齐旧数据缺失的 `session_id` 字段

对应提交：slice_anchor收敛+历史数据迁移

后续计划：架构巩固到此告一段落，正式进入 memory（自涌现记忆）框架开发阶段。

## 2026-07-04 · v0.2.2 — 杂项修复：summary_agent 属性名 bug + hook_core 注释 + README 同步

变更：
- [修复] `session_core.py` 里 `self.summary_agent.summary_ai` 应为 `self.summary_agent.agent_ai`（属性名写错，历史遗留）
- [清理] `hook/hook_core.py` 补充 `trigger`/`_match` 等核心方法的设计意图注释（纯注释，无逻辑变化）
- [清理] `README.md` 同步 `prompt/prompts/` 装饰器自动发现机制的目录结构描述（跟进 v0.0.15 的实现）

对应提交：属性名bug+hook_core注释+README同步

后续计划：继续优化整体架构代码，推进 memory 系统主线。

## 2026-07-04 · v0.2.1 — hook 解耦：pre_toolUse 无条件注入取代 plan_hook 按工具匹配

契机：`plan_hook.py` 里 `inject_agents`（只匹配 `plan_design`）/`inject_session`（匹配 `plan_mode_on`/`plan_mode_off`/`plan_update`）两个钩子本质都是往 `tool_args` 塞 `agents`/`session`，工具变多后每加一个需要这些对象的工具就要再注册一条匹配规则，维护成本随工具数线性增长。

变更：
- [收口] 删除 `hook/hooks/plan_hook/`，新增 `hook/hooks/pre_toolUse/inject_import_args/`：无条件给全部工具调用注入 `agents`/`session`/`hooks`/`Loop` 四个对象，工具自己决定用不用
- [修复] `loop_core.py::_pre_tool_use_hooks` 漏传参数：`hooks.trigger()` 补上 `hooks=self.hooks`/`Loop=Loop`（否则该 hook 一触发就因缺参数抛异常，注入静默失效）
- [修复] `tool_core.py::_make_parmeters` 的 schema 生成：排除 `VAR_KEYWORD`（`**kwargs`），避免其被当成必填字段塞进 function-calling schema 误导 LLM
- [迭代] 17 个工具函数签名统一加 `**kwargs` 兜底，吞掉无条件注入带来的多余参数，避免 `TypeError`
- [清理] `README.md` 同步 hook 解耦后的目录结构（`plan_hook` 替换为 `pre_toolUse/inject_import_args`）及设计决策描述

对应提交：hook解耦+漏传参修复+kwargs兜底 · `e0ca032`(README同步hook解耦)

后续计划：继续优化整体架构代码，推进 memory 系统主线。

## 2026-07-04 · v0.2.0 — command 安全白名单：修 `/` flag 校验漏洞 + 新增系统信息查询命令

契机：agent 想查电脑配置（内存/显卡）推荐语音模型包，`systeminfo`/`wmic`/`nvidia-smi` 均不在白名单被拦。排查时发现一个更深的既有漏洞。

变更：
- [修复] `_validate_flags` 之前硬编码只校验 `-` 开头参数，`dir`/`findstr`/`tasklist`/`netstat` 等 Windows 命令声明的 `/xxx` flag 白名单形同摆设，任何 `/flag` 直接放过。改成按命令自身声明的前缀风格（`-`/`=` 或 `/`/`:`）动态判断
- [新增] `systeminfo`、`nvidia-smi`（标准逐 flag 白名单）
- [新增] `wmic`（非 flag 式语法，改用动词/开关黑名单--只放行 `get`/`list` 查询，堵死 `call`/`set`/`delete`/`create` 和 `/format`（XSL 注入面）/`output`/`append`）

对应提交：`62e7a91`(flag校验漏洞修复+systeminfo/wmic)

后续计划：管道场景下 `_validate_flags` 拿整条命令行对**管道第一个命令**的白名单校验，各段命令各自的 flag 未被正确归属校验（如 `systeminfo | findstr /B ...` 中 `/B` 会被拿去对 `systeminfo` 校验）。已记录，本次不修。

## 2026-07-04 · v0.1.1 — 修复 notice 系统提示未写入 session 的历史疏漏

变更：
- [修复] `_force_final_reply`（v0.1.0 合并出的方法）里的系统提示此前只进了 `message_list`、没写入 session--这是原代码就有的疏漏，不是 v0.1.0 引入的。已对齐 `_sent_message_api` 的写入方式

对应提交：notice系统提示写入session

后续计划：继续优化整体架构代码。

## 2026-07-04 · v0.1.0 — loop_core 重构：纯 ReAct 引擎 + plan 编排剥离

契机：`loop/loop_core.py` 把“ReAct 引擎 + plan 编排 + mode 切换探测”三件事揉在一起的 292 行，需要瘦身为对 plan 零感知的纯 ReAct 引擎，plan 分步编排剥离成独立的 `loop/orchestrator.py::PlanRunner`。

变更：
- [重构] `loop_core.py` 瘦身为纯 ReAct 引擎，plan 编排剥离成 `loop/orchestrator.py::PlanRunner`；`loop_run` 对外签名不变，`main.py` 与 subagent 零改动
- [修复] 死循环空转：`run_turn` 补齐“无 tool_calls”分支
- [修复] plan 无限烧 token：`PlanRunner` 用无进展检测（连续 3 轮拿到同一 step 熔断）取代 `while True`
- [修复] `json.loads` 裸奔：工具参数解析失败给空 args 兜底
- [迭代] `Plan` 新增 `advance()` 公开 API，收回 Loop 对私有方法/内部属性的直接扒取；合并 3 处重复 LLM 调用 + 2 处雷同收尾逻辑

对应提交：loop_core重构+PlanRunner剥离

后续计划：在 PlanRunner 之上加 goal 模式编排（goal 包 plan 包 step + 不合格重新 plan 回边），预留扩展点，未实现。

## 2026-07-04 · v0.0.16 — system_prompt 插入时机与 round 计数解耦

变更：
- [重构] `Session` 构造时直接写入 round 0 的 system_prompt，round 计数从 1 开始，不再与 system_prompt 插入时机耦合

对应提交：system_prompt插入时机解耦

后续计划：继续优化整体架构代码。

## 2026-07-04 · v0.0.15 — prompt 分块改为装饰器 + 目录自动发现注册机制

变更：
- [重构] `prompt_core.py` 瘦身，新增 `prompt_register.py`（`@register_prompt` 装饰器），各分块迁移为 `prompt/prompts/{name}/prompt.py` 目录结构，与 tool/hook 的自动发现机制对齐

对应提交：`c33ffdb`(prompt装饰器自动发现)

后续计划：继续优化整体架构代码。

## 2026-07-04 · v0.0.14 — README 同步 prompt_structor 重构

变更：
- [清理] `README.md` 目录结构和分层组合说明同步改为 `prompt/` 包描述

对应提交：`70c7104`(README同步prompt_structor)

后续计划：继续优化整体架构代码。

## 2026-07-04 · v0.0.13 — 重构 prompt_structor：拆分为 prompt/ 包

变更：
- [重构] `agent/prompt_structor.py`（单文件硬拼接）拆分为独立的 `prompt/` 包：`prompt_core.py` 负责组装，`agent_prompt/agents/` 收纳各 agent 身份定义，新增 `skill_prompt`/`tool_prompt` 两个分块目录

对应提交：prompt_structor拆分为prompt包

后续计划：继续优化整体架构代码。

## 2026-07-03 · v0.0.12 — tool_prompt 文案清理

变更：
- [清理] `file_glob`/`file_grep`/`file_write` 的 tool_prompt 去除/调整学习模式相关提示语

对应提交：tool_prompt文案清理

后续计划：重构 `prompt_structor`，将 system_prompt 拆成按语义分块的可组装结构（如 subagent 使用触发规则等），替代当前紧凑单文件硬拼接。

## 2026-07-03 · v0.0.11 — memory_recall tool_prompt 补充使用场景

变更：
- [迭代] `memory_recall` 的 tool_prompt 补充一条何时使用场景的说明

对应提交：`a724e8d`(memory_recall tool_prompt补充)

后续计划：继续优化整体架构代码。

## 2026-07-03 · v0.0.10 — web_search/web_fetch 改为批量并行

变更：
- [重构] `web_search`/`web_fetch` 入参改为 list，内部用 `ThreadPoolExecutor` 并行处理并做单项错误隔离
- [修复] web_fetch 失败信息里 `error` 始终为 None 的 bug；去掉 web_fetch 中多余的 print 调试输出
- [清理] 补充两个工具的 tool_prompt 说明文档

对应提交：web批量并行+error修复

后续计划：继续优化整体架构代码。

## 2026-07-03 · v0.0.9 — file_tool 拆分 + plan_tool 细化 + subagent_tool 新增 + coding-conduct 技能

变更：
- [重构] `file_tool` 从单一 `file_read`/`file_write` 拆分为 `file_edit`（局部唯一替换）/`file_glob`（按文件名查找）/`file_grep`（按正则搜索内容）/`file_read`/`file_write` 五件套，统一收进 `tool/tools/file_tool/`
- [迭代] `plan_tool` 从单一 `plan_create` 细化为 `plan_design`/`plan_update`/`plan_mode_on`/`plan_mode_off` 四个工具，新增 `session/session_plan.py` 负责 Plan 状态读取
- [新增] `subagent_tool`（`subagent_create` + `subagent_core.py`），支持并行子 agent 集群
- [新增] `skill/coding-conduct/skill.md` 技能
- [清理] 误跟踪的 `memory.db` 二进制文件被移除；`loop/loop_core.py` 大改

对应提交：`db9d675`(file_tool拆分+plan_tool细化+subagent+coding-conduct)

后续计划：继续优化整体架构代码。

## 2026-07-01 · v0.0.8 — loop 重构跟进，即将进入 plan_loop 阶段

变更：
- [迭代] `plan_agent.md` 补充说明、`agents.yaml` 调整、`loop_core.py` 补充逻辑、`plan_create` 工具与其 tool_prompt 微调

对应提交：loop重构跟进+plan工具微调

后续计划：即将进入 plan_loop 阶段。

## 2026-07-01 · v0.0.7 — loop 重构完成，进入 plan_mode 开发阶段

变更：
- [重构] `core/loop.py` 移出 core，迁移为独立的 `loop/loop_core.py` 模块；`rich_output.py` 从 `core/` 提升到项目根
- [清理] README 大幅扩写记录新架构

对应提交：loop模块迁移+README扩写

后续计划：进入 plan_mode 开发阶段。

## 2026-06-30 · v0.0.6 — hook 模块 + plan_tool + session 整体优化

变更：
- [新增] `hook/` 事件驱动系统（`hook_core.py` + `hooks/plan_hook`/`session_compress`/`session_slice` 三个自动发现子模块）
- [新增] `tool/tools/plan_tool/plan_create`（首版 plan 工具）与 `tool/tools/memory_recall`
- [新增] `agent/agents.yaml` 首次引入（YAML 驱动 agent 定义），新增 `plan_agent.md`
- [重构] 历史 `tools/` 目录整体迁移合并进 `tool/tools/`（两套目录统一）；`session_core.py` 大幅重构（约 323 行改动）

对应提交：`896e186`(hook模块+plan_tool+session重构)

后续计划：继续优化整体架构代码。

## 2026-06-26 · v0.0.5 — session 重构（提交自标 v0.09）

变更：
- [新增] `session/` 模块（`session_core.py`/`session_compress.py`），session 落盘到 `session_detail/*.json`
- [重构] `core/agent.py` 迁移为 `agent/agent_core.py`，新增 `agent_prompt/`（main/slice/summary 三套 agent 定义）
- [新增] `core/loop.py`、`core/local_model.py`（GTE embedding 本地模型接入）；引入本地中文 embedding 模型权重（`local_model/nlp_gte_sentence-embedding_chinese-base/`）
- [新增] `tools/session_recall`（记忆召回）、`tools/session_compress`、`tools/session_slice`

对应提交：`e097db7`(session重构+本地embedding)

后续计划：继续优化整体架构代码。

## 2026-06-20 · v0.0.4 — 基础 tools 完善完毕，进入 memory 框架阶段

变更：
- [新增] 大批量工具集群：`tools/command`（含约 1300 行 `security.py` 安全白名单雏形）、`file_read`、`file_write`、`skill_tool`、`user_intention`、`web_fetch`、`web_search`
- [重构] `tool/tool_register.py` 迁移改名为 `tools/_tool_register.py` 并扩展为自动发现机制
- [新增] `core/prompt_structor.py`/`core/runtime.py`；`memory/system.md` 承接 06-13 的 system prompt

对应提交：基础tools集群+自动发现

后续计划：进入 memory 框架搭建阶段。

## 2026-06-13 · v0.0.3 — system_agent_prompt 更新

变更：
- [新增] `prompt/agents_prompt/system_agent_prompt.md` 作为 system prompt 早期版本
- [清理] 提交中意外带入两份问答语料 md 文件（06-20 提交中被移除）

对应提交：`07b543e`(system_agent_prompt)

后续计划：继续完善基础架构。

## 2026-06-12 · v0.0.2 — 新增基础性内容：工具、记忆、核心

变更：
- [新增] `core/`（`agent.py`/`rich_output.py`）、`memory/`（`USER.py` 占位）、`tool/`（`tool_register.py`）三大目录雏形
- [新增] `AGENTS.py`/`SOUL.md`/`SYSTEM.py` 作为早期身份定义的占位文件

对应提交：基础三大目录雏形

后续计划：继续完善基础架构。

## 2026-06-11 · v0.0.1 — 项目初始化

变更：
- [新增] 搭建最基础的项目骨架：`.gitignore`、`.python-version`、`main.py`、`pyproject.toml`、`README.md`

对应提交：`f3251ba`(项目初始化) · `057eb45`(项目初始文件夹目录)

后续计划：继续完善基础架构。
