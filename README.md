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
├── __init__.py                 # 导出常量
├── pyproject.toml              # 项目元数据
├── .env                        # API key & 模型配置（不纳入版本控制）
├── memory.db                   # 旧版记忆系统遗留（SQLite）
│
├── core/                       # 核心运行时
│   ├── loop.py                 # ReAct 推理循环：消息发送 → 工具调用 → 兜底
│   ├── rich_output.py          # Rich 终端输出（thinking/content/tool/system）
│   ├── local_model.py          # 本地模型配置引用
│   └── __init__.py
│
├── agent/                      # Agent 集群
│   ├── agent_core.py           # Agent 类 + Agents 容器（YAML 驱动）
│   ├── agents.yaml             # 4 个 Agent 定义：main/slice/summary/plan
│   ├── prompt_structor.py      # Prompt 分层组合：系统/身份/记忆/时间
│   ├── __init__.py
│   └── agent_prompt/           # Markdown 格式的 Agent system prompt
│       ├── system_prompt.md    # 认知架构
│       ├── main_agent.md       # 主 Agent 身份
│       ├── slice_agent.md      # 切片 Agent
│       ├── summary_agent.md    # 摘要 Agent
│       └── plan_agent.md       # 计划 Agent
│
├── session/                    # 会话生命周期
│   ├── session_core.py         # Session 类（持久化 / 切片 / 压缩 / message_list 重建）
│   ├── __init__.py
│   ├── session_summary.json    # 跨会话摘要索引
│   ├── session_detail/         # 每个会话的完整 JSON（切片 + 消息流，~8.5MB）
│   └── session_plan/           # plan_create 落盘的计划文件
│
├── hook/                       # 事件驱动 Hook 系统
│   ├── hook_core.py            # HookManager：注册 / 触发 / 匹配 / 异步
│   ├── __init__.py             # 自动发现 hook/hooks/*/
│   └── hooks/
│       ├── __init__.py
│       ├── session_slice/      # 每轮后异步切片（LLM + 嵌入）
│       ├── session_compress/   # Token 超限时同步压缩
│       └── plan_hook/          # pre_toolUse 注入 agents 容器
│
├── tool/                       # 工具系统
│   ├── tool_core.py            # 工具注册 / 匹配 / subagent_loop
│   ├── __init__.py             # 自动发现 tool/tools/*/
│   └── tools/
│       ├── __init__.py
│       ├── command/            # 命令行执行（8 层安全检查白名单 + security.py）
│       ├── file_read/          # 文件读取（带行号）
│       ├── file_write/         # 文件写入（workspace 隔离）
│       ├── web_search/         # DuckDuckGo 搜索
│       ├── web_fetch/          # 网页内容抓取
│       ├── memory_recall/      # 语义搜索历史会话切片
│       ├── session_slice/      # 读取特定会话原文
│       ├── plan_tool/
│       │   └── plan_create/    # 分步执行计划
│       ├── skill_list/         # 技能发现与加载
│       └── user_intention/     # 用户意图分类（P0-P6）
│
├── local_model/                # 本地中文嵌入模型（GTE，~196MB）
│
├── memory/                     # 记忆系统（待实现）
│   ├── agent_memory/
│   ├── experience_memory/
│   └── user_memory/
│
├── skill/                      # 技能系统
│   └── competitive-analysis/   # 竞品分析技能
│
├── workspace/                  # 工作区（不参与项目代码）
│   ├── Alear030_self/          # 备用的 hook_plan / main_plan / plan_loop / coding_guidelines
│   ├── splendid_project/       # 外部技能项目
│   ├── scripts/
│   ├── screenshots/
│   └── docs/
│
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

`system_prompt.md`（认知架构）+ `main_agent.md`（身份）+ 最近 3 个 session 的 slice 摘要（动态记忆）+ 当前时间戳 = 最终 system prompt。每层独立，改一不伤三。

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
