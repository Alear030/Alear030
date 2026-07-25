from pathlib import Path
from tool.tool_core import register_tool

from config import WORK_SPACE

MAX_RESULTS = 200

tool_desc = '按文件名glob模式查找文件，返回按修改时间排序的文件路径列表'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'

if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else None
else:
    tool_prompt = None

@register_tool(tool_name='file_glob',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='file_read_tool')
def file_glob(pattern:str,path:str=None,**kwargs)->str:
    search_path = Path(path) if path else WORK_SPACE

    if not search_path.is_absolute():
        return f"错误: path 必须是绝对路径，收到: {path}"

    if not search_path.exists():
        return f"错误: 目录不存在: {search_path}"

    if not search_path.is_dir():
        return f"错误: path 必须是目录: {search_path}"

    try:
        matched_files = [f for f in search_path.glob(pattern) if f.is_file()]
    except Exception as ee:
        return f"错误: pattern 无效: {ee}"

    if not matched_files:
        return f"[file_glob] 未找到匹配文件: pattern={pattern}, path={search_path}"

    matched_files.sort(key=lambda f:f.stat().st_mtime,reverse=True)

    # 总数要在截断前记下,否则达上限时永远只会报 MAX_RESULTS,真实匹配量丢失
    matched_total = len(matched_files)
    truncated = matched_total > MAX_RESULTS
    matched_files = matched_files[:MAX_RESULTS]

    header = f"[file_glob] 匹配到 {matched_total} 个文件"
    if truncated:
        header += f"（已达单次上限 {MAX_RESULTS} 条，仅显示前 {MAX_RESULTS} 条，请缩小 pattern 范围）"

    return header + '\n\n' + '\n'.join(str(f) for f in matched_files)
