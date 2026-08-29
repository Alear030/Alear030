# Repository Guidelines

> 权威关系：协作、安全、写入和验证约束以本文件为准；运行行为与架构事实以现场代码、注册器和配置为准；`CLAUDE.md` 仅作历史参考，引用前必须对照源码。
>
> 维护原则：这里只保留无法通过常规探索自发现的长期规则、稳定不变量和源码入口。工具、Hook、Prompt、Widget 等易变清单以目录现状为准，不在本文件逐项枚举。

## 项目定位

Alear030 是从仓库根目录运行的 Python Agent Harness，负责工具编排、多 Agent 路由、会话生命周期、事件驱动 Hook 和跨会话记忆；它不是供外部导入的库。`main.py` 是高层装配与 Textual TUI 启动入口，具体运行行为以现场代码、注册器和 `agent/agents.yaml` 为准，README 仅作概览。

项目存在三个不同层级的 Agent：`agent/agents.yaml` 配置的常驻 Agent、`subagent_create` 创建的运行时子代理，以及宿主开发工具自身的协作 Agent。讨论生命周期、权限和路由时必须明确所指层级，不得混用。

仓库公开并采用 MIT 许可证。所有落笔内容都可能被陌生人阅读，不得写入本机绝对路径、内部协作语境或无助于维护的过程叙述。

## 协作与写入

- 基本节奏是：探索 → 规划 → 用户拍板 → 执行 → 验收。只读探索可随时进行。
- 所有文件修改默认先在对话中展示拟议全文或等价 diff，取得用户明确确认后再落盘。编辑器的 Accept/Keep 属于写入后的审阅，不算事前批准。
- 无行为影响的纯文本改动可以免除单独的规划闸门，但不能免除“先预览、明确确认、后落盘”。
- 触碰行为、机制或调用链时，规划必须说明生产者、消费者、生命周期、验证方式与取舍风险；切片应尽量做到可独立提交。
- 任务字面范围不足以达标时，可以提出超范围项，但必须等待用户拍板后才能实施。
- 写盘前确认当前目录是仓库根，并检查 `git status --short`。只修改任务直接需要的内容，不顺手重构、格式化或清理历史代码，保留用户已有改动。
- 不要让多个 Agent 同时编辑同一 checkout。
- 临时截断或禁用路径时，只增加入口 `return` 或等价 guard，禁止删除或清空原函数体；移除 guard 后必须能够原样恢复。
- 任务收尾时检查是否产生了无法从源码自发现的长期规则。确有必要沉淀时，仍须先预览再修改本文件，不强制调用未加载的技能。

## 验证

- `python main.py` 不是无副作用的冒烟测试：构造 Session 会写文件，交互可能调用模型 API、下载权重或更新记忆。未经单独批准，不运行真实模型、embedding 下载、benchmark 或生产数据写入。
- 按“AST/静态检查 → 目标单测或无模型探针 → 端到端”逐层验证；涉及项目代码验证时使用 `$alear030-verify`，具体注意事项以该技能为准。
- 从仓库根运行全量单测：`python -m unittest discover`，不要追加 `-s test`。
- 单个测试模块使用 `python -m test.<package>.<module>`，不要直接运行 `python test/...py`。
- shell 内联 Python 内容若包含反引号或复杂正则转义，应先落成临时脚本再执行，避免命令替换或转义改变原文。
- 机制改动应在规划阶段确定验证方法；可稳定复用且不触碰真实数据的探针，优先固化进 `test/`。

## 架构手册

以下内容是维护时必须守住的稳定边界；实现细节仍须从对应源码入口重新确认。

### 装配与扩展

- 高层对象装配集中在 `main.py`，常驻 Agent 配置入口是 `agent/agents.yaml`。
- 新增能力必须沿既有 Tool、Hook、Prompt 或界面注册机制接入，不得另建平行注册表。探索入口包括 `tool/tool_core.py`、`hook/hook_core.py`、`prompt/prompt_register.py` 及对应目录的加载代码。
- 工具运行时对象由 `pre_toolUse` Hook 注入。工具通过 `kwargs.get(...)` 获取注入对象，判空后采用“报错返回”，不得假设模型能够构造这些对象。入口见 `hook/hooks/pre_toolUse/` 和 `tool/tool_core.py`。
- Prompt 是进程启动时构建的快照；运行中修改 Prompt 文件不会自动刷新当前进程。入口见 `prompt/prompt_core.py` 和 `prompt/prompt_register.py`。

### Session 与 Memory

