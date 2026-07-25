# Changelog

版本号采用语义化风格（`major.minor.patch`）：新增能力/结构性重构记 `minor`，bug 修复/小改进记 `patch`，架构级破坏性里程碑记 `major`（预留）。项目无正式发布流程，版本号仅用于标记改动批次，不对应 tag。

按时间倒序排列，最新改动在最上面。每个版本块是一个主题统一的工作批次（可跨多天），日期取批次的实际时间跨度（单天标 `YYYY-MM-DD`，跨天标 `YYYY-MM-DD ~ YYYY-MM-DD`）。

**变更类型标签**：`[新增]` 新功能/新模块 · `[迭代]` 既有功能改进 · `[修复]` bug 修复 · `[重构]` 结构性重构 · `[收口]` 机制收敛/职责归一 · `[清理]` 版本控制治理/文档同步 · `[删除]` 移除功能。重大改动写「契机」（动机/根因）和「验证」（过程声明），小修省略。每块末尾「对应提交」列出 commit hash + 一句话，保证可回溯。

> **⚠ v0.6.2 及更早版本块的 commit hash 已全部失效**：2026-07-26 对仓库执行过一次 `git filter-repo` 历史重写（清理泄漏语料），全部 49 个 commit 的 hash 随之改变，写入时正确的旧 hash 现已无法解析。待开源前历史彻底定稿后统一回填——2026-07-05 之后的 commit 可按 message 的 `YYYYMMDD_HHMMSS` 前缀经 `git log --grep` 定位（该前缀写在 message 正文里，不随历史重写变化），更早的 14 个 commit 无稳定前缀，需按日期与描述人工比对。

## 2026-07-26 · v0.6.5 — hook 补齐 enabled 开关，三套注册表范式对齐

契机：tool（`tool_enabled`）和 prompt（`enabled`）两套注册表都带整体开关，只有 hook 缺，想临时停掉某个钩子只能注释整个装饰器或给目录加下划线前缀，粗糙且容易忘记还原。本次不引入新机制，只把已存在的范式补到第三套注册表上。

变更：
- [新增] `HookDef` 加 `enabled: bool = True` 字段，`hooks.register(..., enabled=False)` 声明式禁用；带默认值的字段放在 dataclass 末尾，不打乱现有位置参数构造
- [新增] `trigger()` 循环开头按 `enabled` 过滤，过滤点特意置于 `_match` 与线程池 `submit` 之前——否则 `background=True` 的禁用钩子仍会进 `_pending`，导致 `wait_all()` 退出时白等
- [迭代] `register` 加载日志区分 ` (disabled)` 后缀，启动时一眼看出哪些钩子是关的
- 现有 5 个 hook 全不传参走默认 `True`，行为零变化

验证：临时脚本 4 项断言（默认状态未变、禁用不触发且返回空列表、禁用与 `match` 条件正交、后台禁用不进 `_pending`）+ 全量 `unittest` 10 项通过，脚本验证后删除。

对应提交：`b2acec9`(hook enabled 开关)

后续计划：暂不加 `hooks.disable()`/`enable()` 运行时方法（当前无调用方，属投机性控制面），需要在进程运行中切换钩子时再评估。

## 2026-07-26 · v0.6.4 — 开源前收尾：文档对齐代码、依赖声明补全与路径校验修复

契机：README 多处描述已与代码实际漂移（agent 数量、prompt 分块数、tool 列表、memory 模块状态），`pyproject.toml` 缺 10 个运行时依赖声明，新用户按文档走不通完整上手流程；同轮排查中发现三处路径校验因 API 误用而形同虚设。

