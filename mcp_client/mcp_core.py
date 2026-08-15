"""MCP 客户端门面：配置 → 连接 → 工具注册 → 工具表刷新的编排，全同步接口。

其余模块（main.py、工具、TUI）只跟这一层打交道，看不到 asyncio，也不直接碰 supervisor。
"""
import threading

from rich_output import rich_print

from .mcp_config import read_config,build_params,is_enabled,server_type,McpConfigError
from .mcp_supervisor import get_supervisor,McpSupervisorError
from .mcp_bridge import register_server_tools,unregister_server_tools,refresh_agent_tools


class McpManager:

    def __init__(self):
        # server_key -> 已注册的工具名列表；断开时据此从工具表摘除
        self._server_tools:dict[str,list] = {}
        # server_key -> 最近一次失败原因，供 server_status 展示，不静默吞
        self._errors:dict[str,str] = {}
        self._lock = threading.Lock()
        # main.py 装配后传入，用于注册/注销后刷新各 agent 的 tool_list 快照
        self._agents = None
        self._prewarmed = False

    def bind_agents(self,agents):
        self._agents = agents

    # ---------- 单个 server ----------

    def connect_server(self,server_key:str)->dict:
        servers = read_config()
        entry = servers.get(server_key)
        if entry is None:
            return {'server':server_key,'ok':False,'error':f'mcp.json 中不存在 server {server_key}'}
        return self._connect_entry(server_key,entry)

    def _connect_entry(self,server_key:str,entry:dict)->dict:
        try:
            params = build_params(server_key,entry)
        except McpConfigError as ee:
            # 占位符缺失等配置问题：跳过这个 server 并记录原因，不拿空值去连
            with self._lock:
                self._errors[server_key] = str(ee)
            rich_print(f'mcp server {server_key} 配置无效：{ee}',type='system_error')
            return {'server':server_key,'ok':False,'error':str(ee)}

        try:
            tools = get_supervisor().connect(server_key,params)
        except Exception as ee:
            message = f'{type(ee).__name__}: {ee}'
            with self._lock:
                self._errors[server_key] = message
            rich_print(f'mcp server {server_key} 连接失败：{message}',type='system_error')
            return {'server':server_key,'ok':False,'error':message}

        tool_names = register_server_tools(server_key,tools)
        with self._lock:
            self._server_tools[server_key] = tool_names
            self._errors.pop(server_key,None)
        refresh_agent_tools(self._agents)

        rich_print(f'mcp server {server_key} connected, {len(tool_names)} tools loaded...',type='system_message')
        return {'server':server_key,'ok':True,'tools':tool_names}

    def disconnect_server(self,server_key:str)->dict:
        with self._lock:
            tool_names = self._server_tools.pop(server_key,None)

        try:
            get_supervisor().disconnect(server_key)
        except McpSupervisorError as ee:
            # 会话已经不在了也要把工具摘干净，否则模型仍能看到失效工具
            rich_print(f'mcp server {server_key} 断开异常：{ee}',type='system_error')

        removed = unregister_server_tools(server_key,tool_names or [])
        refresh_agent_tools(self._agents)
        return {'server':server_key,'ok':True,'removed_tools':removed}

    def reconnect_server(self,server_key:str)->dict:
        if server_key in self._server_tools:
            self.disconnect_server(server_key)
        return self.connect_server(server_key)

    # ---------- 批量与状态 ----------

    def prewarm(self):
        """后台逐个连上 enabled 的 server；单个失败只记录并继续，不阻塞启动、不影响其它 server。"""
        if self._prewarmed:
            return
        self._prewarmed = True
        threading.Thread(target=self._prewarm_run,name='mcp-prewarm',daemon=True).start()

    def _prewarm_run(self):
        try:
            servers = read_config()
        except Exception as ee:
            rich_print(f'mcp.json 读取失败：{ee}',type='system_error')
            return

        for server_key,entry in servers.items():
            if not is_enabled(entry):
                continue
            self._connect_entry(server_key,entry)

    def server_status(self)->list[dict]:
        """配置态 + 连接态 + 工具数 + 失败原因，供 mcp_server_list 工具与排查使用。"""
        try:
            servers = read_config()
        except Exception as ee:
            return [{'server':'<config>','ok':False,'error':f'mcp.json 读取失败：{ee}'}]

        connected = set(get_supervisor().connected_servers())
        status = []
        for server_key,entry in servers.items():
            status.append({
                'server':server_key,
                'type':server_type(entry),
                'enabled':is_enabled(entry),
                'connected':server_key in connected,
                'tool_count':len(self._server_tools.get(server_key,[])),
                'error':self._errors.get(server_key),
            })
        return status

    def shutdown(self):
        get_supervisor().shutdown()


_manager = None
_manager_lock = threading.Lock()


def get_mcp_manager()->McpManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = McpManager()
    return _manager


def prewarm_mcp_servers(agents=None):
    """启动期非阻塞接入：连接在后台线程逐个进行，就绪一个刷新一次 agent 工具表。"""
    manager = get_mcp_manager()
    manager.bind_agents(agents)
    manager.prewarm()


def shutdown_mcp_servers():
    """显式关闭；进程退出时 supervisor 也会 atexit 兜底调用一次，幂等。"""
    get_mcp_manager().shutdown()
