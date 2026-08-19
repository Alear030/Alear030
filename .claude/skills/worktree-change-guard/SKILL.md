---
name: worktree-change-guard
description: worktree 改非 test/ 文件(生产代码)后,Read worktree 路径确认改动落地。防 Edit 跟 git worktree 硬链接改到主仓库、worktree 没改。在 worktree 改 memory/loop/session/agent/tool/hook/prompt/config 等生产代码后必须使用,不要跳过。
user-invocable: false
---

# worktree 改文件校验

## 背景
git worktree 对未修改文件可能硬链接主仓库。Edit 改 worktree 的生产代码文件(`memory/`、`loop/`、`session/` 等)时,可能跟硬链接改到主仓库,worktree 没改。测试跑 worktree 代码(没改),一直崩,排查很久(本 session 踩过:`memory_core.py` Edit 改主仓库,worktree 没改,测试崩)。

## 何时触发
在 worktree(路径含 `.claude/worktrees/`)用 Edit 改非 test/ 的生产代码文件后,立即触发。

## 校验流程
1. 确认当前在 worktree:工作目录含 `.claude/worktrees/`
2. 对刚 Edit 的文件,Read worktree 完整路径,确认改动落地(搜索改动的内容是否在 worktree 文件里)
3. 若 worktree 文件没改动(Read 看不到改动),说明 Edit 改到了主仓库:
   - 用 Bash python 直接改 worktree 路径(`open(worktree_path, 'w').write(...)`)
   - 改完再 Read worktree 确认
4. 报告:改对位置(worktree)还是改错(主仓库,已用 Bash 修正)

## 注意
- `test/` 文件(如 `test/longmemeval_bench/`)不受硬链接影响(Edit 改 worktree 正常),不需校验
- 只对生产代码(`memory/`、`loop/`、`session/`、`agent/`、`tool/`、`hook/`、`prompt/`、`config.py` 等)校验
- Bash python 直接改文件(`open`/`write`)不跟硬链接,最稳;Edit 可能跟链接,要校验

## 示例
Edit 改 `memory/memory_core.py`(worktree):
1. Read `D:\Alear030\.claude\worktrees\<name>\memory\memory_core.py` 确认改动
2. 若没改 → Bash python 直接改 worktree 路径
3. 再 Read 确认改动落地
