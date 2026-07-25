# Alear030 — 从零自研的 Agent Harness

**Model + Harness = Agent**

Alear030 不是一个"Python Agent 框架"，它是一个完整的 Agent 基础设施（Harness）——处理工具编排、多 Agent 路由、会话生命周期、事件驱动 Hook、跨会话记忆召回。


---

## 架构概览

```
Alear030/
├── main.py                     # 入口：创建 Session → 进入 loop → 触发 Hook
├── config.py                   # 集中配置（MODEL_LEVEL / 路径 / 常量）
├── rich_output.py              # Rich 终端输出（thinking/content/tool/system）
├── __init__.py                 # 导出常量
├── pyproject.toml              # 项目元数据
├── .env                        # API key & 模型配置（不纳入版本控制）
│
├── loop/                       # ReAct 推理循环
│   ├── loop_core.py            # Loop 类 — 纯 ReAct 引擎（main/subagent 共用，对 plan 编排零感知）
│   ├── orchestrator.py         # PlanRunner — plan 分步编排器，独立于 Loop（无进展熔断）
│   └── __init__.py
│
├── agent/                      # Agent 集群
│   ├── agent_core.py           # Agent 类 + Agents 容器（YAML 驱动）
│   ├── agents.yaml             # 5 个 Agent 定义：main/slice/summary/plan/memory
│   └── __init__.py
│
├── prompt/                     # Prompt 分层组合（装饰器 + 目录自动发现注册，对齐 tool/hook 惯例）
│   ├── prompt_core.py          # Prompt 类：薄封装，调用 build_prompt(agent)
│   ├── prompt_register.py      # @register_prompt 装饰器 + build_prompt（order 排序/condition 过滤/enabled 开关）
│   ├── __init__.py             # 自动发现并 import prompt/prompts/*/prompt.py
│   └── prompts/                # 各分块独立注册
│       ├── system_prompt/      # 认知架构（仅 main agent 注入）
│       ├── agent_prompt/       # {agent_name}_agent.md 身份（main/slice/summary/plan/memory）
│       ├── session_recent/     # 最近 3 个 session 的 slice 摘要（动态记忆，仅 main）
│       ├── memory_prompt/      # 用户画像注入（读 user.json，动态记忆，仅 main）
│       ├── timeline_prompt/    # 跨会话时间线（读 timeline.json，近/远分层渲染，仅 main）
│       ├── attachment_prompt/  # 运行时通知/中断处理协议声明（仅 main）
│       ├── tool_prompt/        # 工具使用原则 + 已持有工具的 name+简短描述
│       ├── skill_prompt/       # 技能使用原则 + 已注册技能列表（仅 skill_tool 权限）
│       └── basic_prompt/       # 当前时间戳
│
├── session/                    # 会话生命周期
│   ├── session_core.py         # Session 类（持久化 / 切片 / 压缩 / message_list 重建 / plan 初始化）
│   ├── session_plan.py         # Plan / Plan_step 类（读取/刷新 plan 状态）
│   ├── __init__.py
│   ├── session_detail/         # 每个会话的完整 JSON（切片 + 消息流，不纳入版本控制）
│   └── session_plan/           # plan_design 落盘的计划文件（不纳入版本控制）
│
├── hook/                       # 事件驱动 Hook 系统
│   ├── hook_core.py            # HookManager：注册 / 触发 / 匹配 / 异步
│   ├── __init__.py             # 自动发现 hook/hooks/*/
│   └── hooks/                  # 按 hook point 分层，递归发现 **/hook.py
│       ├── __init__.py
│       ├── pre_toolUse/
│       │   └── inject_import_args/  # 无条件注入，给全部工具塞 agents/session/hooks/Loop
│       ├── after_round/
│       │   ├── memory_pipeline/     # 后台：切片 + 摘要，把 worthy slice 交给 Memory
│       │   └── session_compress/    # 同步：Token 超限时压缩
│       └── after_session/
│           ├── final_memory_pipeline/ # 后台：会话退出时处理最终定型尾片
│           └── session_timeline/      # 后台：把 worthy slice 提炼成跨会话时间线事件
│
├── tool/                       # 工具系统
│   ├── tool_core.py            # 工具注册 / 匹配 / subagent_loop
│   ├── __init__.py             # 自动发现 tool/tools/*/
│   └── tools/
│       ├── __init__.py
│       ├── command/            # 命令行执行（8 层安全检查白名单 + security.py）
│       ├── file_tool/          # 文件读写工具集群
│       │   ├── file_read/      # 文件读取（带行号）
│       │   ├── file_write/     # 文件写入/新建（workspace 隔离，整体覆盖）
│       │   ├── file_edit/      # 文件局部编辑（唯一字符串替换，不覆盖全文件）
│       │   ├── file_glob/      # 按文件名 glob 模式查找文件
│       │   └── file_grep/      # 按正则表达式搜索文件内容
│       ├── web_search/         # DuckDuckGo 搜索
│       ├── web_fetch/          # 网页内容抓取
│       ├── memory_recall/      # 语义搜索历史会话切片
│       ├── session_slice/      # 读取特定会话原文
│       ├── plan_tool/          # plan 工具集群（调用 Loop 跑 plan_agent）
│       │   ├── plan_design/    # 创建/修改分步计划
│       │   ├── plan_update/    # 更新指定 step 的状态和结果
│       │   ├── plan_mode_on/   # 激活 plan 执行模式
│       │   └── plan_mode_off/  # 结束 plan 执行模式
│       ├── subagent_tool/      # 并行子 agent 集群（仅只读工具权限）
│       │   └── subagent_create/# 并行创建并运行多个 subagent
│       ├── skill_list/         # 技能发现与加载
│       ├── skill_finish/       # 技能创建收尾：确认后回写 skill_info
│       └── interaction/        # 用户交互：反向提问 / 澄清（ask_user_question）
│
├── local_model/                # 本地中文嵌入模型（GTE）+ local_model_core.py
│
├── memory/                     # 跨会话记忆系统：slice 分类 / 去重 / user_info 画像提炼 / 时间线生成
│   ├── memory_core.py          # 主线：分类、按 (session_id,start,end) 去重、slice_node 入库、画像更新
│   ├── memory_storage/         # 派生记忆：slice_node.json / user.json / timeline.json（运行时更新）
│   └── memory_config/          # 画像维度模板等运行时配置
│
├── skill/                      # 技能系统
│   ├── coding-conduct/
│   └── competitive-analysis/   # 竞品分析技能
│
├── workspace/                  # 工作区（不参与项目代码）
├── z_ccstudy/                  # 学习 & 实验代码（不影响主项目）
└── z_old_code/                 # 旧架构代码（归档）
```

