"""
命令安全层
=============================================

安全模型（默认放行，拦截不可逆操作）:
  早期是白名单准入——"不在知识库里的不许做"。实测该模型两头不讨好：
  真实会话 49 次调用里误伤 12 次（git -C、npm --prefix、netstat -ano 全被拒），
  而 `&` 之后的命令从不经过校验，白名单本身可被绕过。
  故翻转为：绝大多数命令放行，只硬拒不可逆且难以人工挽回的操作。
  威胁模型是"防模型手滑"，不是"防人类对手蓄意绕过"。

  COMMAND_WHITELIST 保留，但降级为分类表：命中沿用其 read/write/neutral 类别，
  未命中标 unknown 并照常执行。

校验流程（每条子命令各走一遍）:
  第0层: 分段 —— 按引号外的 && || & ; | 切开，逐段校验，杜绝分隔符绕过
  第1层: 重定向 —— 算子放行，目标路径按写操作校验
  第2层: 不可逆命令 —— format/diskpart/shutdown 等直接拒
  第3层: 分类 —— 查 COMMAND_WHITELIST 定类别，未登记为 unknown
  第4层: 子命令分类 —— git/pip/npm 子命令细分只读/写入/破坏性
  第5层: 危险路径 —— 写操作不能落在 /、~、/etc、C:\\Windows 等
  第6层: 注入检测 —— $()、``、${}、换行、ANSI-C 引用、$IFS
  第7层: 不可逆模式 —— rm -rf、del /s、git reset --hard、curl|bash 等硬拒
  第8层: 高风险警告 —— git push --force 等只提示不拦
"""

import re
import os
from dataclasses import dataclass, field
import threading

from typing import Optional, Callable

# ============================================================
#  flag 参数类型
# ============================================================
FlagArgType = str  # 'none' | 'number' | 'string' | 'path' | 'EOF' | '{}'


@dataclass
class CommandConfig:
    """单个命令的安全配置"""
    name: str
    safe_flags: dict[str, FlagArgType] = field(default_factory=dict)
    category: str = 'neutral'
    respects_double_dash: bool = True
    # 返回 None 放行，返回字符串即拒绝原因。原先只返回 bool，调用方只能吐笼统的
    # "未通过额外安全检查"，模型不知道该怎么改；日志显示它确实会照 reason 换写法。
    additional_check: Optional[Callable[[str, list[str]], Optional[str]]] = None
    regex: Optional[str] = None


# ============================================================
#  逐命令 flag 白名单
# ============================================================
# 设计原则:
#   1. 只列出"安全的" flag，不在列表里的 → 拒绝
#   2. 每个 flag 声明参数类型，防止参数注入
#   3. 故意排除危险 flag，注释说明原因
#   4. 合并短flag自动展开（-la → -l -a）

