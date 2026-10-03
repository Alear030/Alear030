"""PreToolUse(Edit|Write|NotebookEdit)：在 worktree 里工作时，拦下落到同一仓库其他 checkout 的写入。

worktree 与主仓库的目录结构完全一致，同名路径极易写错；写错时改动静默落到另一个 checkout，
本 worktree 纹丝不动，症状只在测试或 diff 里滞后出现。这里在落盘前按路径归属拦截：
目标所在 checkout 与当前 checkout 共享同一个 .git、却不是同一个工作树，就拒绝，并回给模型本 worktree 的对应路径。
当前在主仓库 checkout 里工作时不做任何判断。

例外：主 checkout 专属的 ignored 内容（.local/ 记录页、.cc_file/ 等）放行——目标在主 checkout 里被 gitignore、
本 worktree 里又没有同名文件时，写到主 checkout 才是对的，按提示改写进 worktree 反而会把内容分裂成两处。
data_guard 列出的运行数据目录不在例外内：那些被 ignore 是因为它们是不可恢复的数据，不是因为它们只属于主 checkout。
"""

import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True  # 下面从同目录 import，不在 .claude/hooks/ 里留 __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_guard import PROTECTED  # noqa: E402  运行数据目录清单只在 data_guard 维护一处


def _main_only_ignored(main_root, rel, worktree):
    """rel 在主 checkout 里被 gitignore、不在运行数据目录里、且本 worktree 没有同名文件。"""
    rel_posix = rel.replace("\\", "/")
    if any(rel_posix.lower() == p or rel_posix.lower().startswith(p + "/") for p in PROTECTED):
        return False
    if os.path.exists(os.path.join(worktree, rel)):
        return False
    try:
        out = subprocess.run(["git", "-C", main_root, "check-ignore", "-q", "--", rel_posix],
                             capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False  # 查不了就按没有例外处理，照常拦
    return out.returncode == 0


def _abs(path, base):
    # Git Bash 风格的 /d/foo 转成 D:/foo；相对路径按 base 解析
    m = re.match(r"^/([a-zA-Z])/(.*)$", path)
    if m and os.name == "nt":
        path = f"{m.group(1)}:/{m.group(2)}"
    return os.path.realpath(os.path.join(base, path))


def _key(path):
    return os.path.normcase(path)


def _checkout(path):
    """从 path 向上找最近的 .git，返回 (工作树根, 共享 .git 目录, 是否 worktree)；找不到返回 None。"""
    cur = path
    while True:
        dot_git = os.path.join(cur, ".git")
        if os.path.isdir(dot_git):
            return cur, dot_git, False
        if os.path.isfile(dot_git):
            with open(dot_git, encoding="utf-8") as f:
                m = re.match(r"gitdir:\s*(.+)", f.read().strip())
            if not m:
                return None
            # 相对 gitdir（worktree.useRelativePaths）按 .git 文件所在目录解析
            gitdir = os.path.realpath(os.path.join(cur, m.group(1).strip())).replace("\\", "/")
            idx = gitdir.lower().find("/.git/worktrees/")
            if idx < 0:
                return None  # submodule 等其他 gitdir 形态，不归本 hook 管
            return cur, os.path.realpath(gitdir[:idx + len("/.git")]), True
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    tool_input = data.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    cwd = data.get("cwd") or os.getcwd()
    if not target:
        return

    here = _checkout(os.path.realpath(cwd))
    if here is None or not here[2]:
        return
    path = _abs(target, cwd)
    there = _checkout(path)
    if there is None or _key(there[1]) != _key(here[1]) or _key(there[0]) == _key(here[0]):
        return

    worktree = here[0]
    rel = os.path.relpath(path, there[0])
    if rel.split(os.sep)[0] == ".git":
        hint = "目标在仓库的 .git 内部，worktree 里没有对应路径。确实要改的话，请用户来做。"
    elif there[2]:
        hint = "目标在同一仓库的另一个 worktree 里。确实要跨 checkout 写入的话，请用户来做。"
    elif _main_only_ignored(there[0], rel, worktree):
        return
    else:
        suggested = os.path.join(worktree, rel).replace("\\", "/")
        hint = f"当前在 worktree 里工作，这个路径指向主仓库 checkout。本 worktree 里对应的路径是：{suggested}"
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"worktree_guard：{hint}",
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 守卫自身出错时放行，不让一个 hook bug 卡死整个会话
        print(f"worktree_guard 内部错误，已放行：{e!r}", file=sys.stderr)
