## skill_finish 工具

用途: 技能创建/更新流程的收尾。把刚写盘的技能回写进 advanced_task_node，给对应 task node 打上/更新 skill_info 标记，这样 memory_pipeline 后续再识别到同一批相似任务时不会重复提示"建议创建/更新技能"。

### 何时使用:
- create-skill 流程已走完(起草->用户确认->写盘->subagent 测试->判断通过)，且判断结果已向用户汇报并获得确认
- 触发来源是 memory_pipeline 系统提示(场景 A)：手上有 attachment 里带的 `task_id`
- 创建与更新两种场景都适用：创建时 skill_name 是刚写盘的新技能目录名；更新时 skill_name 是被修订的已有技能目录名

### 何时不要使用:
- 场景 B(用户主动要求创建技能)：没有 task_id，不存在要回写的 task node，判断通过即结束，不要调用本工具
- 技能文件还没写盘，或判断尚未通过，或用户还没确认--提前调用会写入半成品状态
- task_id 不是 attachment 给的整数时不调用(不要自己编一个)

### 参数说明:
- task_id (必填): 整数，取自最初 memory_pipeline attachment 里的"任务id"，对应 advanced_task_node 中要回写的那个 node
- skill_name (必填): 技能目录名，必须与 `skill/<name>/skill.md` 的 frontmatter `name` 完全一致。创建时是刚写盘的新目录；更新时是被修订的已有目录。工具内部会按这个名字去读 skill.md 的 description 作为 skill_desc

### 调用后:
- 工具从 `skill/<skill_name>/skill.md` 读 frontmatter 的 description 作为 skill_desc
- 写回 advanced_task_node.json 中对应 task_id 的 node:写 skill_info(skill_name / skill_desc / skill_source_nodes)、把 task_desc 更新为 skill_desc、把原 task_slices_nodes 固化进 skill_info.skill_source_nodes 后清空
- 更新场景下，新累积的 task_slices_nodes 会追加进已有的 skill_source_nodes(existing + new)，不丢旧来源；写回后 task_slices_nodes 清空，从 0 重新累积，达 3 个新变体才会再次触发"更新"提示
- 返回成功或失败信息；成功表示该 node 已带上 skill_info 标记，后续相似任务只会累积来源、不会立即重复触发提示

### 注意事项:
- skill_name 必须是已经写盘存在的技能目录，否则工具会返回"未找到 skill.md"失败
- 本工具只做回写，不创建/修订技能文件、不跑测试；技能本体的创建与更新由 create-skill 技能流程负责，本工具在它之后收尾