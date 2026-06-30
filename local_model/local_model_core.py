import io
import os
import threading
import base64,struct
import numpy as np

from transformers import logging as transformers_logging
from contextlib import redirect_stderr

from config import LOCAL_EMBEDDING_MODEL


os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
transformers_logging.set_verbosity_error()


_embedding_model = None
_embedding_lock = threading.Lock()


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:  # 双重检查，拿到锁后再确认一次
                with redirect_stderr(io.StringIO()):
                    from sentence_transformers import SentenceTransformer
                    _embedding_model = SentenceTransformer(str(LOCAL_EMBEDDING_MODEL), device="cpu")
    
    return _embedding_model


def embedding_to_b64(embedding) -> str:
    """numpy 数组 → base64 字符串"""
    emb_bytes = struct.pack(f'{len(embedding)}f', *embedding)
    return base64.b64encode(emb_bytes).decode()


def embedding_from_b64(b64_str: str) -> np.ndarray:
    """base64 字符串 → numpy 数组"""
    emb_bytes = base64.b64decode(b64_str)
    return np.array(struct.unpack(f'{len(emb_bytes)//4}f', emb_bytes))