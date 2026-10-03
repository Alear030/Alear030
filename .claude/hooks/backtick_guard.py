"""PreToolUse(Bash)：拦下会被 bash 命令替换吃掉反引号的命令。

双引号串（`python -c "..."`、`git commit -m "..."` 等）与定界符不带引号的 heredoc（<<EOF）里，
反引号会被 bash 当成命令替换执行，内容静默变形。本项目文案里反引号标识符很密，这个坑反复踩过。
这里按引号状态扫描整条命令：单引号串、<<'EOF'、转义过的 \\`、引号外的反引号都放行。
有意做命令替换时用 $(...)。PowerShell 工具不挂本 hook：那边反引号是转义符，是另一回事。
"""

import json
import re
import sys

HEREDOC = re.compile(r"<<(-?)[ \t]*(?:'([^']*)'|\"([^\"]*)\"|\\?([A-Za-z_][\w]*))")


def _offending(command):
    if "`" not in command:
        return None
    i, n = 0, len(command)
    pending = []  # 本行登记、下一行起读正文的 heredoc：(定界符, 是否展开, 是否 <<-)
    while i < n:
        ch = command[i]
        if ch == "\\":
            i += 2
        elif ch == "'":
            end = command.find("'", i + 1)
            i = n if end < 0 else end + 1
        elif ch == '"':
            i += 1
            while i < n and command[i] != '"':
                if command[i] == "\\":
                    i += 1
                elif command[i] == "`":
                    return "双引号串"
                i += 1
            i += 1
        elif ch == "#" and (i == 0 or command[i - 1].isspace()):
            end = command.find("\n", i)
            i = n if end < 0 else end
        elif command.startswith("<<<", i):
            i += 3
        elif command.startswith("<<", i):
            m = HEREDOC.match(command, i)
            if not m:
                i += 2
                continue
            delim = m.group(2) if m.group(2) is not None else m.group(3) if m.group(3) is not None else m.group(4)
            expands = m.group(4) is not None and not command.startswith("\\", m.start(4) - 1)
            pending.append((delim, expands, m.group(1) == "-"))
            i = m.end()
        elif ch == "\n" and pending:
            i += 1
            for delim, expands, dash in pending:
                while i < n:
                    end = command.find("\n", i)
                    line = command[i:] if end < 0 else command[i:end]
                    i = n if end < 0 else end + 1
                    if (line.lstrip("\t") if dash else line) == delim:
                        break
                    if expands and re.search(r"(?<!\\)`", line):
                        return f"定界符未加引号的 heredoc（<<{delim}）"
            pending = []
        else:
            i += 1
    return None


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
                "也可以改用单引号串或 <<'EOF'。确实要做命令替换的，用 $(...)。"
            ),
        }
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 守卫自身出错时放行
        print(f"backtick_guard 内部错误，已放行：{e!r}", file=sys.stderr)
