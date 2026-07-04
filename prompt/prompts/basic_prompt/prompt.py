from datetime import datetime

from prompt.prompt_register import register_prompt


# 系统基础提示，注入当前系统时间
@register_prompt(prompt_name='basic_prompt',order=50)
def build(agent)->str:
    time_now = datetime.now()
    return '#系统基础提示' + '\n\n' + f'当前系统时间为:{time_now}'
