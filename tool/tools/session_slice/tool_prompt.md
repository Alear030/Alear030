## session_slice 工具说明

用途: 根据已知的历史 `session_id` 与轮次范围，读取该段对话原文，用于核对摘要、画像或任务提炼所依赖的具体上下文。

### 何时使用:
- 已通过 memory_recall 得到候选切片，需要查看其原始对话以确认摘要是否准确时
- 已知历史 session_id 和目标 round 范围，需要追溯某项结论、用户事实或任务细节的来源时
- memory 管线需要基于原文进一步提炼信息，而不是仅依据 slice 摘要时
- advanced task 需要比较历史与当前任务的工具协作和执行流程时

### 何时不要使用:
- 需要按语义寻找相关历史内容，但尚不知道 session_id 或轮次范围 → 先用 memory_recall
- 只需当前 session 的对话内容 → 直接使用当前上下文
- 只需要切片的 topic、关键词或 summary_detail → 直接使用 memory_recall 的返回结果

### 参数说明:
- session_id (必填): 历史 session 的唯一标识，由 memory_recall 或来源节点返回
- start_round (必填): 读取范围的起始轮次，通常原样使用来源中的 start_round
- end_round (必填): 读取范围的结束轮次，通常原样使用来源中的 end_round
- include_tool_messages (选填，默认 false): 是否保留 `tool_calls` 与 `tool_result`。核对 advanced task 的执行步骤、工具协作和实际结果时设为 true；一般摘要或用户信息核对保持默认值，减少无关内容与 token 消耗

### 调用后:
- 返回指定轮次范围内的消息列表，每条包含 message_role、message_content 和 message_round 等原始字段
- 默认排除 tool_calls 与 tool_result；`include_tool_messages=true` 时按原顺序一并返回
- 若 session_id 不存在，返回包含 error 字段的 JSON，不要把它当作空对话或继续编造历史内容

### 注意事项:
- 该工具只读取已有范围，不做语义检索、摘要或跨 session 聚合
- 优先使用来源给出的完整 session_id / start_round / end_round 原样调用，避免自行猜测轮次范围
- 单次读取范围应与目标切片一致；无关地扩大范围会引入额外上下文并降低后续提炼准确性
- 工具消息通常体积较大；只有判断确实依赖工具动作、参数或结果时才启用 include_tool_messages
