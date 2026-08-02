from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.theme import Theme

output_theme = Theme({
    "markdown.h1": "bold #3b7dd8",
    # 次深：二级标题
    "markdown.h2": "bold #4a90d9",
    # 中蓝：三级标题
    "markdown.h3": "bold #569cd6",
    # 偏灰蓝：引用块（和文字区分开）
    "markdown.block_quote": "#6ba5d1",
    # 浅蓝：行内代码
    "markdown.code": "#7db8e0",
    # 表格边框：淡蓝
    "markdown.table.border": "#8ec5e5",
    # 表格表头：中蓝
    "markdown.table.header": "bold #569cd6",
    # 列表符号、分割线等杂项：最淡
    "markdown.item.bullet": "#9fd2ef",
    "markdown.hr": "#9fd2ef",
})

console = Console(theme=output_theme)

# 中间信息的接收器注册表：TUI 等非终端环境可以注册自己的接收器来消费 rich_print 事件。
# 只要有任何接收器注册，rich_print 就不再往 terminal console 输出，全部转给接收器。
# 接收器签名：recv(event_type: str, message: str, meta: dict | None = None) -> None
_output_receivers: list = []
# 终端 fallback 流式缓冲：stream_id -> 累积文本
_stream_buffers: dict[str, str] = {}


def register_output_receiver(recv) -> None:
    """注册一个中间信息接收器，返回 None。

    同一个接收器重复注册会被重复调用，调用方自己保证去重。
    """
    _output_receivers.append(recv)


def unregister_output_receiver(recv) -> None:
    """注销一个已注册的接收器。不存在时静默跳过。"""
    try:
        _output_receivers.remove(recv)
    except ValueError:
        pass


# 后续需要增加agent的name、role、type
def rich_print(message:str,type:str=None):
    # 临时截断：TUI 占终端时 rich 直写会撞崩 Windows 控制台；后续整删 rich_output
    return
    message = message if message else ''
    event_type = type or 'none'
    # 有接收器就全部推给接收器，不再打终端
    if _output_receivers:
        for recv in _output_receivers:
            recv(event_type, message)
        return
    try:
        match type:
            case 'agent_thinking':
                console.print(Panel(message,title='Thinking',title_align='left',style="#C1EEFF",border_style='dim',padding=(0,1)))
            case 'subagent_thinking':
                console.print(Panel(message,title='Subagent Thinking',title_align='left',style="#b8f0b8",border_style='dim',padding=(0,1)))
            case 'agent_content':
                console.print(Panel(Markdown(message),title='Assistant',title_align='left',style="#62aeff"))
            case 'tool_call':
                console.print(Panel(message,title='tool_call',title_align='left',style="#F9FFD0"))
            case 'tool_result':
                console.print(Panel(message,title='tool_result',title_align='left',style="#DBE0B4"))
            case 'system_message':
                console.print(Panel(message,title='system_message',title_align='left',style="#B1B1B1"))
            case 'system_error':
                console.print(Panel(message,title='system_error',title_align='left',style="#ED3A3A"))
            case _:
                console.print(Panel(message,title='none',title_align='left',style="#FFFFFF"))
    except UnicodeEncodeError:
        # Windows GBK console 遇到非GBK字符(如¥)时 legacy_windows_render 崩溃,降级二进制写避免中断
        import sys
        sys.stdout.buffer.write(f'[{type or "none"}] '.encode('utf-8',errors='replace'))
        sys.stdout.buffer.write(message.encode('utf-8',errors='replace'))
        sys.stdout.buffer.write(b'\n')
        sys.stdout.flush()
