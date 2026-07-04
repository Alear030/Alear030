from pathlib import Path
from tool.tool_core import register_tool

from config import WORK_SPACE
from rich_output import rich_print

tool_desc = '创建或覆盖本地文本文件，会自动创建父目录'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'

if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else None
else:
    tool_prompt = None

@register_tool(tool_name='file_write',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='file_write_tool')
def file_write(file_path:str,content:str,**kwargs)->str:
    path = Path(file_path)

    if not path.absolute():
        return f"错误: file_path 必须是绝对路径，收到: {file_path}"
    
    if path.exists() and path.is_dir():
        return f"错误: 目标路径是目录，不能作为文件写入: {file_path}"
    
    path_exist = path.exists()

    if not path.resolve().is_relative_to(WORK_SPACE):
        rich_print(message='⚠️ AGENT正在尝试在非工作空间中写入文件',type='system_error')
        return f'错误，当前写入路径非工作空间，学习模式下不可在工作空间外写入文件，工作空间地址：{WORK_SPACE}'

    try:
        path.parent.mkdir(parents=True,exist_ok=True)
    except Exception as ee:
        return f'error can not creat father directory {ee}'
    
    try:
        path.write_text(content,encoding='utf-8')
    except Exception as ee:
        return f'error cannot write this file {ee}'
    
    char_count = len(content)
    status = '已覆盖' if path_exist else '已写入'

    tool_result = f'[file_write] {status}文件:{file_path}\n写入字符数:{char_count}'
    if path_exist:
        tool_result = f"[file_writer] 警告: 文件已存在，已覆盖原内容\n路径: {file_path}\n写入字符数: {char_count}"

    return tool_result


    

