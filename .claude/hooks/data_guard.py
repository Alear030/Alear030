"""PreToolUse(Bash|PowerShell)：删除、移动、覆盖真实运行数据目录前，交给用户决定。

这些目录里是会话、派生记忆、trace 与诊断日志的唯一一份，ignore 了也不代表能从 git 恢复；
memory_configs 下的真身 JSON 会被管线长出新维度，覆盖等于清零。按 CLAUDE.md，动它们要用户明确授权，
所以这里返回 ask 而不是 deny：授权的那一下留给用户。

判据按 token 解析命令：路径参数按追踪到的 cd 解析成绝对路径，是受保护目录本身、其祖先或后代、
或通配符能匹配到它，即算命中；管道里不带路径参数的删除动词沿用上游命令的路径；cp 一类只看目的地；
git clean -x / git stash -a 视为波及全部。只读命令不触发。
这是防手误的启发式，不是沙箱：变量间接、脚本内部的删除（python 里的 shutil.rmtree 等）看不到。
隔离与还原走 alear030-clear-logdata 的 logdata.py，它只收 session id，不会命中这里。
"""

import fnmatch
import json
import os
import re
import shlex
import sys

PROTECTED = (
    "session/session_detail",
    "session/session_plan",
    "memory/memory_storage",
    "memory/memory_log",
    "eval/trace/trace_log",
    "log/log_data",
    "memory/memory_config/memory_configs",
)

# 参数里的每个路径都会被删、搬、清空或改写
WRITE_ALL = {
    "rm", "rmdir", "del", "erase", "rd", "unlink", "shred", "truncate", "mv", "move", "tee",
    "remove-item", "ri", "clear-content", "clc", "clear-item", "cli", "move-item", "mi",
    "rename-item", "ren", "rni", "set-content", "sc", "out-file",
}
COPY = {"cp", "copy", "copy-item", "cpi"}
CHANGE_DIR = {"cd", "pushd", "set-location", "sl", "chdir"}
NESTED_SHELL = {"bash", "sh", "zsh", "powershell", "pwsh"}
# 不改变语义、只是包在命令前面的前缀
WRAPPERS = {"sudo", "command", "builtin", "exec", "xargs", "nohup", "time", "then", "do", "else",
            "{", "(", "&", ".", "call", "%", "foreach-object", "foreach"}
CMD_FLAG = re.compile(r"^/[a-zA-Z]{1,4}(?::\S*)?$")  # cmd.exe / robocopy 的 /s /q /MIR
SEPARATORS = {";", "&&", "||", "&", "\n"}
REDIRECTS = {">", ">|", "&>", "*>"}


def _checkout(path):
    """返回 path 所在 checkout 的根，以及（若是 worktree）主仓库根。"""
    cur = path
    while True:
        dot_git = os.path.join(cur, ".git")
        if os.path.isdir(dot_git):
            return [cur]
        if os.path.isfile(dot_git):
            try:
                with open(dot_git, encoding="utf-8") as f:
                    m = re.match(r"gitdir:\s*(.+)", f.read().strip())
            except OSError:
                return [cur]
            roots = [cur]
            if m:
                gitdir = os.path.realpath(os.path.join(cur, m.group(1).strip())).replace("\\", "/")
                idx = gitdir.lower().find("/.git/worktrees/")
                if idx >= 0:
                    roots.append(gitdir[:idx])
            return roots
        parent = os.path.dirname(cur)
        if parent == cur:
            return []
        cur = parent


def _protected(cwd):
    roots = []
    for start in (cwd, os.environ.get("CLAUDE_PROJECT_DIR")):
        if start:
            roots += _checkout(os.path.realpath(start))
    return {_key(os.path.join(root, p)): p for root in roots for p in PROTECTED}


def _key(path):
    return os.path.normcase(os.path.normpath(path))