变更：
- [修复] `file_read`/`file_glob`/`file_grep` 三处绝对路径校验误用 `Path.absolute()` 而非 `is_absolute()`——前者对相对路径也返回真值，校验形同虚设
- [新增] `LICENSE`（MIT）与 `.env.example`；后者只列运行必需的三级模型配置，`VOLC_*`/`BENCH_API_KEY` 等历史遗留或 benchmark 专用键不列入，避免误导新用户
- [迭代] `pyproject.toml` 补全 `description` 及此前一直缺失的 10 个运行时依赖声明（openai/pyyaml/tiktoken/rich/sentence-transformers/ddgs/requests/beautifulsoup4/numpy/python-dotenv）
- [清理] README 修正与代码漂移的多处描述：agents.yaml 4→5 个 agent（补 memory）、prompt 分块 6→9 块（补 memory_prompt/timeline_prompt/attachment_prompt）、hook 目录树按 hook point 重排、tool 列表补 skill_finish/interaction 并删已废弃的 user_intention 引用、memory 模块描述从「开发中空白骨架」更正为「分类/去重/画像/时间线主线已跑通」；运行章节补 `git clone`→`pip install`→`cp .env.example .env` 完整上手流程
- [重构] `user_intention` 工具：删调试 print、修拼写错误变量名（masseges→messages、rounter→router），配置读取从 `.env` 里并不存在的 `main_BASE_URL` 等废弃键改为对齐项目统一的 `config.MODEL_LEVEL` 模式（工具本身仍保持 disabled）
- [清理] 移除两处死代码（memory_pipeline hook 里注释掉的测试短路 `return`、session_core 里被 print 替代后遗留的 rich_print 死注释）及 `memory_core.py` 一处写死的本机绝对路径注释；`security.py` 移除对 Claude Code 源码文件路径/行数的具体归属描述，只保留通用设计模型说明；`.gitignore`/CLAUDE.md 补充 `.cc_file/` 目录约定

对应提交：`3749de5`(开源前收尾)

后续计划：核实 `skill_finish`/`skill_list` 的 `skill_name` 参数是否需要防路径穿越校验（rglob 实测证明当前不可利用，可标注为已验证无需修改）；推进 README「安全边界」说明段落；决定是否为 memory_storage/memory_config 提供脱敏 demo 数据。

## 2026-07-22 · v0.6.3 — 模型 API 失败的统一错误边界

契机：模型 API 调用失败（如账户余额不足）会直接崩穿 `main.py` 顶层循环、丢掉整轮对话。落地 20260702 暂缓方案（`polished-wondering-cook.md`）的第一部分，用统一错误边界替代层层 try/except。

变更：
- [修复] 三处 `chat.completions.create` 共用的 `_chat` 统一把裸异常翻译成 `LoopAPIError`（rich_print system_error 面板 + `raise from` 保留异常链）
- [修复] `_sent_message_api`/`_force_final_reply` 失败时回滚多塞进 `message_list` 的那条消息，避免残留连续两条 user 消息
- [修复] `loop_run` 顶层 `except LoopAPIError` 兜底返回错误字符串，并手动补 `session.round += 1`（因该路径跳过了 `_close_round`）

验证：`unittest.mock` 临时探针验证异常翻译、消息回滚、`loop_run` 不崩、round 正确自增共 4 项，验证后删除。

对应提交：`a658907`(统一错误边界)

后续计划：`_tool_calls_api` 的 tool_calls 参数解析（`json.loads`）和 `match_tool` 的工具内部异常两块仍未纳入此边界，留在原方案里，后续需要时再确认范围。

## 2026-07-21 · v0.6.2 — CLAUDE.md 补充验证经验

变更：
- [清理] CLAUDE.md 补两条验证经验：`unittest discover` 出失败时先 `git stash` 回退改动前重跑，区分历史遗留断言漂移与本次改动引入的新问题；Windows 上 `Path.read_text`/`write_text` 读写中文文本必须显式传 `encoding='utf-8'`，否则走系统默认 GBK 码页崩溃

对应提交：`fb5a337`(CLAUDE.md 验证经验)

后续计划：继续观察是否还有其他遗漏 encoding 的读写点。

## 2026-07-21 · v0.6.1 — 提炼类 prompt 中文输出约束与运行时提示措辞收紧