---

## 核心设计决策

### 1. Multi-Agent 集群，而非单 Agent 函数调用

5 个 Agent 各有独立身份、模型等级、工具授权，定义在 `agents.yaml`（main/slice/summary/plan/memory）。不是 main 的函数——共享记忆空间，独立推理。

### 2. 会话切片 + 嵌入召回，而非 RAG

每轮对话 LLM 切话题边界 → 本地 GTE 模型算嵌入 → 余弦相似度搜索。不是"搜文档"，是"唤起经历"。定型切片再经后台 Memory 管线分类、去重、提炼用户画像与跨会话时间线。

### 3. 事件驱动 Hook 系统

Hook 自动发现 → 注册 → 多事件点触发 → 同步/异步执行 → match 条件过滤。扩展一个 Hook 只需在对应 hook point 下新建 `hook.py`。当前挂了 5 个：`pre_toolUse` 的 `inject_import_args`（给全部工具统一注入 `agents`/`session`/`hooks`/`Loop`，工具自己决定用不用，无需按工具名逐一注册匹配）；`after_round` 的 `memory_pipeline`（后台切片摘要）与 `session_compress`（同步压缩）；`after_session` 的 `final_memory_pipeline`（尾片处理）与 `session_timeline`（时间线生成）。

### 4. 工具注册 + OpenAI Schema 自动生成

装饰器 `@register_tool` + `inspect.signature` → 自动生成 function-calling 参数 schema。新增工具零样板代码。

### 5. Prompt 分层组合

`prompt/prompts/` 下每个分块用 `@register_prompt(order, condition, enabled)` 独立注册，`build_prompt(agent)` 按 order 排序、按 condition/enabled 过滤后拼接：`system_prompt`（认知架构，仅 main）+ `tool_prompt`（工具原则 + 已持有工具的 name+简短描述）+ `skill_prompt`（技能原则 + 已注册技能列表，仅 skill_tool 权限）+ `session_recent`（最近 3 个 session 的 slice 摘要，动态记忆，仅 main）+ `memory_prompt`（读 `user.json` 注入用户画像，仅 main）+ `timeline_prompt`（读 `timeline.json` 做近/远分层的跨会话时间线，仅 main）+ `attachment_prompt`（运行时通知/中断处理协议，仅 main）+ `agent_prompt`（`{agent_name}_agent.md` 身份）+ `basic_prompt`（当前时间戳）= 最终 system prompt。`session_recent`/`memory_prompt`/`timeline_prompt` 在 Agent 初始化时读盘，是**启动快照**，同进程后续写入不会自动刷新。新增分块只需在 `prompts/` 下建目录写 `prompt.py`，自动发现注册，不改其他分块。

### 6. 模块解耦

agent\sesion\tool\hook… 等模块彼此之间通过main.py进行链接，通过hook在loop中的注入进行交互，而非彼此之间相互引用，避免后续框架扩展、功能扩展的场景造成不必要的循环引用的麻烦，避免在各种子文件下懒引用的不优雅
---

## 运行

```bash
git clone <repo-url>
cd Alear030
pip install -e .

cp .env.example .env
# 编辑 .env —— 只填 MAX/MEDIUM/LOW_LEVEL_* 三级模型配置即可（可指向同一服务商，仅 model_name 不同）

python main.py
```

## 技术栈

Python ≥3.10 · OpenAI SDK · DeepSeek API · Rich · PyYAML · tiktoken · sentence-transformers · DuckDuckGo Search

---
