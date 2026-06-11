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
def rich_print(message:set,type:str=None):
    match type:
        case 'thinking':
            console.print(Panel(message,title='Thinking',title_align='left',style='#7ab8f3'))
        case 'content':
            console.print(Panel(Markdown(message),title='Assistant',title_align='left',style='#4a90d9'))
        case 'tool_call':
            console.print(Panel(message,title='tool_call',title_align='left',style='#EEFF6D'))
        case 'tool_result':
            console.print(Panel(message,title='tool_result',title_align='left',style="#C9DD42"))
        case 'system_error':
            console.print(Panel(message,title='system_error',title_align='left',style="#ED3A3A"))