变更：
- [迭代] slice/summary/session_timeline 三份提炼类 prompt 补充中文输出约束：`topic`/`key_words`/`summary_detail`/`thread`/`summary`/`keywords` 统一用中文输出，英文对话也概括成中文（检索向量走中文 embedding 模型，跨语言会抵消召回）
- [迭代] attachment_prompt 措辞收紧：删去「注入后不重复展示」这句与当前实现不符的描述，补充「非必要不向用户提到系统提示存在，默默使用」的隐蔽性要求
- [删除] `session_recent` prompt 分块经 `enabled=False` 禁用（职责已被 timeline system prompt 分块覆盖）
- [修复] `main.py` 退出收尾注释 typo（推出->退出）

对应提交：`61da56d`(中文输出约束+attachment措辞+session_recent禁用+typo)

后续计划：观察中文输出约束落地后 embedding 召回准确率变化。

## 2026-07-21 · v0.6.0 — timeline 注入收口：attachment 路径改为 system prompt 分块

契机：跨会话 timeline 原经 `before_session` hook 走 attachment 注入，与 `session_recent`/`memory_prompt` 的 system prompt 快照是两条并行通路，同一份 `timeline.json` 数据却分两套渲染逻辑。将 timeline 统一为 system prompt 分块，消除双源，并同次收口旧 attachment 路径。

变更：
- [新增] `prompt/prompts/timeline_prompt/prompt.py`：启动时读 `timeline.json` 做近/远分层渲染（近段含叙事线索、远段仅关键词+摘要），与旧 attachment 渲染逻辑等价但独立实现，不 import memory_core
- [收口] 删除 `before_session/session_timeline_inject` 整个 hook，及 `memory_core.py` 的 `inject_timeline_attachment`/`get_historical_timeline` 方法与模块级 `timeline_content`/`count_token`/`RECENT_TIMELINE` 辅助代码；`session_core.session_compress` 与 `after_round/session_compress` hook 调用签名同步去掉 `memory` 参数
- [修复] timeline_prompt 原稿两处必现 bug：`timeline` 变量未定义分支下的 `NameError`、`read_text` 缺 `encoding='utf-8'` 致 Windows 下 GBK 解码中文崩溃
- [清理] CLAUDE.md 同步更新启动流程图、Hook 系统表与 Prompt 快照说明；补齐 `test/memory_pipeline` 两个测试文件的过时断言（`session_timeline_extract` 失败降级为 fallback entry 而非 None、`slice_type_define` 无命中返回新构造对象而非原对象）

验证：AST 全量解析（302 文件）+ import 链路确认 timeline 分块注册、旧 hook 不再加载；`session_compress` 签名探针确认去 memory 依赖；36 项单测全绿；无关历史失败经 git stash 交叉验证排除。

对应提交：`95591e8`(timeline system prompt 化 + 旧 attachment 路径收口)

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
- [清理] `test/`、真实 session/memory 语料及 `bench_secret.py` 纳入 .gitignore；CLAUDE.md 正式纳入版本跟踪（供并行 worktree 共享项目宪法）；取消跟踪已泄漏 session_detail；开源前仍需 filter-repo 重写历史

验证：三轮真实 REPL 确认压缩后可由摘要恢复首轮唯一标记；AST + `_emit`/`_update` 分叉探针确认 skill candidate 产出逻辑。

对应提交：`103b444`(四大模块落地) · `645c6ee`(skill更新闭环) · `e3e749c`(compress落地) · `af29115`(timeline fallback) · `05dc5c5`(阈值250000) · `57511e5`(合并+端到端验证) · `6785b16`(CLAUDE.md纳入跟踪) · `1d30e8c`(test纳入gitignore) · `bc236e8`(bench_secret)

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

对应提交：`4744c61`(slice重复修复) · `aa57b35`(memory管线主体+benchmark+ask_user_question)

后续计划：收口 timeline、task memory 与 skill 生命周期，并用 benchmark 验证记忆链路的召回质量。

## 2026-07-05 ~ 2026-07-06 · v0.3.1 — 切片可靠性与命令白名单修复

