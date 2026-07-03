import time
import requests

from bs4 import BeautifulSoup
from tool.tool_core import register_tool
from pathlib import Path
from loop import *

tool_desc = '用于抓取指定URL的网页内容'

tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content else None
else:
    tool_prompt = None


@register_tool(tool_name='web_fetch',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='web_tool')
def web_fetch(url: str) -> str:
    print(f'web_fetching {url}...')
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
            return '\n'.join(lines)[:5000]

        except Exception as e:
            time.sleep(1)
    else:
        return f'web_fetch 失败: {error}'