# Alear030 — 从零自研的 Agent Harness

**Model + Harness = Agent**

Alear030 不是一个"Python Agent 框架"，它是一个完整的 Agent 基础设施（Harness）——处理工具编排、多 Agent 路由、会话生命周期、事件驱动 Hook、跨会话记忆召回。

一个多月，零 CS 背景，从需求反推结构，纯 Python 自研。

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
│   ├── loop_core.py            # Loop 类 — 全项目唯一推理引擎（main/subagent 共用，含 plan 分步循环）
│   └── __init__.py
│
├── agent/                      # Agent 集群
│   ├── agent_core.py           # Agent 类 + Agents 容器（YAML 驱动）
│   ├── agents.yaml             # 4 个 Agent 定义：main/slice/summary/plan
│   └── __init__.py
│
├── prompt/                     # Prompt 分层组合
│   ├── prompt_core.py          # Prompt 类：按语义分块拼装 system prompt
│   ├── __init__.py
│   ├── agent_prompt/
│   │   ├── system_prompt.md    # 认知架构（仅 main agent 注入）
│   │   └── agents/             # 各 Agent 自身身份/职责
│   │       ├── main_agent.md
│   │       ├── slice_agent.md
│   │       ├── summary_agent.md
│   │       └── plan_agent.md
│   ├── tool_prompt/            # 工具使用原则（+ 已持有工具的 name+简短描述）
│   └── skill_prompt/           # 技能使用原则（+ 已注册技能列表，仅 skill_tool 权限注入）
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
│   └── hooks/
│       ├── __init__.py
│       ├── session_slice/      # after_round 后台钩子：异步切片（LLM + 嵌入）
│       ├── session_compress/   # after_round 同步钩子：Token 超限时压缩
│       └── plan_hook/          # pre_toolUse 匹配 plan_design/plan_mode_on/plan_mode_off，注入 agents/session
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
│       └── user_intention/     # 用户意图分类（P0-P6）
│
├── local_model/                # 本地中文嵌入模型（GTE）+ local_model_core.py
│
├── memory/                     # 记忆系统（预留空目录，待实现）
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

4 个 Agent 各有独立身份、模型等级、工具授权，定义在 `agents.yaml`。不是 main 的函数——共享记忆空间，独立推理。

### 2. 会话切片 + 嵌入召回，而非 RAG

每轮对话 LLM 切话题边界 → 本地 GTE 模型算嵌入 → 余弦相似度搜索。不是"搜文档"，是"唤起经历"。

### 3. 事件驱动 Hook 系统

Hook 自动发现 → 注册 → 多事件点触发 → 同步/异步执行 → match 条件过滤。扩展一个 Hook 只需新建 `hook.py`。

### 4. 工具注册 + OpenAI Schema 自动生成

装饰器 `@register_tool` + `inspect.signature` → 自动生成 function-calling 参数 schema。新增工具零样板代码。

### 5. Prompt 分层组合

`prompt/` 包按语义分块拼装：`system_prompt.md`（认知架构，仅 main）+ `tool_prompt`（工具原则 + 已持有工具的 name+简短描述）+ `skill_prompt`（技能原则 + 已注册技能列表，仅 skill_tool 权限）+ 最近 3 个 session 的 slice 摘要（动态记忆）+ `{agent_name}_agent.md`（身份）+ 当前时间戳 = 最终 system prompt。每层独立，改一不伤三。

### 6. 模块解耦

agent\sesion\tool\hook… 等模块彼此之间通过main.py进行链接，通过hook在loop中的注入进行交互，而非彼此之间相互引用，避免后续框架扩展、功能扩展的场景造成不必要的循环引用的麻烦，避免在各种子文件下懒引用的不优雅
---

## 运行

```bash
# 确保 .env 中配置了模型参数
python main.py
```

## 技术栈

Python ≥3.10 · OpenAI SDK · DeepSeek API · Rich · PyYAML · tiktoken · sentence-transformers · DuckDuckGo Search

---