变更：
- [重构] slice agent 边界提示词：以“自包含最小单元”同时约束过拆和过合；`key_words` 改为随信息密度自适应
- [修复] 切片 JSON markdown 围栏致解析失败：输出补 markdown 去壳；切片输入保留 `tool_calls`/`tool_result` 供切片及 task 提炼消费
- [修复] Windows 风格 `/` flag 白名单大小写匹配：`/flag` 统一转大写比对；command prompt 从白名单唯一来源动态生成可用命令清单
- [迭代] `_build_step_prompt` 注意事项格式：分行编号避免拼接成一整段

对应提交：`5571fb6`(slice agent重写+去壳) · `ba39d40`(命令白名单大小写+动态清单) · `63ec4c8`(step prompt格式)

后续计划：推进 memory 消费端（slice 分类/task 提炼）链路。

## 2026-07-05 · v0.3.0 — slice 结构收敛：topic/key_words/summary_detail 收拢进 slice_anchor

契机：slice 的元数据字段（session_id/time_stamp/start_round/end_round/slice_embedding/worthy_summary）和内容锚点字段（topic/key_words/summary_detail）职责不同，扁平结构混在一起不利于后续 memory 系统给 anchor 扩展字段，先收拢分层。

变更：
- [重构] `_session_slice` 构造 slice_data 时把 `topic`/`key_words`/`summary_detail` 收拢进新的 `slice_anchor` 子字典；`_session_slice_summary` 同步改为读写 `slice_anchor` 路径
- [迭代] 适配两处读取存储态 slice 的下游：`memory_recall` 工具返回结果字段读取、`session_recent` prompt 分块渲染（对外字段形状不变，只改内部读取路径）
- [清理] 一次性脚本迁移历史 34 个 `session_detail/*.json`（33 个含 slice，共 200 条）：旧扁平结构转 `slice_anchor` 嵌套结构，补齐旧数据缺失的 `session_id` 字段

对应提交：`19c20f6`(slice_anchor收敛+历史数据迁移)

后续计划：架构巩固到此告一段落，正式进入 memory（自涌现记忆）框架开发阶段。

## 2026-07-04 · v0.2.2 — 杂项修复：summary_agent 属性名 bug + hook_core 注释 + README 同步

变更：
- [修复] `session_core.py` 里 `self.summary_agent.summary_ai` 应为 `self.summary_agent.agent_ai`（属性名写错，历史遗留）
- [清理] `hook/hook_core.py` 补充 `trigger`/`_match` 等核心方法的设计意图注释（纯注释，无逻辑变化）
- [清理] `README.md` 同步 `prompt/prompts/` 装饰器自动发现机制的目录结构描述（跟进 v0.0.15 的实现）

对应提交：`a60a892`(属性名bug+hook_core注释+README同步)

后续计划：继续优化整体架构代码，推进 memory 系统主线。

## 2026-07-04 · v0.2.1 — hook 解耦：pre_toolUse 无条件注入取代 plan_hook 按工具匹配

契机：`plan_hook.py` 里 `inject_agents`（只匹配 `plan_design`）/`inject_session`（匹配 `plan_mode_on`/`plan_mode_off`/`plan_update`）两个钩子本质都是往 `tool_args` 塞 `agents`/`session`，工具变多后每加一个需要这些对象的工具就要再注册一条匹配规则，维护成本随工具数线性增长。

变更：
- [收口] 删除 `hook/hooks/plan_hook/`，新增 `hook/hooks/pre_toolUse/inject_import_args/`：无条件给全部工具调用注入 `agents`/`session`/`hooks`/`Loop` 四个对象，工具自己决定用不用
- [修复] `loop_core.py::_pre_tool_use_hooks` 漏传参数：`hooks.trigger()` 补上 `hooks=self.hooks`/`Loop=Loop`（否则该 hook 一触发就因缺参数抛异常，注入静默失效）
- [修复] `tool_core.py::_make_parmeters` 的 schema 生成：排除 `VAR_KEYWORD`（`**kwargs`），避免其被当成必填字段塞进 function-calling schema 误导 LLM
- [迭代] 17 个工具函数签名统一加 `**kwargs` 兜底，吞掉无条件注入带来的多余参数，避免 `TypeError`
- [清理] `README.md` 同步 hook 解耦后的目录结构（`plan_hook` 替换为 `pre_toolUse/inject_import_args`）及设计决策描述

