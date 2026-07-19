# Changelog

版本号采用语义化风格（`major.minor.patch`），按改动性质人工判断：结构性重构/新增能力记 `minor`，bug 修复记 `patch`。项目无正式发布流程，版本号仅用于标记改动批次，不对应 tag。

按时间倒序排列，最新改动在最上面。

## 2026-07-19

### v0.5.0 — 记忆系统闭环：任务经验技能化、跨会话时间线与可恢复的上下文压缩

- 新增 task memory pipeline：定型 slice 按 `user_info` 与 `task` 分类；task 通过 normal/advanced 两级节点聚合，使用 `merged`/`no_match`/`failed` 三态契约路由，累积相似任务后产生 skill candidate
- 新增 Session 归属的纯内存 Attachment：`interrupt` 用于技能候选确认，`notification` 用于自动注入；首轮请求渲染后清空，不写入 session 事实数据
- 新增 skill 创建与更新闭环：`create-skill` 从来源 slice 回溯素材，`skill_finish` 将技能信息及新增来源写回 advanced task node，避免重复提示，并支持累计新变体后的更新 candidate
- 新增 session timeline：会话结束提炼 worthy slice 为 `thread`/`summary`/`keywords` 写入 timeline；下次启动按 token 预算经 attachment 注入，辅助 `memory_recall` 圈定历史 session
- timeline 提炼失败时，以 slice 的 `summary_detail`/`topic`/`key_words` 写入可追溯 fallback entry，避免单个 session 整段历史缺失；空 summary 的注入渲染同步兼容
- 重写 session compress：token 计数改为 main agent 全量 `message_list`，超过正式阈值 `250000` 后保留 system 与最后切片原始消息，自动以 attachment 注入更早切片摘要并恢复跨会话 timeline；三轮真实 REPL 验证压缩后可由摘要恢复首轮唯一标记
- 清理运行数据与 benchmark 密钥的版本控制：`test/`、真实 session/memory 语料及 `bench_secret.py` 均不再误提交；开源前仍需统一脱敏并重写历史泄漏文件

后续计划：继续跑通 LongMemEval benchmark basic 四格，并观察真实会话中的 compress 触发频率、压缩后衔接质量与 timeline fallback 的召回效果。

## 2026-07-14

### v0.4.0 — memory 自涌现管线：从 session slice 到用户画像与可量化召回基线

- 新增 memory pipeline、storage、config 与 prompt 子模块：after_round 处理已定型 worthy slice，after_session 补入最终尾片；`user_info` 经提取、reform 和身份去重后更新用户画像模板
- Hook 生命周期重组：session slice/compress 归入 `after_round`，新增 `after_session/final_memory_pipeline`，使 session 原始消息与派生 memory 数据职责分离
- 接入 `ask_user_question` 交互工具，为后续技能固化确认提供用户闸门
- 新增 recall benchmark 基线：metrics 纯函数、真实 `memory_recall` harness 与 18 条查询/104 项分级标注，用于后续比较召回质量
- 修复 slice 重复：按重喂窗口真实起点归一化 round、校验连续性并砍尾重接，消除 slice agent 重编号造成的重叠堆积
- command 白名单同步修复 Windows `/` flag 大小写与提示词可见命令列表，避免白名单和模型认知脱节

后续计划：收口 timeline、task memory 与 skill 生命周期，并用 benchmark 验证记忆链路的召回质量。

## 2026-07-05

### v0.3.1 — 切片可靠性与命令白名单修复

- 重写 slice agent 的边界提示词，以“自包含最小单元”同时约束过拆和过合；`key_words` 改为随信息密度自适应
- 修复切片 JSON markdown 围栏导致的解析失败，并保留工具调用与结果供切片及 task 提炼消费
- 修复 Windows 风格 `/` flag 白名单大小写匹配，command prompt 从白名单唯一来源动态生成可用命令清单

## 2026-07-05

### v0.3.0 — slice 结构收敛：topic/key_words/summary_detail 收拢进 slice_anchor，正式进入 memory 框架阶段

