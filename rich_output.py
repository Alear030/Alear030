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

# 后续需要增加agent的name、role、type
def rich_print(message:str,type:str=None):
    message = message if message else ''
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