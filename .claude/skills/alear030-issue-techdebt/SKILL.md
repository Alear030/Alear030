---
name: alear030-issue-techdebt
description: "把 Alear030 审查/复盘发现的待优化问题记录成 GitHub issue。当用户说'记一下这个问题'、'把问题清单传上去'、'创建/上传 tech-debt issue'、'整理成 issue' 时使用。项目有固定的 tech-debt 标签 + 严重度标题前缀 + 三段式正文（issue背景/issue功能/issue检查）规范，不要用 GitHub 默认标签（bug/enhancement 等）或自由发挥的格式。"
---

# Alear030 技术债 issue 上传

把审查/复盘/日常发现的「当前看可能有问题，后续需要修改优化」的技术债记录到 GitHub 仓库 `Alear030/Alear030-remote`。固定规范：`tech-debt` 专属标签 + 严重度标题前缀 + 三段式正文，与仓库已建的 issue 模板保持风格统一。

## 生成前先做的事

1. 确认 gh 已登录：`gh auth status`（需有 `repo` scope，否则不能建 issue）。
2. 确认远程仓库：`git remote -v`，仓库应为 `Alear030/Alear030-remote`。
3. 收集/整理待记录的问题清单，每条包含：问题描述、证据（`文件:行号`）、建议方向。如果是审查报告的产物，先按严重度分级（高/中/低）。

## 标签与严重度规范

- **统一用 `tech-debt` 标签**（仓库已建，紫灰色 `#d4c5f9`）。**不要**用 GitHub 默认标签（bug/enhancement/question 等）。
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
gh issue create --repo Alear030/Alear030-remote --title "[高] <一句话描述>" --body-file <临时文件> --label tech-debt

# 批量时逐条执行，单条失败单独重试，不中断其余
```

- 标题：严重度前缀 + 一句话（能看出改什么）。
- 证据必须给到 `文件:行号` 级别，方便定位。
- 完成后跑 `gh issue list --repo Alear030/Alear030-remote --label tech-debt` 确认全部落地为 OPEN。

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