对应提交：`2cc0e3b`(hook解耦+漏传参修复+kwargs兜底) · `50bf72e`(README同步hook解耦)

后续计划：继续优化整体架构代码，推进 memory 系统主线。

## 2026-07-04 · v0.2.0 — command 安全白名单：修 `/` flag 校验漏洞 + 新增系统信息查询命令

契机：agent 想查电脑配置（内存/显卡）推荐语音模型包，`systeminfo`/`wmic`/`nvidia-smi` 均不在白名单被拦。排查时发现一个更深的既有漏洞。

变更：
- [修复] `_validate_flags` 之前硬编码只校验 `-` 开头参数，`dir`/`findstr`/`tasklist`/`netstat` 等 Windows 命令声明的 `/xxx` flag 白名单形同摆设，任何 `/flag` 直接放过。改成按命令自身声明的前缀风格（`-`/`=` 或 `/`/`:`）动态判断
- [新增] `systeminfo`、`nvidia-smi`（标准逐 flag 白名单）
- [新增] `wmic`（非 flag 式语法，改用动词/开关黑名单--只放行 `get`/`list` 查询，堵死 `call`/`set`/`delete`/`create` 和 `/format`（XSL 注入面）/`output`/`append`）

对应提交：`a9885d1`(flag校验漏洞修复+systeminfo/wmic)

后续计划：管道场景下 `_validate_flags` 拿整条命令行对**管道第一个命令**的白名单校验，各段命令各自的 flag 未被正确归属校验（如 `systeminfo | findstr /B ...` 中 `/B` 会被拿去对 `systeminfo` 校验）。已记录，本次不修。

## 2026-07-04 · v0.1.1 — 修复 notice 系统提示未写入 session 的历史疏漏

变更：
- [修复] `_force_final_reply`（v0.1.0 合并出的方法）里的系统提示此前只进了 `message_list`、没写入 session--这是原代码就有的疏漏，不是 v0.1.0 引入的。已对齐 `_sent_message_api` 的写入方式

对应提交：`03ffc93`(notice系统提示写入session)

后续计划：继续优化整体架构代码。

## 2026-07-04 · v0.1.0 — loop_core 重构：纯 ReAct 引擎 + plan 编排剥离

契机：`loop/loop_core.py` 把“ReAct 引擎 + plan 编排 + mode 切换探测”三件事揉在一起的 292 行，需要瘦身为对 plan 零感知的纯 ReAct 引擎，plan 分步编排剥离成独立的 `loop/orchestrator.py::PlanRunner`。

变更：
- [重构] `loop_core.py` 瘦身为纯 ReAct 引擎，plan 编排剥离成 `loop/orchestrator.py::PlanRunner`；`loop_run` 对外签名不变，`main.py` 与 subagent 零改动
- [修复] 死循环空转：`run_turn` 补齐“无 tool_calls”分支
- [修复] plan 无限烧 token：`PlanRunner` 用无进展检测（连续 3 轮拿到同一 step 熔断）取代 `while True`
- [修复] `json.loads` 裸奔：工具参数解析失败给空 args 兜底
- [迭代] `Plan` 新增 `advance()` 公开 API，收回 Loop 对私有方法/内部属性的直接扒取；合并 3 处重复 LLM 调用 + 2 处雷同收尾逻辑

对应提交：`eeeaaf2`(loop_core重构+PlanRunner剥离)

后续计划：在 PlanRunner 之上加 goal 模式编排（goal 包 plan 包 step + 不合格重新 plan 回边），预留扩展点，未实现。

## 2026-07-04 · v0.0.16 — system_prompt 插入时机与 round 计数解耦

变更：
- [重构] `Session` 构造时直接写入 round 0 的 system_prompt，round 计数从 1 开始，不再与 system_prompt 插入时机耦合

对应提交：`221b824`(system_prompt插入时机解耦)

后续计划：继续优化整体架构代码。

