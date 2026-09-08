import time
import json
import requests

from dataclasses import asdict
from bs4 import BeautifulSoup
from tool.tool_core import tool,ToolCallResult
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed

tool_desc = '用于批量抓取多个URL的网页内容'

# 失败 content 的统一前缀：web_fetch() 收尾展示失败列表时靠 removeprefix 摘原因，写读两端必须同源
_FAIL_PREFIX = 'web_fetch 失败: '

tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content else None
else:
    tool_prompt = None

# 交付前自检阈值——保守起点，防止误杀正常静态页；宁可漏报不误杀
_MAX_CONTENT_CHARS = 5000
_MIN_CONTENT_CHARS = 200
_SHORT_LINE_LEN = 20
_SHORT_LINE_RATIO_SUSPECT = 0.7
_UNIQUE_LINE_RATIO_SUSPECT = 0.5
_REPLACEMENT_RATIO_REJECT = 0.05
_CONTROL_CHAR_RATIO_REJECT = 0.03
_CONTROL_CHAR_LOW = '\x80'
_CONTROL_CHAR_HIGH = '\x9f'


def _ratio(count:int, total:int)->float:
    return count / total if total else 0.0


# 质量判定（样板页/JS 渲染页）与编码判定（乱码）共用的交付前自检；返回 (verdict, reason, diagnostics)
def _assess_content(lines:list[str], full_text:str)->tuple[str,str|None,dict]:
    total_chars = len(full_text)
    # 替换字符与控制字符共用一次遍历，避免对未截断的整段正文分别扫两遍
    replacement_count = 0
    control_count = 0
    for c in full_text:
        if c == '�':
            replacement_count += 1
        elif _CONTROL_CHAR_LOW <= c <= _CONTROL_CHAR_HIGH:
            control_count += 1
    replacement_ratio = _ratio(replacement_count, total_chars)
    control_ratio = _ratio(control_count, total_chars)
    short_line_ratio = _ratio(sum(1 for l in lines if len(l) <= _SHORT_LINE_LEN), len(lines))
    # short_line_ratio 只测行长度，测不出「长行反复出现」这类样板；唯一行占比补上重复度这一维
    unique_line_ratio = _ratio(len(set(lines)), len(lines))

    diagnostics = {
        'extracted_chars': total_chars,
        'short_line_ratio': round(short_line_ratio, 3),
        'unique_line_ratio': round(unique_line_ratio, 3),
        'replacement_char_ratio': round(replacement_ratio, 4),
        'control_char_ratio': round(control_ratio, 4),
    }
    # total_chars 为 0 时 replacement_ratio/control_ratio 已是 0.0，天然落不进这条判据，不用再额外判 total_chars
    if replacement_ratio > _REPLACEMENT_RATIO_REJECT or control_ratio > _CONTROL_CHAR_RATIO_REJECT:
        return 'reject','疑似编码解析失败（替换字符/控制字符占比过高）',diagnostics
    if (total_chars < _MIN_CONTENT_CHARS or short_line_ratio > _SHORT_LINE_RATIO_SUSPECT
            or (lines and unique_line_ratio < _UNIQUE_LINE_RATIO_SUSPECT)):
        return 'suspect','疑似 JS 渲染页或样板内容，正文信息量过低',diagnostics
    return 'ok',None,diagnostics


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

            # 用 resp.content（字节）而非 resp.text，交给 BeautifulSoup 的 UnicodeDammit 做编码探测；
            # 只有 HTTP 头显式声明了 charset 才作为覆盖优先级传入，避免 requests 对无声明响应默认猜 ISO-8859-1 污染判断
            content_type = resp.headers.get('Content-Type', '')
            from_encoding = resp.encoding if 'charset=' in content_type.lower() else None
            soup = BeautifulSoup(resp.content, 'html.parser', from_encoding=from_encoding)
            # 去掉 script/style
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()

            text = soup.get_text(separator='\n', strip=True)
            # 去空行
            lines = [l for l in text.split('\n') if l.strip()]
            full_text = '\n'.join(lines)
            verdict,reason,diagnostics = _assess_content(lines, full_text)
            if verdict == 'reject':
                # content 只放分类结论：TUI 失败列表靠 removeprefix 摘这段展示给人看，原始片段挪进 diagnostics，只给模型看，不用迁就人类可读的截断长度
                content = f'{_FAIL_PREFIX}{reason}'
                # unicode_escape 把触发 reject 的替换字符/C1 控制字符转成 \xNN 打印形式，
                # 避免这些字符原样经 json.dumps(ensure_ascii=False) 落进 trace，重现 issue #141 里那种 trace 幻影损坏
                diagnostics['raw_snippet'] = full_text[:100].encode('unicode_escape').decode('ascii')
            else:
                # 先剔后截再交付：C0 只留 \t\n（含 \r 一并剔除），另剔 C1 与替换字符，防低占比残留进 trace
                content = ''.join(c for c in full_text if c in ('\t', '\n') or not (c == '�' or '\x00' <= c <= '\x1f' or '\x7f' <= c <= '\x9f'))[:_MAX_CONTENT_CHARS]
            diagnostics['truncated'] = diagnostics['extracted_chars'] > _MAX_CONTENT_CHARS
            result = {'url':url,'content':content,'success':verdict != 'reject','diagnostics':diagnostics}
            if verdict == 'suspect':
                result['quality_warning'] = reason
            return result

        except Exception as e:
            error = e
            time.sleep(1)

    return {'url':url,'content':f'{_FAIL_PREFIX}{error}','success':False}