def _resolve(arg, cur):
    m = re.match(r"^/([a-zA-Z])(/.*)?$", arg)
    if m and os.name == "nt":
        arg = f"{m.group(1)}:{m.group(2) or '/'}"
    arg = os.path.expanduser(arg)
    if os.path.isabs(arg):
        return _key(arg)
    return None if cur is None else _key(os.path.join(cur, arg))


def _hits(path, protected):
    if path is None:
        return []
    out = []
    for key, name in protected.items():
        glob_at = next((i for i, c in enumerate(path) if c in "*?["), -1)
        if glob_at >= 0:
            fixed = os.path.dirname(path[:glob_at])  # 通配符之前的确定目录：落在受保护目录里面也算
            hit = (fnmatch.fnmatch(key, path) or fnmatch.fnmatch(key, os.path.join(path, "*"))
                   or fixed == key or fixed.startswith(key + os.sep))
        else:
            hit = key == path or key.startswith(path.rstrip("\\/") + os.sep) or path.startswith(key + os.sep)
        if hit:
            out.append(name)
    return out


def _tokens(command):
    # Windows 路径里的反斜杠换成 /（只换夹在路径字符之间的，保留 \; \rm 这类转义）
    text = re.sub(r"(?<=[\w.:*~])\\(?=[\w.*~])", "/", command).replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:  # 引号不配对：退化成按空白切
        return text.split()


def _path_args(args, cmd_style=False):
    out = []
    for a in args:
        if not a or a.startswith(("-", "$")) or a in ("{}", "}", "{"):
            continue
        if cmd_style and CMD_FLAG.match(a):
            continue
        out.append(a)
    return out


def _flags(args):
    return {a.lower() for a in args if a.startswith("-")}


def _git_targets(args):
    """git 子命令会破坏的路径参数；None 表示不破坏，"ALL" 表示整个工作区（含 ignored）。"""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-C", "-c") else 1
    if i >= len(args):
        return None
    sub, rest = args[i].lower(), args[i + 1:]
    flags = _flags(rest)
    paths = _path_args([a for a in rest if a != "--"])
    if sub == "clean":
        if any("x" in f.lower() for f in flags if not f.startswith("--")) or "--ignored" in flags:
            return paths or "ALL"
        return None
    if sub == "stash":
        return "ALL" if flags & {"-a", "--all"} else None
    if sub in ("rm", "mv"):
        return paths
    if sub == "restore":
        return None if "--staged" in flags and "--worktree" not in flags else paths
    if sub == "checkout":
        return paths[1:] if paths and "--" not in rest else paths
    if sub == "reset":
        return "ALL" if "--hard" in flags else None
    return None


def _targets(verb, args):
    """返回这条命令会破坏的路径参数；[] 表示带路径但不破坏，None 表示不是破坏性动词，"PIPE" 表示要用管道上游的路径。"""
    flags = _flags(args)
    if verb in WRITE_ALL or (verb == "new-item" and "-force" in flags) or (verb == "sed" and any(f.startswith("-i") for f in flags)):
        paths = _path_args(args, cmd_style=verb in ("rd", "del", "erase", "move"))
        if verb == "sed":
            paths = paths[1:]  # 第一个非选项参数是 sed 脚本
        return paths or "PIPE"
    if verb in COPY:
        for i, a in enumerate(args):
            if a.lower() in ("-t", "--target-directory", "-destination") and i + 1 < len(args):
                return [args[i + 1]]
        paths = _path_args(args, cmd_style=verb == "copy")
        return paths[-1:] if len(paths) >= 2 else []
    if verb == "robocopy":
        paths = _path_args(args, cmd_style=True)
        return paths[1:2] if {"/mir", "/purge"} & {a.lower() for a in args} else []
    if verb == "rsync":
        paths = _path_args(args)
        return paths[-1:] if any(f.startswith("--delete") for f in flags) else []
    if verb == "find":
        lowered = [a.lower() for a in args]
        destructive = "-delete" in lowered or any(
            a in ("-exec", "-execdir", "-ok") and i + 1 < len(args) and _verb(args[i + 1]) in WRITE_ALL
            for i, a in enumerate(lowered))
        if not destructive:
            return None
        roots = []
        for a in args:
            if a.startswith(("-", "(", "!")):
                break
            roots.append(a)
        return roots or ["."]
    return None


