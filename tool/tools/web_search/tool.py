import os
import time
import json

from dotenv import load_dotenv
from tool.tool_core import register_tool
from ddgs import DDGS
from rich_output import rich_print
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed

load_dotenv()
search_goal_url = os.getenv('HTTP_PROXY')

tool_desc = '用于关键词批量并行搜索,得到相关网页标题、链接、概述'


tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8').strip()
    tool_prompt = tool_prompt_content if tool_prompt_content else None
else:
    tool_prompt = None


# 单个关键词的搜索逻辑，供线程池并行调用
def _search_one(key_word:str)->dict:
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
            return {'key_word':key_word,'result':'\n\n'.join(rq_return)}

    rich_print(f'web_search attempt all fail for {key_word}.....',type='system_error')
    return {'key_word':key_word,'result':'web_search all fail to try'}


@register_tool(tool_name='web_search',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='web_tool')
def web_search(key_words:list[str])->str:
    with ThreadPoolExecutor(max_workers=min(len(key_words),5)) as tp:
        search_queue = {
            tp.submit(_search_one,key_word):key_word for key_word in key_words
        }
        results = []
        for thread in as_completed(search_queue):
            try:
                results.append(thread.result())
            except Exception as EE:
                key_word = search_queue[thread]
                rich_print(f'web_search error:{EE}',type='system_error')
                results.append({'key_word':key_word,'result':f'web_search 失败: {EE}'})

    return json.dumps(results,ensure_ascii=False)
