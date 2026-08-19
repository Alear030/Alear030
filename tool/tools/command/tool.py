import subprocess
import locale
import os
import signal
from pathlib import Path
from tool.tool_core import register_tool
from .security import validate_command,is_destructive_category,COMMAND_WHITELIST

MAX_TIMEOUT = 120
# stdout/stderr 各自独立计算。曾有一次递归目录探测返回上百万 token 直接打爆模型请求，
# 且因请求本身失败连压缩机制都来不及触发；同目录 file_glob/file_grep/web_fetch 都有上限，这里补齐。
MAX_OUTPUT_CHARS = 8000

# ── 编码处理 ──
# 子进程输出没有单一正确编码：Windows 原生命令(dir/systeminfo)按系统码页输出(中文环境 GBK)，
# 而 Python 脚本、git 等普遍输出 UTF-8。固定用任何一方解码都会让另一方乱码
# (硬编码 utf-8 曾导致原生命令中文乱码，固定系统编码则导致 Python 输出乱码，两个坑都踩过)。
# 因此不在 subprocess 层解码，改为取 bytes 后由 _decode 按 UTF-8 优先、失败回落系统编码。
_SYSTEM_ENCODING = locale.getpreferredencoding(do_setlocale=False)

# 超时后要连孙进程一起清理，故建独立进程组/会话，让整棵树有统一的可 kill 句柄
_SPAWN_KWARGS = {'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session':True}


def _decode(raw:bytes)->str:
    # UTF-8 是自校验编码：整段能解通基本就是 UTF-8，解不通说明是本地码页。
    # 已知残余风险：极短的 GBK 中文(一两个汉字)有小概率碰巧构成合法 UTF-8 而被误判；
    # 长文本几乎必然触发回落，这是该策略的固有代价。
    if not raw:
        return ''
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode(_SYSTEM_ENCODING,errors='replace')


def _section(raw:bytes,name:str)->str:
    # 超长输出保留首尾各半：编译/测试类命令的关键错误常在末尾，只截头部会丢掉最有用的信息
    text = _decode(raw).strip()
    total = len(text)
    if total <= MAX_OUTPUT_CHARS:
        return f"\n--- {name} ---\n{text or '(无输出)'}"
    half = MAX_OUTPUT_CHARS//2
    omitted = total-MAX_OUTPUT_CHARS
    body = f"{text[:half]}\n\n… 已省略 {omitted} 字符，请缩小命令范围或改用 file_grep …\n\n{text[-half:]}"
    return f"\n--- {name} (原始 {total} 字符，已截断至 {MAX_OUTPUT_CHARS}，中间省略 {omitted} 字符) ---\n{body}"


def _kill_tree(proc)->None:
    # communicate 超时只会 kill 直接子进程(cmd.exe)，它派生的孙进程会游离，必须按整棵树清
    if os.name == 'nt':
        subprocess.run(['taskkill','/T','/F','/PID',str(proc.pid)],capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(proc.pid),signal.SIGKILL)
        except (ProcessLookupError,PermissionError):
            proc.kill()
    # 回收管道，避免句柄残留
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass

tool_desc = '执行本地 shell 命令（拦截不可逆的破坏性操作），返回退出码、stdout 和 stderr'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else None
else:
    tool_prompt = None

# shell 方言按运行平台注入：日志里模型反复写 ls/mv/pwd 再吃 'not recognized' 报错，
# 根源是 prompt 从没说清底层其实是 cmd.exe（旧版还拿 `ls -la` 当示例，等于反向教错）
if os.name == 'nt':
    _shell_block = (
        '\n\n当前 shell: Windows cmd.exe（命令经 cmd /c 执行）\n'
        '- 列目录用 dir 不是 ls；移动改名用 move 不是 mv；复制用 copy 不是 cp\n'
        '- 看文件用 type 不是 cat；找命令用 where 不是 which；看当前目录用 cd 不是 pwd\n'
        '- 路径分隔符是反斜杠，含空格的路径要用双引号包起来\n'
        '- 确实需要 Unix 风格命令时，显式走 bash -c "..." 或改用 python -c "..."'
    )