## 2026-07-04 · v0.0.15 — prompt 分块改为装饰器 + 目录自动发现注册机制

变更：
- [重构] `prompt_core.py` 瘦身，新增 `prompt_register.py`（`@register_prompt` 装饰器），各分块迁移为 `prompt/prompts/{name}/prompt.py` 目录结构，与 tool/hook 的自动发现机制对齐

对应提交：`87daf7b`(prompt装饰器自动发现)

后续计划：继续优化整体架构代码。

## 2026-07-04 · v0.0.14 — README 同步 prompt_structor 重构

变更：
- [清理] `README.md` 目录结构和分层组合说明同步改为 `prompt/` 包描述

对应提交：`9151cb8`(README同步prompt_structor)

后续计划：继续优化整体架构代码。

## 2026-07-04 · v0.0.13 — 重构 prompt_structor：拆分为 prompt/ 包

变更：
- [重构] `agent/prompt_structor.py`（单文件硬拼接）拆分为独立的 `prompt/` 包：`prompt_core.py` 负责组装，`agent_prompt/agents/` 收纳各 agent 身份定义，新增 `skill_prompt`/`tool_prompt` 两个分块目录

对应提交：`8ee3112`(prompt_structor拆分为prompt包)

后续计划：继续优化整体架构代码。

## 2026-07-03 · v0.0.12 — tool_prompt 文案清理

变更：
- [清理] `file_glob`/`file_grep`/`file_write` 的 tool_prompt 去除/调整学习模式相关提示语

对应提交：`1dedf5e`(tool_prompt文案清理)

后续计划：重构 `prompt_structor`，将 system_prompt 拆成按语义分块的可组装结构（如 subagent 使用触发规则等），替代当前紧凑单文件硬拼接。

## 2026-07-03 · v0.0.11 — memory_recall tool_prompt 补充使用场景

变更：
- [迭代] `memory_recall` 的 tool_prompt 补充一条何时使用场景的说明

对应提交：`a3c09e4`(memory_recall tool_prompt补充)

后续计划：继续优化整体架构代码。

## 2026-07-03 · v0.0.10 — web_search/web_fetch 改为批量并行

变更：
- [重构] `web_search`/`web_fetch` 入参改为 list，内部用 `ThreadPoolExecutor` 并行处理并做单项错误隔离
- [修复] web_fetch 失败信息里 `error` 始终为 None 的 bug；去掉 web_fetch 中多余的 print 调试输出
- [清理] 补充两个工具的 tool_prompt 说明文档

对应提交：`54bfc6c`(web批量并行+error修复)

后续计划：继续优化整体架构代码。

## 2026-07-03 · v0.0.9 — file_tool 拆分 + plan_tool 细化 + subagent_tool 新增 + coding-conduct 技能

变更：
- [重构] `file_tool` 从单一 `file_read`/`file_write` 拆分为 `file_edit`（局部唯一替换）/`file_glob`（按文件名查找）/`file_grep`（按正则搜索内容）/`file_read`/`file_write` 五件套，统一收进 `tool/tools/file_tool/`
- [迭代] `plan_tool` 从单一 `plan_create` 细化为 `plan_design`/`plan_update`/`plan_mode_on`/`plan_mode_off` 四个工具，新增 `session/session_plan.py` 负责 Plan 状态读取
- [新增] `subagent_tool`（`subagent_create` + `subagent_core.py`），支持并行子 agent 集群
- [新增] `skill/coding-conduct/skill.md` 技能
- [清理] 误跟踪的 `memory.db` 二进制文件被移除；`loop/loop_core.py` 大改

对应提交：`ec95e4c`(file_tool拆分+plan_tool细化+subagent+coding-conduct)

后续计划：继续优化整体架构代码。

## 2026-07-01 · v0.0.8 — loop 重构跟进，即将进入 plan_loop 阶段

变更：
- [迭代] `plan_agent.md` 补充说明、`agents.yaml` 调整、`loop_core.py` 补充逻辑、`plan_create` 工具与其 tool_prompt 微调

对应提交：`5a55b7d`(loop重构跟进+plan工具微调)

