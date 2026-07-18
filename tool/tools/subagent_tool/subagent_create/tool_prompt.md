## subagent_create 工具说明

用途: 并行创建并运行多个 subagent，每个 subagent 独立执行一条任务，互不共享上下文，全部完成后按 subagent_id 排序汇总结果返回。

### 何时使用:
- 任务可以拆解为多条互相独立、不依赖彼此中间结果的子任务，适合并行处理时
- 需要对多个目标分别执行相同流程时，例如：多个文件分别分析/检查、多个主题分别调研、多个网页分别抓取总结

### 何时不要使用:
- 子任务之间有先后依赖或需要共享中间结果 → 顺序执行，不要用本工具
- 只有一个任务 → 直接自己处理，不必创建 subagent
- 任务需要写文件或执行命令 → 默认情况下 subagent 只有只读工具权限（file_read/memory_recall/session_slice/web_search/web_fetch），交给它会因缺少工具而失败或答非所问；确实需要时可通过下方 `tool_autho` 参数显式授权，但优先考虑这类任务是否该由主 agent 自己完成

### 参数说明:
- subagent_files (必填): subagent 配置列表，每个元素为一个 dict，需包含:
  - subagent_id: 唯一编号，用于结果排序和对应
  - system_prompt: 该 subagent 的角色设定
  - task_desc: 具体任务描述
  - check_standard: 验收标准，会与 task_desc 一并拼入 subagent 的任务指令，要求其依据此标准自查输出。这不是代码层面强制校验，仅是提示词层面的要求，实际执行效果取决于 subagent 是否遵循
  - tool_autho (可选): 字符串列表，显式指定该 subagent 的工具授权类别，完全替换默认的只读四类（basic_tool/file_read_tool/memory_tool/web_tool）。可选类别：
    - `basic_tool`/`file_read_tool`/`memory_tool`/`web_tool`：默认已包含的只读类别
    - `file_write_tool`：写入/编辑本地文件，有副作用
    - `command_tool`：执行本地 shell 命令，有副作用且风险最高
    - `skill_tool`：查询与加载已有技能
    传入前先确认任务确实需要这些权限，不要无差别授予高权限类别。`plan_tool`（计划编排）、`subagent_tool`（创建下一层 subagent）、`interaction_tool`（向真实用户提问，subagent 在后台线程执行会因等待终端输入而卡死）都不属于"独立执行一条任务"的职责范围，不要授予 subagent
- max_subagent (不需要传入，默认 5): len(subagent_files)超出max_subagent数量上限，会报错拒绝执行

### 上下文隔离:
每个 subagent 拥有独立上下文，无法访问主对话的历史记录、已获取的网页内容或中间结果。subagent 只能通过自身工具（文件读取/网络搜索等）重新获取信息。设计任务时需确保 task_desc 和 check_standard 包含 subagent 独立完成任务所需的全部信息，不要依赖主对话中未持久化、subagent 拿不到的内容。

### file_read 精确性要求:
subagent 可用的 file_read 工具依赖精确的绝对路径读取文件，不会自行搜索或猜测文件名。若任务涉及读取文件，task_desc 中必须给出明确的绝对路径（如 `D:\Alear030\tool\tools\command\tool.py`），而不是笼统的目录或模块描述（如"检查 command 模块"）。若目标是一个目录下的多个文件，需要在 task_desc 中把这些文件的绝对路径逐一列出。

### 调用示例:
```json
{
  "subagent_files": [
    {
      "subagent_id": 1,
      "system_prompt": "你是一个专注于代码分析的助手，只做只读检查，不修改任何文件。",
      "task_desc": "使用 file_read 读取以下文件并检查未处理异常的位置：D:\\Alear030\\tool\\tools\\command\\tool.py、D:\\Alear030\\tool\\tools\\command\\security.py",
      "check_standard": "列出具体文件名、行号，以及问题描述"
    },
    {
      "subagent_id": 2,
      "system_prompt": "你是一个专注于代码分析的助手，只做只读检查，不修改任何文件。",
      "task_desc": "使用 file_read 读取文件 D:\\Alear030\\tool\\tools\\session_slice\\tool.py，检查未处理异常的位置",
      "check_standard": "列出具体文件名、行号，以及问题描述"
    }
  ]
}
```
注意：`subagent_files` 必须是 JSON 数组（每个元素是 object），不要把整个数组序列化成字符串传入。task_desc 中涉及的文件必须写绝对路径，理由见上方「file_read 精确性要求」。

### 调用后:
- 返回 JSON 数组，每个元素包含 subagent_id 和对应的 result，按 subagent_id 升序排列
- 未指定 tool_autho 的 subagent 只有只读工具：文件读取（file_read）、历史记忆召回与对话片段读取（memory_recall/session_slice）、网络搜索与网页抓取（web_search/web_fetch），无法写文件、执行命令；指定了 tool_autho 的 subagent 按其授权类别对应可用