- 原始 Session 消息和 `session_slice` 是事实源；`slice_node`、`user_info`、`timeline` 等均是可追溯、可重建的派生物，不得反写派生结果替代原文。
- Session 读写、切片和压缩入口在 `session/session_core.py`；Memory 摄入与提炼由 `hook/hooks/after_round/`、`hook/hooks/after_session/` 和 `memory/memory_core.py` 协作完成。
- `json_lock` 只保护短时读取、合并和写入。持锁期间禁止调用模型或 embedding；耗时处理必须在锁外完成，再在锁内按身份或坐标合并。
- Memory 存储入口在 `memory/memory_storage/memory_storage_core.py`。修改派生数据结构时必须保留来源坐标和可追溯性，并检查所有生产者与消费者。
- 任何真实历史数据 replay 都必须在执行前后比对相关文件哈希并报告证据。

### Loop

- Loop 的工具调用、模式切换和异常收口入口在 `loop/loop_core.py`。
- 强制收尾通过不再向模型提供 tools 实现，不能只依赖 Prompt 要求模型停止调用工具。
- mode 切换以工具批次执行前后的 Session 状态 diff 为准；切换生效后，本批剩余调用和后续流程必须遵守代码层硬边界。
- 模型 API 的建连和流式异常统一收口为 `LoopAPIError`，避免在不同调用路径重复包装或产生不同语义。

### MCP

- MCP 客户端目录必须使用 `mcp_client/`；不要创建顶层 `mcp/`，否则可能遮蔽第三方包。
- asyncio 隔离在 `mcp_client/mcp_supervisor.py` 的 supervisor 边界内，应用层通过同步接口访问，不把事件循环扩散到其他模块。
- 远端工具的 `inputSchema` 直接作为工具契约，不通过 Python 闭包签名反推。
- 转发远端调用前必须剔除 Hook 注入的运行时对象；工具名保持 `mcp__{server}__{tool}` 形式。注册与转发入口见 `mcp_client/mcp_bridge.py`。

## 编码与数据

- Python 使用四空格缩进和 UTF-8；命名采用 snake_case、PascalCase、UPPER_SNAKE_CASE。
- 持久化读写显式指定 `encoding='utf-8'`；JSON 默认使用 `ensure_ascii=False, indent=2`；写文件前创建父目录。
- LLM 输出的 JSON 解析必须容忍代码块包裹、字段缺失和结构抖动，并在进入业务逻辑前校验响应形状。
- 存量 typo 只允许兼容，不得扩散：`MEMORTY` 属于 config，`loker`、`slef` 属于 `memory_storage_core`。
- 更完整的编码规则见 `.cursor/rules/coding-conventions.mdc`；若规则与现场实现冲突，先报告并确认，不自行扩大修改范围。
- `session/session_detail/`、`session/session_plan/`、`memory/memory_storage/`、`memory/memory_config/`、`memory/memory_log/` 和 `local_model/` 包含真实、敏感或昂贵数据。未经明确授权，不得删除、清场或批量覆盖；不确定路径归属时先询问用户。
- 禁止提交 `.env`、API Key、会话原文、生成记忆、诊断日志和模型权重，包括 `pytorch_model.bin`、`model.safetensors`。

## 技能入口

只引用当前会话实际加载且具有 `SKILL.md` 的技能：

- `$alear030-verify`：按项目约束验证代码改动。
- `$alear030-multitask-code`：生产代码修改采用 Plan → Execute → Review 纪律。
- `$alear030-multitask-pipeline`：跨模块大改或机制路径变更采用完整协作流水线；小改使用轻量执行与复核。
- `$alear030-style-notes`：编写或修改用户代码及注释时遵守中文、极简、动作导向的注释风格。
- `$worktree-change-guard`：在 worktree 修改非 `test/` 生产代码后核对改动确实落在目标 checkout。
- `$scan-claude-markers`：扫描和处理源码中的 `@claude` 标记。完成后回写 `# done(@claude): <做了什么>`；`@claude(ignore)` 是用户备注，不得改动。
- `$alear030-issue-pretodoHandle`：从 GitHub Projects 的 pre-todo 列处理下一个 issue。
- `$alear030-issue-techdebt`：按项目格式记录审查或复盘发现的技术债。
- `$commit-message`：生成符合项目规范的提交信息。
- `$changelog-refresh`：将一批提交归纳到 `CHANGELOG.md` 的版本块。

新增 Tool、Hook、Prompt 或 Widget 时，当前没有可调用的本地扩展技能；应从现有同类实现、注册器和目录加载逻辑开始探索，不得把仅有目录但缺少 `SKILL.md` 的内容当成技能调用。

## 提交

提交信息格式为：

`YYYYMMDD_HHMMSS <一句话主题，最多 50 字>`

空一行后填写正文。提交时必须使用 `$commit-message` 生成信息，并且只暂存本任务相关文件。

版本叙事使用 `$changelog-refresh` 按版本块归纳，不机械对应单次提交。未经用户要求，不暂存、不提交，也不修改 Git 配置。
