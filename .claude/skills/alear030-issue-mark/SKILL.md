---
name: alear030-issue-mark
description: "把 Alear030 审查/复盘发现的待优化问题按规范标签和格式记录成 GitHub issue。当用户说'记一下这个问题'、'把问题清单传上去'、'创建/上传 tech-debt issue'、'整理成 issue' 时使用。项目有固定的标签体系（tech-debt/boundary-violation/eval-require 等）+ 严重度标题前缀 + 三段式正文（issue背景/issue功能/issue检查）规范，不要用 GitHub 默认标签（bug/enhancement 等）或自由发挥的格式。"
---

# Alear030 issue 标记与上传

把审查/复盘/日常发现的问题按项目固定的标签体系和格式记录到 GitHub 仓库 `Alear030/Alear030`。核心是**打对标签**——`tech-debt`/`boundary-violation`/`eval-require` 等标签各自的判据和叠加规则，加上严重度标题前缀 + 三段式正文，与仓库已建的 issue 模板保持风格统一。

## 生成前先做的事

1. 确认 gh 已登录：`gh auth status`（需有 `repo` scope，否则不能建 issue）。
2. 确认远程仓库：`git remote -v`，仓库应为 `Alear030/Alear030`。
3. 收集/整理待记录的问题清单，每条包含：问题描述、证据（`文件:行号`）、建议方向。如果是审查报告的产物，先按严重度分级（高/中/低）。

## 标签与严重度规范

- **统一用 `tech-debt` 标签**（仓库已建，紫灰色 `#d4c5f9`）。**不要**用 GitHub 默认标签（bug/enhancement/question 等）。
- **`boundary-violation` 是叠加标签，不是替代 `tech-debt`**（仓库已建，红色 `#b60205`，定义："对象跨越自身接口直接读写另一对象内部状态，模块/实例边界被打穿的一类问题"）。问题的本质是"外部代码绕过对象自己的方法，直接摸/改另一个对象的内部字段"（迪米特法则违规）时，`tech-debt` + `boundary-violation` 两个标签一起打；如果只是逻辑/健壮性/命名/schema 这类问题，不涉及跨对象摸内部状态，只打 `tech-debt`。例：#123（`Loop._close_round` 直接改 `session.round`）、#124（`Agent` 不该持有的 `tool_list`/`match_tool`）两个都打了双标签；#125（`agent_profile_update` 的裸字符串 key 打错静默变新增）不涉及跨对象摸内部状态，只打了 `tech-debt`。
- **`eval-require` 也是叠加标签**（仓库已建，定义："结论目前只靠代码审查或理论推导得出，需要用 trace/eval 实测数据验证效果与影响的问题"），可以叠在 `tech-debt` 或 `research` 任一主标签上（不像 `boundary-violation` 目前只依附 `tech-debt`）。判据：这条结论/改动目前只是"看代码/推理出来应该是这样"，还没有真实 trace/eval 数据支撑，需要后续跑数据验证才能确认。例：#129（attachment 拼接顺序改成前置后，是否真的提升了 prompt 缓存命中率——目前只有前缀缓存分叉点的理论推导，需要跑真实 session 的 trace 数据对比验证）。
- 严重度用**标题前缀**区分：`[高]` / `[中]` / `[低]`。
- 策略可配置：如果用户指定不同的标签名或严重度标记，按用户要求执行。

## 正文结构（三段式）

每个 issue 正文必须用以下三段式，与仓库模板 `feature_refactor_template.md` 一致：

```markdown
## issue背景（现状 + 风险）

<现状是什么、痛点在哪、为什么需要改。**存在风险**：涉及既有路径/数据安全/兼容性时明确列出。附证据 `文件:行号`。>

## issue功能（目标 + 建议方案）

- 目标点 1
- **建议方案**：方案方向（可列多个做取舍对比）

## issue检查（验收标准）

- [ ] 验收点 1
- [ ] 验收点 2
```

## 创建流程

逐条用 gh CLI 创建（PowerShell 环境，正文含中文/引号/路径，用临时文件传最稳）：

```powershell
# 单条创建
gh issue create --repo Alear030/Alear030 --title "[高] <一句话描述>" --body-file <临时文件> --label tech-debt

# 涉及边界违规（外部代码直接摸另一对象内部状态）时叠加 boundary-violation
gh issue create --repo Alear030/Alear030 --title "[高] <一句话描述>" --body-file <临时文件> --label tech-debt --label boundary-violation

# 批量时逐条执行，单条失败单独重试，不中断其余
```

- 标题：严重度前缀 + 一句话（能看出改什么）。
- 证据必须给到 `文件:行号` 级别，方便定位。
- 完成后跑 `gh issue list --repo Alear030/Alear030 --label tech-debt` 确认全部落地为 OPEN。

## 真实例子（照着这个语感写）

```text
标题：[高] build_prompt 对分块函数无隔离，单块异常炸整个 Agent 构造
标签：tech-debt
正文：
## issue背景（现状 + 风险）
启动单点故障：build_prompt 对每个分块函数无任何隔离，任一 function 抛异常即炸整个 Agent 构造，且无日志可定位。
**存在风险**：一条坏数据（timeline.json/user.json/skill frontmatter）即可杀全启动。
证据：prompt/prompt_register.py:34

## issue功能（目标 + 建议方案）
- 目标：单块异常不拖垮启动
- **建议方案**：中心化 try/except——捕获后记 log 跳过该块
## issue检查（验收标准）
- [ ] 单个分块抛异常时应用可正常启动
- [ ] 日志有明确告警指向出错分块
```

## 边界情况

- 一次上传多条时，逐条创建并报告 URL；如果某条标题冲突/网络失败，单独重试。
- 低严重度问题：如果用户说「只建高+中」，低优先级可以不建；要建时再补。
- 如果用户提到「创建 issue 模板」而不是记录具体问题，那是走模板创建流程（远程 `.github/ISSUE_TEMPLATE/`），不是本技能范围，先问清意图。
- **研究性课题不走本技能。** 「需要先想清楚再动手、没有明确验收标准」的开放性问题，用 `research` 标签和 `.github/ISSUE_TEMPLATE/research_template.md` 的结构（问题 / 具体触发点 / 现状盘点 / 需要研究的问题 / 不在范围内 / 背景来源），不要硬套三段式——三段式要求写出「目标 + 建议方案 + 验收标准」，而研究性议题恰恰是这三样都还没有答案。标题也不加严重度前缀。