COMMAND_WHITELIST: dict[str, CommandConfig] = {

    # ═══════════════════════════════════════════════════════
    #  文件列表/搜索类（只读）
    # ═══════════════════════════════════════════════════════
    "ls": CommandConfig(
        name="ls", category="read",
        safe_flags={
            "-l": "none", "-a": "none", "-A": "none", "-h": "none",
            "-R": "none", "-r": "none", "-t": "none", "-S": "none",
            "-1": "none", "-F": "none", "-G": "none", "-i": "none",
            "-d": "none", "-L": "none", "-p": "none", "-s": "none",
            "-n": "none", "-g": "none", "-o": "none", "-k": "none",
            "-q": "none", "-u": "none", "-c": "none", "-U": "none",
            "-X": "none", "-B": "none", "-m": "none", "-w": "none",
            "--help": "none", "--version": "none",
            "--color": "string", "--format": "string",
            "--sort": "string", "--time": "string",
            "--group-directories-first": "none",
            "--ignore": "string", "--hide": "string",
            "--indicator-style": "string", "--quoting-style": "string",
        },
    ),
    "dir": CommandConfig(
        name="dir", category="read",
        safe_flags={
            "/A": "string", "/B": "none", "/C": "none", "/D": "none",
            "/L": "none", "/N": "none", "/O": "string", "/P": "none",
            "/Q": "none", "/R": "none", "/S": "none", "/T": "string",
            "/W": "none", "/X": "none", "/?": "none",
        },
    ),

    # ═══════════════════════════════════════════════════════
    #  文件内容查看（只读）
    # ═══════════════════════════════════════════════════════
    "cat": CommandConfig(
        name="cat", category="read",
        safe_flags={
            "-n": "none", "-b": "none", "-s": "none", "-v": "none",
            "-E": "none", "-T": "none", "-A": "none", "-e": "none",
            "-t": "none", "--help": "none", "--version": "none",
        },
    ),
    "head": CommandConfig(
        name="head", category="read",
        safe_flags={
            "-n": "number", "-c": "number", "-q": "none", "-v": "none",
            "--help": "none", "--version": "none",
        },
    ),
    "tail": CommandConfig(
        name="tail", category="read",
        safe_flags={
            "-n": "number", "-c": "number", "-f": "none", "-F": "none",
            "-q": "none", "-v": "none", "-r": "none",
            "--help": "none", "--version": "none",
        },
    ),
    "type": CommandConfig(name="type", category="read", safe_flags={}),
    "more": CommandConfig(name="more", category="read", safe_flags={}),

    # ═══════════════════════════════════════════════════════
    #  文本搜索（只读）
    # ═══════════════════════════════════════════════════════
    "grep": CommandConfig(
        name="grep", category="read",
        safe_flags={
            "-i": "none", "-v": "none", "-c": "none", "-l": "none",
            "-L": "none", "-n": "none", "-H": "none", "-h": "none",
            "-r": "none", "-R": "none", "-w": "none", "-x": "none",
            "-o": "none", "-q": "none", "-s": "none", "-E": "none",
            "-F": "none", "-G": "none", "-P": "none",
            "-A": "number", "-B": "number", "-C": "number", "-m": "number",
            "-e": "string", "-f": "string",
            "--color": "string", "--help": "none", "--version": "none",
            "--line-number": "none", "--with-filename": "none",
            "--no-filename": "none", "--only-matching": "none",
            "--extended-regexp": "none", "--fixed-strings": "none",
            "--perl-regexp": "none", "--ignore-case": "none",
            "--invert-match": "none", "--word-regexp": "none",
            "--line-regexp": "none", "--count": "none",
            "--files-with-matches": "none", "--files-without-match": "none",
            "--max-count": "number", "--context": "number",
            "--after-context": "number", "--before-context": "number",
            "--exclude": "string", "--exclude-dir": "string",
            "--include": "string", "--recursive": "none",
        },
    ),
    "findstr": CommandConfig(
        name="findstr", category="read",
        safe_flags={
            "/B": "none", "/E": "none", "/L": "none", "/R": "none",
            "/S": "none", "/I": "none", "/X": "none", "/V": "none",
            "/N": "none", "/M": "none", "/O": "none", "/P": "none",
            "/C": "string", "/D": "string", "/A": "string", "/?": "none",
        },
    ),

    # ═══════════════════════════════════════════════════════
    #  文件查找（只读）
    # ═══════════════════════════════════════════════════════
    "find": CommandConfig(
        name="find", category="read",
        safe_flags={
            "-name": "string", "-iname": "string",
            "-type": "string", "-size": "string",
            "-maxdepth": "number", "-mindepth": "number",
            "-mtime": "string", "-atime": "string", "-ctime": "string",
            "-user": "string", "-group": "string",
            "-perm": "string", "-empty": "none",
            "-print": "none", "-print0": "none", "-ls": "none",
            "-path": "string", "-ipath": "string",
            "-regex": "string", "-iregex": "string",
            "-newer": "string", "-anewer": "string", "-cnewer": "string",
            "-links": "string", "-inum": "string",
            # 故意排除: -exec, -execdir, -ok, -okdir (执行任意命令)
            # 故意排除: -delete (删除文件)
            # 故意排除: -fprint, -fprint0, -fls (写入文件)
        },
    ),
    "where": CommandConfig(
        name="where", category="read",
        safe_flags={"/R": "none", "/Q": "none", "/F": "none", "/T": "none", "/?": "none"},
    ),
    "which": CommandConfig(
        name="which", category="read",
        safe_flags={"-a": "none", "--help": "none", "--version": "none"},
    ),

    # ═══════════════════════════════════════════════════════
    #  文件信息（只读）
    # ═══════════════════════════════════════════════════════
    "file": CommandConfig(
        name="file", category="read",
        safe_flags={
            "-b": "none", "-i": "none", "-z": "none", "-L": "none",
            "-h": "none", "-k": "none", "-m": "string", "-f": "string",
            "--help": "none", "--version": "none",
            "--mime": "none", "--mime-type": "none", "--mime-encoding": "none",
        },
    ),
    "wc": CommandConfig(
        name="wc", category="read",
        safe_flags={
            "-c": "none", "-l": "none", "-w": "none", "-m": "none",
            "-L": "none", "--help": "none", "--version": "none",
        },
    ),
    "stat": CommandConfig(
        name="stat", category="read",
        safe_flags={
            "-L": "none", "-f": "string", "-t": "string",
            "-c": "string", "--help": "none", "--version": "none",
        },
    ),
    "du": CommandConfig(
        name="du", category="read",
        safe_flags={
            "-h": "none", "-s": "none", "-a": "none", "-c": "none",
            "-d": "number", "--max-depth": "number",
            "-k": "none", "-m": "none", "-L": "none",
            "--help": "none", "--version": "none",
            "--apparent-size": "none", "--exclude": "string",
            "--threshold": "string", "--time": "none",
        },
    ),
    "df": CommandConfig(
        name="df", category="read",
        safe_flags={
            "-h": "none", "-H": "none", "-k": "none", "-m": "none",
            "-T": "none", "-t": "string", "-l": "none", "-i": "none",
            "--help": "none", "--version": "none",
            "--total": "none", "--output": "string",
        },
    ),

    # ═══════════════════════════════════════════════════════
    #  进程/系统信息（只读）
    # ═══════════════════════════════════════════════════════
    "ps": CommandConfig(
        name="ps", category="read",
        safe_flags={
            "-e": "none", "-A": "none", "-a": "none", "-u": "string",
            "-x": "none", "-f": "none", "-l": "none", "-j": "none",
            "-o": "string", "-p": "string", "-t": "string",
            "-w": "none", "-H": "none", "-L": "none",
            "-C": "string", "-G": "string", "-g": "string",
            "-U": "string", "-s": "string",
            "--help": "none", "--version": "none",
            "--pid": "string", "--user": "string",
            "--sort": "string", "--forest": "none",
            "--headers": "none", "--no-headers": "none",
            # 故意排除: BSD风格 'e' 修饰符（泄露环境变量）
        },
        additional_check=lambda cmd, args: _check_bsd_ps_e(args),
    ),
    "top": CommandConfig(
        name="top", category="read",
        safe_flags={
            "-b": "none", "-n": "number", "-d": "number",
            "-p": "string", "-H": "none", "-c": "none",
            "-o": "string", "-u": "string",
        },
    ),
    "tasklist": CommandConfig(
        name="tasklist", category="read",
        safe_flags={
            "/S": "string", "/U": "string", "/P": "string",
            "/M": "string", "/FI": "string", "/FO": "string",
            "/NH": "none", "/V": "none", "/?": "none",
        },
    ),
    "netstat": CommandConfig(
        name="netstat", category="read",
        safe_flags={
            "-a": "none", "-n": "none", "-p": "string",
            "-t": "none", "-u": "none", "-l": "none", "-s": "none",
            "-r": "none", "-i": "none", "-g": "none",
            "--help": "none", "--version": "none",
        },
    ),
    "systeminfo": CommandConfig(name="systeminfo", category="read", safe_flags={"/FO": "string", "/NH": "none", "/?": "none"}),
    "wmic": CommandConfig(
        name="wmic", category="read", safe_flags={},
        # wmic 非 flag 式语法，逐 flag 白名单不适用，改用 additional_check 的动词/开关黑名单
        # (/format 按取值判定，内置格式名放行、指向文件或 URL 的 XSL 拒绝)
        additional_check=lambda cmd, args: _check_wmic_safe(cmd, args),
    ),
    "nvidia-smi": CommandConfig(
        name="nvidia-smi", category="read",
        safe_flags={
            "-L": "none", "--list-gpus": "none",
            "--query-gpu": "string", "--format": "string",
            "-q": "none", "--query": "none",
            "--help": "none", "-h": "none", "--version": "none", "-v": "none",
        },
    ),

    # ═══════════════════════════════════════════════════════
    #  网络（只读）
    # ═══════════════════════════════════════════════════════
    "ping": CommandConfig(
        name="ping", category="read",
        safe_flags={
            "-n": "number", "-c": "number", "-t": "none",
            "-w": "number", "-i": "number", "-4": "none", "-6": "none",
            "--help": "none", "--version": "none",
        },
    ),
    "curl": CommandConfig(
        name="curl", category="read",
        safe_flags={
            "-I": "none", "-i": "none", "-v": "none", "-s": "none",
            "-L": "none", "-f": "none", "-o": "path", "-O": "none",
            "-H": "string", "-X": "string", "-u": "string",
            "-d": "string", "--data": "string",
            "--help": "none", "--version": "none",
        },
    ),
    "wget": CommandConfig(
        name="wget", category="read",
        safe_flags={
            "-O": "path", "-q": "none", "-nv": "none", "-c": "none",
            "-t": "number", "--help": "none", "--version": "none",
        },
    ),

    # ═══════════════════════════════════════════════════════
    #  Git
    # ═══════════════════════════════════════════════════════
    "git": CommandConfig(
        name="git", category="neutral",
        safe_flags={
            "--help": "none", "--version": "none", "-C": "path",
            "-c": "string", "--no-pager": "none",
            "--oneline": "none", "--graph": "none", "--decorate": "none",
            "--all": "none", "--stat": "none", "--patch": "none",
            "--name-only": "none", "--name-status": "none",
            "--format": "string", "--pretty": "string",
            "--author": "string", "--since": "string", "--until": "string",
            "--grep": "string", "--max-count": "number", "-n": "number",
            "--force": "none", "--force-with-lease": "none",
            "--set-upstream": "none", "-u": "none",
            "--dry-run": "none", "--tags": "none", "--branches": "none",
            "--remotes": "none", "--delete": "none", "-d": "none", "-D": "none",
            "--hard": "none", "--soft": "none", "--mixed": "none",
            "--cached": "none", "--staged": "none",
            "--amend": "none", "--no-edit": "none",
            "--no-verify": "none", "--no-gpg-sign": "none",
            "--rebase": "none", "--merge": "none", "--ff": "none",
            "--no-ff": "none", "--squash": "none",
            "--interactive": "none", "-i": "none",
            "--continue": "none", "--abort": "none", "--skip": "none",
            "--orphan": "string", "-b": "string", "-m": "string",
            "--message": "string", "--file": "string",
            "--depth": "number", "--shallow-since": "string",
            "--quiet": "none", "-q": "none", "--verbose": "none", "-v": "none",
            "--short": "none", "--porcelain": "none",
            "--abbrev": "number", "--no-abbrev": "none",
            "--diff-filter": "string", "--follow": "none",
            "--find-copies": "none", "--find-renames": "none",
            "--ignore-space-change": "none", "--ignore-all-space": "none",
            "--word-diff": "none", "--color-words": "none",
            "--check": "none", "--exit-code": "none",
            "--no-color": "none", "--color": "string",
            "--relative": "none", "--no-relative": "none",
            "--text": "none", "--binary": "none",
            "--full-index": "none", "--src-prefix": "string",
            "--dst-prefix": "string", "--output": "string",
            "--no-renames": "none", "--minimal": "none",
            "--patience": "none", "--histogram": "none",
            "--anchored": "string", "--diff-algorithm": "string",
            "--ignore-submodules": "string",
            "--submodule": "string", "--no-ext-diff": "none",
            "--textconv": "none", "--no-textconv": "none",
            "--ignore-cr-at-eol": "none",
            "--function-context": "none", "-W": "none",
            "--raw": "none", "--patch-with-raw": "none",
            "--numstat": "none", "--shortstat": "none",
            "--dirstat": "string", "--cumulative": "none",
            "--summary": "none", "--name-only-tags": "none",
            "--committer-date-is-author-date": "none",
            "--ignore-date": "none", "--reset-author": "none",
            "--signoff": "none", "--no-signoff": "none",
            "--allow-empty": "none", "--allow-empty-message": "none",
            "--cleanup": "string", "--date": "string",
            "--local": "none", "--global": "none", "--system": "none",
            "--list": "none", "--unset": "none", "--unset-all": "none",
            "--get": "none", "--get-all": "none", "--get-regexp": "none",
            "--get-urlmatch": "string", "--replace-all": "none",
            "--add": "none", "--remove-section": "none",
            "--rename-section": "none", "--fixed-value": "none",
            "--includes": "none", "--no-includes": "none",
            "--null": "none", "-z": "none", "--name-only-tags": "none",
            "--type": "string", "--bool": "none", "--int": "none",
            "--bool-or-int": "none", "--path": "none", "--expiry-date": "none",
            "--show-origin": "none", "--show-scope": "none",
            "--default": "string", "--edit": "none", "--no-replace-objects": "none",
            "--literal-pathspecs": "none", "--glob-pathspecs": "none",
            "--noglob-pathspecs": "none", "--icase-pathspecs": "none",
            "--sparse": "none", "--no-sparse": "none",
            "--full-tree": "none", "--full-history": "none",
            "--dense": "none", "--sparse": "none",
            "--simplify-merges": "none", "--simplify-by-decoration": "none",
            "--branches": "none", "--tags": "none", "--remotes": "none",
            "--glob": "string", "--exclude": "string",
            "--reflog": "none", "--single-worktree": "none",
            "--walk-reflogs": "none", "--merge-base": "none",
            "--independent": "none", "--is-ancestor": "none",
            "--fork-point": "none", "--boundary": "none",
            "--use-bitmap-index": "none", "--no-use-bitmap-index": "none",
            "--progress": "none", "--no-progress": "none",
            "--missing": "string", "--exclude-promisor-objects": "none",
            "--filter": "string", "--no-filter": "none",
            "--recurse-submodules": "string",
            "--no-recurse-submodules": "none",
            "--shallow-exclude": "string",
            "--shallow-since": "string",
            "--deepen": "number", "--shallow-since": "string",
            "--unshallow": "none", "--update-shallow": "none",
            "--refmap": "string", "--ipv4": "none", "--ipv6": "none",
            "--negotiation-tip": "string",
            "--negotiate-only": "none",
            "--dry-run": "none", "--porcelain": "none",
            "--prune": "none", "--no-prune": "none",
            "--track": "none", "--no-track": "none",
            "--set-upstream-to": "string",
            "--unset-upstream": "none",
            "--detach": "none", "--guess": "none", "--no-guess": "none",
            "--overlay": "none", "--no-overlay": "none",
            "--conflict": "string", "--rerere-autoupdate": "none",
            "--no-rerere-autoupdate": "none",
            "--autostash": "none", "--no-autostash": "none",
            "--gpg-sign": "string", "--no-gpg-sign": "none",
            "--strategy": "string", "--strategy-option": "string",
            "--verify-signatures": "none", "--no-verify-signatures": "none",
            "--summary": "none", "--no-summary": "none",
            "--log": "string", "--no-log": "none",
            "--first-parent": "none", "--no-first-parent": "none",
            "--cherry-pick": "none", "--no-cherry-pick": "none",
            "--left-only": "none", "--right-only": "none",
            "--cherry": "none", "--no-cherry": "none",
            "--merges": "none", "--no-merges": "none",
            "--min-parents": "number", "--max-parents": "number",
            "--no-min-parents": "none", "--no-max-parents": "none",
            "--since": "string", "--after": "string",
            "--until": "string", "--before": "string",
            "--author": "string", "--committer": "string",
            "--grep-reflog": "string", "--regexp-ignore-case": "none",
            "--basic-regexp": "none", "--extended-regexp": "none",
            "--fixed-strings": "none", "--perl-regexp": "none",
            "--remove-empty": "none", "--no-remove-empty": "none",
            "--topo-order": "none", "--date-order": "none",
            "--author-date-order": "none", "--reverse": "none",
            "--do-walk": "none", "--no-walk": "none",
            "--show-linear-break": "none", "--show-notes": "string",
            "--no-notes": "none", "--standard-notes": "none",
            "--no-standard-notes": "none", "--show-signature": "none",
            "--relative-date": "none", "--date": "string",
            "--parents": "none", "--children": "none",
            "--left-right": "none", "--cherry-mark": "none",
            "--skip": "number", "--max-count": "number",
            "--header": "none", "--no-header": "none",
            "--commit-header": "none", "--no-commit-header": "none",
            "--expand-tabs": "number", "--no-expand-tabs": "none",
            "--expand-tabs": "none", "--tab-size": "number",
            "--show-email": "none", "--no-show-email": "none",
            "--abbrev-commit": "none", "--no-abbrev-commit": "none",
            "--full-diff": "none", "--no-full-diff": "none",
            "--stat": "string", "--compact-summary": "none",
            "--no-compact-summary": "none",
            "--ext-diff": "none", "--no-ext-diff": "none",
            "--textconv": "none", "--no-textconv": "none",
            "--ignore-submodules": "string",
            "--ignore-all-space": "none",
            "--ignore-blank-lines": "none",
            "--inter-hunk-context": "number",
            "-U": "number", "--unified": "number",
            "--output-indicator-new": "string",
            "--output-indicator-old": "string",
            "--output-indicator-context": "string",
            "--ws-error-highlight": "string",
            "--ita-invisible-in-index": "none",
            "--ita-visible-in-index": "none",
            "--staged": "none", "--worktree": "none",
            "--untracked-files": "string",
            "--ignore-submodules": "string",
            "--ignored": "string", "--no-ignored": "none",
            "--column": "string", "--no-column": "none",
            "--sort": "string", "--show-stash": "none",
            "--no-show-stash": "none",
            "--show-current": "string", "--no-show-current": "none",
            "--points-at": "string", "--merged": "string",
            "--no-merged": "string", "--contains": "string",
            "--no-contains": "string",
            "--format": "string", "--branches": "none",
            "--remotes": "none", "--tags": "none",
            "--upload-pack": "string", "--receive-pack": "string",
            "--exec": "string", "--server-option": "string",
            "--thin": "none", "--no-thin": "none",
            "--keep": "none", "--no-keep": "none",
            "--recurse-submodules": "string",
            "--jobs": "number", "-j": "number",
            "--atomic": "none", "--no-atomic": "none",
            "--mirror": "string", "--no-mirror": "none",
            "--push-option": "string", "-o": "string",
            "--signed": "none", "--no-signed": "none",
            "--follow-tags": "none", "--no-follow-tags": "none",
            "--verify": "none", "--no-verify": "none",
            "--prune": "none", "--no-prune": "none",
            "--porcelain": "none", "--progress": "none",
            "--check-self-contained-and-connected": "none",
            "--no-check-self-contained-and-connected": "none",
            "--auto-maintenance": "none", "--no-auto-maintenance": "none",
            "--write-commit-graph": "none", "--no-write-commit-graph": "none",
            "--prefetch": "none", "--no-prefetch": "none",
            "--show-forced-updates": "none", "--no-show-forced-updates": "none",
            "--set-upstream": "none", "--no-set-upstream": "none",
            "--force-with-lease": "string", "--force-if-includes": "none",
            "--delete": "none", "--prune": "none",
            "--no-recurse-submodules": "none",
            "--recurse-submodules": "string",
            "--on-demand": "none", "--no-on-demand": "none",
            "--all": "none", "--append": "none", "--no-append": "none",
            "--mirror": "none", "--no-mirror": "none",
            "--dissociate": "none", "--no-dissociate": "none",
            "--single-branch": "none", "--no-single-branch": "none",
            "--no-tags": "none", "--recurse-submodules": "string",
            "--no-recurse-submodules": "none",
            "--shallow-submodules": "none", "--no-shallow-submodules": "none",
            "--remote-submodules": "none", "--no-remote-submodules": "none",
            "--separate-git-dir": "string",
            "--reference": "string", "--reference-if-able": "string",
            "--config": "string", "--template": "string",
            "--bare": "none", "--no-bare": "none",
            "--sparse": "none", "--no-sparse": "none",
            "--filter": "string", "--no-filter": "none",
            "--also-filter-submodules": "none",
            "--no-also-filter-submodules": "none",
            "--branch": "string", "-b": "string",
            "--quiet": "none", "-q": "none",
            "--verbose": "none", "-v": "none",
            "--progress": "none", "--no-progress": "none",
            "--origin": "string", "-o": "string",
            "--depth": "number",
            "--shallow-since": "string",
            "--shallow-exclude": "string",
            "--no-checkout": "none", "--no-hardlinks": "none",
            "--shared": "none", "--no-shared": "none",
            "--local": "none", "--no-local": "none",
            "--no-recurse-submodules": "none",
            "--recurse-submodules": "string",
            "--jobs": "number",
            "--server-option": "string",
            "--ipv4": "none", "--ipv6": "none",
            "--negotiation-tip": "string",
            "--negotiate-only": "none",
            "--update-head-ok": "none", "--no-update-head-ok": "none",
            "--push-option": "string",
            "--signed": "none", "--no-signed": "none",
            "--force": "none", "-f": "none",
            "--force-with-lease": "string",
            "--force-if-includes": "none",
            "--delete": "none",
            "--prune": "none",
            "--no-verify": "none",
            "--dry-run": "none", "-n": "none",
            "--porcelain": "none",
            "--progress": "none",
            "--set-upstream": "none", "-u": "none",
            "--set-upstream-to": "string",
            "--unset-upstream": "none",
            "--push-option": "string", "-o": "string",
            "--receive-pack": "string",
            "--exec": "string",
            "--thin": "none", "--no-thin": "none",
            "--atomic": "none", "--no-atomic": "none",
            "--follow-tags": "none", "--no-follow-tags": "none",
            "--signed": "none", "--no-signed": "none",
            "--mirror": "none", "--no-mirror": "none",
            "--all": "none", "--branches": "none",
            "--tags": "none",
            "--prune": "none", "--no-prune": "none",
            "--dry-run": "none",
            "--porcelain": "none",
            "--prune-tags": "none", "--no-prune-tags": "none",
            "--auto-maintenance": "none", "--no-auto-maintenance": "none",
            "--write-commit-graph": "none", "--no-write-commit-graph": "none",
            "--prefetch": "none", "--no-prefetch": "none",
            "--show-forced-updates": "none", "--no-show-forced-updates": "none",
            "--check-self-contained-and-connected": "none",
            "--no-check-self-contained-and-connected": "none",
            "--recurse-submodules": "string",
            "--no-recurse-submodules": "none",
            "--on-demand": "none", "--no-on-demand": "none",
            "--server-option": "string",
            "--ipv4": "none", "--ipv6": "none",
            "--negotiation-tip": "string",
            "--negotiate-only": "none",
        },
    ),

    # ═══════════════════════════════════════════════════════
    #  开发工具
    # ═══════════════════════════════════════════════════════
    "python": CommandConfig(
        name="python", category="neutral",
        safe_flags={
            "-c": "string", "-m": "string", "-V": "none",
            "--version": "none", "-h": "none", "--help": "none",
            "-v": "none", "-vv": "none", "-q": "none",
            "-B": "none", "-E": "none", "-I": "none",
            "-O": "none", "-OO": "none", "-s": "none",
            "-S": "none", "-u": "none", "-W": "string",
            "-X": "string", "-i": "none",
        },
    ),
    "python3": CommandConfig(
        name="python3", category="neutral",
        safe_flags={
            "-c": "string", "-m": "string", "-V": "none",
            "--version": "none", "-h": "none", "--help": "none",
            "-v": "none", "-q": "none", "-B": "none", "-E": "none",
            "-I": "none", "-O": "none", "-s": "none", "-S": "none",
            "-u": "none", "-W": "string", "-X": "string",
        },
    ),
    "pip": CommandConfig(
        name="pip", category="write",
        safe_flags={
            "list": "none", "show": "string", "freeze": "none",
            "search": "string", "check": "none",
            "--help": "none", "--version": "none", "-V": "none",
            "--outdated": "none", "--format": "string",
            "--exclude": "string", "--include": "string",
            "--no-index": "none", "--index-url": "string",
            "--extra-index-url": "string", "--proxy": "string",
            "--retries": "number", "--timeout": "number",
            "--exists-action": "string", "--trusted-host": "string",
            "--cert": "string", "--client-cert": "string",
            "--cache-dir": "string", "--no-cache-dir": "none",
            "--disable-pip-version-check": "none",
            "--no-color": "none", "--no-python-version-warning": "none",
            "--use-feature": "string", "--use-deprecated": "string",
        },
    ),
    "node": CommandConfig(
        name="node", category="neutral",
        safe_flags={
            "-e": "string", "-p": "string", "-v": "none",
            "--version": "none", "-h": "none", "--help": "none",
            "--check": "none", "--eval": "string", "--print": "string",
            "--require": "string", "--inspect": "none",
            "--inspect-brk": "none", "--no-warnings": "none",
            "--trace-warnings": "none", "--redirect-warnings": "string",
            "--trace-sync-io": "none", "--trace-event-categories": "string",
            "--max-old-space-size": "number", "--max-semi-space-size": "number",
            "--expose-gc": "none", "--harmony": "none",
            "--prof": "none", "--prof-process": "none",
            "--zero-fill-buffers": "none", "--v8-options": "none",
            "--tls-min-v1.0": "none", "--tls-min-v1.1": "none",
            "--tls-min-v1.2": "none", "--tls-min-v1.3": "none",
            "--enable-source-maps": "none",
            "--experimental-modules": "none",
            "--experimental-vm-modules": "none",
            "--experimental-worker": "none",
            "--experimental-repl-await": "none",
            "--experimental-json-modules": "none",
            "--experimental-wasm-modules": "none",
            "--experimental-policy": "string",
            "--icu-data-dir": "string",
            "--preserve-symlinks": "none",
            "--preserve-symlinks-main": "none",
            "--input-type": "string",
            "--experimental-specifier-resolution": "string",
            "--experimental-loader": "string",
            "--title": "string",
        },
    ),
    "npm": CommandConfig(
        name="npm", category="write",
        safe_flags={
            "list": "none", "ls": "none", "view": "string",
            "outdated": "none", "audit": "none",
            "--help": "none", "--version": "none", "-v": "none",
            "--global": "none", "-g": "none",
            "--depth": "number", "--json": "none",
            "--parseable": "none", "--long": "none",
            "--silent": "none", "--quiet": "none",
            "--loglevel": "string", "--color": "string",
            "--no-color": "none", "--unicode": "none",
            "--no-unicode": "none",
        },
    ),

    # ═══════════════════════════════════════════════════════
    #  其他只读/中性命令
    # ═══════════════════════════════════════════════════════
    "echo": CommandConfig(name="echo", category="neutral", safe_flags={"-n": "none", "-e": "none", "-E": "none"}),
    "printf": CommandConfig(name="printf", category="neutral", safe_flags={"-v": "string"}),
    "date": CommandConfig(
        name="date", category="read",
        safe_flags={
            "-u": "none", "-R": "none", "-I": "none",
            "-d": "string", "-r": "string",
            "--date": "string", "--reference": "string",
            "--utc": "none", "--universal": "none",
            "--iso-8601": "string", "--rfc-email": "none",
            "--rfc-3339": "string", "--debug": "none",
            "--help": "none", "--version": "none",
            # 故意排除: -s/--set (设置系统时间)
            # 故意排除: -f/--file (批量设置时间)
        },
        additional_check=lambda cmd, args: _check_date_positional(args),
    ),
    "time": CommandConfig(name="time", category="read", safe_flags={"-p": "none", "--help": "none"}),
    "env": CommandConfig(name="env", category="read", safe_flags={"-i": "none", "-0": "none", "--help": "none"}),
    "printenv": CommandConfig(name="printenv", category="read", safe_flags={"-0": "none", "--help": "none"}),
    "pwd": CommandConfig(name="pwd", category="read", safe_flags={"-L": "none", "-P": "none", "--help": "none"}),
    "hostname": CommandConfig(
        name="hostname", category="read",
        safe_flags={
            "-f": "none", "-s": "none", "-i": "none", "-I": "none",
            "-a": "none", "-d": "none", "-A": "none",
            "--fqdn": "none", "--short": "none",
            "--ip-address": "none", "--all-ip-addresses": "none",
            "--alias": "none", "--domain": "none", "--all-fqdns": "none",
            "--help": "none", "--version": "none",
            # 故意排除: 位置参数（会设置hostname）
            # 故意排除: -F/--file, -b/--boot
        },
        regex=r"^hostname(?:\s+(?:-[a-zA-Z]|--[a-zA-Z-]+))*\s*$",
    ),
    "uname": CommandConfig(name="uname", category="read", safe_flags={"-a": "none", "-s": "none", "-n": "none", "-r": "none", "-m": "none", "--help": "none"}),
    "tree": CommandConfig(
        name="tree", category="read",
        safe_flags={
            "-a": "none", "-d": "none", "-l": "none", "-f": "none",
            "-x": "none", "-L": "number",
            "-P": "string", "-I": "string",
            "--gitignore": "none", "--prune": "none",
            "--noreport": "none", "--charset": "string",
            "--filelimit": "number",
            "-q": "none", "-N": "none", "-Q": "none",
            "-p": "none", "-u": "none", "-g": "none",
            "-s": "none", "-h": "none", "--du": "none",
            "-D": "none", "-F": "none", "--inodes": "none",
            "-v": "none", "-t": "none", "-c": "none",
            "-U": "none", "-r": "none",
            "--dirsfirst": "none", "--sort": "string",
            "-i": "none", "-A": "none", "-S": "none",
            "-n": "none", "-C": "none",
            "-X": "none", "-J": "none",
            "-H": "string", "--nolinks": "none",
            "-T": "string", "--hyperlink": "none",
            "--fromfile": "none", "--help": "none", "--version": "none",
            # 故意排除: -R (会在子目录写 00Tree.html)
            # 故意排除: -o/--output (写文件)
        },
    ),
    "diff": CommandConfig(name="diff", category="read", safe_flags={"-u": "none", "-r": "none", "-q": "none", "-w": "none", "-b": "none", "--help": "none"}),
    "sort": CommandConfig(name="sort", category="read", safe_flags={"-n": "none", "-r": "none", "-u": "none", "-k": "string", "-t": "string", "--help": "none"}),
    "uniq": CommandConfig(name="uniq", category="read", safe_flags={"-c": "none", "-d": "none", "-u": "none", "-i": "none", "--help": "none"}),
    "cut": CommandConfig(name="cut", category="read", safe_flags={"-d": "string", "-f": "string", "-c": "string", "-s": "none", "--help": "none"}),
    "tr": CommandConfig(name="tr", category="read", safe_flags={"-d": "none", "-s": "none", "-c": "none", "--help": "none"}),
    "xxd": CommandConfig(name="xxd", category="read", safe_flags={"-l": "number", "-s": "number", "-c": "number", "-g": "number", "--help": "none"}),
    "od": CommandConfig(name="od", category="read", safe_flags={"-A": "string", "-t": "string", "-j": "number", "-N": "number", "--help": "none"}),
    "awk": CommandConfig(name="awk", category="read", safe_flags={"-F": "string", "-v": "string", "-f": "string", "--help": "none"}),
    "sed": CommandConfig(
        name="sed", category="read",
        safe_flags={
            "-n": "none", "-e": "string", "-f": "string",
            "-r": "none", "-E": "none",
            "--quiet": "none", "--silent": "none",
            "--expression": "string", "--file": "string",
            "--regexp-extended": "none", "--posix": "none",
            "--help": "none", "--version": "none",
            # 故意排除: -i/--in-place (直接修改文件)
        },
    ),
    "jq": CommandConfig(name="jq", category="read", safe_flags={"-r": "none", "-c": "none", "-s": "none", "-n": "none", "--help": "none"}),
    "man": CommandConfig(name="man", category="read", safe_flags={"-k": "none", "-f": "none", "-w": "none", "-a": "none", "--help": "none"}),
    "help": CommandConfig(name="help", category="read", safe_flags={"-d": "none", "-m": "none", "-s": "none"}),
    "clear": CommandConfig(name="clear", category="neutral", safe_flags={}),
    "reset": CommandConfig(name="reset", category="neutral", safe_flags={}),
    "true": CommandConfig(name="true", category="neutral", safe_flags={}),
    "false": CommandConfig(name="false", category="neutral", safe_flags={}),
    "yes": CommandConfig(name="yes", category="neutral", safe_flags={}),
    "sleep": CommandConfig(name="sleep", category="neutral", safe_flags={}),
    "tee": CommandConfig(name="tee", category="write", safe_flags={"-a": "none", "-i": "none", "--help": "none"}),
    "cal": CommandConfig(name="cal", category="read", safe_flags={"-y": "none", "-3": "none", "-m": "none", "-j": "none", "--help": "none"}),
    "uptime": CommandConfig(name="uptime", category="read", safe_flags={"-p": "none", "-s": "none", "--help": "none"}),
    "id": CommandConfig(name="id", category="read", safe_flags={"-u": "none", "-g": "none", "-G": "none", "-n": "none", "-r": "none", "--help": "none"}),
    "free": CommandConfig(name="free", category="read", safe_flags={"-h": "none", "-b": "none", "-k": "none", "-m": "none", "-g": "none", "-t": "none", "-s": "number", "--help": "none"}),
    "locale": CommandConfig(name="locale", category="read", safe_flags={"-a": "none", "-m": "none", "-c": "none", "-k": "string", "--help": "none"}),
    "groups": CommandConfig(name="groups", category="read", safe_flags={"--help": "none"}),
    "nproc": CommandConfig(name="nproc", category="read", safe_flags={"--all": "none", "--ignore": "number", "--help": "none"}),
    "basename": CommandConfig(name="basename", category="read", safe_flags={"-a": "none", "-s": "string", "-z": "none", "--help": "none"}),
    "dirname": CommandConfig(name="dirname", category="read", safe_flags={"-z": "none", "--help": "none"}),
    "realpath": CommandConfig(name="realpath", category="read", safe_flags={"-e": "none", "-m": "none", "-L": "none", "-P": "none", "-s": "none", "-q": "none", "--help": "none"}),
    "readlink": CommandConfig(name="readlink", category="read", safe_flags={"-f": "none", "-e": "none", "-m": "none", "-n": "none", "-v": "none", "-q": "none", "-s": "none", "--help": "none"}),
    "strings": CommandConfig(name="strings", category="read", safe_flags={"-n": "number", "-t": "string", "-e": "string", "-f": "none", "--help": "none"}),
    "hexdump": CommandConfig(name="hexdump", category="read", safe_flags={"-C": "none", "-b": "none", "-c": "none", "-d": "none", "-o": "none", "-x": "none", "-n": "number", "-s": "number", "-v": "none", "--help": "none"}),
    "nl": CommandConfig(name="nl", category="read", safe_flags={"-b": "string", "-d": "string", "-f": "string", "-h": "string", "-i": "number", "-l": "number", "-n": "string", "-p": "none", "-s": "string", "-v": "number", "-w": "number", "--help": "none"}),
    "paste": CommandConfig(name="paste", category="read", safe_flags={"-d": "string", "-s": "none", "-z": "none", "--help": "none"}),
    "column": CommandConfig(name="column", category="read", safe_flags={"-t": "none", "-s": "string", "-n": "none", "-o": "string", "-x": "none", "-c": "number", "-L": "none", "-R": "none", "-N": "string", "-H": "number", "--help": "none"}),
    "tac": CommandConfig(name="tac", category="read", safe_flags={"-b": "none", "-r": "none", "-s": "string", "--help": "none"}),
    "rev": CommandConfig(name="rev", category="read", safe_flags={"--help": "none"}),
    "fold": CommandConfig(name="fold", category="read", safe_flags={"-b": "none", "-s": "none", "-w": "number", "--help": "none"}),
    "expand": CommandConfig(name="expand", category="read", safe_flags={"-i": "none", "-t": "string", "--help": "none"}),
    "unexpand": CommandConfig(name="unexpand", category="read", safe_flags={"-a": "none", "-t": "string", "--help": "none"}),
    "fmt": CommandConfig(name="fmt", category="read", safe_flags={"-c": "none", "-s": "none", "-t": "none", "-u": "none", "-w": "number", "-p": "string", "-g": "number", "--help": "none"}),
    "comm": CommandConfig(name="comm", category="read", safe_flags={"-1": "none", "-2": "none", "-3": "none", "--check-order": "none", "--nocheck-order": "none", "--total": "none", "-z": "none", "--help": "none"}),
    "cmp": CommandConfig(name="cmp", category="read", safe_flags={"-b": "none", "-i": "number", "-l": "none", "-n": "number", "-s": "none", "--help": "none"}),
    "numfmt": CommandConfig(name="numfmt", category="read", safe_flags={"--from": "string", "--to": "string", "--format": "string", "--padding": "number", "--delimiter": "string", "--field": "string", "--suffix": "string", "--header": "number", "--round": "string", "--debug": "none", "--help": "none"}),
    "expr": CommandConfig(name="expr", category="read", safe_flags={"--help": "none"}),
    "test": CommandConfig(name="test", category="read", safe_flags={}),
    "getconf": CommandConfig(name="getconf", category="read", safe_flags={"-a": "none", "-v": "string", "--help": "none"}),
    "seq": CommandConfig(name="seq", category="read", safe_flags={"-f": "string", "-s": "string", "-w": "none", "--help": "none"}),
    "sha256sum": CommandConfig(name="sha256sum", category="read", safe_flags={"-b": "none", "-t": "none", "-c": "none", "--check": "none", "--quiet": "none", "--status": "none", "--strict": "none", "-w": "none", "--tag": "none", "-z": "none", "--help": "none", "--version": "none"}),
    "sha1sum": CommandConfig(name="sha1sum", category="read", safe_flags={"-b": "none", "-t": "none", "-c": "none", "--check": "none", "--quiet": "none", "--status": "none", "--strict": "none", "-w": "none", "--tag": "none", "-z": "none", "--help": "none", "--version": "none"}),
    "md5sum": CommandConfig(name="md5sum", category="read", safe_flags={"-b": "none", "-t": "none", "-c": "none", "--check": "none", "--quiet": "none", "--status": "none", "--strict": "none", "-w": "none", "--tag": "none", "-z": "none", "--help": "none", "--version": "none"}),

    # ═══════════════════════════════════════════════════════
    #  安全写入命令
    # ═══════════════════════════════════════════════════════
    "mkdir": CommandConfig(name="mkdir", category="write", safe_flags={"-p": "none", "-v": "none", "-m": "string", "--help": "none"}),
    "touch": CommandConfig(name="touch", category="write", safe_flags={"-a": "none", "-m": "none", "-t": "string", "-c": "none", "--help": "none"}),
    "cp": CommandConfig(name="cp", category="write", safe_flags={"-r": "none", "-R": "none", "-v": "none", "-n": "none", "-i": "none", "-u": "none", "--help": "none"}),
    "mv": CommandConfig(name="mv", category="write", safe_flags={"-v": "none", "-n": "none", "-i": "none", "-u": "none", "--help": "none"}),
    "rmdir": CommandConfig(name="rmdir", category="write", safe_flags={"-p": "none", "-v": "none", "--help": "none"}),
    "chmod": CommandConfig(name="chmod", category="write", safe_flags={"-R": "none", "-v": "none", "-c": "none", "--help": "none"}),
    "ln": CommandConfig(name="ln", category="write", safe_flags={"-s": "none", "-f": "none", "-n": "none", "-v": "none", "--help": "none"}),

    # ═══════════════════════════════════════════════════════
    #  删除 / 进程 / 系统状态
    # ═══════════════════════════════════════════════════════
    # 这几条此前既不在白名单也不在硬拒表，闸门翻转后一路走 unknown 分支放行。
    # 登记进来不是为了卡 flag（未登记 flag 本来就不拒），而是为了让类别如实反映
    # 它们在写：category=write 才会真正参与 _check_dangerous_paths 的路径校验。
    # 递归删除仍由 BLOCKING_PATTERNS 的 rm -r / rm -f / del /s 拦在更前面。
    "rm": CommandConfig(name="rm", category="write", safe_flags={"-v": "none", "-i": "none", "-I": "none", "-d": "none", "--help": "none"}),
    "del": CommandConfig(name="del", category="write", safe_flags={"/P": "none", "/A": "string", "/F": "none"}),
    "erase": CommandConfig(name="erase", category="write", safe_flags={"/P": "none", "/A": "string", "/F": "none"}),
    # 杀进程可逆、且是排障常用操作，硬拒会重演 netstat -ano 那类误伤，按 write 放行
    "kill": CommandConfig(name="kill", category="write", safe_flags={"-9": "none", "-15": "none", "-l": "none", "-s": "string", "--help": "none"}),
    "killall": CommandConfig(name="killall", category="write", safe_flags={"-9": "none", "-i": "none", "-v": "none", "-s": "string", "--help": "none"}),
    "pkill": CommandConfig(name="pkill", category="write", safe_flags={"-9": "none", "-f": "none", "-u": "string", "--help": "none"}),
    "taskkill": CommandConfig(name="taskkill", category="write", safe_flags={"/PID": "number", "/IM": "string", "/F": "none", "/T": "none"}),

    # reg 与 icacls 不整条拒：reg query 是常用诊断，icacls <path> 只是查看 ACL。
    # 按动词/开关判定，只拦真正写注册表或改权限的形式（与 wmic 同一套做法）。
    "reg": CommandConfig(name="reg", category="read", additional_check=lambda cmd, args: _check_reg_safe(cmd, args)),
    "icacls": CommandConfig(name="icacls", category="read", additional_check=lambda cmd, args: _check_icacls_safe(cmd, args)),

    # ═══════════════════════════════════════════════════════
    #  不在这张表里的命令会被标 unknown 并照常放行——本表是分类表，不是准入名单。
    #  真正的拦截在 DESTRUCTIVE_COMMANDS 与 BLOCKING_PATTERNS；
    #  解释器的 -c/-e 载荷由 _check_interpreter_payload 递归过闸。
    # ═══════════════════════════════════════════════════════
}