后续计划：即将进入 plan_loop 阶段。

## 2026-07-01 · v0.0.7 — loop 重构完成，进入 plan_mode 开发阶段

变更：
- [重构] `core/loop.py` 移出 core，迁移为独立的 `loop/loop_core.py` 模块；`rich_output.py` 从 `core/` 提升到项目根
- [清理] README 大幅扩写记录新架构

对应提交：`bd4722b`(loop模块迁移+README扩写)

后续计划：进入 plan_mode 开发阶段。

## 2026-06-30 · v0.0.6 — hook 模块 + plan_tool + session 整体优化

变更：
- [新增] `hook/` 事件驱动系统（`hook_core.py` + `hooks/plan_hook`/`session_compress`/`session_slice` 三个自动发现子模块）
- [新增] `tool/tools/plan_tool/plan_create`（首版 plan 工具）与 `tool/tools/memory_recall`
- [新增] `agent/agents.yaml` 首次引入（YAML 驱动 agent 定义），新增 `plan_agent.md`
- [重构] 历史 `tools/` 目录整体迁移合并进 `tool/tools/`（两套目录统一）；`session_core.py` 大幅重构（约 323 行改动）

对应提交：`3cab3e8`(hook模块+plan_tool+session重构)

后续计划：继续优化整体架构代码。

## 2026-06-26 · v0.0.5 — session 重构（提交自标 v0.09）

变更：
- [新增] `session/` 模块（`session_core.py`/`session_compress.py`），session 落盘到 `session_detail/*.json`
- [重构] `core/agent.py` 迁移为 `agent/agent_core.py`，新增 `agent_prompt/`（main/slice/summary 三套 agent 定义）
- [新增] `core/loop.py`、`core/local_model.py`（GTE embedding 本地模型接入）；引入本地中文 embedding 模型权重（`local_model/nlp_gte_sentence-embedding_chinese-base/`）
- [新增] `tools/session_recall`（记忆召回）、`tools/session_compress`、`tools/session_slice`

对应提交：`436d40e`(session重构+本地embedding)

后续计划：继续优化整体架构代码。

## 2026-06-20 · v0.0.4 — 基础 tools 完善完毕，进入 memory 框架阶段

变更：
- [新增] 大批量工具集群：`tools/command`（含约 1300 行 `security.py` 安全白名单雏形）、`file_read`、`file_write`、`skill_tool`、`user_intention`、`web_fetch`、`web_search`
- [重构] `tool/tool_register.py` 迁移改名为 `tools/_tool_register.py` 并扩展为自动发现机制
- [新增] `core/prompt_structor.py`/`core/runtime.py`；`memory/system.md` 承接 06-13 的 system prompt

对应提交：`6ade27c`(基础tools集群+自动发现)

后续计划：进入 memory 框架搭建阶段。

## 2026-06-13 · v0.0.3 — system_agent_prompt 更新

变更：
- [新增] `prompt/agents_prompt/system_agent_prompt.md` 作为 system prompt 早期版本
- [清理] 提交中意外带入两份问答语料 md 文件（06-20 提交中被移除）

对应提交：`17994ae`(system_agent_prompt)

后续计划：继续完善基础架构。

## 2026-06-12 · v0.0.2 — 新增基础性内容：工具、记忆、核心

变更：
- [新增] `core/`（`agent.py`/`rich_output.py`）、`memory/`（`USER.py` 占位）、`tool/`（`tool_register.py`）三大目录雏形
- [新增] `AGENTS.py`/`SOUL.md`/`SYSTEM.py` 作为早期身份定义的占位文件

对应提交：`282bd2d`(基础三大目录雏形)

后续计划：继续完善基础架构。

## 2026-06-11 · v0.0.1 — 项目初始化

变更：
- [新增] 搭建最基础的项目骨架：`.gitignore`、`.python-version`、`main.py`、`pyproject.toml`、`README.md`

对应提交：`c9ed61e`(项目初始化) · `c7e0064`(项目初始文件夹目录)

后续计划：继续完善基础架构。
