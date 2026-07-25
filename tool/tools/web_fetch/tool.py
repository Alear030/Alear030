import time
import json
import requests

from bs4 import BeautifulSoup
from tool.tool_core import register_tool
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from loop import *

tool_desc = '用于批量抓取多个URL的网页内容'

tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content else None
else:
    tool_prompt = None


# 单个URL的抓取逻辑，供线程池并行调用
def _fetch_one(url:str)->dict:
    error = None
    for round in range(3):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, 'html.parser')
            # 去掉 script/style
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()

            text = soup.get_text(separator='\n', strip=True)
            # 去空行，截断到 5000 字符
            lines = [l for l in text.split('\n') if l.strip()]
            return {'url':url,'content':'\n'.join(lines)[:5000]}

        except Exception as e:
            error = e
            time.sleep(1)

    return {'url':url,'content':f'web_fetch 失败: {error}'}


@register_tool(tool_name='web_fetch',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='web_tool')
def web_fetch(urls: list[str], **kwargs) -> str:
    # 空列表会让下面的 max_workers=0，ThreadPoolExecutor 直接抛 ValueError
    if not urls:
        return '错误: urls 不能为空，请至少传入一个 URL'

    with ThreadPoolExecutor(max_workers=min(len(urls),5)) as tp:
        fetch_queue = {
            tp.submit(_fetch_one,url):url for url in urls
        }
        results = []
        for thread in as_completed(fetch_queue):
            try:
                results.append(thread.result())
            except Exception as e:
                url = fetch_queue[thread]
                results.append({'url':url,'content':f'web_fetch 失败: {e}'})

    return json.dumps(results,ensure_ascii=False)