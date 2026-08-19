---
name: alear030-issue-pretodoHandle
description: "从 GitHub Projects 看板 pre-todo 列认领一个 issue，开分支、规划（等用户确认）、开发、验证、合并到本地 master、删分支、推进看板状态到 done。当用户说'处理下一个 issue'、'跑一下 issue workflow'、'从 pre-todo 取一个任务'等时使用。"
---

# Alear030 pre-todo issue 处理流程

看板驱动的单槽 issue 处理协议：一次只认领一个 issue，从 `pre-todo` 出发，经 `Planning`（用户确认方案）、`inprogress`（开发验证），合并到本地 `master` 后推进到 `done`。以看板状态为事实源，Agent 按本协议逐步执行，人在规划闸门把关。

## 状态机

```text
pre-todo → Planning → inprogress → done
       └────────── blocked（卡住/需你介入时）────────┘
```

- `pre-todo → Planning`：Agent 认领并开分支
- `Planning → inprogress`：方案经用户确认后进入开发
- `inprogress → done`：合并进本地 `master` 之后
- `blocked`：遇到需要用户输入的点时移入，处理后回到原状态

## 处理前先做的事

1. `gh auth status` 确认已登录（需 `repo` scope）。
2. `git status --short` 必须为空；当前需基于 `master`。脏工作区直接中止并报告，不自动 stash。
3. 找到看板：`gh project list --owner Alear030` 取 project number，`gh project view <number>` 确认 status 字段含 pre-todo/Planning/inprogress/done/blocked。
4. 确认当前处理目标：远程尚无代码时合并目标是本地 `master`；代码推上远程后按 `origin/HEAD` 调整。

## 流程

1. **认领**
   - `gh project view <number>` 列出 pre-todo 中的 issue，默认取创建最早的（FIFO）。
   - 移卡到 Planning：`gh project item-edit --id <item-id> --field Status --project-id <project-id> --value Planning`
   - 在 issue 评论写认领记录 + 分支名。
2. **开分支**
   - `git checkout -b feat/issue-<n>-<slug> master`
3. **规划**
   - 读 issue 三段式正文（issue背景 / issue功能 / issue检查）。
   - 探索相关代码，产出方案贴出来。
   - **闸门**：等用户确认才继续；被否 → 移卡回 pre-todo（或 blocked），删分支，恢复工作区。
4. **开发**
   - 移卡 Planning → inprogress。
   - 按项目惯例实现（会话内先展示 diff 再落盘）。
5. **验证**
   - 按 `alear030-verify` 的规则：先 AST/静态检查，再目标单测，最后才端到端。
   - `python -m unittest discover` 必须从仓库根目录跑，不带 `-s test`。
6. **自检**
   - 逐条对照 issue 的「issue检查」验收清单；测试全绿才允许合并。
7. **合并**
   - `git checkout master && git merge --no-ff feat/issue-<n>-<slug>`
   - 合并后删除分支：`git branch -d feat/issue-<n>-<slug>`
   - 移卡 inprogress → done；`gh issue close <n>`。
8. **收尾**
   - 按 `changelog-refresh` 更新 CHANGELOG，按 `commit-message` 规范提交。
9. **询问**
   - 是否继续处理下一个 pre-todo。

## 边界情况

- 工作区脏：中止并报告，不自动处理。
- 规划被否：移卡回 pre-todo 或 blocked，删分支。
- 开发中需用户输入（需求歧义/数据安全问题）：移卡 blocked，问用户，处理完回 inprogress。
- issue 没有「issue检查」验收点：规划阶段补写验收标准给用户确认。
- 合并冲突：停下报告，不强解。
- 单槽串行：一次一个 issue，做完问用户再取下一个。
