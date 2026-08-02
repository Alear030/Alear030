"""主进程 embedding 客户端：spawn worker，JSON-lines 请求/响应，带锁与超时。"""
from __future__ import annotations

import atexit
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


WARMUP_TIMEOUT_SEC = 120
ENCODE_TIMEOUT_SEC = 60
SHUTDOWN_TIMEOUT_SEC = 10


class EmbeddingWorkerError(RuntimeError):
    pass


class EmbeddingClient:
    def __init__(self):
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._responses: queue.Queue = queue.Queue()
        self._next_id = 1
        self._atexit_registered = False
        self._warmed = False

    def _register_atexit(self) -> None:
        if self._atexit_registered:
            return
        atexit.register(self.shutdown)
        self._atexit_registered = True

    def _reader_loop(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        try:
            for raw in proc.stdout:
                line = raw.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._responses.put(payload)
        finally:
            # 进程结束时唤醒可能在等的请求
            self._responses.put({'_eof': True})

    def _spawn(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return

        self._drain_responses()
        # -u 无缓冲，保证 JSON lines 及时可见；PYTHONIOENCODING 防止 Windows 子进程 stdin 落回 gbk
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        self._proc = subprocess.Popen(
            [sys.executable, '-u', '-m', 'local_model.embedding_worker'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(Path(__file__).resolve().parents[1]),
            bufsize=1,
            env=env,
        )
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            args=(self._proc,),
            name='embedding-worker-reader',
            daemon=True,
        )
        self._reader_thread.start()
        self._register_atexit()
        self._warmed = False

        # stderr 另线程排空，避免管道堵死；内容仅用于排障时可扩展
        threading.Thread(
            target=self._drain_stderr,
            args=(self._proc,),
            name='embedding-worker-stderr',
            daemon=True,
        ).start()

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        if proc.stderr is None:
            return
        for _ in proc.stderr:
            pass

    def _drain_responses(self) -> None:
        while True:
            try:
                self._responses.get_nowait()
            except queue.Empty:
                break

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _kill(self) -> None:
        proc = self._proc
        self._proc = None
        self._warmed = False
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=SHUTDOWN_TIMEOUT_SEC)
        except Exception:
            pass
        self._drain_responses()

    def _request(self, op: str, timeout: float, **fields: Any) -> dict:
        with self._lock:
            return self._request_locked(op, timeout, **fields)

    def _request_locked(self, op: str, timeout: float, *, allow_restart: bool = True, **fields: Any) -> dict:
        if not self._alive():
            self._spawn()

        assert self._proc is not None and self._proc.stdin is not None
        req_id = self._next_id
        self._next_id += 1
        payload = {'id': req_id, 'op': op, **fields}
        try:
            self._proc.stdin.write(json.dumps(payload, ensure_ascii=True) + '\n')
            self._proc.stdin.flush()
        except Exception as error:
            self._kill()
            if allow_restart:
                self._spawn()
                return self._request_locked(op, timeout, allow_restart=False, **fields)
            raise EmbeddingWorkerError(f'写入 embedding worker 失败: {error}') from error

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._kill()
                raise EmbeddingWorkerError(f'embedding worker 超时({timeout:.0f}s) op={op}')
            try:
                resp = self._responses.get(timeout=remaining)
            except queue.Empty:
                self._kill()
                raise EmbeddingWorkerError(f'embedding worker 超时({timeout:.0f}s) op={op}') from None

            if resp.get('_eof'):
                self._kill()
                if allow_restart:
                    self._spawn()
                    return self._request_locked(op, timeout, allow_restart=False, **fields)
                raise EmbeddingWorkerError('embedding worker 意外退出')

            if resp.get('id') != req_id:
                # 过期/错序响应丢弃
                continue
            if not resp.get('ok'):
                raise EmbeddingWorkerError(resp.get('error') or 'embedding worker 返回失败')
            result = resp.get('result')
            if not isinstance(result, dict):
                raise EmbeddingWorkerError('embedding worker 响应缺少 result')
            return result

    def ensure_started(self) -> None:
        with self._lock:
            if not self._alive():
                self._spawn()

    def warmup_async(self) -> None:
        """spawn + 后台发 warmup，不阻塞调用方。"""
        self.ensure_started()

        def _warm() -> None:
            try:
                with self._lock:
                    if self._warmed and self._alive():
                        return
                    self._request_locked('warmup', WARMUP_TIMEOUT_SEC)
                    self._warmed = True
            except Exception:
                # 预热失败不炸主进程；首次 encode 会再试
                pass

        threading.Thread(target=_warm, name='embedding-warmup', daemon=True).start()

    def warmup_sync(self) -> None:
        with self._lock:
            if self._warmed and self._alive():
                return
            self._request_locked('warmup', WARMUP_TIMEOUT_SEC)
            self._warmed = True

    def encode(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            if not self._warmed or not self._alive():
                self._request_locked('warmup', WARMUP_TIMEOUT_SEC)
                self._warmed = True
            result = self._request_locked('encode', ENCODE_TIMEOUT_SEC, texts=texts)
        vectors = result.get('vectors')
        if not isinstance(vectors, list) or not vectors:
            raise EmbeddingWorkerError('embedding worker 未返回 vectors')
        return vectors

    def shutdown(self) -> None:
        with self._lock:
            if not self._alive():
                self._kill()
                return
            try:
                self._request_locked('shutdown', SHUTDOWN_TIMEOUT_SEC, allow_restart=False)
            except Exception:
                pass
            self._kill()


_client: EmbeddingClient | None = None
_client_lock = threading.Lock()


def get_embedding_client() -> EmbeddingClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = EmbeddingClient()
    return _client
