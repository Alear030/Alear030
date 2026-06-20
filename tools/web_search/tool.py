import os
import time

from dotenv import load_dotenv
from tools._tool_register import register_tool
from ddgs import DDGS
from core import *
from pathlib import Path

load_dotenv()
search_goal_url = os.getenv('HTTP_PROXY')

tool_desc = '用于关键词批量搜索,得到相关网页标题、链接、概述'


tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8').strip()
    tool_prompt = tool_prompt_content if tool_prompt_content else None
else:
    tool_prompt = None


@register_tool(tool_name='web_search',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,role=['main'])
def web_search(key_word:str):
    for round in range(3):
        try:
            with DDGS(search_goal_url) as ddg:
                rq_list = list(ddg.text(key_word,max_results=10))
                rq_return = []

                for i,r in enumerate(rq_list,1):
                    title = r['title']
                    href = r['href']
                    desc = r['body']

                    line = f'标题：{title} 链接：{href} 描述：{desc}'
                    rq_return.append(line)
        except Exception as EE:
            rich_print(f'web_search error:{EE}',type='system_error')
            time.sleep(1)
        else:
            break
    else:
        rich_print('web_search attempt all fail.....',type='system_error')
        return 'web_search all fail to try'
    
    return '\n\n'.join(rq_return)
    