"""PreToolUse(Bash|PowerShell)：删除、移动、覆盖真实运行数据目录前，交给用户决定。

这些目录里是会话、派生记忆、trace 与诊断日志的唯一一份，ignore 了也不代表能从 git 恢复；
memory_configs 下的真身 JSON 会被管线长出新维度，覆盖等于清零。按 CLAUDE.md，动它们要用户明确授权，
所以这里返回 ask 而不是 deny：授权的那一下留给用户。

判据按 token 解析命令：路径参数按追踪到的 cd 解析成绝对路径，是受保护目录本身、其祖先或后代、
或通配符能匹配到它，即算命中；管道里不带路径参数的删除动词沿用管道里最近一个带路径的上游命令；
cp / rsync 一类只看目的地；heredoc 正文是数据，不当命令解析。
git 分两类：clean -x / stash -a 作用于 ignored 文件，视为波及全部；checkout / restore / rm / mv / reset --hard
只动被跟踪的文件，只在受保护目录里确实有被跟踪文件时才算命中。只读命令不触发。
这是防手误的启发式，不是沙箱：变量间接、脚本内部的删除（python 里的 shutil.rmtree 等）、
Write / Edit 工具的整体覆盖都不在视野内。
隔离与还原走 alear030-clear-logdata 的 logdata.py，它只收 session id，不会命中这里。
"""

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys

# 与 CLAUDE.md「数据与版本控制安全」一节同级；再往上一级的目录里有被跟踪的源码
PROTECTED = (
    "session/session_detail",
    "session/session_plan",
    "memory/memory_storage/memory_storages",
    "memory/memory_log/memory_logs",
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
COPY = {"cp", "copy", "copy-item", "cpi", "rsync"}
CHANGE_DIR = {"cd", "pushd", "set-location", "sl", "chdir", "push-location"}
NESTED_SHELL = {"bash", "sh", "zsh", "powershell", "pwsh", "cmd"}
# 不改变语义、只是包在命令前面的前缀；值为它自己吃掉的选项形态
WRAPPERS = {"command", "builtin", "exec", "nohup", "time", "then", "do", "else",
            "{", "(", "&", ".", "call", "%", "foreach-object", "foreach"}
WRAPPERS_WITH_OPTS = {"sudo", "env", "xargs", "nice", "timeout", "stdbuf", "ionice"}
OPT_WITH_VALUE = {"-u", "-g", "-n", "-i", "-I", "-L", "-P", "-d", "-E", "-s", "-k", "--signal", "--user"}
CMD_FLAG = re.compile(r"^/[a-zA-Z]{1,4}(?::\S*)?$")  # cmd.exe / robocopy 的 /s /q /MIR
SEPARATORS = {";", "&&", "||", "&", "\n"}
REDIRECTS = {">", ">|", "&>", "*>"}
HEREDOC = re.compile(r"<<-?[ \t]*(?:'([^']*)'|\"([^\"]*)\"|\\?([A-Za-z_]\w*))")


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


def _key(path):
    return os.path.normcase(os.path.normpath(path))


def _protected(cwd):
    """{绝对路径 key: (相对名, 所在仓库根)}"""
    roots = []
    for start in (cwd, os.environ.get("CLAUDE_PROJECT_DIR")):
        if start:
            roots += _checkout(os.path.realpath(start))
    return {_key(os.path.join(root, p)): (p, root) for root in roots for p in PROTECTED}


def _has_tracked(root, rel):
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "--", rel], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return True  # 查不了就按有算，宁可多问一次
    return out.returncode != 0 or bool(out.stdout.strip())


def _resolve(arg, cur):
    arg = re.sub(r"^-[A-Za-z]+:", "", arg)  # PowerShell 的 -Path:x
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
    glob_at = next((i for i, c in enumerate(path) if c in "*?["), -1)
    for key in protected:
        if glob_at >= 0:
            fixed = os.path.dirname(path[:glob_at])  # 通配符之前的确定目录：落在受保护目录里面也算
            hit = (fnmatch.fnmatch(key, path) or fnmatch.fnmatch(key, os.path.join(path, "*"))
                   or fixed == key or fixed.startswith(key + os.sep))
        else:
            hit = key == path or key.startswith(path.rstrip("\\/") + os.sep) or path.startswith(key + os.sep)
        if hit:
            out.append(key)
    return out


def _strip_heredocs(command):
    """去掉 heredoc 正文：那是喂给命令的数据，不是要执行的命令。"""
    lines, out, pending = command.split("\n"), [], []
    for line in lines:
        if pending:
            delim, dash = pending[0]
            if (line.lstrip("\t") if dash else line) == delim:
                pending.pop(0)
            continue
        out.append(line)
        for m in HEREDOC.finditer(line):
            pending.append((next(g for g in m.groups() if g is not None), line[m.start() + 2:m.start() + 3] == "-"))
    return "\n".join(out)


def _tokens(command):
    # Windows 路径里的反斜杠换成 /（只换夹在路径字符之间的，保留 \; \rm 这类转义）
    text = re.sub(r"(?<=[\w.:*~])\\(?=[\w.*~])", "/", _strip_heredocs(command)).replace("\n", " ; ")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:  # 引号不配对：退化成按空白切
        return text.split()


