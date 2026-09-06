from datetime import datetime

from prompt import prompt


# 系统基础提示，注入当前系统时间
# 每次进程启动重新求值,放 system prompt 会把它之后的工具 schema 一起顶出缓存,故走 attachment
# target 用哨兵 all 不写死名单:agents.yaml 加了新 agent 也能跟着拿到时间
@prompt.register_prompt(prompt_name='basic_prompt',order=50,type="notification",target=['all'])
def build()->str:
    time_now = datetime.now()
    return '#系统基础提示' + '\n\n' + f'当前系统时间为:{time_now}'
