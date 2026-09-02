---
name: alear030-issue-fix
description: "把一个 GitHub issue 从拉取到 commit 走完修复流水线：定位问题→提出方案（拍板闸门）→修复→测试→code review→commit。与 alear030-issue-pretodoHandle 分工：那个从看板 pre-todo 认领、负责分支/PR/看板推进，本技能在当前 checkout 直接修、止于 commit，不 push 不合并。兼容模式：带 issue 号直接修（如 alear030-issue-fix 12），不带号则拉取 tech-debt 标签的 open issue 清单（时间正序）供挑选。当用户说'修一下这个issue'、'issue 流水线'、'处理 issue 12'、报 issue 号要求修复时使用；只要'看一下/分析'不修的不要用本技能。"
---

# Alear030 issue 修复流水线

把单个 issue 从「拉取」走到「commit」。分工边界：`alear030-issue-pretodoHandle` 管看板认领、开分支、PR 合并与看板推进；本技能不认领、不开分支、不 push，在当前 checkout 修完提交即止。两道硬闸门贯穿全程：**方案提出后必须停下等用户拍板**；**只暂存本任务相关文件**（工作区常有他人未提交改动，见 Hard lessons）。

## 流程

1. **拉取 issue**
   - 带号：`gh issue view <n> --json number,title,body,labels,state`，读全文（背景/建议方案/验收标准三段）。
   - 不带号：`gh issue list --label tech-debt --state open --limit 100 --json number,title,state,createdAt`，按 createdAt 正序输出清单（编号/日期/严重度前缀/一句话总结）交用户挑选；挑定后回到上一条。
   - 网络异常（GraphQL EOF 等）：原样重试一次，再失败停下报告，不无限重试。

2. **定位问题**（只读，不改任何文件）
   - 拿 issue 的证据行号核对现场代码，扫同文件/同调用链的相邻风险，用只读探针核实数据现状（读真实数据文件可以，写不行）。
   - 影响面三问：生产者/消费者是谁、异常从哪逃出去、现有防御网（如 build_prompt 的分块隔离）罩不罩得住。
   - **复核 issue 前提是否仍成立**：立项时的结论可能被后续修复改变（先例：#8 的"无隔离"前提被 #5 合入改变）。前提已变时如实说，验收标准逐条标注"已满足/未满足"。
   - 输出：问题定性（属实/已变化/不成立）+ 根因 + 影响面。先报告，报告不等于方案。

3. **提出方案**（拍板闸门）
   - 按 AGENTS.md 机制改动四要素给出：生产者/消费者、生命周期、验证方式、取舍风险。
   - 明确改动文件清单 + 测试方案（镜像目录）+ **范围外**（明确提出但不做的，等拍板）。
   - **停下等用户确认。未拍板不写任何文件。**方案被拒就回第 2 步重做，不自行折中。

4. **修复**
   - 按拍板方案最小改动，遵守 `$alear030-multitask-code`（先预览后落盘、不顺手重构）与 `$alear030-style-notes`（中文极简动作导向注释）。
   - 生产代码落盘后走 `$alear030-worktree-change-guard` 回读核对改动落在目标 checkout。

5. **测试**
   - 走 `$alear030-verify`：AST/静态 → 目标单测 → 全量。测试放 `test/` 下镜像源码目录，探针用 case_* 裸函数 + `__main__` runner + 纯 ASCII PASS 行，`python -m test.xxx` 点号路径跑。
   - 涉真实数据的场景一律 tempfile 模拟（patch 路径或 reload），不碰 session/memory/local_model 真实文件。
   - `python -m unittest discover` 基线必须保持绿；既有兄弟探针跑一遍防回归。

6. **code review**
   - 派恰好一个 review subagent：`subagent_type: general-purpose`（本环境无 bugbot 类型），`run_in_background: false`，prompt 按四段形状——Full Repository Path / Diff: uncommitted changes / Custom Instructions。
   - Custom Instructions 必须写清：评审范围（本任务文件清单）；**test/ 整体被 gitignore，diff 看不到，要求 subagent 直接读测试文件**；工作区他人未提交改动文件清单（排除，不产出 findings）；重点（正确性 + 与用户代码风格一致性：中文注释、`func(kw='v')` 等号无空格、探针惯例）。
   - findings 处置：机械性修正（测试补丁、词表对齐、坐标换算类）当场修掉并重跑测试；设计层面的只报告不动，交用户拍板。

7. **commit**
   - 走 `$alear030-commit-message`：时间戳标题 + 当前进度/后续计划正文，`git commit -F -` heredoc 传入。
   - `git add` 逐个点名本任务文件；`git diff --staged --stat` 核对；提交后 `git log -1` 验正文、`git status --short` 验残留（他人文件必须原样未动）。
   - **止步于此**：关 issue、追评、push、PR 都是用户的单独指令，不代做。

## Hard lessons

- **工作区共存**：dev worktree 常年有另一条工作线的未提交改动。`git status --short` 先看全貌，add 逐个点名，绝不 `git add -A`；提交后残留必须与开工前一致。
- **issue 会过时**：先复核前提再动手，否则会修一个已经被修掉的问题（#8 教训）。
- **网络抖动**：gh 命令 EOF/超时重试一次是常态，连败两次就停，别把它当 bug 查。
- **验收标准是对照表**：解决说明按 issue 验收条目逐项打勾写——但那是收尾指令的事，本技能只负责把代码修到经得起那张表。
