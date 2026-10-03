"""PreToolUse(Bash|PowerShell)：拦下反引号会被 shell 静默改写的命令。

本项目文案里反引号标识符很密，这个坑在两种 shell 里都踩过，失效形态相同：内容静默变形，不报错。

bash：双引号串（`python -c "..."`、`git commit -m "..."` 等）与定界符不带引号的 heredoc（<<EOF）里，
反引号会被当成命令替换执行。按引号状态扫描整条命令：单引号串、$'...'、<<'EOF'、转义过的 \\`、
引号外的反引号都放行；双引号里的 $(...) 会开出新的引号上下文，按普通命令继续扫描
（"$(cat <<'EOF' ... EOF)" 放行）。有意做命令替换时用 $(...)。嵌套 shell 的单引号串（bash -c '...'）不展开检查。

PowerShell：反引号是转义符，双引号串 "..." 与 here-string @"..."@ 里的 `n、`t 会变成换行、制表符。
单引号串 '...' 与 @'...'@ 是字面量，放行；引号外的反引号（行尾续行）放行。
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


def _offending_ps(s):
    """PowerShell：返回违规位置描述或 None。"""
    if "`" not in s:
        return None
    i, n = 0, len(s)
    while i < n:
        if s.startswith("@'", i):  # 字面 here-string，结束符 '@ 必须在行首
            m = re.compile(r"^'@", re.M).search(s, i + 2)
            i = n if not m else m.end()
        elif s.startswith('@"', i):
            m = re.compile(r'^"@', re.M).search(s, i + 2)
            body = s[i + 2:m.start() if m else n]
            if "`" in body:
                return "here-string @\"...\"@ "
            i = n if not m else m.end()
        elif s[i] == "'":
            i += 1
            while i < n:
                if s[i] == "'":
                    if s.startswith("''", i):  # '' 是单引号串里的转义单引号
                        i += 2
                        continue
                    break
                i += 1
            i += 1
        elif s[i] == '"':
            i += 1
            while i < n and s[i] != '"':
                if s[i] == "`":
                    return "双引号串"
                i += 1
            i += 1
        elif s.startswith("<#", i):
            end = s.find("#>", i + 2)
            i = n if end < 0 else end + 2
        elif s[i] == "#":
            end = s.find("\n", i)
            i = n if end < 0 else end
        else:
            i += 1
    return None


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    command = (data.get("tool_input") or {}).get("command") or ""
    if data.get("tool_name") == "PowerShell":
        where = _offending_ps(command)
        reason = (
            f"backtick_guard：{where}里有反引号，PowerShell 会把它当转义符（`n 变换行、`t 变制表符），内容会静默变形。"
            "改用单引号串 '...' 或 @'...'@；含反引号的长内容先用 Write 落成 scratchpad 里的文件再读入（commit message 用 -F 文件）。"
        )
    else:
        where = _offending(command)
        reason = (
            f"backtick_guard：{where}里有反引号，bash 会把它当命令替换执行，内容会静默变形。"
            "含反引号的内容先用 Write 落成 scratchpad 里的文件再执行（commit message 用 -F 文件）；"
            "也可以改用单引号串或 <<'EOF'（包在 \"$(cat <<'EOF' ... EOF)\" 里也可以）。确实要做命令替换的，用 $(...)。"
        )
    if not where:
        return
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 守卫自身出错时放行
        print(f"backtick_guard 内部错误，已放行：{e!r}", file=sys.stderr)
