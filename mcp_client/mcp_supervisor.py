"""MCP 的 asyncio 隔离层：唯一碰事件循环的模块，对外只暴露同步方法。

官方 mcp SDK 是纯 asyncio，而本项目应用层零 asyncio、并发全走线程。这里把阻抗封死在一处：
一个 daemon 线程跑独立事件循环，循环里只有一个常驻 supervisor task 持有 ClientSessionGroup。

为什么连接/断开必须排队进 supervisor task：stdio_client 内部是 anyio task group，
anyio 要求 cancel scope 在哪个 task 进入就在哪个 task 退出。若每次 connect/disconnect 都用
run_coroutine_threadsafe 起新 task，关闭时必然撞 "Attempted to exit cancel scope in a
different task"。call_tool 不涉及 cancel scope（只是往 memory stream 发消息再等回复），
因此直接派给事件循环，不排队、不被慢连接堵住。
"""
import atexit
import asyncio
import threading

from concurrent.futures import Future

from mcp.client.session_group import ClientSessionGroup


LOOP_START_TIMEOUT_SEC = 10
CONNECT_TIMEOUT_SEC = 30
DISCONNECT_TIMEOUT_SEC = 15
TOOL_CALL_TIMEOUT_SEC = 120
SHUTDOWN_TIMEOUT_SEC = 15

# 工具名前缀：用配置里的 server_key 而非 server 自报名，两个 server 自报同名也不会撞
TOOL_NAME_TEMPLATE = 'mcp__{server_key}__{tool_name}'


def tool_name_prefix(server_key:str)->str:
    return f'mcp__{server_key}__'


class McpSupervisorError(Exception):
    pass


