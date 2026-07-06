import subprocess
import locale
from pathlib import Path
from tool.tool_core import register_tool
from .security import validate_command,is_destructive_category,is_write_category,COMMAND_WHITELIST

MAX_TIMEOUT = 120

# ── 编码处理 ──
# Windows 中文环境默认 GBK (cp936)，Linux/macOS 默认 UTF-8。
# 硬编码 utf-8 会导致 Windows 下中文命令输出乱码。
# locale.getpreferredencoding() 自动获取系统实际编码。
_SYSTEM_ENCODING = locale.getpreferredencoding(do_setlocale=False)

tool_desc = '执行本地 shell 命令（白名单安全模型），返回退出码、stdout 和 stderr'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else None
else:
    tool_prompt = None

# 白名单命令清单直接从 COMMAND_WHITELIST 生成并拼进 tool_prompt，避免文档与代码脱节导致模型盲猜命令名
_whitelist_names = ', '.join(sorted(COMMAND_WHITELIST.keys()))
_whitelist_block = f'\n\n当前系统可用命令（白名单，未列出的命令名会被拒绝）:\n{_whitelist_names}'
tool_prompt = (tool_prompt or '') + _whitelist_block


@register_tool(tool_name='command',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='command_tool')
def command(command:str,timeout:int=120,**kwargs)->str:
    safe, reason, category, destructive_warning = validate_command(command)

    if not safe:
        return (
            f"[command_runner] ❌ 安全验证未通过\n"
            f"命令: {command}\n"
            f"类别: {category}\n"
            f"原因: {reason}\n"
            f"\n提示: 该命令或其 flag 不在安全白名单中。"
            f"如需执行，请手动在终端中运行。"
        )
    
    if is_destructive_category(category):
        return (
            f"[command_runner] ❌ 拒绝执行破坏性操作\n"
            f"命令: {command}\n"
            f"类别: {category}\n"
            f"原因: {reason}\n"
            f"\n该命令属于破坏性操作，已自动拒绝。"
        )
    
    if timeout <= 0:
        return f"[command_runner] 错误: timeout 必须大于 0，收到: {timeout}"
    if timeout > MAX_TIMEOUT:
        timeout = MAX_TIMEOUT

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding=_SYSTEM_ENCODING,
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (
            f"[command_runner] ⏰ 命令超时\n"
            f"命令: {command}\n"
            f"超时时间: {timeout} 秒"
        )
    except Exception as e:
        return (
            f"[command_runner] ❌ 命令执行异常\n"
            f"命令: {command}\n"
            f"错误: {type(e).__name__}: {e}"
        )
    
    stdout = result.stdout.strip() if result.stdout else "(无输出)"
    stderr = result.stderr.strip() if result.stderr else "(无输出)"
    exit_code = result.returncode

    category_label = {
        "read": "📖 只读", "write": "✏️ 写入", "neutral": "⚪ 中性"
    }.get(category, f"🏷️ {category}")

    warning_line = ""
    if destructive_warning:
        warning_line = f"\n⚠️ 警告: {destructive_warning}"

    output = (
        f"[command_runner] 命令执行完成 [{category_label}]{warning_line}\n"
        f"命令: {command}\n"
        f"退出码: {exit_code}\n"
        f"\n--- stdout ---\n{stdout}\n"
        f"\n--- stderr ---\n{stderr}"
    )

    return output