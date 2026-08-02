"""Embedding worker 子进程入口：唯一允许加载 sentence_transformers 的进程。

协议：stdin/stdout 各一行一个 JSON（带 id）。日志与库噪音只写 stderr，避免污染协议。
跑法：python -m local_model.embedding_worker
"""
from __future__ import annotations

import io
import json
import os
import sys
import traceback
from contextlib import redirect_stderr
from pathlib import Path


# 尽早压掉 tokenizer 并行警告；在 import transformers 之前设置
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'


def _force_utf8_stdio() -> None:
    # Windows 默认 stdin 常是 gbk：客户端按 utf-8 写中文会被读坏，tokenizer 直接炸
    for stream_name in ('stdin', 'stdout', 'stderr'):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def _log(msg: str) -> None:
    sys.stderr.write(msg.rstrip() + '\n')
    sys.stderr.flush()


def _reply(payload: dict) -> None:
    # ensure_ascii：管道协议走纯 ASCII，避免宿主控制台编码再搅一次
    sys.stdout.write(json.dumps(payload, ensure_ascii=True) + '\n')
    sys.stdout.flush()


def _weights_ready(model_dir: Path) -> bool:
    return any((model_dir / name).exists() for name in ('pytorch_model.bin', 'model.safetensors'))


class EmbeddingRuntime:
    def __init__(self):
        # 延迟读 config：worker 启动时再 import，避免协议循环被无关副作用打断
        from config import LOCAL_EMBEDDING_MODEL, LOCAL_MODEL_PATH, MODELSCOPE_EMBEDDING_ID

        self.model_dir = Path(LOCAL_EMBEDDING_MODEL)
        self.model_root = Path(LOCAL_MODEL_PATH)
        self.modelscope_id = MODELSCOPE_EMBEDDING_ID
        self._model = None

    def _download(self) -> None:
        from modelscope import snapshot_download

        _log(f'downloading embedding weights {self.modelscope_id} ...')
        snapshot_download(self.modelscope_id, cache_dir=str(self.model_root))
        if not _weights_ready(self.model_dir):
            raise RuntimeError(
                f'嵌入模型下载后仍未找到权重文件。请手动下载 {self.modelscope_id} '
                f'并解压到 {self.model_dir}'
            )
        _log('embedding weights download done')

    def warmup(self) -> dict:
        if self._model is not None:
            return {'ready': True}

        if not _weights_ready(self.model_dir):
            self._download()

        from transformers import logging as transformers_logging

        transformers_logging.set_verbosity_error()

        stderr_buffer = io.StringIO()
        try:
            with redirect_stderr(stderr_buffer):
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(str(self.model_dir), device='cpu')
        except Exception as error:
            noise = stderr_buffer.getvalue()
            raise RuntimeError(
                f'加载嵌入模型失败({self.model_dir}): {error}\n{noise}'
            ) from error

        return {'ready': True}

    def encode(self, texts: list) -> dict:
        if not isinstance(texts, list) or not texts or not all(isinstance(t, str) for t in texts):
            raise ValueError('encode.texts 必须是非空字符串列表')
        self.warmup()
        vectors = self._model.encode(texts)
        # 统一成 list[list[float]]，主进程再还原 ndarray
        return {'vectors': [list(map(float, row)) for row in vectors]}


def main() -> int:
    _force_utf8_stdio()
    runtime = EmbeddingRuntime()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        req_id = None
        try:
            req = json.loads(line)
            req_id = req.get('id')
            op = req.get('op')
            if op == 'warmup':
                result = runtime.warmup()
                _reply({'id': req_id, 'ok': True, 'result': result})
            elif op == 'encode':
                result = runtime.encode(req.get('texts'))
                _reply({'id': req_id, 'ok': True, 'result': result})
            elif op == 'shutdown':
                _reply({'id': req_id, 'ok': True, 'result': {'bye': True}})
                return 0
            else:
                _reply({'id': req_id, 'ok': False, 'error': f'unknown op: {op!r}'})
        except Exception as error:
            _log(traceback.format_exc())
            _reply({'id': req_id, 'ok': False, 'error': f'{type(error).__name__}: {error}'})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
