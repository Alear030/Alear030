"""PreToolUse(Bash|PowerShell)，挂在 alear030-reviewer 子代理的 frontmatter 上：把审查者的「只读」从提示词约定变成机制。

审查者要留着 Bash/PowerShell 读 git、调 gh、在仓库外做最小实验，所以工具白名单拦不住写操作；
它曾因 heredoc 被截断而误执行过一条 git commit。这里拒绝三类命令：
- git 的写操作：只放行读类子命令（status、log、show、diff 等）与几种只读形态（branch 列表、stash list 等）
- gh 的写操作：只放行 view / list / diff / checks 类与不带写参数的 gh api
- 在仓库工作区内删、搬、覆盖、重定向写入文件：复用 data_guard 的命令解析，把仓库根当成受保护目录
仓库外的临时目录照常可写。和 data_guard 一样是防手误的启发式，脚本内部的写入看不到。
"""

import json
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_guard as dg  # noqa: E402

GIT_READ = {
    "status", "log", "show", "diff", "blame", "ls-files", "ls-tree", "ls-remote", "rev-parse", "rev-list",
    "merge-base", "fetch", "cat-file", "grep", "describe", "shortlog", "check-ignore", "check-attr",
    "for-each-ref", "name-rev", "whatchanged", "show-ref", "version", "help", "count-objects", "cherry",
    "range-diff", "var", "show-branch",
}
# 子命令本身可读可写，只放行这些首参数形态
GIT_READ_FORMS = {
    "stash": {"list", "show"}, "worktree": {"list"}, "remote": {"", "-v", "show", "get-url"},
    "reflog": {"", "show"}, "notes": {"list", "show"},
}
GIT_BRANCH_WRITE_FLAGS = {"-d", "-D", "-m", "-M", "-c", "-C", "-f", "-u", "--delete", "--move", "--copy",
                          "--force", "--set-upstream-to", "--unset-upstream", "--edit-description"}
GH_READ = {
    "pr": {"view", "diff", "list", "checks", "status"}, "issue": {"view", "list", "status"},
    "repo": {"view"}, "run": {"view", "list"}, "release": {"view", "list"}, "search": None,
    "auth": {"status"}, "browse": None,
}
GH_API_WRITE_FLAGS = {"-f", "-F", "--field", "--raw-field", "--input"}


def _git_violation(args):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-C", "-c") else 1
    if i >= len(args):
        return None
    sub, rest = args[i].lower(), args[i + 1:]
    if sub in GIT_READ:
        return None
    if sub in GIT_READ_FORMS:
        first = rest[0].lower() if rest else ""
        return None if first in GIT_READ_FORMS[sub] else f"git {sub} {first}".strip()
    if sub == "branch":
        positional = [a for a in rest if not a.startswith("-")]
        listing = not positional or {"--list", "-l", "-a", "-r", "--contains", "--merged", "--no-merged"} & set(rest)
        if listing and not GIT_BRANCH_WRITE_FLAGS & set(rest):
            return None
        return "git branch（建分支/删分支）"
    if sub == "tag":
        return None if not rest or rest[0] in ("-l", "--list") else "git tag"
    if sub == "config":
        return None if rest and rest[0] in ("--get", "--get-all", "--list", "-l", "--get-regexp") else "git config"
    return f"git {sub}"


def _gh_violation(args):
    if not args:
        return None
    group = args[0].lower()
    if group == "api":
        method = next((args[i + 1].upper() for i, a in enumerate(args[:-1]) if a in ("-X", "--method")), "GET")
        if method != "GET" or GH_API_WRITE_FLAGS & set(args):
            return "gh api（写请求）"
        return None
    if group in GH_READ:
        allowed = GH_READ[group]
        if allowed is None or (len(args) > 1 and args[1].lower() in allowed):
            return None
    return f"gh {' '.join(args[:2])}"


def _commands(command):
    """按分隔符与管道切出每条命令，剥掉前缀，返回 (动词, 参数)；嵌套 shell 递归展开。"""
    out, cmd = [], []
    for t in dg._tokens(command) + [";"]:
        if t in dg.SEPARATORS or t in ("|", "(", ")", "{", "}"):
            words = dg._unwrap([w for w in cmd if w not in dg.REDIRECTS])
            cmd = []
            if not words:
                continue
            verb, args = dg._verb(words[0]), words[1:]
            if verb in dg.NESTED_SHELL:
                for i, a in enumerate(args):
                    if re.match(r"^-[a-z]*c$", a.lower()) or a.lower() in ("-command", "/c", "/k"):
                        inner = " ".join(args[i + 1:]) if verb in ("powershell", "pwsh", "cmd") else (args[i + 1] if i + 1 < len(args) else "")
                        out.extend(_commands(inner))
                        break
            else:
                out.append((verb, args))
        else:
            cmd.append(t)
    return out


def _violation(command, cwd):
    for verb, args in _commands(command):
        found = _git_violation(args) if verb == "git" else _gh_violation(args) if verb == "gh" else None
        if found:
            return found
    roots = {}
    for start in (cwd, os.environ.get("CLAUDE_PROJECT_DIR")):
        if start:
            for root in dg._checkout(os.path.realpath(start)):
                roots[dg._key(root)] = (".", root)
    if roots and dg._check(command, cwd, roots):
        return "在仓库工作区内删除、移动或写入文件"
    return None


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    command = (data.get("tool_input") or {}).get("command") or ""
    cwd = os.path.realpath(data.get("cwd") or os.getcwd())
    found = _violation(command, cwd)
    if not found:
        return
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"readonly_guard：审查执行者只读，这条命令涉及{found}。"
                "读 git 与 gh 的输出照常可以；实验请放在仓库外的临时目录里。"
                "如果确实需要改动才能确认一条发现，把它记成存疑，交回派发方。"
            ),
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 守卫自身出错时放行
        print(f"readonly_guard 内部错误，已放行：{e!r}", file=sys.stderr)
