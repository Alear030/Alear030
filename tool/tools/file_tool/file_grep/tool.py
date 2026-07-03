import re

from pathlib import Path
from tool.tool_core import register_tool

from config import WORK_SPACE

MAX_RESULT_LINES = 200

tool_desc = '在指定目录或文件中按正则表达式搜索文本内容，返回匹配的文件路径、行号和行内容'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'

if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else None
else:
    tool_prompt = None

@register_tool(tool_name='file_grep',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='file_read_tool')
def file_grep(pattern:str,path:str=None,glob:str=None)->str:
    search_path = Path(path) if path else WORK_SPACE

    if not search_path.absolute():
        return f"错误: path 必须是绝对路径，收到: {path}"

    if not search_path.exists():
        return f"错误: 路径不存在: {search_path}"

    try:
        regex = re.compile(pattern)
    except re.error as ee:
        return f"错误: pattern 不是合法的正则表达式: {ee}"

    if search_path.is_file():
        candidate_files = [search_path]
    else:
        candidate_files = [f for f in search_path.rglob(glob if glob else '*') if f.is_file()]

    results = []
    for file in candidate_files:
        try:
            lines = file.read_text(encoding='utf-8').splitlines()
        except (UnicodeDecodeError,PermissionError,OSError):
            continue

        for line_num,line in enumerate(lines,start=1):
            if regex.search(line):
                results.append(f'{file}:{line_num}:{line}')
                if len(results) >= MAX_RESULT_LINES:
                    break
        if len(results) >= MAX_RESULT_LINES:
            break

    if not results:
        return f"[file_grep] 未找到匹配内容: pattern={pattern}, path={search_path}"

    header = f"[file_grep] 匹配到 {len(results)} 行"
    if len(results) >= MAX_RESULT_LINES:
        header += f"（已达单次上限 {MAX_RESULT_LINES} 行，请使用 glob 缩小搜索范围）"

    return header + '\n\n' + '\n'.join(results)
