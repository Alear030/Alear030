from tool.tool_core import register_tool
from pathlib import Path

MAX_LINES = 2000

tool_desc = '用于读取本地文件，支持行号、offset和limit'

tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8').strip()
    tool_prompt = tool_prompt_content if tool_prompt_content else None
else:
    tool_prompt = None

@register_tool(tool_name='file_read',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='file_read_tool')
def file_read(file_path:str,offset:int=0,limit:int=2000)->str:
    file_path = Path(file_path)

    if not file_path.absolute():
        return f'错误:file_path必须是绝对路径，收到{file_path}'
    
    if not file_path.exists():
        return f'错误:文件不存在:{file_path}'
    
    if file_path.is_dir():
        return f'错误:这是一个目录而非文件:{file_path}'
    
    if offset < 0:
        return f'错误:offset不能为负数，收到的是:{offset}'
    
    if limit<=0:
        return f'错误:limit必须大于0,收到的是{limit}'
    
    if limit >= MAX_LINES:
        limit = MAX_LINES

    try:
        file_content = file_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return f'错误:文件不是UTF-8编码,无法正确读取:{file_path}'
    except Exception as ee:
        return f'错误:读取文件失败:{ee}'

    if not file_content.strip():
        return f"警告：文件内容为空:{file_path}"
    
    lines = file_content.splitlines()
    lines_total = len(lines)

    if offset >= lines_total:
        return f"提示:文件共有{lines_total}行内容，offset={offset}已超出范围"
    
    lines_selected = lines[offset:offset+limit]
    selected_line = len(lines_selected)

    lines_contents = []
    for i,line in enumerate(lines_selected):
        line_num = offset+i+1
        lines_contents.append(f'{line_num:6}\t{line}')

    line_end = offset + selected_line
    file_header = f'[file_reader]文件：{file_path}\n总行数:{lines_total},显示:{offset+1} - {line_end}'

    if limit == MAX_LINES and selected_line == MAX_LINES:
        file_header = f'\n已达到单次读取文本上限{MAX_LINES}行，如需继续读取请使用offset继续读取'

    return file_header + '\n\n' + '\n'.join(lines_contents)
