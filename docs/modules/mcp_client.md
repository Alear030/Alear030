# Alear030 MCP 客户端

**中文** · English（暂缺）

← [返回 README](../../README.md) · [文档目录](../index.md)

`mcp_client/` 让 Alear030 作为 **MCP 客户端**接入外部 server，把远端工具接进本项目原有的工具体系。stdio 与 Streamable HTTP 两种传输都由 `mcp_client/mcp.json` 驱动。

本文讲机制。配置写法见 [配置说明](../CONFIGURATION.md)，工具体系本身见 [扩展指南](../EXTENDING.md)，架构总览见 [架构文档](../ARCHITECTURE.md)。

> **本文所有技术断言都对着代码核对过。** 没核实的推测一律不写，已知的粗糙处在最后一节如实列出。

---

## 目录

- [四层结构](#四层结构)
- [一次连接走过的路径](#一次连接走过的路径)
- [四个非显而易见的约束](#四个非显而易见的约束)
- [配置与凭证](#配置与凭证)
- [超时、错误与关闭](#超时错误与关闭)
- [已知的粗糙处](#已知的粗糙处)

---

## 四层结构

| 文件 | 职责 | 对外可见性 |
|------|------|-----------|
| `mcp_config.py` | `mcp.json` 读写、`${VAR}` 占位符展开、传输类型推断、条目校验 | 内部 |
| `mcp_supervisor.py` | **唯一碰 asyncio 的模块**：daemon 线程 + 独立事件循环 + 常驻 supervisor task | 内部 |
| `mcp_bridge.py` | 远端工具 → 本项目工具体系：注册闭包、结果渲染、agent 工具表刷新 | 内部 |
| `mcp_core.py` | 同步门面 `McpManager`，编排「配置 → 连接 → 注册 → 刷新」 | `__init__.py` 只导出这一层 |

`mcp_client/__init__.py` 只导出三个函数：`get_mcp_manager`、`prewarm_mcp_servers`、`shutdown_mcp_servers`。**其余模块（`main.py`、工具、TUI）只跟门面打交道，看不到 asyncio，也不直接碰 supervisor。**

## 一次连接走过的路径

```text
main.py: prewarm_mcp_servers(agents=agents)
  → McpManager.bind_agents(agents) + prewarm()
  → 起 daemon 线程 'mcp-prewarm'，逐个遍历 mcp.json 里 enabled 的 server
  → _connect_entry(server_key, entry)
      → mcp_config.build_params()       展开 ${VAR}，构造 SDK 参数对象
      → supervisor.connect()            命令入队 → supervisor task 串行执行
      → mcp_bridge.register_server_tools()  逐个 tool.tool_register(...)
      → mcp_bridge.refresh_agent_tools()    agents.refresh_all_tool_list()
```

**启动不被 MCP 阻塞**：`prewarm()` 起后台线程后立刻返回，TUI 照常启动。连上一个 server 就注册一批工具、刷新一次 agent 工具表；单个 server 失败只记进 `McpManager._errors`，不影响其它 server，也不影响启动。

## 四个非显而易见的约束

### 1. 目录不能叫 `mcp`

仓库根就是 `sys.path[0]`，顶层出现 `mcp/` 会**遮蔽已安装的 `mcp` pip 包**，import 直接错乱。`config.py:75` 的注释就钉在这条上。同理，包名和目录名都要避开。

### 2. asyncio 封死在 supervisor，且连接必须排队

官方 mcp SDK 是纯 asyncio，而本项目应用层零 asyncio、并发全走线程。阻抗封在一处：**一个 daemon 线程跑独立事件循环，循环里只有一个常驻 supervisor task 持有 `ClientSessionGroup`。**

关键约束是 **connect / disconnect 必须排队进那个 task**：

```text
_supervise()  ← 唯一常驻 task
  async with ClientSessionGroup(...) as group:
      while True: 从 asyncio.Queue 取命令，串行执行 connect / disconnect
  # 退出 async with 仍在本 task 内，cancel scope 进出配对
```

`stdio_client` 内部是 anyio task group，anyio 要求 **cancel scope 在哪个 task 进入就在哪个 task 退出**。若每次 connect/disconnect 都用 `run_coroutine_threadsafe` 起新 task，关闭时必然撞 `Attempted to exit cancel scope in a different task`。

**`call_tool` 是例外**：它只是往 memory stream 发消息再等回复，不涉及 cancel scope，因此直接 `run_coroutine_threadsafe` 派给事件循环——不排队，不会被一个慢连接堵住正常工具调用。

### 3. 工具表是运行时可变的，但 system prompt 不是

`agent.tool_list` 原本是构造期快照。MCP 工具连上后经 `agents.refresh_all_tool_list()` 重取，而 `loop._chat` 每次现读 `tool_list`，所以**刷新后下一次模型调用即生效**。

**但 system prompt 是启动快照，不会刷新。** MCP 工具只在 function-calling schema 里可见，不进 `tool_prompt` 分块——模型能调用它们，但 system prompt 里的工具清单不包含它们。

### 4. schema 不走 `inspect.signature`

内置工具的参数契约由 `inspect.signature` 从函数签名推导。MCP 工具走不通这条：闭包签名是 `**kwargs`，推导不出任何契约。所以 `register_server_tools` 把 MCP 自己的 `inputSchema`（本身就是 JSON Schema）经 `tool.tool_register(tool_parameters=...)` 直接采用。

**由此产生 MCP 工具与内置工具唯一的行为差异**：内置工具靠 `**kwargs` 自然吞掉 `pre_toolUse` 注入的运行时对象，而 `_make_proxy` 的闭包要把参数原样转发给远端，所以必须显式剔除注入项——`mcp_bridge.py` 里的 `_INJECTED_KEYS = {'agents','session','hooks','Loop','memory','tcr','emit'}`。

**新增 `pre_toolUse` 注入项时必须同步这个集合**，否则运行时对象会被当成业务参数发给远端 server。

## 配置与凭证

- 工具名格式 `mcp__{server_key}__{tool_name}`，**前缀用 `mcp.json` 里的配置 key 而非 server 自报名**——两个 server 自报同名也不会撞。实现见 `_name_hook`：`ClientSessionGroup` 会把 server 自报的 `Implementation` 传进来，这里刻意不用它。
- 授权走工具类别 `mcp_tool`（`agent/agents.yaml` 里 main 开、其余关）；具体启用哪些 server 由 `mcp.json` 每条的 `enabled` 控制。`enabled: false` 表示登记但不连接，用于控制 schema 膨胀。
- **凭证在 `mcp.json` 里只以 `${VAR}` 占位符出现**，真值走 `.env`。只认 `${VAR}` 这一种写法，不支持 `$VAR` / `${VAR:-default}` 等 shell 变体。
- **占位符解析不到时跳过该 server 并记录原因，不拿空值去连**——`_expand_str` 抛 `McpConfigError`，`_connect_entry` 捕获后写进 `_errors` 并返回失败。
- 传输类型缺省按 `url` 字段有无推断（有 `url` → http，否则 stdio），这样能和 Claude Code / Desktop 的配置互相拷贝。

## 超时、错误与关闭

超时常量集中在 `mcp_supervisor.py` 顶部：

| 常量 | 值 | 用途 |
|------|-----|------|
| `LOOP_START_TIMEOUT_SEC` | 10 | 事件循环线程启动 |
| `CONNECT_TIMEOUT_SEC` | 30 | 单个 server 建连 |
| `DISCONNECT_TIMEOUT_SEC` | 15 | 单个 server 断开 |
| `TOOL_CALL_TIMEOUT_SEC` | 120 | 远端工具调用 |
| `SHUTDOWN_TIMEOUT_SEC` | 15 | 整体关闭 |

HTTP 传输另有两个分开的超时：建连 `timeout`（默认 30s）与 SSE 长连接读超时 `sse_read_timeout`（默认 300s）——远端工具可能跑很久才吐第一个字节，两者不能共用一个值。

错误处理的三条：

- **远端工具自报失败（`isError`）和传输失败分开处理**，但都落 `error` 态。前者是工具逻辑错误，把远端返回的文本给模型让它据此修正；后者是调用失败。
- 错误的 `tool_call_extra_info` 形状与 `tool_core._error_result` 保持一致——**TUI 与模型看到的错误结构不分内置 / MCP**。
- 结果渲染优先取 content blocks，`structuredContent` 只在没有 blocks 时兜底（FastMCP 会把标量 `"hi"` 包成 `{"result":"hi"}`，当首选会白给模型加一层无意义嵌套）。非文本内容不进历史：base64 图片一条就能把 session token 顶爆，只留 `[image 约 NKB 已省略]` 占位。单条结果超过 `MCP_TOOL_RESULT_MAX_CHARS`（默认 4000）截断。

关闭走 `shutdown_mcp_servers()`，**幂等**：主动调用与 supervisor 的 `atexit` 兜底各调一次都安全。断开时即使 supervisor 报「会话已经不在了」，也仍然把工具从工具表摘干净——否则模型还能看到失效工具。

## 已知的粗糙处

- `mcp_core.py` 的 `server_status()` 文档字符串写着「供 `mcp_server_list` 工具与排查使用」，但**仓库里并不存在 `mcp_server_list` 这个工具**。目前 `server_status()` 只有排查用途，没有工具层入口——模型无法查询 MCP server 状态。
- `mcp_config.py` 提供了 `write_config()` 并注明「运行时增删 server 的工具走这条」，同样**没有对应的工具实现**。运行时改 `mcp.json` 目前只能手工改文件再重启。
- `McpManager.reconnect_server()` 已实现但无调用方。
- `_prewarm_run()` 里读配置失败是静默 `return`——这一条失败不会进 `_errors`，也不会出现在 `server_status()` 里，排查时看不到原因。
