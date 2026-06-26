import jieba
jieba.setLogLevel(20)
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import json

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed

from tools._tool_register import register_tool
from config import LOCAL_EMBEDDING_MODEL,SESSION_MEMORTY_DETAIL_PATH


import threading


_embedding_model = None
_embedding_lock = threading.Lock()

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:  # 双重检查，拿到锁后再确认一次
                from sentence_transformers import SentenceTransformer
                _embedding_model = SentenceTransformer(str(LOCAL_EMBEDDING_MODEL), device="cpu")
    return _embedding_model

tool_desc = '用于历史对话片段召回&回忆'
tool_prompt_file = Path(__file__).parent/'tool_prompt.md'
if tool_prompt_file.exists():
    tool_prompt_content = tool_prompt_file.read_text(encoding='utf-8')
    tool_prompt = tool_prompt_content.strip() if tool_prompt_content.strip() else None
else:
    tool_prompt = None