# ============================================================
#  Git 子命令分类
# ============================================================
GIT_READ_ONLY = {
    "status", "log", "diff", "show", "branch", "tag",
    "remote", "config", "ls-files", "ls-tree", "rev-parse",
    "rev-list", "describe", "blame", "shortlog", "stash",
    "reflog", "cherry", "bisect", "grep", "archive",
    "whatchanged", "notes", "worktree", "submodule",
    "for-each-ref", "name-rev", "symbolic-ref", "update-ref",
    "count-objects", "fsck", "prune", "verify-pack",
    "show-ref", "pack-refs", "replace", "verify-commit",
    "verify-tag", "check-ref-format", "check-attr",
    "check-ignore", "check-mailmap", "checkout-index",
    "column", "credential", "diff-files", "diff-index",
    "diff-tree", "fast-export", "fast-import",
    "fmt-merge-msg", "get-tar-commit-id", "hash-object",
    "help", "index-pack", "instaweb", "interpret-trailers",
    "log", "ls-remote", "merge-base", "merge-file",
    "merge-index", "merge-one-file", "merge-tree",
    "mktag", "mktree", "multi-pack-index", "pack-objects",
    "patch-id", "prune-packed", "quiltimport",
    "range-diff", "read-tree", "rebase", "receive-pack",
    "reflog", "remote-ext", "remote-fd", "repack",
    "request-pull", "rerere", "reset", "restore",
    "revert", "rm", "send-email", "send-pack",
    "sh-i18n--envsubst", "show-branch", "show-index",
    "show-ref", "sparse-checkout", "stash", "stripspace",
    "svn", "switch", "symbolic-ref", "unpack-file",
    "unpack-objects", "update-index", "update-ref",
    "update-server-info", "upload-archive",
    "upload-pack", "var", "verify-commit", "verify-pack",
    "verify-tag", "web--browse", "whatchanged",
    "worktree", "write-tree",
}

