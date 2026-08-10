import os
import time
import json

from dataclasses import asdict
from dotenv import load_dotenv
from tool.tool_core import register_tool,ToolCallResult
from ddgs import DDGS
from rich_output import rich_print
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed

load_dotenv()
# DDGS 走代理，从环境变量取
search_goal_url = None
if os.getenv('HTTP_PROXY'):
    search_goal_url = os.getenv('HTTP_PROXY')

tool_desc = '用于关键词批量并行搜索,得到相关网页标题、链接、概述'


tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8').strip()
    tool_prompt = tool_prompt_content if tool_prompt_content else None
else:
    tool_prompt = None


@register_tool(tool_name='web_search',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='web_tool')
def web_search(key_words:list[str],**kwargs)->ToolCallResult:

    emit = kwargs.get('emit',None)
    tcr = kwargs.get('tcr',None)

    # tcr 注入判空，match_tool 总传，直接调用兜底报错
    if tcr is None:
        return 'web_search 缺少 tcr 注入，请通过 match_tool 调用'

    # 空/空白关键词短路，避免线程池 max_workers=0 或空串进搜索
    key_words = [k for k in (key_words or []) if k and str(k).strip()]
    if not key_words:
        msg = 'web_search 未传入关键词，请传入关键词重试'
        tcr.tool_call_state = {'tool_call_state':'error'}
        tcr.tool_call_extra_info = [{
            "id":"tool_call_error_info",
            "type":"Horizontal",
            "content":[
                {"id":"tool_call_error_info_pointer","type":"Static","content":"⎿","css":{"color":"rgba(255,255,255,0.5)","width":"2","height":"auto"}},
                {"id":"tool_call_error_info_message","type":"Static","content":msg,"css":{"color":"rgba(255,255,255,0.5)","width":"100%","height":"auto"}}
            ],
            "css":{"width":"100%","height":"auto"}
        }]
        tcr.tool_call_result = {'role':'tool','tool_call_id':tcr.tool_call_id,'content':json.dumps({'error':'empty_key_words','message':msg},ensure_ascii=False)}
        if emit:
            emit(content=asdict(tcr))
        return tcr

    # 更新 tool_call_state tool_name tool_call_extra_info
    key_words_str = ' '.join(key_words)
    tcr.tool_call_state = {'tool_call_state':'processing'}
    tcr.tool_call_extra_info = [{
        "id": "web_search_proceed_info",
        "type": "Horizontal",
        "content": [
            {"id": "web_search_proceed_info_pointer", "type": "Static", "content": "⎿", "css": {"color": "rgba(255,255,255,0.5)", "width": "2","height":"auto"}},
            {"id": "web_search_proceed_info_message", "type": "Static", "content": f"searching for: {key_words_str}", "css": {"color": "rgba(255,255,255,0.5)", "width": "100%","height":"auto"}}
        ],
        "css":{"width":"100%","height":"auto"}
    }]
    # 有 emit 则发送 TUI 重新渲染 tool_call_widget
    if emit:
        emit(content=asdict(tcr))

    # 单个关键词的搜索逻辑，供线程池并行调用
    def _search_one(key_word:str)->dict:
        # 失败重试，最多 3 次
        for attempt in range(3):
            try:
                with DDGS(search_goal_url) as ddg:
                    rq_list = list(ddg.text(key_word,max_results=10))
                    rq_return = []

                    for i,r in enumerate(rq_list,1):
                        title = r['title']
                        href = r['href']
                        desc = r['body']
                        line = f'{i}. 标题：{title} 链接：{href} 描述：{desc}'
                        rq_return.append(line)
            except Exception as EE:
                rich_print(f'web_search error:{EE}',type='system_error')
                time.sleep(1)
            else:
                return {'key_word':key_word,'result':'\n\n'.join(rq_return),'success':True}
        rich_print(f'web_search attempt all fail for {key_word}.....',type='system_error')
        return {'key_word':key_word,'result':'web_search all fail to try','success':False}

    # 线程池并行调用单个关键词的搜索逻辑
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
                results.append({'key_word':key_word,'result':f'web_search 失败: {EE}','success':False})

    # 任一关键词成功即整体 success，部分失败条目仍回传模型
    success_list = [item for item in results if item.get('success')]
    tool_call_result_flag = bool(success_list)
    fail_key_words = [item['key_word'] for item in results if not item.get('success')]

    if tool_call_result_flag:
        state = 'success'
        state_message = f'web_search completed：{len(success_list)}/{len(results)} keywords succeeded'
    else:
        state = 'error'
        state_message = f' failed:{", ".join(fail_key_words)}'

    tcr.tool_call_state = {'tool_call_state':state}
    tcr.tool_call_result = {'role':'tool','tool_call_id':tcr.tool_call_id,'content':json.dumps(results,ensure_ascii=False)}
    # 收尾写状态与结果，进度提示替换为结果态
    tcr.tool_call_extra_info = [{
        "id": "web_search_proceed_info",
        "type": "Horizontal",
        "content": [
            {"id": "web_search_proceed_info_pointer", "type": "Static", "content": "⎿", "css": {"color": "rgba(255,255,255,0.5)", "width": "2","height":"auto"}},
            {"id": "web_search_proceed_info_message", "type": "Static", "content": state_message, "css": {"color": "rgba(255,255,255,0.5)", "width": "100%","height":"auto"}}
        ],
        "css":{"width":"100%","height":"auto"}
    }]

    # 发送最终态给 TUI 更新 widget
    if emit:
        emit(content=asdict(tcr))

    return tcr