@tool.tool_register(tool_name='web_fetch',tool_desc=tool_desc,tool_prompt=tool_prompt,tool_enabled=True,tool_autho='web_tool')
def web_fetch(urls: list[str], **kwargs)->ToolCallResult:

    emit = kwargs.get('emit',None)
    tcr = kwargs.get('tcr',None)

    # tcr 注入判空，match_tool 总传，直接调用兜底报错
    if tcr is None:
        return 'web_fetch 缺少 tcr 注入，请通过 match_tool 调用'

    # 空列表会让下面的 max_workers=0，ThreadPoolExecutor 直接抛 ValueError
    if not urls:
        msg = 'web_fetch 未传入 URL，请至少传入一个 URL 重试'
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
        tcr.tool_call_result = {'role':'tool','tool_call_id':tcr.tool_call_id,'content':json.dumps({'error':'empty_urls','message':msg},ensure_ascii=False)}
        if emit:
            emit(content=asdict(tcr))
        return tcr

    # 更新 tool_call_state tool_call_extra_info，开跑前发 processing 进度
    tcr.tool_call_state = {'tool_call_state':'processing'}
    tcr.tool_call_extra_info = [{
        "id": "web_fetch_proceed_info",
        "type": "Horizontal",
        "content": [
            {"id": "web_fetch_proceed_info_pointer", "type": "Static", "content": "⎿", "css": {"color": "rgba(255,255,255,0.5)", "width": "2","height":"auto"}},
            {"id": "web_fetch_proceed_info_message", "type": "Static", "content": f"fetching {len(urls)} urls...", "css": {"color": "rgba(255,255,255,0.5)", "width": "100%","height":"auto"}}
        ],
        "css":{"width":"100%","height":"auto"}
    }]
    # 有 emit 则发送 TUI 重新渲染 tool_call_widget
    if emit:
        emit(content=asdict(tcr))

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
                results.append({'url':url,'content':f'{_FAIL_PREFIX}{e}','success':False})

    # 任一 URL 成功即整体 success，部分失败条目仍回传模型
    success_list = [item for item in results if item.get('success')]
    tool_call_result_flag = bool(success_list)
    fail_urls = [item['url'] for item in results if not item.get('success')]

    if tool_call_result_flag:
        state = 'success'
    else:
        state = 'error'
    state_message = f'web_fetch completed：{len(success_list)}/{len(results)} urls succeeded'


    tcr.tool_call_state = {'tool_call_state':state}
    tcr.tool_call_result = {'role':'tool','tool_call_id':tcr.tool_call_id,'content':json.dumps(results,ensure_ascii=False)}
    # 收尾写状态与结果，进度提示替换为结果态
    tcr.tool_call_extra_info = [{
        "id": "web_fetch_proceed_info",
        "type": "Horizontal",
        "content": [
            {"id": "web_fetch_proceed_info_pointer", "type": "Static", "content": "⎿", "css": {"color": "rgba(255,255,255,0.5)", "width": "2","height":"auto"}},
            {"id": "web_fetch_proceed_info_message", "type": "Static", "content": state_message, "css": {"color": "rgba(255,255,255,0.5)", "width": "100%","height":"auto"}}
        ],
        "css":{"width":"100%","height":"auto"}
    }]
    # 失败 URL 明细：按原 urls 顺序追加失败项行，成功项不上屏
    fail_items = [item for item in results if not item.get('success')]
    fail_items.sort(key=lambda item: urls.index(item['url']))
    for i,item in enumerate(fail_items):
        reason = item['content'].removeprefix(_FAIL_PREFIX)[:100]
        tcr.tool_call_extra_info.append({
            "id": f"web_fetch_fail_info_{i}",
            "type": "Horizontal",
            "content": [{"id": f"web_fetch_fail_info_{i}_message", "type": "Static", "content": f"{item['url']} -> {reason}", "css": {"color": "rgba(255,255,255,0.5)", "width": "100%","height":"auto","margin-left":"2"}}],
            "css":{"width":"100%","height":"auto"}
        })

    # 发送最终态给 TUI 更新 widget
    if emit:
        emit(content=asdict(tcr))

    return tcr