GIT_WRITE = {
    "add", "mv", "commit", "checkout", "restore", "switch",
    "merge", "rebase", "pull", "fetch", "push",
    "init", "clone", "revert", "cherry-pick",
    "stash", "branch", "tag", "remote",
    # reset/clean 本身只是改工作区，真正不可逆的 --hard / -f 由 BLOCKING_PATTERNS 拦
    "reset", "clean",
}


# ============================================================
#  危险路径模式
# ============================================================
DANGEROUS_PATHS = [
    (r"^/$", "根目录 /"),
    (r"^~$", "用户主目录 ~"),
    (r"^/etc", "系统配置目录 /etc"),
    (r"^/boot", "系统引导目录 /boot"),
    (r"^/sys", "系统信息目录 /sys"),
    (r"^/proc", "进程信息目录 /proc"),
    (r"^/dev", "设备目录 /dev"),
    # 反斜杠数量曾写成 \\\\，正则语义要求路径含两个字面反斜杠，真实路径只有一个，三条从未命中。
    # 盘符泛化：多系统机器上 D:\Windows 同样是系统目录；正反斜杠都收，大小写由匹配处的 IGNORECASE 兜。
    (r"^[a-zA-Z]:[\\/]?$", "Windows 盘符根目录"),
    (r"^[a-zA-Z]:[\\/]Windows\b", "Windows 系统目录"),
    (r"^[a-zA-Z]:[\\/]Program Files", "Windows 程序目录"),
]