契机：slice 的元数据字段（session_id/time_stamp/start_round/end_round/slice_embedding/worthy_summary）和内容锚点字段（topic/key_words/summary_detail）职责不同，扁平结构混在一起不利于后续 memory 系统给 anchor 扩展字段，先收拢分层。

- `session_core.py::_session_slice` 构造 slice_data 时把 `topic`/`key_words`/`summary_detail` 收拢进新的 `slice_anchor` 子字典；`_session_slice_summary` 同步改为读写 `slice_anchor` 路径
- 同步适配两处读取存储态 slice 的下游代码：`memory_recall` 工具返回结果的字段读取、`session_recent` prompt 分块的渲染逻辑（对外返回/渲染的字段形状不变，只改内部读取路径）
- 一次性脚本迁移历史 34 个 `session_detail/*.json` 文件（33 个含 slice，共 200 条）：旧扁平结构转成 `slice_anchor` 嵌套结构，同时补齐旧数据里缺失的 `session_id` 字段（此前该字段没有落盘，是 `memory_recall` 读取时动态注入的）

后续计划：架构巩固到此告一段落，正式进入 memory（自涌现记忆）框架开发阶段。

## 2026-07-04

### v0.2.2 — 杂项修复：summary_agent 属性名 bug + hook_core 注释补充 + README 同步

- 修复：`session_core.py` 里 `self.summary_agent.summary_ai` 应为 `self.summary_agent.agent_ai`（属性名写错，历史遗留）
- `hook/hook_core.py` 补充 `trigger`/`_match` 等核心方法的设计意图注释（纯注释，无逻辑变化）
- `README.md` 同步 `prompt/prompts/` 装饰器自动发现机制的目录结构描述（跟进 v0.0.15 的实现，此前 README 一直没补上）

### v0.2.1 — hook 解耦：pre_toolUse 无条件注入取代 plan_hook 按工具匹配

契机：`plan_hook.py` 里 `inject_agents`（只匹配 `plan_design`）/`inject_session`（匹配 `plan_mode_on`/`plan_mode_off`/`plan_update`）两个钩子本质都是往 `tool_args` 塞 `agents`/`session`，工具变多后每加一个需要这些对象的工具就要再注册一条匹配规则，维护成本随工具数线性增长。

- 删除 `hook/hooks/plan_hook/`，新增 `hook/hooks/pre_toolUse/inject_import_args/`：无条件给全部工具调用注入 `agents`/`session`/`hooks`/`Loop` 四个对象，工具自己决定用不用
- 修 `loop_core.py::_pre_tool_use_hooks` 漏传参数：`hooks.trigger()` 补上 `hooks=self.hooks`/`Loop=Loop`，与新 hook 的函数签名对齐（否则该 hook 一触发就因缺参数抛异常，注入静默失效）
- 修 `tool_core.py::_make_parmeters` 的 schema 生成：排除 `VAR_KEYWORD`（即 `**kwargs`），避免其被当成必填字段塞进 function-calling schema 误导 LLM
- 17 个工具函数签名统一加 `**kwargs` 兜底，吞掉无条件注入带来的多余参数，避免 `TypeError`

### v0.2.0 — command 安全白名单：修 `/` flag 校验漏洞 + 新增系统信息查询命令

契机：agent 想查电脑配置（内存/显卡）推荐语音模型包，`systeminfo`/`wmic`/`nvidia-smi` 均不在白名单被拦。排查时发现一个更深的既有漏洞。

- 修复：`_validate_flags` 之前硬编码只校验 `-` 开头参数，`dir`/`findstr`/`tasklist`/`netstat` 等 Windows 命令声明的 `/xxx` flag 白名单形同摆设，任何 `/flag` 直接放过不校验。改成按命令自身声明的前缀风格（`-`/`=` 或 `/`/`:`）动态判断
- 新增：`systeminfo`、`nvidia-smi`（标准逐 flag 白名单）
- 新增：`wmic`（非 flag 式语法，改用动词/开关黑名单——只放行 `get`/`list` 查询，堵死 `call`/`set`/`delete`/`create` 和 `/format`（XSL 注入面）/`output`/`append`）