class McpSupervisor:

    def __init__(self):
        self._lock = threading.Lock()
        self._thread:threading.Thread|None = None
        self._loop:asyncio.AbstractEventLoop|None = None
        self._group:ClientSessionGroup|None = None
        self._cmds:asyncio.Queue|None = None
        self._ready = threading.Event()
        self._start_error:BaseException|None = None
        # server_key -> ClientSession；disconnect_from_server 要求传 session 对象，group 自己不按 key 索引
        self._sessions:dict = {}
        # component_name_hook 读它给工具打前缀；连接命令串行在 supervisor task 上，读写时序确定
        self._connecting_key:str|None = None
        self._atexit_registered = False

    # ---------- 事件循环线程 ----------

    def ensure_started(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._ready.clear()
            self._start_error = None
            self._thread = threading.Thread(target=self._run_loop,name='mcp-supervisor',daemon=True)
            self._thread.start()

        if not self._ready.wait(timeout=LOOP_START_TIMEOUT_SEC):
            raise McpSupervisorError(f'MCP supervisor 启动超时({LOOP_START_TIMEOUT_SEC}s)')
        if self._start_error is not None:
            raise McpSupervisorError(f'MCP supervisor 启动失败：{self._start_error}')

        self._register_atexit()

    def _register_atexit(self):
        if self._atexit_registered:
            return
        atexit.register(self.shutdown)
        self._atexit_registered = True

    def _run_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._supervise())
        except BaseException as ee:
            self._start_error = ee
            self._ready.set()
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self._loop = None
            self._group = None
            self._cmds = None
            self._sessions = {}

    # 唯一常驻 task：持有 group 的 async with，并串行消费连接/断开命令
    async def _supervise(self):
        self._cmds = asyncio.Queue()
        async with ClientSessionGroup(component_name_hook=self._name_hook) as group:
            self._group = group
            self._ready.set()
            while True:
                op,payload,future = await self._cmds.get()
                if op == 'shutdown':
                    if not future.cancelled():
                        future.set_result(None)
                    break
                try:
                    result = await self._handle_cmd(op,payload)
                    if not future.cancelled():
                        future.set_result(result)
                except BaseException as ee:
                    if not future.cancelled():
                        future.set_exception(ee)
        # 退出 async with 仍在本 task 内，cancel scope 进出配对

    async def _handle_cmd(self,op:str,payload):
        # 只在 _supervise 的 async with 内被调用，group 必不为空
        group = self._group
        if group is None:
            raise McpSupervisorError('MCP session group 尚未就绪')

        if op == 'connect':
            server_key,params = payload
            if server_key in self._sessions:
                raise McpSupervisorError(f'server {server_key} 已连接')
            self._connecting_key = server_key
            try:
                session = await group.connect_to_server(params)
            finally:
                self._connecting_key = None
            self._sessions[server_key] = session
            prefix = tool_name_prefix(server_key)
            return [tool for name,tool in group.tools.items() if name.startswith(prefix)]

        if op == 'disconnect':
            server_key = payload
            session = self._sessions.pop(server_key,None)
            if session is None:
                raise McpSupervisorError(f'server {server_key} 未连接')
            await group.disconnect_from_server(session)
            return True

        raise McpSupervisorError(f'未知 supervisor 命令：{op}')

    # group 把 server 自报的 Implementation 传进来，这里不用它，改用配置 key 保证唯一
    def _name_hook(self,name:str,server_info)->str:
        key = self._connecting_key or (getattr(server_info,'name',None) or 'unknown')
        return TOOL_NAME_TEMPLATE.format(server_key=key,tool_name=name)

    # ---------- 同步门面 ----------

    def _submit(self,op:str,payload,timeout:float):
        self.ensure_started()
        loop = self._loop
        cmds = self._cmds
        if loop is None or cmds is None:
            raise McpSupervisorError('MCP supervisor 事件循环不可用')

        future:Future = Future()
        loop.call_soon_threadsafe(cmds.put_nowait,(op,payload,future))
        return future.result(timeout=timeout)

    def connect(self,server_key:str,params)->list:
        """连上一个 server，返回它带来的工具列表（mcp.types.Tool）。"""
        return self._submit('connect',(server_key,params),CONNECT_TIMEOUT_SEC)

    def disconnect(self,server_key:str)->bool:
        return self._submit('disconnect',server_key,DISCONNECT_TIMEOUT_SEC)

    def connected_servers(self)->list[str]:
        return list(self._sessions.keys())

    def call_tool(self,mcp_name:str,arguments:dict):
        """调用远端工具。不排队：与连接命令并发，避免慢连接阻塞正常调用。"""
        loop = self._loop
        group = self._group
        if loop is None or group is None:
            raise McpSupervisorError('MCP supervisor 未运行，工具不可用')
        cf = asyncio.run_coroutine_threadsafe(group.call_tool(mcp_name,arguments or {}),loop)
        try:
            return cf.result(timeout=TOOL_CALL_TIMEOUT_SEC)
        except TimeoutError:
            cf.cancel()
            raise McpSupervisorError(f'MCP 工具调用超时({TOOL_CALL_TIMEOUT_SEC}s)：{mcp_name}')

    def shutdown(self):
        """幂等：主动关闭 + atexit 兜底各调一次都安全。"""
        with self._lock:
            thread = self._thread
            loop = self._loop
            cmds = self._cmds
            self._thread = None
        if thread is None or not thread.is_alive() or loop is None or cmds is None:
            return

        try:
            future:Future = Future()
            loop.call_soon_threadsafe(cmds.put_nowait,('shutdown',None,future))
            future.result(timeout=SHUTDOWN_TIMEOUT_SEC)
        except Exception as ee:
            pass

        thread.join(timeout=SHUTDOWN_TIMEOUT_SEC)


_supervisor = None
_supervisor_lock = threading.Lock()


def get_supervisor()->McpSupervisor:
    global _supervisor
    if _supervisor is None:
        with _supervisor_lock:
            if _supervisor is None:
                _supervisor = McpSupervisor()
    return _supervisor