def _path_args(args, cmd_style=False):
    out = []
    for a in args:
        if not a or a.isdigit() or a.startswith(("$", "{", "}")) or (a.startswith("-") and not re.match(r"^-[A-Za-z]+:.", a)):
            continue
        if cmd_style and CMD_FLAG.match(a):
            continue
        out.append(a)
    return out


def _flags(args):
    return {a.lower() for a in args if a.startswith("-")}


def _git_targets(args):
    """返回 (会破坏的路径参数, 是否只动被跟踪文件)；路径为 None 表示不破坏，"ALL" 表示整个工作区。"""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-C", "-c") else 1
    if i >= len(args):
        return None, False
    sub, rest = args[i].lower(), args[i + 1:]
    flags = _flags(rest)
    paths = _path_args([a for a in rest if a != "--"])
    if sub == "clean":
        if any("x" in f.lower() for f in flags if not f.startswith("--")) or "--ignored" in flags:
            return paths or "ALL", False
        return None, False
    if sub == "stash":
        return ("ALL" if flags & {"-a", "--all"} else None), False
    if sub in ("rm", "mv"):
        return paths, True
    if sub == "restore":
        return (None if "--staged" in flags and "--worktree" not in flags else paths), True
    if sub == "checkout":
        return (paths[1:] if paths and "--" not in rest else paths), True
    if sub == "reset":
        return ("ALL" if "--hard" in flags else None), True
    return None, False


def _targets(verb, args):
    """返回这条命令会破坏的路径参数；[] 表示带路径但不破坏，None 表示不是破坏性动词，"PIPE" 表示要用管道上游的路径。"""
    flags = _flags(args)
    lowered = [a.lower() for a in args]
    if verb == "new-item":
        if "-force" not in flags or "directory" in lowered:
            return None  # 对已存在目录 -Force 不清空内容
        return _path_args(args) or None
    if verb == "sed":
        if not any(f.startswith("-i") or f.startswith("--in-place") for f in flags):
            return None
        return _path_args(args)[1:]  # 第一个非选项参数是 sed 脚本
    if verb == "tee":
        return _path_args(args) or None  # 不带文件参数时只写 stdout
    if verb in WRITE_ALL:
        return _path_args(args, cmd_style=verb in ("rd", "del", "erase", "move")) or "PIPE"
    if verb in COPY:
        for i, a in enumerate(lowered):
            if a in ("-t", "--target-directory", "-destination") and i + 1 < len(args):
                return [args[i + 1]]
        paths = _path_args(args, cmd_style=verb == "copy")
        return paths[-1:] if len(paths) >= 2 else []
    if verb == "robocopy":
        paths = _path_args(args, cmd_style=True)
        return paths[1:2]
    if verb == "find":
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


def _unwrap(words):
    """剥掉 sudo -u x / env -i X=1 / xargs -0 -n1 / timeout 10 / cmd /c 这类前缀。"""
    while words:
        w = _verb(words[0])
        if w in WRAPPERS or re.match(r"^[A-Za-z_]\w*=", words[0]):
            words = words[1:]
        elif w in WRAPPERS_WITH_OPTS:
            words = words[1:]
            while words and (words[0].startswith("-") or re.match(r"^[A-Za-z_]\w*=", words[0])
                             or (w == "timeout" and re.match(r"^\d", words[0]))):
                opt = words[0]
                words = words[1:]
                if opt in OPT_WITH_VALUE and words:
                    words = words[1:]
        else:
            break
    return words


def _check(command, cwd, protected):
    tokens = _tokens(command)
    cur = cwd
    hits = []
    upstream = []  # 当前管道里最近一个带路径参数的上游命令的路径
    piped = False
    cmd = []

    def add(paths, tracked_only=False):
        for a in paths:
            for key in _hits(_resolve(a, cur), protected):
                if not tracked_only or _has_tracked(protected[key][1], protected[key][0]):
                    hits.append(key)

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
        add(redirect_targets)
        cmd = []
        words = _unwrap(words)
        if not words:
            return
        verb, args = _verb(words[0]), words[1:]
        if verb in NESTED_SHELL:
            for i, a in enumerate(args):
                al = a.lower()
                if re.match(r"^-[a-z]*c$", al) or al in ("-command", "/c", "/k"):
                    inner = " ".join(args[i + 1:]) if verb in ("powershell", "pwsh", "cmd") else args[i + 1] if i + 1 < len(args) else ""
                    hits.extend(_check(inner, cur, protected))
                    break
            return
        if verb in CHANGE_DIR:
            dest = _path_args(args)
            cur = _resolve(dest[0], cur) if dest else None
            return
        if verb == "git":
            targets, tracked_only = _git_targets(args)
            if targets == "ALL":
                hits.extend(k for k, (name, root) in protected.items()
                            if not tracked_only or _has_tracked(root, name))
            elif targets:
                add(targets, tracked_only)
        else:
            targets = _targets(verb, args)
            if targets == "PIPE":
                if piped:
                    add(upstream)
            elif targets:
                add(targets)
        if _path_args(args) and not words[0].startswith("$"):  # 脚本块里的 $_.x -gt 0 是表达式，不是上游命令
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
    names = sorted({protected[k][0] for k in _check(command, cwd, protected)})
    if not names:
        return
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                f"data_guard：这条命令会删除、移动或覆盖真实运行数据（{', '.join(names)}），删了无法从 git 恢复，需要用户明确授权。"
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