def _verb(token):
    name = token.lstrip("\\").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _check(command, cwd, protected):
    tokens = _tokens(command)
    cur = cwd
    hits = []
    upstream = []  # 当前管道里上游命令的路径参数
    piped = False
    cmd = []

    def flush():
        nonlocal cur, upstream, cmd
        words, redirect_targets = [], []
        i = 0
        while i < len(cmd):
            t = cmd[i]
            if t.isdigit() and i + 1 < len(cmd) and cmd[i + 1] in REDIRECTS | {">>", "<", ">&"}:
                i += 1  # 2>/dev/null 里的文件描述符，不是参数
                continue
            if t in REDIRECTS and i + 1 < len(cmd):
                redirect_targets.append(cmd[i + 1])
                i += 2
                continue
            if t in (">>", "<", ">&") and i + 1 < len(cmd):  # 追加、输入、句柄复制不覆盖文件
                i += 2
                continue
            words.append(t)
            i += 1
        for t in redirect_targets:
            hits.extend(_hits(_resolve(t, cur), protected))
        cmd = []
        # 剥掉前缀：sudo / env X=1 / cmd /c / 赋值语句 等
        while words:
            w = _verb(words[0])
            if w in WRAPPERS or re.match(r"^[A-Za-z_]\w*=", words[0]):
                words = words[1:]
            elif w == "env":
                words = words[1:]
            elif w == "cmd" and len(words) > 1 and words[1].lower() == "/c":
                words = words[2:]
            else:
                break
        if not words:
            return
        verb, args = _verb(words[0]), words[1:]
        if verb in NESTED_SHELL:
            for i, a in enumerate(args):
                if a.lower() in ("-c", "-command") and i + 1 < len(args):
                    hits.extend(_check(" ".join(args[i + 1:]) if verb in ("powershell", "pwsh") else args[i + 1], cur, protected))
                    break
            return
        if verb in CHANGE_DIR:
            dest = _path_args(args)
            cur = _resolve(dest[0], cur) if dest else None
            return
        targets = _git_targets(args) if verb == "git" else _targets(verb, args)
        if targets == "ALL":
            hits.extend(protected.values())
        elif targets == "PIPE":
            if piped:
                for a in upstream:
                    hits.extend(_hits(_resolve(a, cur), protected))
        elif targets:
            for a in targets:
                hits.extend(_hits(_resolve(a, cur), protected))
        upstream = _path_args(args)

    for t in tokens:
        if t in SEPARATORS:
            flush()
            piped, upstream = False, []
        elif t == "|":
            flush()
            piped = True
        elif t in ("(", ")", "{", "}"):
            flush()  # 子 shell 与脚本块不切断管道：| % { rm $_ } 里的 rm 仍接上游
        else:
            cmd.append(t)
    flush()
    return hits


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    command = (data.get("tool_input") or {}).get("command") or ""
    cwd = os.path.realpath(data.get("cwd") or os.getcwd())
    protected = _protected(cwd)
    if not protected:
        return
    hits = sorted(set(_check(command, cwd, protected)))
    if not hits:
        return
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"data_guard：这条命令会删除、移动或覆盖真实运行数据（{', '.join(hits)}），删了无法从 git 恢复，需要用户明确授权。"
                "有确认框时由用户在框里决定；被直接拦下时不要换写法绕过，向用户说明要做什么、为什么，"
                "得到授权后请用户用 `! <命令>` 亲自执行。清理测试会话走 alear030-clear-logdata 的隔离流程。"
            ),
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 守卫自身出错时放行
        print(f"data_guard 内部错误，已放行：{e!r}", file=sys.stderr)
