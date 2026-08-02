"""嵌入模型门面：主进程只做权重判据 / b64 / 远程代理；重模型在 embedding_worker 子进程。"""
from __future__ import annotations

import base64
import struct
import threading

import numpy as np

from config import LOCAL_EMBEDDING_MODEL
from .embedding_client import get_embedding_client


_proxy = None
_proxy_lock = threading.Lock()


def _weights_ready() -> bool:
    # 195MB 的权重不进版本控制,全新 clone 上只有 config/tokenizer 等骨架文件。
    # 判据取权重文件而非目录:目录一定存在(骨架文件已跟踪),缺的只是权重。
    return any((LOCAL_EMBEDDING_MODEL / name).exists() for name in ('pytorch_model.bin', 'model.safetensors'))


def embedding_weights_ready() -> bool:
    """公共判据:本地嵌入权重是否已就绪。TUI 启动提示等外部调用走这条,不直接依赖私有 _weights_ready。"""
    return _weights_ready()


class _EmbeddingProxy:
    """兼容 SentenceTransformer.encode 的最小表面：encode(texts) -> ndarray。"""

    def encode(self, texts, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        if not isinstance(texts, list) or not texts:
            raise ValueError('encode 需要非空文本列表')
        vectors = get_embedding_client().encode([str(t) for t in texts])
        return np.asarray(vectors, dtype=np.float32)


def _get_embedding_model():
    global _proxy
    if _proxy is None:
        with _proxy_lock:
            if _proxy is None:
                _proxy = _EmbeddingProxy()
    return _proxy


def prewarm_embedding_model() -> bool:
    """拉起 embedding worker 并异步 warmup；立即返回，不阻塞 TUI 启动。

    权重缺失时直接跳过:不在后台静默下载 195MB,留给首次真正需要它的调用(worker 内)处理。
    """
    if not _weights_ready():
        return False
    get_embedding_client().warmup_async()
    return True


def shutdown_embedding_worker() -> None:
    """显式关闭 worker；进程退出时 embedding_client 也会 atexit 调用。"""
    get_embedding_client().shutdown()


def embedding_to_b64(embedding) -> str:
    """numpy 数组 → base64 字符串"""
    emb_bytes = struct.pack(f'{len(embedding)}f', *embedding)
    return base64.b64encode(emb_bytes).decode()


def embedding_from_b64(b64_str: str) -> np.ndarray:
    """base64 字符串 → numpy 数组"""
    emb_bytes = base64.b64decode(b64_str)
    return np.array(struct.unpack(f'{len(emb_bytes)//4}f', emb_bytes))
