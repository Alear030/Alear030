"""PreToolUse(Bash)：拦下会被 bash 命令替换吃掉反引号的命令。

双引号串（`python -c "..."`、`git commit -m "..."` 等）与定界符不带引号的 heredoc（<<EOF）里，
反引号会被 bash 当成命令替换执行，内容静默变形。本项目文案里反引号标识符很密，这个坑反复踩过。
这里按引号状态扫描整条命令：单引号串、$'...'、<<'EOF'、转义过的 \\`、引号外的反引号都放行；
双引号里的 $(...) 会开出新的引号上下文，按普通命令继续扫描（"$(cat <<'EOF' ... EOF)" 放行）。
有意做命令替换时用 $(...)。PowerShell 工具不挂本 hook：那边反引号是转义符，是另一回事。
嵌套 shell 的单引号串（bash -c '...'）里的内容不展开检查。
"""

import json
import re
import sys

HEREDOC = re.compile(r"<<(-?)[ \t]*(?:'([^']*)'|\"([^\"]*)\"|\\?([A-Za-z_][\w]*))")
COMMENT_LEAD = " \t\n;&|()"


def _scan(s, i, in_subst):
    """从 i 起按普通上下文扫描；in_subst 时遇到配对的 ) 返回。返回 (违规位置描述或 None, 结束下标)。"""
    n, depth, pending = len(s), 0, []
    while i < n:
        ch = s[i]
        if ch == "\\":
            i += 2
        elif s.startswith("$'", i):
            i += 2
            while i < n and s[i] != "'":
                i += 2 if s[i] == "\\" else 1
            i += 1
        elif ch == "'":
            end = s.find("'", i + 1)
            i = n if end < 0 else end + 1
        elif ch == '"':
            i += 1
            while i < n and s[i] != '"':
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == "`":
                    return "双引号串", i
                if s.startswith("$(", i):
                    where, i = _scan(s, i + 2, True)
                    if where:
                        return where, i
                    continue
                i += 1
            i += 1
        elif s.startswith("$(", i):
            where, i = _scan(s, i + 2, True)
            if where:
                return where, i
        elif ch == "#" and (i == 0 or s[i - 1] in COMMENT_LEAD):
            end = s.find("\n", i)
            i = n if end < 0 else end
        elif s.startswith("<<<", i):
            i += 3
        elif s.startswith("<<", i):
            m = HEREDOC.match(s, i)
            if not m:
                i += 2
                continue
            delim = next(g for g in m.groups()[1:] if g is not None)
            expands = m.group(4) is not None and s[m.start(4) - 1] != "\\"
            pending.append((delim, expands, m.group(1) == "-"))
            i = m.end()
        elif ch == "\n" and pending:
            i += 1
            for delim, expands, dash in pending:
                while i < n:
                    end = s.find("\n", i)
                    line = s[i:] if end < 0 else s[i:end]
                    i = n if end < 0 else end + 1
                    if (line.lstrip("\t") if dash else line) == delim:
                        break
                    if expands and re.search(r"(?<!\\)`", line):
                        return f"定界符未加引号的 heredoc（<<{delim}）", i
            pending = []
        elif in_subst and ch == "(":
            depth += 1
            i += 1
        elif in_subst and ch == ")":
            if depth == 0:
                return None, i + 1
            depth -= 1
            i += 1
        else:
            i += 1
    return None, i


def _offending(command):
    if "`" not in command:
        return None
    return _scan(command, 0, False)[0]


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    command = (data.get("tool_input") or {}).get("command") or ""
    where = _offending(command)
    if not where:
        return
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"backtick_guard：{where}里有反引号，bash 会把它当命令替换执行，内容会静默变形。"
                "含反引号的内容先用 Write 落成 scratchpad 里的文件再执行（commit message 用 -F 文件）；"
                "也可以改用单引号串或 <<'EOF'（包在 \"$(cat <<'EOF' ... EOF)\" 里也可以）。确实要做命令替换的，用 $(...)。"
            ),
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 守卫自身出错时放行
        print(f"backtick_guard 内部错误，已放行：{e!r}", file=sys.stderr)