# ============================================================
#  不可逆操作：硬拒模式与命令
# ============================================================
# 闸门从"白名单准入"翻转为"破坏性拦截"后，未知命令默认放行，
# 真正的兜底全部落在这里。只收录不可逆、批量、事后难以人工挽回的操作。
DESTRUCTIVE_COMMANDS = {
    # 磁盘 / 分区 / 文件系统
    "format", "diskpart", "fdisk", "parted", "mkfs", "shred", "dd",
    # Windows 系统级破坏与备份销毁
    "vssadmin", "wbadmin", "bcdedit", "cipher", "takeown",
    # 电源
    "shutdown", "reboot", "halt", "poweroff",
    # 提权
    "sudo", "su", "runas",
    # 改账户与属主：Windows 下基本用不到，POSIX 下需要特权，
    # 误伤面极小而后果不可逆，直接硬拒
    "chown", "chgrp", "passwd",
}

BLOCKING_PATTERNS = [
    # Git 不可逆
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard 会丢弃未提交的更改"),
    (r"\bgit\s+clean\b[^;&|\n]*-[a-zA-Z]*f", "git clean -f 会永久删除未跟踪文件"),

    # POSIX 递归 / 强制删除
    (r"(^|[;&|\n]\s*)rm\s+-[a-zA-Z]*[rR]", "rm -r 递归删除文件"),
    (r"(^|[;&|\n]\s*)rm\s+-[a-zA-Z]*f", "rm -f 强制删除文件"),

    # Windows 批量 / 静默 / 递归删除
    (r"(^|[;&|\n]\s*)del\b[^;&|\n]*\s/[sSqQ]\b", "del /s 或 /q 批量静默删除"),
    (r"(^|[;&|\n]\s*)(rd|rmdir)\b[^;&|\n]*\s/[sS]\b", "rd /s 递归删除目录"),
    (r"(^|[;&|\n]\s*)(del|erase)\b[^;&|\n]*[*?]", "del 通配符批量删除"),
    (r"(^|[;&|\n]\s*)rm\b[^;&|\n]*[*?]", "rm 通配符批量删除"),

    # 数据库
    (r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b", "删除或清空数据库对象"),
    (r"\bDELETE\s+FROM\s+\w+[ \t]*(;|\"|'|\n|$)", "删除表中所有行"),

    # 基础设施
    (r"\bkubectl\s+delete\b", "删除 Kubernetes 资源"),
    (r"\bterraform\s+destroy\b", "销毁 Terraform 基础设施"),

    # 嵌套执行：真正跑起来的那条命令不经任何校验，等于把前面所有检查一次性绕开。
    # 默认放行模型下这类"命令的命令"必须硬拒，否则 curl|bash、find -exec rm 都能落地。
    (r"\bfind\b[^;&|\n]*\s-(exec|execdir|ok|okdir|delete)\b", "find -exec/-delete 会执行未经校验的嵌套命令"),
    (r"\|\s*(bash|sh|zsh|ksh|dash|powershell|pwsh|cmd)\b", "把管道内容直接交给 shell 执行"),
    (r"\|\s*xargs\b", "xargs 会对每个输入执行未经校验的命令"),
    (r"\b(iex|Invoke-Expression)\b", "PowerShell Invoke-Expression 会执行动态构造的内容"),
]


# ============================================================
#  破坏性命令警告模式（有风险但可恢复，只提示不拦）
# ============================================================
DESTRUCTIVE_PATTERNS = [
    # Git 高风险但可恢复
    (r"\bgit\s+push\b[^;&|\n]*[ \t](--force|--force-with-lease|-f)\b", "git push --force 可能覆盖远程历史"),
    (r"\bgit\s+checkout\s+(--\s+)?\.[ \t]*($|[;&|\n])", "git checkout . 可能丢弃所有工作区更改"),
    (r"\bgit\s+restore\s+(--\s+)?\.[ \t]*($|[;&|\n])", "git restore . 可能丢弃所有工作区更改"),
    (r"\bgit\s+stash[ \t]+(drop|clear)\b", "git stash drop/clear 可能永久删除暂存更改"),
    (r"\bgit\s+branch\s+(-D[ \t]|--delete\s+--force)\b", "git branch -D 可能强制删除分支"),
    (r"\bgit\s+(commit|push|merge)\b[^;&|\n]*--no-verify\b", "可能跳过安全钩子"),
    (r"\bgit\s+commit\b[^;&|\n]*--amend\b", "可能重写最后一次提交"),

]


# ============================================================
#  解析函数
# ============================================================

# Windows 下 \ 是路径分隔符而非转义符。此前统一按 POSIX 把它吞掉，
# D:\Alear030\... 被解析成 D:Alear030...，合法路径打碎后当成命令名拒绝。
_BACKSLASH_ESCAPES = os.name != "nt"

# cmd.exe 与 sh 都把这些当命令分隔符：只校验第一段，等于给后续段留了绕过口子
_TWO_CHAR_OPS = ("&&", "||")
_ONE_CHAR_OPS = ("&", ";", "|")

# 重定向不再一刀切硬拒(那让 2>&1、> NUL、跑测试存日志全做不了)，改为放行算子、校验目标路径。
# fd 复制 >&N 必须整体识别：否则其中的 & 会走 _ONE_CHAR_OPS 触发分段，
# `python app.py > log.txt 2>&1` 会被切成两段而把 `1` 当成命令名去校验。
_REDIR_DUP = re.compile(r"[0-9]*>&[0-9]+")
_REDIR_OP = re.compile(r"[0-9]*(?:>>|>|<)")


def scan_command(command: str) -> tuple[list[tuple[str, str]], str, str]:
    """单趟扫描命令串，返回 (token 序列, 引号外裸文本, 单引号外文本)。

    token 为 ('word', 文本) 或 ('op', 分隔符)。
    引号/转义扫描此前在 parse_command 和注入检测的两个循环里各写了一遍，
    三份实现容易漂移，统一收口到这里作为唯一权威表示。

    unquoted 用于判重定向/换行；expandable 保留双引号内文本，
    因为 sh 里 $() 和反引号在双引号内照样展开。
    """
    tokens: list[tuple[str, str]] = []
    unquoted = ""
    expandable = ""
    current = ""
    in_single = False
    in_double = False
    escaped = False
    i = 0
    n = len(command)

    def flush() -> None:
        nonlocal current
        if current:
            tokens.append(("word", current))
            current = ""

    while i < n:
        ch = command[i]

        if escaped:
            current += ch
            unquoted += ch
            expandable += ch
            escaped = False
            i += 1
            continue

        if ch == "\\" and _BACKSLASH_ESCAPES and not in_single:
            escaped = True
            i += 1
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            current += ch
            i += 1
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            current += ch
            i += 1
            continue

        if in_single:
            current += ch
            i += 1
            continue

        if in_double:
            current += ch
            expandable += ch
            i += 1
            continue

        if ch in (">", "<"):
            # fd 前缀(2> 里的 2)此前已按普通字符进了 current，回退出来连同算子一起交给正则
            fd = ""
            while current and current[-1].isdigit():
                fd = current[-1] + fd
                current = current[:-1]
            flush()
            start = i - len(fd)
            m = _REDIR_DUP.match(command, start) or _REDIR_OP.match(command, start)
            # start 处必然是 [0-9]*[<>]，正则一定命中；兜底分支只为让类型收敛
            op_text = m.group(0) if m else ch
            tokens.append(("redir", op_text))
            # fd 那几位已经计入过 unquoted/expandable，只补算子部分，避免重复
            unquoted += op_text[len(fd):]
            expandable += op_text[len(fd):]
            i = m.end() if m else i + 1
            continue

        two = command[i:i + 2]
        if two in _TWO_CHAR_OPS:
            flush()
            tokens.append(("op", two))
            unquoted += two
            expandable += two
            i += 2
            continue

        if ch in _ONE_CHAR_OPS:
            flush()
            tokens.append(("op", ch))
            unquoted += ch
            expandable += ch
            i += 1
            continue

        if ch in (" ", "\t"):
            flush()
            unquoted += ch
            expandable += ch
            i += 1
            continue

        current += ch
        unquoted += ch
        expandable += ch
        i += 1

    flush()
    return (tokens, unquoted, expandable)


def split_segments(command: str) -> list[list[str]]:
    """按引号外的分隔符切成多条子命令，每条给出自己的 token 列表。

    只有 op 才分段；redir 属于某条命令的一部分，随该段一起留下。
    """
    segments: list[list[str]] = []
    current: list[str] = []
    for kind, text in scan_command(command)[0]:
        if kind == "op":
            if current:
                segments.append(current)
                current = []
        elif text:
            current.append(text)
    if current:
        segments.append(current)
    return segments


def _extract_redirects(tokens: list[str]) -> tuple[list[str], list[str]]:
    """摘掉重定向算子与目标，返回 (命令自身的 token, 重定向目标)。

    目标必须单独拿出来校验：它总是写操作，而基础命令可能是 read
    (`git status > C:\\Windows\\x`)，混在位置参数里会被 read 分支早返回放过。
    算子与目标也必须从 token 中剔除，否则 log.txt 会被当成命令的位置参数扫。
    引号外的裸 > < 只可能是重定向，故按整词匹配算子即可（带引号的 token 不会命中）。
    """
    clean: list[str] = []
    targets: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if _REDIR_DUP.fullmatch(tok):
            i += 1  # fd 复制(2>&1)没有路径目标
            continue
        if _REDIR_OP.fullmatch(tok):
            if i + 1 < len(tokens):
                targets.append(tokens[i + 1])
            i += 2
            continue
        clean.append(tok)
        i += 1
    return (clean, targets)


def parse_command(command: str) -> tuple[str, list[str]]:
    """解析命令字符串，提取基础命令和参数列表（只看第一段）。"""
    segments = split_segments(command)
    if not segments:
        return ("", [])
    return (segments[0][0].lower(), segments[0][1:])


def _expand_short_flags(arg: str, config: CommandConfig) -> list[str]:
    """展开合并的短 flag（-la → -l -a）"""
    if not arg.startswith("-") or arg.startswith("--") or len(arg) <= 2:
        return [arg]
    flags_str = arg[1:]
    expanded = []
    for ch in flags_str:
        flag = f"-{ch}"
        if flag in config.safe_flags and config.safe_flags[flag] == "none":
            expanded.append(flag)
        else:
            return [arg]
    return expanded


def _flag_style(config: CommandConfig) -> tuple[str, str]:
    """按该命令自己声明的 flag 前缀风格返回 (前缀, 分隔符)：Windows 命令用 '/' + ':'，其余用 '-' + '='"""
    if any(k.startswith("/") for k in config.safe_flags):
        return ("/", ":")
    return ("-", "=")


def _positional_args(args: list[str], config: CommandConfig) -> list[str]:
    """挑出非 flag 的位置参数。

    闸门翻转后 flag 不再是准入条件，但仍要分清哪些 token 是 flag 的取值、
    哪些才是真正的路径，否则危险路径检查会把 --index-url 的 URL 当路径扫。
    未登记的 flag 一律按"不吃参数"处理：宁可把它后面的 token 也当路径多扫一遍。
    """
    prefix, sep = _flag_style(config)

    if prefix == "-":
        expanded_args = []
        for arg in args:
            expanded_args.extend(_expand_short_flags(arg, config))
    else:
        expanded_args = list(args)

    positional: list[str] = []
    i = 0
    while i < len(expanded_args):
        arg = expanded_args[i]

        if prefix == "-" and arg == "--" and config.respects_double_dash:
            positional.extend(expanded_args[i + 1:])
            break

        if not arg.startswith(prefix):
            positional.append(arg)
            i += 1
            continue

        flag_name = arg.split(sep, 1)[0] if sep in arg else arg
        if prefix == "/":
            # Windows 命令的 / flag 大小写不敏感（dir /b 等价于 dir /B），白名单键统一按大写登记
            flag_name = flag_name.upper()

        # 已登记且需要取值、且值没跟在同一个 token 里 → 下一个 token 是它的参数
        if config.safe_flags.get(flag_name) in ("number", "string", "path", "EOF", "{}") and sep not in arg:
            i += 2
        else:
            i += 1

    return positional


# ============================================================
#  安全检查函数
# ============================================================

def _check_bsd_ps_e(args: list[str]) -> Optional[str]:
    """检查 ps 命令的 BSD 风格 'e' 修饰符（泄露环境变量）"""
    for a in args:
        if not a.startswith("-") and re.match(r"^[a-zA-Z]*e[a-zA-Z]*$", a):
            return f"ps 的 BSD 修饰符 '{a}' 含 e，会连进程环境变量一起打印"
    return None


def _check_date_positional(args: list[str]) -> Optional[str]:
    """检查 date 的位置参数是否安全（必须以 + 开头）"""
    flags_with_args = {"-d", "--date", "-r", "--reference", "--iso-8601", "--rfc-3339"}
    i = 0
    while i < len(args):
        token = args[i]
        if token.startswith("--") and "=" in token:
            i += 1
        elif token.startswith("-"):
            if token in flags_with_args:
                i += 2
            else:
                i += 1
        else:
            if not token.startswith("+"):
                return f"date 的位置参数 '{token}' 不以 + 开头，可能是在设置系统时间而非格式化输出"
            i += 1
    return None


def _check_wmic_safe(cmd: str, args: list[str]) -> Optional[str]:
    """wmic 语法非 flag 式，改用动词白名单：只允许 get/list 查询，堵住 call/set/delete/create。

    /format 不整条拒：取值是内置格式名(list/csv/...)时只是换个输出排版，
    指向文件或 URL 时才是 XSL 注入——wmic ... /format:"http://x/e.xsl" 能执行远程代码。
    此前一刀切把 /format:list 也拒了，实测把模型逼去绕道 PowerShell。
    """
    WMIC_DENY_VERBS = {"call", "set", "delete", "create", "assoc"}
    WMIC_DENY_SWITCHES = {"/output", "/append", "/namespace"}
    WMIC_SAFE_FORMATS = {"list", "table", "csv", "value", "xml", "rawxml", "mof", "htable", "hform"}
    has_query_verb = False
    for arg in args:
        low = _strip_quotes(arg).lower()
        if low in WMIC_DENY_VERBS:
            return f"wmic 动词 '{low}' 会修改系统状态，只允许 get / list 查询"
        if low in ("get", "list"):
            has_query_verb = True
        for switch in WMIC_DENY_SWITCHES:
            if low == switch or low.startswith(switch + ":"):
                return f"wmic 开关 '{switch}' 会写文件或切换 WMI 命名空间，不予放行"
        if low == "/format" or low.startswith("/format:"):
            # 取值自带引号时要再剥一层：整个 token 以 / 开头，_strip_quotes 剥不掉内层的
            value = _strip_quotes(low[len("/format:"):]) if low.startswith("/format:") else ""
            if value not in WMIC_SAFE_FORMATS:
                return (
                    f"wmic /format: 只接受内置格式名（{'、'.join(sorted(WMIC_SAFE_FORMATS))}），"
                    f"收到 '{value or '(空)'}'；指向文件或 URL 的 XSL 会被当作代码执行"
                )
    if not has_query_verb:
        return "wmic 必须带 get 或 list 查询动词，否则无法确认它只是在读取信息"
    return None


def _check_injection(command: str) -> tuple[bool, str]:
    """检查命令注入模式（分隔符改由 split_segments 逐段校验，此处不再兜底）"""
    _, unquoted, expandable = scan_command(command)

    # 命令替换在双引号内照样生效，故查 expandable 而非 unquoted
    if "`" in expandable:
        return (False, "命令包含反引号命令替换")
    if "$(" in expandable:
        return (False, "命令包含 $() 命令替换")
    if "${" in expandable:
        return (False, "命令包含 ${} 参数替换")

    # 换行只查引号外：引号内的换行是单条命令的参数内容(如 python -c 的多行脚本)，
    # 引号外的换行才真正分隔多个命令
    if "\n" in unquoted or "\r" in unquoted:
        return (False, "命令包含换行符，可能分隔多个命令")

    # 重定向不在此拦：算子放行，改由 _validate_segment 校验目标路径

    # ANSI-C 引用
    if re.search(r"\$'[^']*'", command):
        return (False, "命令包含 ANSI-C 引用 $'...'，可能隐藏字符")

    # IFS 注入
    if re.search(r"\$IFS|\$\{[^}]*IFS", command):
        return (False, "命令包含 IFS 变量，可能绕过安全检查")

    return (True, "")


def _strip_quotes(arg: str) -> str:
    # 词法器有意保留引号(scan_command 的 current += ch)，比对路径前必须剥掉，
    # 否则 '"C:\Program Files\x"' 的开头是引号，^C: 永远匹配不到
    if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in ("'", '"'):
        return arg[1:-1]
    return arg


def _check_dangerous_paths(args: list[str], category: str) -> tuple[bool, str]:
    """检查危险路径（只对写操作生效）"""
    if category in ("read", "neutral"):
        return (True, "")
    for arg in args:
        if arg.startswith("-"):
            continue
        target = _strip_quotes(arg)
        for pattern, reason in DANGEROUS_PATHS:
            # Windows 路径大小写不敏感，c:\windows 必须与 C:\Windows 同等对待；
            # POSIX 几条是全小写字面量，加 IGNORECASE 只会多命中 /ETC，更严不会更松
            if re.match(pattern, target, re.IGNORECASE):
                return (False, f"危险路径 '{target}': {reason}")
    return (True, "")


def _check_blocking(command: str) -> Optional[str]:
    """检查不可逆操作，返回拦截原因；这是默认放行模型下的最后一道闸"""
    for pattern, reason in BLOCKING_PATTERNS:
        if re.search(pattern, command):
            return reason
    return None


def _check_destructive(command: str) -> Optional[str]:
    """检查破坏性命令模式，返回警告信息"""
    for pattern, warning in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, command):
            return warning
    return None