else:
    _shell_block = '\n\n当前 shell: POSIX sh（命令经 /bin/sh -c 执行）'
tool_prompt = (tool_prompt or '') + _shell_block

# 已登记命令清单从 COMMAND_WHITELIST 生成并拼进 tool_prompt，避免文档与代码脱节。
# 闸门翻转后它只是分类表：未登记的命令照样能跑，只是会被标成 unknown
_known_names = ', '.join(sorted(COMMAND_WHITELIST.keys()))
_known_block = f'\n\n已登记命令（会带上只读/写入分类标签；未列出的命令同样可执行，只是标为 unknown）:\n{_known_names}'
tool_prompt = (tool_prompt or '') + _known_block


@register_tool(tool_name='command',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='command_tool')
def command(command:str,timeout:int=120,cwd:str=None,**kwargs)->str:
    safe, reason, category, destructive_warning = validate_command(command)

    if not safe:
        return (
            f"[command] ❌ 安全验证未通过\n"
            f"命令: {command}\n"
            f"类别: {category}\n"
            f"原因: {reason}\n"
            f"\n提示: 该命令被判定为不可逆的破坏性操作。"
            f"如确需执行，请手动在终端中运行。"
        )

    if is_destructive_category(category):
        return (
            f"[command] ❌ 拒绝执行破坏性操作\n"
            f"命令: {command}\n"
            f"类别: {category}\n"
            f"原因: {reason}\n"
            f"\n该命令属于破坏性操作，已自动拒绝。"
        )

    if timeout <= 0:
        return f"[command] 错误: timeout 必须大于 0，收到: {timeout}"
    # 钳制不再静默：否则模型会以为自己设的值生效了
    timeout_notice = ''
    if timeout > MAX_TIMEOUT:
        timeout_notice = f"\n提示: 请求超时 {timeout} 秒，已按上限钳制为 {MAX_TIMEOUT} 秒"
        timeout = MAX_TIMEOUT

    # cwd 只对本次调用生效，不跨调用持久——不引入会话级当前目录这个新的状态事实源
    if cwd:
        cwd_path = Path(cwd)
        if not cwd_path.is_dir():
            return (
                f"[command] 错误: cwd 不是一个存在的目录\n"
                f"cwd: {cwd}"
            )
        cwd = str(cwd_path)

    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            **_SPAWN_KWARGS,
        )
    except Exception as e:
        return (
            f"[command] ❌ 命令执行异常\n"
            f"命令: {command}\n"
            f"错误: {type(e).__name__}: {e}"
        )

    try:
        raw_out,raw_err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        return (
            f"[command] ⏰ 命令超时\n"
            f"命令: {command}\n"
            f"超时时间: {timeout} 秒（子进程树已清理）{timeout_notice}"
        )
    except Exception as e:
        _kill_tree(proc)
        return (
            f"[command] ❌ 命令执行异常\n"
            f"命令: {command}\n"
            f"错误: {type(e).__name__}: {e}"
        )

    exit_code = proc.returncode

    category_label = {
        "read": "📖 只读", "write": "✏️ 写入", "neutral": "⚪ 中性"
    }.get(category, f"🏷️ {category}")

    cwd_line = f"工作目录: {cwd}\n" if cwd else ""

    warning_line = ""
    if destructive_warning:
        warning_line = f"\n⚠️ 警告: {destructive_warning}"

    output = (
        f"[command] 命令执行完成 [{category_label}]{warning_line}{timeout_notice}\n"
        f"命令: {command}\n"
        f"{cwd_line}"
        f"退出码: {exit_code}\n"
        f"{_section(raw_out,'stdout')}\n"
        f"{_section(raw_err,'stderr')}"
    )

    return output
