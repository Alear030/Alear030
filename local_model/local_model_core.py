import io
import os
import threading
import base64,struct
import numpy as np

from transformers import logging as transformers_logging
from contextlib import redirect_stderr

from config import LOCAL_EMBEDDING_MODEL, LOCAL_MODEL_PATH, MODELSCOPE_EMBEDDING_ID
from rich_output import rich_print


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


def embedding_weights_ready() -> bool:
    """公共判据:本地嵌入权重是否已就绪。TUI 启动提示等外部调用走这条,不直接依赖私有 _weights_ready。"""
    return _weights_ready()


def _download_embedding_model():
    from modelscope import snapshot_download

    # 走 rich_print:TUI 接管后裸 print 不可见;下载多发生在后台切片线程,receiver 已就绪
    rich_print(
        message=f'本地嵌入模型权重缺失,正在从 ModelScope 下载 {MODELSCOPE_EMBEDDING_ID}（约 195MB,仅首次需要）...',
        type='system_message',
    )
    # cache_dir 指向 local_model/,modelscope 会按 <id> 落成 local_model/iic/xxx/,正好等于 LOCAL_EMBEDDING_MODEL
    snapshot_download(MODELSCOPE_EMBEDDING_ID,cache_dir=str(LOCAL_MODEL_PATH))

    if not _weights_ready():
        raise RuntimeError(
            f'嵌入模型下载后仍未找到权重文件。请手动下载 {MODELSCOPE_EMBEDDING_ID} 并解压到 {LOCAL_EMBEDDING_MODEL}'
        )
    rich_print(message='嵌入模型下载完成',type='system_message')


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


def prewarm_embedding_model() -> bool:
    """在守护线程里提前加载嵌入模型,返回是否真的启动了预热。

    切片/摘要是第一批用到嵌入的调用,若等到那时才懒加载,这 8.6s(实测)会算进会话链路。
    权重缺失时直接跳过:不在后台静默下载 195MB,留给首次真正需要它的调用显式处理并报错。
    """
    if not _weights_ready():
        return False

    def _warm():
        try:
            _get_embedding_model()
        except Exception as error:
            rich_print(message=f'嵌入模型预热失败,将在首次使用时重试: {error}',type='system_error')

    threading.Thread(target=_warm,name='embedding-prewarm',daemon=True).start()
    return True


def embedding_to_b64(embedding) -> str:
    """numpy 数组 → base64 字符串"""
    emb_bytes = struct.pack(f'{len(embedding)}f', *embedding)
    return base64.b64encode(emb_bytes).decode()


def embedding_from_b64(b64_str: str) -> np.ndarray:
    """base64 字符串 → numpy 数组"""
    emb_bytes = base64.b64decode(b64_str)
    return np.array(struct.unpack(f'{len(emb_bytes)//4}f', emb_bytes))