# ============================================================
#  主验证函数
# ============================================================

# 多段命令对外展示最重的那个类别
_SEVERITY = {"read": 0, "neutral": 1, "unknown": 2, "write": 3, "destructive": 4}


# ============================================================
#  解释器载荷：命令的命令
# ============================================================
# bash -c "rm -rf x" 与 rm -rf x 是同一个操作，但前者此前完全不过检——
# bash 既不在分类表也不在硬拒表，走 unknown 放行，而 -c 后面整条命令
# 只是这个未知命令的一个参数 token，没有任何一层会去看它。
# BLOCKING_PATTERNS 只拦了管道形式 | bash，没拦直接调用形式。
# 威胁模型是"防模型手滑"，而模型在"清理一下 build 目录"这种任务里
# 就会自然写出 bash -c "rm -rf build"，闸门对直接形式拦、对包装形式放，
# 恰好背离了自己的目的。故把载荷取出来当普通命令再过一遍完整闸门。
INTERPRETER_PAYLOAD_FLAGS: dict[str, tuple[str, ...]] = {
    "bash": ("-c",), "sh": ("-c",), "zsh": ("-c",), "ksh": ("-c",), "dash": ("-c",),
    "python": ("-c",), "python3": ("-c",), "py": ("-c",),
    "node": ("-e", "--eval", "-p", "--print"),
    "perl": ("-e",), "ruby": ("-e",),
    "powershell": ("-command", "-c", "-encodedcommand", "-e", "-ec"),
    "pwsh": ("-command", "-c", "-encodedcommand", "-e", "-ec"),
}