后续计划：管道场景下 `_validate_flags` 是拿整条命令行去对**管道第一个命令**的白名单校验，各段命令各自的 flag 未被正确归属校验（例如 `systeminfo | findstr /B ...` 中 `/B` 会被拿去对 `systeminfo` 校验）。已记录，本次不修。

### v0.1.1 — 修复 notice 系统提示未写入 session 的历史疏漏

`_force_final_reply`（v0.1.0 合并出的方法）里的系统提示此前只进了 `message_list`、没写入 session——这是原代码就有的疏漏，不是 v0.1.0 引入的。已对齐 `_sent_message_api` 的写入方式。

### v0.1.0 — loop_core 重构：纯 ReAct 引擎 + plan 编排剥离

`loop/loop_core.py` 从"ReAct 引擎 + plan 编排 + mode 切换探测"三件事揉在一起的 292 行，瘦身为对 plan 零感知的纯 ReAct 引擎；plan 分步编排剥离成独立的 `loop/orchestrator.py::PlanRunner`。

- 修死循环空转：`run_turn` 补齐"无 tool_calls"分支
- 修 plan 无限烧 token：`PlanRunner` 用无进展检测（连续 3 轮拿到同一 step 熔断）取代 `while True`
- 修 `json.loads` 裸奔：工具参数解析失败给空 args 兜底
- `Plan` 新增 `advance()` 公开 API，收回 Loop 对私有方法/内部属性的直接扒取
- 合并 3 处重复 LLM 调用 + 2 处雷同收尾逻辑
- `loop_run` 对外签名不变，`main.py` 与 subagent 零改动

后续计划：在 PlanRunner 之上加 goal 模式编排（goal 包 plan 包 step + 不合格重新 plan 回边），预留扩展点，未实现。

### v0.0.16 — system_prompt插入时机与round计数解耦

`Session` 构造时直接写入 round 0 的 system_prompt，round 计数从 1 开始，不再与 system_prompt 插入时机耦合。

### v0.0.15 — prompt分块改为装饰器+目录自动发现注册机制

`prompt_core.py` 瘦身，新增 `prompt_register.py`（`@register_prompt` 装饰器），各分块迁移为 `prompt/prompts/{name}/prompt.py` 目录结构，与 tool/hook 的自动发现机制对齐。

### v0.0.14 — README同步prompt_structor重构

README 目录结构和分层组合说明同步改为 `prompt/` 包描述。

### v0.0.13 — 重构prompt_structor：拆分为prompt/包

`agent/prompt_structor.py`（单文件硬拼接）拆分为独立的 `prompt/` 包：`prompt_core.py` 负责组装，`agent_prompt/agents/` 收纳各 agent 身份定义，新增 `skill_prompt`/`tool_prompt` 两个分块目录。

## 2026-07-03

### v0.0.12 — tool_prompt文案清理

`file_glob`/`file_grep`/`file_write` 的 tool_prompt 去除/调整学习模式相关提示语。

后续计划：重构 `prompt_structor`，将 system_prompt 拆成按语义分块的可组装结构（如 subagent 使用触发规则等），替代当前紧凑单文件硬拼接。

### v0.0.11 — memory_recall tool_prompt补充使用场景

`memory_recall` 的 tool_prompt 补充一条何时使用场景的说明。

### v0.0.10 — web_search/web_fetch改为批量并行

两个工具入参改为 list，内部用 `ThreadPoolExecutor` 并行处理并做单项错误隔离；补充两个工具的 tool_prompt 说明文档；顺手修复 web_fetch 失败信息里 error 始终为 None 的 bug；去掉 web_fetch 中多余的 print 调试输出。

### v0.0.9 — file_tool拆分 + plan_tool细化 + subagent_tool新增 + coding-conduct技能

