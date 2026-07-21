import json
import tiktoken

from pathlib import Path


from prompt.prompt_register import register_prompt
from config import MEMORY_STORAGE_PATH

timeline_path = MEMORY_STORAGE_PATH/'timeline.json'
timeline = None
if timeline_path.exists():
    timeline_content_raw = timeline_path.read_text(encoding='utf-8').strip()
    if timeline_content_raw:
        timeline = json.loads(timeline_content_raw)

if timeline:
    timeline_enable = True
else:
    timeline_enable = False


# 与 memory_core.py 的 timeline attachment 渲染逻辑保持一致(近段完整叙事线索、远段仅关键词+摘要，
# 按 token 预算分层)，因为改为 system prompt 注入而非 attachment，故复制一份独立实现，不 import memory_core
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


@register_prompt(prompt_name='timeline',order=30,condition=lambda agent:agent.agent_name == 'main',enabled=timeline_enable)
def timeline_prompt(agent)->str:
    historical_timeline = list(timeline)
    historical_timeline.reverse()

    timeline_token = 0
    timeline_info = None
    for timeline_index, entry in enumerate(historical_timeline):
        tl_content = render_timeline_entry(entry=entry, timeline_token=timeline_token, timeline_index=timeline_index)
        timeline_info = timeline_info + '\n\n' + tl_content if timeline_info else tl_content
        timeline_token += count_token(text=tl_content)

    return (
        "以下是历史会话的时间线概览(按发生顺序,近段最详含叙事线索、远段保留关键词与一句话概括锚定 session_id,"
        "配合 memory_recall 的 session_ids 参数圈定候选范围以提升召回准确率):\n\n"
        + timeline_info
    )