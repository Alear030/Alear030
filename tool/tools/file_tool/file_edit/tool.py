from pathlib import Path
from tool.tool_core import register_tool

from config import WORK_SPACE
from rich_output import rich_print

tool_desc = '对已存在的本地文本文件做局部字符串替换，无需覆盖整个文件'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'

if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else None
else:
    tool_prompt = None

@register_tool(tool_name='file_edit',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='file_write_tool')
def file_edit(file_path:str,old_string:str,new_string:str,replace_all:bool=False,**kwargs)->str:
    path = Path(file_path)

    if not path.absolute():
        return f"错误: file_path 必须是绝对路径，收到: {file_path}"

    if not path.resolve().is_relative_to(WORK_SPACE):
        rich_print(message='⚠️ AGENT正在尝试在非工作空间中编辑文件',type='system_error')
        return f'错误，当前编辑路径非工作空间，学习模式下不可在工作空间外编辑文件，工作空间地址：{WORK_SPACE}'

    if not path.exists():
        return f"错误: 文件不存在，file_edit 只能编辑已存在的文件，如需创建新文件请使用 file_write: {file_path}"

    if path.is_dir():
        return f"错误: 目标路径是目录，不能作为文件编辑: {file_path}"

    if old_string == new_string:
        return "错误: old_string 和 new_string 相同，没有实际改动"

    try:
        content = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return f'错误: 文件不是UTF-8编码,无法正确读取: {file_path}'
    except Exception as ee:
        return f'错误: 读取文件失败: {ee}'

    match_count = content.count(old_string)

    if match_count == 0:
        return f"错误: 在文件中未找到匹配的 old_string，请检查内容是否完全一致（包括空白字符）: {file_path}"

    if match_count > 1 and not replace_all:
        return f"错误: old_string 在文件中出现了 {match_count} 次，不唯一。请提供更多上下文使其唯一，或传入 replace_all=True 替换全部"

    if replace_all:
        new_content = content.replace(old_string,new_string)
        replaced_count = match_count
    else:
        new_content = content.replace(old_string,new_string,1)
        replaced_count = 1

    try:
        path.write_text(new_content,encoding='utf-8')
    except Exception as ee:
        return f'错误: 写入文件失败: {ee}'

    char_diff = len(new_content) - len(content)
    char_diff_str = f'+{char_diff}' if char_diff >= 0 else str(char_diff)

    return f'[file_edit] 已编辑文件: {file_path}\n替换次数: {replaced_count}\n字符数变化: {char_diff_str}'
