# Alear030 配置说明

**中文** · [English](CONFIGURATION.en.md)

← [返回 README](../README.md)

跑起来只需要配 `.env` 里的三级模型，其余全部有默认值。这份文档把所有可配项列全，包括 README 里没展开的 MCP 接入。

---

## 目录

- [必需：三级模型](#必需三级模型)
- [可选：网络代理](#可选网络代理)
- [接入 MCP server](#接入-mcp-server)
- [开启记忆管线](#开启记忆管线)
- [本地嵌入模型](#本地嵌入模型)
- [运行常量（config.py）](#运行常量configpy)

---

## 必需：三级模型

复制模板后编辑：

```bash
cp .env.example .env
```

Alear030 把模型按能力分三级，都走 OpenAI 兼容协议。**三级可以指向同一个服务商，仅 `model_name` 不同**；也可以分别接不同服务商。

```dotenv
MAX_LEVEL_BASE_URL=https://api.deepseek.com
MAX_LEVEL_API_KEY=your-api-key
MAX_LEVEL_MODEL_NAME=deepseek-v4-pro

MEDIUM_LEVEL_BASE_URL=https://api.deepseek.com
MEDIUM_LEVEL_API_KEY=your-api-key
MEDIUM_LEVEL_MODEL_NAME=deepseek-v4-flash

LOW_LEVEL_BASE_URL=https://api.deepseek.com
LOW_LEVEL_API_KEY=your-api-key
LOW_LEVEL_MODEL_NAME=deepseek-v4-flash
```

哪个 Agent 用哪一级由 `agent/agents.yaml` 的 `agent_level` 决定：

| 级别 | 使用者 | 说明 |
|---|---|---|
| `medium_level` | main、slice、summary、plan | 主力档，绝大多数调用走这里 |
| `low_level` | memory | 只做 slice 分类这类结构化抽取，便宜的模型够用 |
| `max_level` | 当前无常驻 Agent 使用 | 保留档位，配置里仍需填写 |

> `max_level` 目前没有常驻 Agent 使用，但 `config.py` 会无条件读取这三组变量，缺失时对应值为 `None`。填上和 medium 相同的值即可。

**模型能力要求**：main / plan 走 function calling，模型必须支持 tools；`loop._chat` 在带 tools 时会固定附加 `thinking: enabled` 的 `extra_body`，不支持该字段的服务商可能需要改 `loop/loop_core.py`。

---

## 可选：网络代理

只有 `web_search` 工具需要走代理时才配，不填则直连：

```dotenv
HTTP_PROXY=
HTTPS_PROXY=
```

---

## 接入 MCP server

Alear030 可以作为 MCP 客户端接入外部 server，stdio 与 Streamable HTTP 两种传输都支持。配置文件是 `mcp_client/mcp.json`（**不纳入版本控制**，仓库里只有 `mcp.json.example` 模板）。

```bash
cp mcp_client/mcp.json.example mcp_client/mcp.json
```

### 配置格式

```jsonc
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "./workspace"],
      "env": {},
      "enabled": true
    },
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": "Bearer ${GITHUB_MCP_TOKEN}" },
      "timeout": 30,
      "enabled": false
    }
  }
}
```

格式与 Claude Code / Claude Desktop 的 MCP 配置**互相可拷贝**。

### 字段

| 字段 | 适用 | 说明 |
|---|---|---|
| `type` | 两者 | `stdio` 或 `http`。**可以省略**——省略时按有没有 `url` 推断 |
| `command` | stdio | 必填。启动 server 的可执行文件 |
| `args` | stdio | 命令行参数数组 |
| `env` | stdio | 传给子进程的环境变量 |
| `cwd` | stdio | 子进程工作目录 |
| `url` | http | 必填。Streamable HTTP 端点 |
| `headers` | http | 请求头，凭证通常放这里 |
| `timeout` | http | 秒，默认 30 |
| `sse_read_timeout` | http | 秒，默认 300 |
| `enabled` | 两者 | 缺省视为启用。`false` 时只登记不连接，用来控制 schema 膨胀 |

### 凭证放 .env，不放配置文件

配置里凭证只能以 `${VAR}` 占位符出现，真值写在 `.env`：

```dotenv
GITHUB_MCP_TOKEN=ghp_xxxxxxxxxxxx
```

占位符在建立连接时展开。**解析不到（变量未设置或为空）会跳过该 server 并记录原因，不会拿空值去连**。

### 连上之后

- 工具名是 `mcp__{server_key}__{tool_name}`，前缀用配置里的 key 而非 server 自报名，两个 server 自报同名也不会撞
- 授权走 `mcp_tool` 类别，在 `agents.yaml` 里对 main 和 plan 开启，其余 Agent 关闭
- MCP server 在启动时由后台线程逐个连接，**单个 server 失败只记录，不影响主程序启动**
- 工具表是运行时可变的：server 连上后各 Agent 的 `tool_list` 会被刷新，下一次模型调用即可见
- **但 system prompt 是启动快照，不会刷新**——MCP 工具只在 function-calling schema 里可见，不会出现在 `tool_prompt` 分块的工具清单里
- 单条 MCP 工具结果超过 `MCP_TOOL_RESULT_MAX_CHARS`（默认 4000 字符）会被截断，防止不受控的远端返回顶爆 session token

---

## 开启记忆管线

`config.py` 里的 `MEMORY_PIPELINE_ENABLED` 默认是 `False`。

**它关掉的不只是「入库」。** `memory_pipeline` hook 的判空在 `session._session_slice()` 之前，所以默认状态下切片、摘要、slice 分类、用户画像、task 节点、时间线**一步都不会发生**。保持默认值 clone 下来跑，会以为记忆功能是坏的。

```python
# config.py
MEMORY_PIPELINE_ENABLED = True
```

代价：开启后每轮对话会额外产生若干次模型调用（一次切片 + 每个待摘要片各一次 + 分类与画像提取）。

整条链路怎么工作见 **[记忆系统](modules/memory.md)**。

---

## 本地嵌入模型

会话切片的语义召回用本地中文 GTE 模型，**不需要任何配置**。

首次运行 `python main.py` 时，权重（约 195MB）会自动从 ModelScope 下载到 `local_model/` 目录。需要联网，仅首次需要，之后离线可用。

模型在独立的 worker 进程里加载，不阻塞 TUI 启动。

---

## 运行常量（config.py）

`config.py` 集中了所有路径与运行常量。改动前先读那里的注释——多数常量后面都写了当初为什么定这个值。

| 常量 | 默认值 | 作用 |
|---|---|---|
| `MEMORY_PIPELINE_ENABLED` | `False` | 跨会话记忆管线总闸，见上一节 |
| `MAX_TOOLCALLS` | 30 | 单轮 ReAct 的最大工具调用次数，超出后强制收尾 |
| `SUB_MAX_TOOLCALLS` | 15 | 临时 subagent 的上限 |
| `PLAN_STALL_LIMIT` | 3 | plan 编排无进展熔断：连续这么多轮拿到同一个 step 就退出 |
| `MAX_SESSION_TOKEN` | 250000 | session 压缩的触发阈值，按模型上下文窗口留安全余量 |
| `STRUCTURED_API_TIMEOUT` | 60 | slice / summary 这类不带 tools 的结构化直调的超时（秒） |
| `STRUCTURED_API_RETRIES` | 0 | 同上，重试次数 |
| `SLICE_TOOL_RESULT_MAX_CHARS` | 2000 | 切片重喂窗口里单条 tool_result 的字符上限 |
| `MCP_TOOL_RESULT_MAX_CHARS` | 4000 | 单条 MCP 工具结果的字符上限 |

### 强制收尾与结构化直调的两个坑

**`MAX_TOOLCALLS` 触顶后不是报错，而是物理断供**——`_force_final_reply` 重新发起一次不带 tools 的请求，让模型只能输出文本。调高这个值等于允许更长的工具链，也等于更大的单轮 token 开销。

**slice / summary 直调固定关掉 thinking**。实测同一份 4.2k tokens 的切片请求，开着 thinking 时挂 61 秒后被网关掐断，关掉后 6.5 秒正常返回。`STRUCTURED_API_TIMEOUT=60` 是在此基础上留的 9 倍余量。

### 数据路径

| 常量 | 路径 |
|---|---|
| `SESSION_MEMORTY_DETAIL_PATH` | `session/session_detail/` |
| `SESSION_PLAN_FILE_PATH` | `session/session_plan/` |
| `MEMORY_STORAGE_PATH` | `memory/memory_storage/memory_storages/` |
| `MCP_CONFIG_PATH` | `mcp_client/mcp.json` |
| `LOCAL_EMBEDDING_MODEL` | `local_model/iic/nlp_gte_sentence-embedding_chinese-base` |
| `WORK_SPACE` | `workspace/` |

这些目录存的都是真实运行数据（会话记录、派生记忆、模型权重），已全部 gitignore。删之前先想清楚——它们不是可随意重建的缓存。
