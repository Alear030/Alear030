import json
import tiktoken

from pathlib import Path


from prompt import prompt
from config import MEMORY_STORAGE_PATH
from log.log_core import Log

timeline_path = MEMORY_STORAGE_PATH/'timeline.json'
timeline = None
if timeline_path.exists():
    # 导入期单点:语法/编码损坏会炸穿启动,build_prompt 隔离够不到模块级,只能就地降级
    # 损坏 → 无时间线分块,pending 记账由 main 构造 Log 时吸收,修复文件重启即恢复
    try:
        timeline_content_raw = timeline_path.read_text(encoding='utf-8').strip()
        if timeline_content_raw:
            timeline = json.loads(timeline_content_raw)
    except Exception as e:
        timeline = None
        Log.pending_record(level='high',source='timeline_prompt',event='timeline_load_skip',detail={
            'error':f'{type(e).__name__}: {e}'
        })

if timeline:
    timeline_enable = True
else:
    timeline_enable = False


# 与 memory_core.py 的 timeline 渲染逻辑保持一致(近段完整叙事线索、远段仅关键词+摘要，
# 按 token 预算分层)，两边各留一份独立实现，不 import memory_core
RECENT_TIMELINE = int(2048)
MIN_FULL_TIMELINE = int(3)
_TOKEN_ENCODING = tiktoken.encoding_for_model(model_name='gpt-4o')


def count_token(text: str) -> int:
    return len(_TOKEN_ENCODING.encode(text))


def render_timeline_entry(entry, timeline_token, timeline_index):
    sid = entry['session_id']
    keywords = '、'.join(entry['keywords'])
    summary = entry.get('summary', '')
    summary_seg = f"。本轮主要讲了{summary}" if isinstance(summary, str) and summary.strip() else ''
    if timeline_index < MIN_FULL_TIMELINE or timeline_token < RECENT_TIMELINE:
        thread = '；'.join(entry['thread'])
        return f"session:{sid}:关键词:{keywords}，总结：{summary_seg}。叙事线索:{thread}"
    return f"session{sid}:关键词:{keywords}，总结：{summary_seg}"


# timeline.json 由 after_session 的 session_timeline hook 写入,跨 session 必变,故走 attachment
@prompt.register_prompt(prompt_name='timeline',order=30,enabled=timeline_enable,type="notification",target=['main'])
def timeline_prompt()->str:
    historical_timeline = list(timeline)
    historical_timeline.reverse()

    timeline_token = 0
    timeline_info = None
    for timeline_index, entry in enumerate(historical_timeline):
        # 内网兜单个条目:一条形状坏只丢这条并带坐标记账,其余时间线照常注入
        try:
            tl_content = render_timeline_entry(entry=entry, timeline_token=timeline_token, timeline_index=timeline_index)
        except Exception as e:
            # timeline_index 换算回 timeline.json 文件序:渲染序是 reverse 后的,直接记账会数错位置
            Log.pending_record(level='medium',source='timeline_prompt',event='timeline_entry_skip',detail={
                'timeline_index':len(historical_timeline)-1-timeline_index,
                'session_id':entry.get('session_id') if isinstance(entry,dict) else None,
                'error':f'{type(e).__name__}: {e}'})
            continue
        timeline_info = timeline_info + '\n\n' + tl_content if timeline_info else tl_content
        timeline_token += count_token(text=tl_content)

    # 全部条目被跳过时干净返回空,build_prompt 过滤空块;不补这行会 str+None 抛 TypeError
    if timeline_info is None:
        return None

    return (
        "以下是历史会话的时间线概览(按发生顺序,近段最详含叙事线索、远段保留关键词与一句话概括锚定 session_id,"
        "配合 memory_recall 的 session_ids 参数圈定候选范围以提升召回准确率):\n\n"
        + timeline_info
    )