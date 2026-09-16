from pathlib import Path

from prompt import prompt
from config import FILE_EDIT_SANDBOX

PROMPT_DIR = Path(__file__).parent


# file_write/file_edit 的写入沙箱说明,随 FILE_EDIT_SANDBOX 出现与否
# 不放进 tool_prompt:工具 schema 是请求里最大的稳定前缀,随配置变化会让不同配置的 checkout 各持一份 schema、互相挤缓存;
# 走 attachment 的代价是会话压缩后与 subagent 都收不到这段说明,闸门本身不受影响;关闭时返回空串,game_begin 不投
# target 只写 main:投递管线只有主 Loop 挂着,被授予 file_write_tool 的 subagent 只能靠工具返回的错误文案
@prompt.register_prompt(prompt_name='file_sandbox_prompt',order=15,type="notification",target=['main'])
def build()->str:
    if not FILE_EDIT_SANDBOX:
        return ''
    sandbox_prompt_file = PROMPT_DIR/'file_sandbox_prompt.md'
    if not sandbox_prompt_file.exists():
        return ''
    return sandbox_prompt_file.read_text(encoding='utf-8').strip()
