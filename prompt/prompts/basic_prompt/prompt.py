from datetime import datetime

from prompt import prompt


# 系统基础提示，注入当前系统时间
# 每次进程启动重新求值,放 system prompt 会把它之后的工具 schema 一起顶出缓存,故走 attachment
# target 只写 main:投递管线只有主 Loop 挂着,投给别的 agent 会永远滞留在 attachment_list
@prompt.register_prompt(prompt_name='basic_prompt',order=50,type="notification",target=['main'])
def build()->str:
    time_now = datetime.now()
    return '#系统基础提示' + '\n\n' + f'当前系统时间为:{time_now}'
