import io
import os
import threading
import base64,struct
import numpy as np

from transformers import logging as transformers_logging
from contextlib import redirect_stderr

from config import LOCAL_EMBEDDING_MODEL, LOCAL_MODEL_PATH, MODELSCOPE_EMBEDDING_ID


os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
transformers_logging.set_verbosity_error()


_embedding_model = None
_embedding_lock = threading.Lock()


# 195MB 的权重不进版本控制,全新 clone 上只有 config/tokenizer 等骨架文件。
# 判据取权重文件而非目录:目录一定存在(骨架文件已跟踪),缺的只是权重;
# 若以目录为判据则永远认为模型就绪,SentenceTransformer 会加载到半个模型后报错。
def _weights_ready() -> bool:
    return any((LOCAL_EMBEDDING_MODEL/name).exists() for name in ('pytorch_model.bin','model.safetensors'))


def _download_embedding_model():
    from modelscope import snapshot_download

    print(f'本地嵌入模型权重缺失,正在从 ModelScope 下载 {MODELSCOPE_EMBEDDING_ID}（约 195MB,仅首次需要）...')
    # cache_dir 指向 local_model/,modelscope 会按 <id> 落成 local_model/iic/xxx/,正好等于 LOCAL_EMBEDDING_MODEL
    snapshot_download(MODELSCOPE_EMBEDDING_ID,cache_dir=str(LOCAL_MODEL_PATH))

    if not _weights_ready():
        raise RuntimeError(
            f'嵌入模型下载后仍未找到权重文件。请手动下载 {MODELSCOPE_EMBEDDING_ID} 并解压到 {LOCAL_EMBEDDING_MODEL}'
        )
    print('嵌入模型下载完成')


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:  # 双重检查，拿到锁后再确认一次
                if not _weights_ready():
                    _download_embedding_model()

                # redirect_stderr 只用于屏蔽 sentence-transformers 的加载噪音;
                # 失败时把吞掉的 stderr 一并抛出,否则用户只看到无上下文的异常
                stderr_buffer = io.StringIO()
                try:
                    with redirect_stderr(stderr_buffer):
                        from sentence_transformers import SentenceTransformer
                        _embedding_model = SentenceTransformer(str(LOCAL_EMBEDDING_MODEL), device="cpu")
                except Exception as error:
                    raise RuntimeError(
                        f'加载嵌入模型失败({LOCAL_EMBEDDING_MODEL}): {error}\n{stderr_buffer.getvalue()}'
                    ) from error

    return _embedding_model


def embedding_to_b64(embedding) -> str:
    """numpy 数组 → base64 字符串"""
    emb_bytes = struct.pack(f'{len(embedding)}f', *embedding)
    return base64.b64encode(emb_bytes).decode()


def embedding_from_b64(b64_str: str) -> np.ndarray:
    """base64 字符串 → numpy 数组"""
    emb_bytes = base64.b64decode(b64_str)
    return np.array(struct.unpack(f'{len(emb_bytes)//4}f', emb_bytes))