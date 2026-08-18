from tool.tool_core import register_tool,tool_call_processing
from pathlib import Path

MAX_LINES = 2000
MAX_LINE_CHARS = 2000
# 行数与单行两个上限的乘积没人管:2000行×2000字符可达400万字符(约百万token),
# 曾把模型请求整个打爆且压缩机制来不及触发。同目录 file_glob/file_grep/web_fetch
# 都有总量约束,这里补齐。约2.5万token,正常2000行源码文件基本触不到。
MAX_TOTAL_CHARS = 100_000

tool_desc = '用于读取本地文件，支持行号、offset和limit'

tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8').strip()
    tool_prompt = tool_prompt_content if tool_prompt_content else None
else:
    tool_prompt = None

@register_tool(tool_name='file_read',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='file_read_tool')
def file_read(file_path:str,offset:int=0,limit:int=2000,**kwargs)->str:
    # 执行tool_call_processing
    tool_call_processing(kwargs.get('tcr',None),kwargs.get('emit',None))

    file_path = Path(file_path)

    if not file_path.is_absolute():
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
    total_chars = 0
    char_capped = False
    for i,line in enumerate(lines_selected):
        line_num = offset+i+1
        # 单行超长(压缩JSON/无换行日志)时MAX_LINES挡不住,这里单独卡字符数兜底
        if len(line) > MAX_LINE_CHARS:
            line = line[:MAX_LINE_CHARS] + f'...[该行已截断，原长{len(line)}字符]'
        # 累计在单行截断之后算,否则一条超长行就能把预算算成天文数字;
        # lines_contents 非空才允许中断,保证至少吐一行、offset 能往前推,不然模型会原地打转
        if total_chars+len(line) > MAX_TOTAL_CHARS and lines_contents:
            char_capped = True
            break
        total_chars += len(line)
        lines_contents.append(f'{line_num:6}\t{line}')

    # 字符预算可能提前中断,实际吐了几行以 lines_contents 为准,不能再用 selected_line
    line_end = offset + len(lines_contents)
    file_header = f'[file_read]文件：{file_path}\n总行数:{lines_total},显示:{offset+1} - {line_end}'

    # 追加而非覆盖:覆盖会丢掉文件路径/总行数/当前范围,agent 就不知道该用哪个 offset 接着读
    # 字符上限复用同一条 offset 续读协议,不另起一种截断形态
    if char_capped:
        file_header += f'\n已达到单次读取字符上限{MAX_TOTAL_CHARS}，如需继续读取请使用offset={line_end}继续读取'
    elif limit == MAX_LINES and selected_line == MAX_LINES:
        file_header += f'\n已达到单次读取文本上限{MAX_LINES}行，如需继续读取请使用offset={line_end}继续读取'

    return file_header + '\n\n' + '\n'.join(lines_contents)
