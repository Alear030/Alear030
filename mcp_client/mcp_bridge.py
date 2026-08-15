"""MCP 工具 → Alear030 工具体系的接入层：注册闭包、结果映射、agent 工具表刷新。

MCP 工具与内置工具唯一的行为差异在参数：内置工具靠 **kwargs 自然吞掉 pre_toolUse 注入的
运行时对象，而这里的闭包要把远端参数原样转发出去，所以必须显式把注入项剔掉。
"""
import json

from dataclasses import asdict

from tool.tool_core import register_tool,unregister_tool,tool_call_processing,ToolCallResult
from config import MCP_TOOL_RESULT_MAX_CHARS

from .mcp_supervisor import get_supervisor,tool_name_prefix


# pre_toolUse 注入 + match_tool 注入的运行时对象，转发给远端前必须剔除
_INJECTED_KEYS = {'agents','session','hooks','Loop','memory','tcr','emit'}


# 非文本内容不塞进历史：base64 图片一条就能把 session token 顶爆，只留可读占位
def _render_block(block)->str:
    block_type = getattr(block,'type',None)

    if block_type == 'text':
        return getattr(block,'text','') or ''

    if block_type == 'image':
        data = getattr(block,'data','') or ''
        mime = getattr(block,'mimeType','image') or 'image'
        return f'[{mime} 约 {len(data)*3//4//1024}KB 已省略]'

    if block_type == 'resource':
        resource = getattr(block,'resource',None)
        uri = getattr(resource,'uri','') if resource else ''
        text = getattr(resource,'text',None) if resource else None
        return text if text else f'[资源 {uri} 非文本内容已省略]'

    return f'[{block_type or "unknown"} 类型内容已省略]'


def _render_result(result)->str:
    # content blocks 优先：这是 MCP 规定必然存在的规范返回，也是最贴合模型阅读的形态。
    # structuredContent 只在没有 blocks 时兜底——它常是 server 侧对标量返回的自动包装
    # （FastMCP 会把 "hi" 包成 {"result":"hi"}），当成首选会白给模型加一层无意义嵌套
    blocks = getattr(result,'content',None) or []
    if blocks:
        text = '\n'.join(_render_block(b) for b in blocks)
    else:
        structured = getattr(result,'structuredContent',None)
        text = json.dumps(structured,ensure_ascii=False) if structured else ''

    if len(text) > MCP_TOOL_RESULT_MAX_CHARS:
        text = f'{text[:MCP_TOOL_RESULT_MAX_CHARS]}\n\n[结果超长已截断，原长 {len(text)} 字符]'
    return text


# 错误形状与 tool_core._error_result 保持一致，TUI 与模型看到的错误结构不分内置/MCP
def _error_extra_info(message:str)->list:
    return [{
        "id":"tool_call_error_info",
        "type":"Horizontal",
        "content":[
            {"id":"tool_call_error_info_pointer","type":"Static","content":"⎿","css":{"color":"rgba(255,255,255,0.5)","width":"2","height":"auto"}},
            {"id":"tool_call_error_info_message","type":"Static","content":message,"css":{"color":"rgba(255,255,255,0.5)","width":"100%","height":"auto"}}
        ],
        "css":{"width":"100%","height":"auto"}
    }]


def _make_proxy(mcp_name:str):
    def _proxy(**kwargs)->ToolCallResult:
        tcr = kwargs.get('tcr') or ToolCallResult(tool_call_name=mcp_name)
        emit = kwargs.get('emit')
        tool_call_processing(tcr,emit)

        arguments = {k:v for k,v in kwargs.items() if k not in _INJECTED_KEYS}

        try:
            result = get_supervisor().call_tool(mcp_name,arguments)
        except Exception as ee:
            message = f'MCP 工具调用失败：{type(ee).__name__}: {ee}'
            tcr.tool_call_state = {'tool_call_state':'error'}
            tcr.tool_call_result = {'role':'tool','content':json.dumps({'error':'mcp_call_failed','message':message},ensure_ascii=False)}
            tcr.tool_call_extra_info = _error_extra_info(message)
            if emit:
                emit(content=asdict(tcr))
            return tcr

        text = _render_result(result)

        # isError 是远端工具自身报的失败，不是传输失败，同样落 error 态让模型据此修正
        if getattr(result,'isError',False):
            tcr.tool_call_state = {'tool_call_state':'error'}
            tcr.tool_call_result = {'role':'tool','content':json.dumps({'error':'mcp_tool_error','message':text},ensure_ascii=False)}
            tcr.tool_call_extra_info = _error_extra_info(text)
        else:
            tcr.tool_call_state = {'tool_call_state':'success'}
            tcr.tool_call_result = {'role':'tool','content':text}

        if emit:
            emit(content=asdict(tcr))
        return tcr

    return _proxy


def register_server_tools(server_key:str,tools:list)->list[str]:
    """把一个 server 带来的工具注册进全局工具表，返回注册出的工具名。

    schema 直接用 MCP 的 inputSchema——闭包签名是 **kwargs，inspect.signature 推不出任何契约。
    """
    prefix = tool_name_prefix(server_key)
    registered = []

    for tool in tools:
        mcp_name = tool.name if tool.name.startswith(prefix) else f'{prefix}{tool.name}'
        description = (tool.description or '').strip() or f'{server_key} 提供的 MCP 工具 {tool.name}'
        register_tool(
            tool_name=mcp_name,
            tool_desc=description,
            tool_prompt='',
            tool_enabled=True,
            tool_autho='mcp_tool',
            tool_parameters=tool.inputSchema,
        )(_make_proxy(mcp_name))
        registered.append(mcp_name)

    return registered


def unregister_server_tools(server_key:str,tool_names:list)->int:
    return sum(1 for name in tool_names if unregister_tool(name))


def refresh_agent_tools(agents=None):
    """注册/注销之后刷新 agent 的工具快照；agents 为空则跳过（无 TUI 的脚本化调用场景）。"""
    if agents is None:
        return
    agents.refresh_all_tool_list()
