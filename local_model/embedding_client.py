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
START_TIMEOUT_SEC = 10
STATUS_TIMEOUT_SEC = 5
STATUS_POLL_SEC = 1.0
READER_JOIN_TIMEOUT_SEC = 1.0


class EmbeddingWorkerError(RuntimeError):
    pass


class EmbeddingNotReadyError(EmbeddingWorkerError):
    def __init__(self, phase: str, error: str | None = None):
        self.phase = phase
        self.worker_error = error
        extra = f' error={error}' if error else ''
        super().__init__(f'embedding 未就绪 phase={phase}{extra}')


class EmbeddingClient:
    def __init__(self):
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._reader_generation = 0
        self._responses: queue.Queue = queue.Queue()
        self._next_id = 1
        self._atexit_registered = False
        self._warmed = False
        self._phase = 'idle'
        self._error = None
        self._poll_thread: threading.Thread | None = None

    def _register_atexit(self) -> None:
        if self._atexit_registered:
            return
        atexit.register(self.shutdown)
        self._atexit_registered = True

    def _reader_loop(self, proc: subprocess.Popen, generation: int) -> None:
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
            # 进程结束时唤醒可能在等的请求；带 generation，防旧 reader 误杀新 worker
            self._responses.put({'_eof': True, '_generation': generation})

    def _join_reader(self) -> None:
        thread = self._reader_thread
        self._reader_thread = None
        if thread is None or not thread.is_alive():
            return
        thread.join(timeout=READER_JOIN_TIMEOUT_SEC)

    def _spawn(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return

        # poll 已死但旧 reader 可能尚未 put _eof；先 join 再 drain，再换代
        self._join_reader()
        self._drain_responses()
        self._reader_generation += 1
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
            args=(self._proc, self._reader_generation),
            name='embedding-worker-reader',
            daemon=True,
        )
        self._reader_thread.start()
        self._register_atexit()
        self._warmed = False
        self._phase = 'idle'
        self._error = None

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
        self._phase = 'idle'
        self._error = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=SHUTDOWN_TIMEOUT_SEC)
        except Exception:
            pass
        self._join_reader()
        self._drain_responses()

    def _request(self, op: str, timeout: float, **fields: Any) -> dict:
        # start/status 超时不杀进程：下载在 boot 线程，stdin 应立刻回；误杀会留下半截权重
        kill_on_timeout = op not in ('start', 'status')
        # status/start 死管道不副作用 spawn：裸进程没有 start，Windows 会留孤儿
        allow_restart = op not in ('start', 'status')
        with self._lock:
            return self._request_locked(op, timeout, allow_restart=allow_restart, kill_on_timeout=kill_on_timeout, **fields)

    def _request_locked(self, op: str, timeout: float, *, allow_restart: bool = True, kill_on_timeout: bool = True, **fields: Any) -> dict:
        # 死管道禁止在此 spawn；重启必须走 _ensure_booted_locked（spawn 后立刻 start）
        if not self._alive():
            raise EmbeddingWorkerError('embedding worker 未运行')

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
                return self._request_locked(op, timeout, allow_restart=False, kill_on_timeout=kill_on_timeout, **fields)
            raise EmbeddingWorkerError(f'写入 embedding worker 失败: {error}') from error

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if kill_on_timeout:
                    self._kill()
                raise EmbeddingWorkerError(f'embedding worker 超时({timeout:.0f}s) op={op}')
            try:
                resp = self._responses.get(timeout=remaining)
            except queue.Empty:
                if kill_on_timeout:
                    self._kill()
                raise EmbeddingWorkerError(f'embedding worker 超时({timeout:.0f}s) op={op}') from None

            if resp.get('_eof'):
                if resp.get('_generation') != self._reader_generation:
                    continue
                self._kill()
                if allow_restart:
                    return self._request_locked(op, timeout, allow_restart=False, kill_on_timeout=kill_on_timeout, **fields)
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

    def _ensure_booted_locked(self) -> None:
        # 活着且本地已 completed ready：不重 boot；死进程即使 _phase 仍是 ready 也要再 start
        if self._alive() and self._phase == 'ready':
            return
        if not self._alive():
            self._spawn()
        result = self._request_locked('start', START_TIMEOUT_SEC, allow_restart=False, kill_on_timeout=False)
        self._apply_status(result)

    def ensure_started(self) -> None:
        with self._lock:
            self._ensure_booted_locked()

    def _apply_status(self, result: dict) -> None:
        if not isinstance(result, dict):
            return
        phase = result.get('phase')
        if isinstance(phase, str):
            self._phase = phase
        if 'error' in result:
            self._error = result.get('error')
        if phase == 'ready':
            self._warmed = True

    def get_status(self) -> dict:
        # worker 已死且不是带着活进程的 completed ready：再 spawn+start，禁止永久 idle
        with self._lock:
            if not self._alive():
                try:
                    self._ensure_booted_locked()
                except Exception:
                    phase = self._phase if self._phase == 'failed' else 'idle'
                    return {'phase': phase, 'weights_ready': False, 'model_ready': False, 'error': self._error}
            try:
                result = self._request_locked('status', STATUS_TIMEOUT_SEC, allow_restart=False, kill_on_timeout=False)
                self._apply_status(result)
                return {
                    'phase': result.get('phase') or self._phase,
                    'weights_ready': bool(result.get('weights_ready')),
                    'model_ready': bool(result.get('model_ready')),
                    'error': result.get('error'),
                }
            except Exception:
                return {'phase': self._phase, 'weights_ready': False, 'model_ready': False, 'error': self._error}

    def warmup_async(self) -> None:
        # spawn 后必须 start；boot 在 worker 线程，这里只轮询 status 更新 _phase
        try:
            self.ensure_started()
        except Exception:
            pass
        thread = self._poll_thread
        if thread is not None and thread.is_alive():
            return

        def _boot_poll() -> None:
            proc = self._proc
            while self._proc is proc and proc is not None and proc.poll() is None:
                try:
                    status = self._request('status', STATUS_TIMEOUT_SEC)
                    self._apply_status(status)
                    if status.get('phase') in ('ready', 'failed'):
                        return
                except Exception:
                    return
                time.sleep(STATUS_POLL_SEC)

        self._poll_thread = threading.Thread(target=_boot_poll, name='embedding-warmup', daemon=True)
        self._poll_thread.start()

    def warmup_sync(self) -> None:
        status = self.get_status()
        if status.get('phase') == 'ready':
            self._warmed = True
            return
        raise EmbeddingNotReadyError(status.get('phase') or self._phase, status.get('error'))

    def encode(self, texts: list[str]) -> list[list[float]]:
        # 下载/加载中立刻抛，禁止再走 120s warmup 等权重
        status = self.get_status()
        phase = status.get('phase') or self._phase
        if phase != 'ready':
            raise EmbeddingNotReadyError(phase, status.get('error'))
        with self._lock:
            if not self._alive():
                raise EmbeddingNotReadyError(self._phase or 'idle', self._error)
            result = self._request_locked('encode', ENCODE_TIMEOUT_SEC, allow_restart=False, kill_on_timeout=True, texts=texts)
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
