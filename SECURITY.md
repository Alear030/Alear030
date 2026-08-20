# 安全说明

**中文** · [English](SECURITY.en.md)

Alear030 是一个给本机单人使用的实验性 Agent Harness。它会在你的机器上**执行命令、读写文件、访问网络**，这份文档说清它的防护边界到哪里，以及不该指望它做什么。

## 威胁模型：防模型手滑，不是沙箱

`command` 工具带一层安全闸门，但它的假设是**模型在正常任务里可能顺手写出不可逆的操作**（比如接到「清理一下 build 目录」就跑出一条递归删除），而不是**有人蓄意构造命令来绕过它**。

具体形态：

- 闸门是**破坏性拦截**，不是准入白名单。`COMMAND_WHITELIST` 只是分类表，没登记的命令标 `unknown` 并照常放行；真正拦截的是 `DESTRUCTIVE_COMMANDS` 与 `BLOCKING_PATTERNS`
- 命令按 `&&`、`||`、`&`、`;`、`|` 分段逐条校验，`bash -c` / `python -c` / `powershell -Command` 这类解释器载荷会被取出来重新过一遍闸门（限一层嵌套，`-EncodedCommand` 因无法静态校验直接拒）
- 危险路径（系统目录、盘符根等）按命令类别判定，写操作才校验目标路径

**真正需要隔离时请用容器或虚拟机，不要指望这一层。** 它拦得住手滑，拦不住蓄意绕过。

## 文件访问是读写不对称的

这一条容易被误解，单独说明：

- **写**：`file_write` 与 `file_edit` 的目标路径必须落在 `workspace/` 或 `skill/` 之内，否则直接拒绝
- **读**：`file_read`、`file_grep`、`file_glob` **可以读磁盘上任意绝对路径**，只要求路径是绝对的

也就是说，模型不能往工作空间外写东西，但能读到你机器上它有权限读的任何文件。如果本机有不希望被读到的内容，这一点要心里有数。

## 其他需要知道的边界

- **运行时临时 subagent 默认只有只读授权**（`basic_tool` / `file_read_tool` / `memory_tool` / `web_tool`），但调用方可以通过 `tool_autho` 参数整个替换掉这份授权，包括授予 `command_tool` 与 `file_write_tool`
- **跨会话记忆会把对话内容落盘**到 `session/session_detail/` 与 `memory/` 下。这些目录已在 `.gitignore` 里，但如果你要分享仓库或截图，注意里面是真实对话
- **MCP 客户端会连接你在 `mcp_client/mcp.json` 里配置的外部 server**，并把远端工具注册进工具表。凭证在配置里只以 `${VAR}` 占位符出现，真值走 `.env`；请自行确认所连 server 的可信度
- **不要在多租户环境、或者会接收不受信任输入的场景里跑这个项目。** 它没有为此设计

安全闸门的完整实现说明见 [架构文档](docs/ARCHITECTURE.md#核心设计决策)。

## 报告安全问题

请通过 GitHub 的 **private vulnerability reporting** 提交（仓库页 → Security → Report a vulnerability），不要开公开 issue。

这是单人维护的实验项目，没有承诺的响应时限，也没有安全更新周期——请按「一份可以读源码、但不该托付重要数据的实验代码」来对待它。
