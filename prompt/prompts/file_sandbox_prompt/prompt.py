from pathlib import Path

from prompt import prompt
from config import FILE_EDIT_SANDBOX

PROMPT_DIR = Path(__file__).parent


# file_write/file_edit 的写入沙箱说明,随 FILE_EDIT_SANDBOX 出现与否
# 放进 tool_prompt 会让开关改动 system prompt 前缀、破坏缓存,故走 attachment;关闭时返回空串,game_begin 不投
# target 只写 main:投递管线只有主 Loop 挂着,被授予 file_write_tool 的 subagent 只能靠工具返回的错误文案
@prompt.register_prompt(prompt_name='file_sandbox_prompt',order=15,type="notification",target=['main'])
def build()->str:
    if not FILE_EDIT_SANDBOX:
        return ''
    sandbox_prompt_file = PROMPT_DIR/'file_sandbox_prompt.md'
    if not sandbox_prompt_file.exists():
        return ''
    return sandbox_prompt_file.read_text(encoding='utf-8').strip()
