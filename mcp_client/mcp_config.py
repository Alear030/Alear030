"""mcp.json 读写与规格化：占位符展开、传输推断、条目校验。

配置进版本控制，凭证只以 ${VAR} 占位符出现，真值从 .env 走 os.environ 取
（config.py 顶部已 load_dotenv，本模块 import config 时即已生效）。
"""
import os
import re
import json
import threading

from datetime import timedelta

from mcp import StdioServerParameters
from mcp.client.session_group import StreamableHttpParameters

from config import MCP_CONFIG_PATH


# ${VAR} 占位符；只认这一种写法，不做 $VAR / ${VAR:-default} 等 shell 变体
_PLACEHOLDER = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}')

# 读改写 mcp.json 的串行锁，与 session/memory 的落盘写法一致
_file_lock = threading.Lock()

DEFAULT_HTTP_TIMEOUT = 30
# SSE 长连接的读超时:远端工具可能跑很久才吐第一个字节，与建连 timeout 分开设
DEFAULT_HTTP_SSE_READ_TIMEOUT = 300


# 占位符缺失时抛出，由调用方转成「跳过该 server 并记录原因」，不拿空值去连
class McpConfigError(Exception):
    pass


def _expand_str(value,server_key:str,field:str)->str:
    if not isinstance(value,str):
        raise McpConfigError(f'server {server_key} 的 {field} 必须是字符串')

    def _sub(m):
        var = m.group(1)
        env = os.environ.get(var)
        if env is None or env == '':
            raise McpConfigError(f'server {server_key} 引用的环境变量 {var} 未设置，请在 .env 中补充')
        return env

    return _PLACEHOLDER.sub(_sub,value)


def _expand_str_list(value,server_key:str,field:str)->list[str]:
    if not isinstance(value,list):
        raise McpConfigError(f'server {server_key} 的 {field} 必须是数组')
    return [_expand_str(v,server_key,field) for v in value]


def _expand_str_dict(value,server_key:str,field:str)->dict[str,str]:
    if not isinstance(value,dict):
        raise McpConfigError(f'server {server_key} 的 {field} 必须是对象')
    return {str(k):_expand_str(v,server_key,field) for k,v in value.items()}


# 生态里大量配置不写 type，按 url 有无推断，保持与 Claude Code/Desktop 配置互拷
def _infer_type(entry:dict)->str:
    declared = (entry.get('type') or '').strip().lower()
    if declared in ('stdio','http','streamable-http','streamable_http'):
        return 'stdio' if declared == 'stdio' else 'http'
    return 'http' if entry.get('url') else 'stdio'


def read_config()->dict:
    """读 mcp.json，返回 {server_key: entry} 原始形态（未展开占位符）。文件不存在视作空配置。"""
    if not MCP_CONFIG_PATH.exists():
        return {}
    with _file_lock:
        raw = MCP_CONFIG_PATH.read_text(encoding='utf-8').strip()
    if not raw:
        return {}
    data = json.loads(raw)
    servers = data.get('mcpServers')
    if not isinstance(servers,dict):
        raise McpConfigError('mcp.json 缺少 mcpServers 对象')
    return servers


def write_config(servers:dict):
    """整体覆写 mcp.json 的 mcpServers。运行时增删 server 的工具走这条，保持单一落盘入口。"""
    with _file_lock:
        MCP_CONFIG_PATH.parent.mkdir(parents=True,exist_ok=True)
        MCP_CONFIG_PATH.write_text(
            json.dumps({'mcpServers':servers},ensure_ascii=False,indent=2),
            encoding='utf-8'
        )


def build_params(server_key:str,entry:dict):
    """把一条 mcp.json 条目规格化成 SDK 的连接参数对象。

    占位符在此展开——展开失败抛 McpConfigError，让调用方跳过这个 server。
    """
    if not isinstance(entry,dict):
        raise McpConfigError(f'server {server_key} 配置不是对象')

    server_type = _infer_type(entry)

    if server_type == 'http':
        url = entry.get('url')
        if not url:
            raise McpConfigError(f'server {server_key} 是 http 类型但缺少 url')
        timeout = entry.get('timeout') or DEFAULT_HTTP_TIMEOUT
        sse_read_timeout = entry.get('sse_read_timeout') or DEFAULT_HTTP_SSE_READ_TIMEOUT
        return StreamableHttpParameters(
            url=_expand_str(url,server_key,'url'),
            headers=_expand_str_dict(entry.get('headers') or {},server_key,'headers'),
            timeout=timedelta(seconds=float(timeout)),
            sse_read_timeout=timedelta(seconds=float(sse_read_timeout)),
        )

    command = entry.get('command')
    if not command:
        raise McpConfigError(f'server {server_key} 是 stdio 类型但缺少 command')
    return StdioServerParameters(
        command=_expand_str(command,server_key,'command'),
        args=_expand_str_list(entry.get('args') or [],server_key,'args'),
        env=_expand_str_dict(entry.get('env') or {},server_key,'env') or None,
        cwd=entry.get('cwd') or None,
    )


def is_enabled(entry:dict)->bool:
    # 缺省视为启用；enabled:false 只登记不连接，用于控制 schema 膨胀
    return bool(entry.get('enabled',True))


def server_type(entry:dict)->str:
    return _infer_type(entry)