# base64 载荷没法静态校验,只能整条拒——正常用途也不会用它
_OPAQUE_PAYLOAD_FLAGS = {"-encodedcommand", "-ec"}

# 内层再套一层解释器直接拒。正常用途不会有两层,而放开递归深度
# 等于给"多包几层就能绕过"留了口子
_MAX_NEST_DEPTH = 1
_nest_state = threading.local()


def _check_nested_command(inner: str, flag: str) -> Optional[str]:
    """把 -c/-e 的取值当成一条普通命令重新过闸,内层被拒则整条拒。"""
    inner = _strip_quotes(inner).strip()
    if not inner:
        return None

    depth = getattr(_nest_state, "depth", 0)
    if depth >= _MAX_NEST_DEPTH:
        return f"{flag} 的内层命令又嵌套了一层解释器调用,不予放行"

    _nest_state.depth = depth + 1
    try:
        ok, err, _category, _warning = validate_command(inner)
    finally:
        _nest_state.depth = depth

    if not ok:
        return f"{flag} 的内层命令未通过校验: {err}"
    return None


def _check_interpreter_payload(base_cmd: str, args: list[str]) -> Optional[str]:
    """解释器的 -c/-e 载荷递归过闸。不是解释器则直接放过。"""
    flags = INTERPRETER_PAYLOAD_FLAGS.get(base_cmd)
    if not flags:
        return None

    for index, arg in enumerate(args):
        low = _strip_quotes(arg).lower()
        # 取值可能跟在同一个 token 里（-c="..."）,也可能是下一个 token
        name, sep, inline = low.partition("=")
        if name not in flags:
            continue
        if name in _OPAQUE_PAYLOAD_FLAGS:
            return f"{name} 的载荷是 base64 编码,无法校验其内容,不予放行"
        if sep:
            return _check_nested_command(arg.partition("=")[2], name)
        if index + 1 < len(args):
            return _check_nested_command(args[index + 1], name)
        return None
    return None