- `file_tool` 从单一 file_read/file_write 拆分为 `file_edit`（局部唯一替换）/`file_glob`（按文件名查找）/`file_grep`（按正则搜索内容）/`file_read`/`file_write` 五件套，统一收进 `tool/tools/file_tool/`
- `plan_tool` 从单一 `plan_create` 细化为 `plan_design`/`plan_update`/`plan_mode_on`/`plan_mode_off` 四个工具，新增 `session/session_plan.py` 负责 Plan 状态读取
- 新增 `subagent_tool`（`subagent_create` + `subagent_core.py`），支持并行子 agent 集群
- 新增 `skill/coding-conduct/skill.md` 技能
- `loop/loop_core.py` 大改；误跟踪的 `memory.db` 二进制文件被移除

## 2026-07-01

### v0.0.8 — loop重构完成，即将进入plan_loop阶段

小幅跟进：`plan_agent.md` 补充说明、`agents.yaml` 调整、`loop_core.py` 补充逻辑、`plan_create` 工具与其 tool_prompt 微调。

后续计划：即将进入 plan_loop 阶段。

### v0.0.7 — loop重构完成，进入plan_mode开发阶段

`core/loop.py` 移出 core，迁移为独立的 `loop/loop_core.py` 模块；`rich_output.py` 从 `core/` 提升到项目根；README 大幅扩写记录新架构。

后续计划：进入 plan_mode 开发阶段。

## 2026-06-30

### v0.0.6 — hook模块 + plan_tool + session整体优化 + before_cc

- 新增 `hook/` 事件驱动系统（`hook_core.py` + `hooks/plan_hook`/`session_compress`/`session_slice` 三个自动发现子模块）
- 新增 `tool/tools/plan_tool/plan_create`（首版 plan 工具）与 `tool/tools/memory_recall`
- `agent/agents.yaml` 首次引入（YAML 驱动 agent 定义），新增 `plan_agent.md`
- 历史 `tools/` 目录整体迁移合并进 `tool/tools/`（两套目录统一）
- `session_core.py` 大幅重构（约 323 行改动）

## 2026-06-26

### v0.0.5 — session重构（提交自标 v0.09）

- 新增 `session/` 模块（`session_core.py`/`session_compress.py`），session 落盘到 `session_detail/*.json`
- `core/agent.py` 迁移为 `agent/agent_core.py`，新增 `agent_prompt/`（main/slice/summary 三套 agent 定义）
- 新增 `core/loop.py`、`core/local_model.py`（GTE embedding 本地模型接入）
- 引入本地中文 embedding 模型权重（`local_model/nlp_gte_sentence-embedding_chinese-base/`）
- 新增 `tools/session_recall`（记忆召回）、`tools/session_compress`、`tools/session_slice`

## 2026-06-20

### v0.0.4 — 基础tools完善完毕，进入memory框架阶段

大批量新增工具集群：`tools/command`（含约 1300 行 `security.py` 安全白名单雏形）、`file_read`、`file_write`、`skill_tool`、`user_intention`、`web_fetch`、`web_search`；`tool/tool_register.py` 迁移改名为 `tools/_tool_register.py` 并扩展为自动发现机制；新增 `core/prompt_structor.py`/`core/runtime.py`；`memory/system.md` 承接 06-13 的 system prompt。

后续计划：进入 memory 框架搭建阶段。

## 2026-06-13

### v0.0.3 — system_agent_prompt 更新

新增 `prompt/agents_prompt/system_agent_prompt.md` 作为 system prompt 早期版本。提交中意外带入两份问答语料 md 文件（06-20 提交中被移除）。

## 2026-06-12

### v0.0.2 — 新增基础性内容:工具、记忆、核心

初步搭出 `core/`（`agent.py`/`rich_output.py`）、`memory/`（`USER.py` 占位）、`tool/`（`tool_register.py`）三大目录的雏形；`AGENTS.py`/`SOUL.md`/`SYSTEM.py` 作为早期身份定义的占位文件。

## 2026-06-11

### v0.0.1 — 项目初始化

阶段一：搭建最基础的项目骨架。两次提交先后补齐 `.gitignore`、`.python-version`、`main.py`、`pyproject.toml`、`README.md`。
</content>
