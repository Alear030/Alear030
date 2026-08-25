---
name: worktree-change-guard
description: worktree 改非 test/ 文件(生产代码)后,Read worktree 绝对路径确认改动落地并核对 diff。有过 Edit 的改动落到主仓库、worktree 没改的先例,根因未追溯到,所以一律回读核对。在 worktree 改 memory/loop/session/agent/tool/hook/prompt/config 等生产代码后必须使用,不要跳过。
user-invocable: false
---

# worktree 改文件校验

## 背景
在 worktree 里用 Edit 改生产代码文件(`memory/`、`loop/`、`session/` 等)时,改动有可能落到主仓库,worktree 没改。测试跑 worktree 代码(没改),一直崩,排查很久(本 session 踩过:`memory_core.py` Edit 改主仓库,worktree 没改,测试崩)。

现象是确认的,根因没追出来——当时没留下足够证据,不清楚是路径解析、工作目录还是别的原因。所以这条规矩不解释原因,只要求结果:改完回读目标 worktree 的绝对路径,核对 diff。

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
- `test/` 文件(如 `test/longmemeval_bench/`)没出过这个问题(Edit 改 worktree 正常),不需校验
- 只对生产代码(`memory/`、`loop/`、`session/`、`agent/`、`tool/`、`hook/`、`prompt/`、`config.py` 等)校验
- Bash python 按完整路径直接写(`open`/`write`)最稳,没出过落错的情况;Edit 有落错的先例,要校验

## 示例
Edit 改 `memory/memory_core.py`(worktree):
1. Read `<repo-root>\.claude\worktrees\<name>\memory\memory_core.py` 确认改动
2. 若没改 → Bash python 直接改 worktree 路径
3. 再 Read 确认改动落地