def _check_reg_safe(cmd: str, args: list[str]) -> Optional[str]:
    """reg 按动词判定:query/export 是读,其余会写注册表。"""
    READ_VERBS = {"query", "export", "compare"}
    for arg in args:
        low = _strip_quotes(arg).lower()
        if low.startswith("/") or low.startswith("-"):
            continue
        if low in READ_VERBS:
            return None
        return f"reg 动词 '{low}' 会修改注册表,只允许 query / export / compare"
    return "reg 必须带 query / export / compare 动词,否则无法确认它只是在读取"


def _check_icacls_safe(cmd: str, args: list[str]) -> Optional[str]:
    """icacls 不带开关时只是查看 ACL;带下列开关才是改权限。"""
    DENY_SWITCHES = {
        "/grant", "/deny", "/remove", "/setowner", "/setintegritylevel",
        "/reset", "/inheritance", "/substitute", "/restore",
    }
    for arg in args:
        low = _strip_quotes(arg).lower()
        head = low.split(":", 1)[0]
        if head in DENY_SWITCHES:
            return f"icacls {head} 会修改文件访问权限或属主,不予放行"
    return None


def _validate_segment(tokens: list[str]) -> tuple[bool, str, str]:
    """对单条子命令跑完整校验，返回 (是否安全, 错误信息, 类别)"""
    tokens, redirect_targets = _extract_redirects(tokens)
    if not tokens:
        return (True, "", "neutral")

    base_cmd = tokens[0].lower()
    args = tokens[1:]
    segment_text = " ".join(tokens)

    # 第0层: 重定向目标。显式传 write——目标永远是写操作，而基础命令可能是 read，
    # 走 read 分支会被 _check_dangerous_paths 早返回直接放过
    ok, err = _check_dangerous_paths(redirect_targets, "write")
    if not ok:
        return (False, f"重定向目标是{err}", "write")

    # 第1层: 不可逆命令硬拒
    if base_cmd in DESTRUCTIVE_COMMANDS:
        return (False, f"命令 '{base_cmd}' 属于不可逆的破坏性操作", "destructive")

    # 第1.5层: 解释器载荷。必须在分类之前——bash/sh 根本不在分类表里,
    # 放到 config 查表之后就永远轮不到它们
    nested_err = _check_interpreter_payload(base_cmd, args)
    if nested_err:
        return (False, nested_err, "destructive")

    # 第2层: 分类。命中白名单沿用其类别；未命中标 unknown 但照常放行——
    # 闸门已翻转，白名单从"准入条件"降级为"分类表"
    config = COMMAND_WHITELIST.get(base_cmd)
    if config is None:
        loose = [a for a in args if not a.startswith("-") and not a.startswith("/")]
        ok, err = _check_dangerous_paths(loose, "unknown")
        if not ok:
            return (False, err, "unknown")
        return (True, "", "unknown")

    category = config.category
    positional = _positional_args(args, config)

    # 第3层: 正则检查
    if config.regex and not re.match(config.regex, segment_text):
        return (False, f"命令格式不符合 {base_cmd} 的安全要求", category)

    # 第4层: git 子命令分类。必须用 positional——-C 的路径参数若混在里面，
    # 会被当成子命令，合法的 git -C <path> status 就此全军覆没
    if base_cmd == "git":
        for arg in positional:
            if arg in GIT_WRITE:
                category = "write"
                break
            elif arg in GIT_READ_ONLY:
                category = "read"
                break

    # 第5层: 额外检查回调（返回原因字符串即拒绝，原因直接回给模型，不再吞成笼统提示）
    if config.additional_check:
        extra_err = config.additional_check(segment_text, args)
        if extra_err:
            return (False, extra_err, category)

    # 第6层: 危险路径
    ok, err = _check_dangerous_paths(positional, category)
    if not ok:
        return (False, err, category)

    return (True, "", category)


def validate_command(command: str) -> tuple[bool, str, str, Optional[str]]:
    """
    多层安全验证。

    返回: (是否安全, 错误信息, 命令类别, 破坏性警告)
    命令类别: 'read' | 'write' | 'destructive' | 'neutral' | 'unknown'
    """
    # 第0层: 命令注入检测
    ok, err = _check_injection(command)
    if not ok:
        return (False, err, "unknown", None)

    # 第0.5层: 不可逆操作硬拒
    blocked = _check_blocking(command)
    if blocked:
        return (False, blocked, "destructive", None)

    # 分段：cmd.exe 会把 & && || ; | 之后的命令照样执行。此前只校验第一段，
    # & 后面写什么都能落地，白名单形同虚设；现在每段各跑一遍完整校验，全过才放行。
    segments = split_segments(command)
    if not segments:
        return (False, "命令为空", "neutral", None)

    worst = None
    for index, tokens in enumerate(segments):
        ok, err, category = _validate_segment(tokens)
        if not ok:
            if len(segments) > 1:
                err = f"第 {index + 1} 段子命令未通过: {err}"
            return (False, err, category, None)
        if worst is None or _SEVERITY.get(category, 0) > _SEVERITY.get(worst, 0):
            worst = category

    destructive_warning = _check_destructive(command)

    return (True, "", worst or "neutral", destructive_warning)


def is_destructive_category(category: str) -> bool:
    return category == "destructive"


# ============================================================
#  自测
# ============================================================
