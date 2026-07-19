---
name: create-skill
description: "把一个已被验证有效的任务模式固化为新的可复用技能文件，或在已固化技能累积新变体时更新该技能。两种触发场景：(1) 收到 attachment_source 为 memory_pipeline 的系统提示（创建或更新两种），内容形如'最近N次任务被识别为相似模式，建议固化为可复用技能'；(2) 用户主动要求，例如'把刚才这个做法存成技能'、'以后能不能直接调用这套流程'、'帮我做一个技能'。命中后需要先向用户确认再动手，不要看到相似模式就自主创建或更新。"
---

# create-skill

把一段被反复验证有效的任务处理方式，写成未来自己（或其他 agent）可以直接复用的 `skill/<name>/skill.md`。核心约束：**任何一次写盘都必须先有用户确认草稿，任何一次测试判断都必须向用户汇报并等待确认**，不能自主跑完全程再一次性汇报结果。

## 两种触发场景

### 场景 A：系统提示触发（memory_pipeline）

会收到 attachment_source 为 memory_pipeline 的系统提示，有两种形态：

- **创建**：形如"最近 N 次任务被识别为相似模式，建议固化为可复用技能"，附带 `task_desc`、`task_detail`、若干条 `task_slices_nodes` 坐标。
- **更新**：形如"已有技能 X 最近又累积了 N 次相似任务的新变体，建议更新该技能"，附带 `技能名`、`当前技能描述`、若干条新变体 `task_slices_nodes` 坐标。

两种都先用 `ask_user_question` 确认用户是否同意（创建/更新），用户同意后才进入素材收集：

**创建**的素材收集：

- `task_slices_nodes` 只是坐标，不能只凭 `task_desc`/`task_detail` 两行摘要脑补步骤。对每一条坐标调用 `session_slice(session_id, start_round, end_round)`，把原始对话逐条读回来，这才是编写 skill.md 的第一手素材。
- 多条坐标横向比较：哪些步骤/判断在每一次里都成立（提炼进技能），哪些只是某一次的具体细节（具体文件名、具体数值、具体措辞，不要照抄进技能）。

**更新**的素材收集：

- 先 `file_read` 已有 `skill/<技能名>/skill.md` 作为修订基线--这是当前已验证有效的技能内容，更新的本质是在它之上补充新变体、修正被新证据推翻的部分，不是推倒重写。
- 再对每条新变体坐标调用 `session_slice` 回溯原始对话，提炼新变体带来的、基线里还没有的步骤/判断/边界。
- 对比基线与新素材：哪些新内容该补进技能，哪些基线描述被新证据修正或细化，哪些基线内容仍然成立保持不动。

### 场景 B：用户主动要求

没有现成的 `task_slices_nodes` 可以追溯，不能假装有 provenance，也不能只凭自己的印象编。先用 `ask_user_question` 采访用户，至少确认：

- 这个技能要让未来的自己做成什么（目标、期望产出）
- 触发时机：以后用户在什么场景、说什么样的话，应该自动命中这个技能（description 是唯一的触发机制，问不清楚会导致以后该触发时反而没触发）
- 当前对话里是否已经有一次具体的成功案例可以参考

在采访之外，可以结合当前对话的上下文联想相关步骤；也可以用 `memory_recall` 按关键词查一查历史上是否有类似任务的痕迹作补充，但这是可选项，不是必须项。这条路径的素材天然不如场景 A 可靠，起草后的用户确认环节更不能省。

## 写 skill.md 的格式要求

参考项目内已有的 `skill/coding-conduct/skill.md`、`skill/competitive-analysis/skill.md`：

- YAML frontmatter 只有 `name` 和 `description` 两个字段。`name` 用英文短横线命名，必须和目录名 `skill/<name>/` 完全一致（`skill_load` 按目录名匹配，不一致会导致技能加载不到）。
- `description` 是唯一的触发机制：要同时写清楚"什么时候用"和"用来做什么"，不要求用户说出技能名字才触发，可以适度写得"push"一点。
- body 是给未来的自己（或其他 agent）看的操作手册，直接写步骤、需要用到的工具、遇到分支怎么判断；不要写"如何创建这个技能"这类元描述——那是这份 create-skill 自己的职责，不属于新技能的内容。

## 起草与确认（写盘前必须完成）

**创建**：把完整的 skill.md 草稿（带 frontmatter）直接展示在对话里，用 `ask_user_question` 明确问用户"这份草稿可以吗，需要调整哪里"。草稿没被用户明确认可前不要调用 file_write。

**更新**：以 diff 为主向用户展示修订--分"新增"/"修改"/"删除"列出相对基线的改动，并附修订后的完整 skill.md 供查看上下文。用 `ask_user_question` 确认"这些修订可以吗"。更新场景用户更关心改了哪、为什么改，diff 让确认更聚焦；但删改已有步骤必须给出新证据理由，不能凭印象删。草稿没被用户明确认可前不要调用 file_write。

## 写盘

用户确认后，用 `file_write` 写入 `D:\Alear030\skill\<name>\skill.md`。创建写新文件，更新覆盖同名已有文件。

## 测试环节

用 `subagent_create` 派一个 subagent 实际执行一次这个技能覆盖的典型任务，验证的是"技能能否被真实发现、加载、并被正确执行"这条完整回路，而不是只读一遍内容判断像不像：

- `tool_autho`：至少要包含 `skill_tool`（否则 subagent 连 `skill_load` 都用不了），再按这个技能实际执行需要的能力加其他类别（比如技能涉及写文件就加 `file_write_tool`，涉及查历史就加 `memory_tool`）。按技能内容判断需要什么，不要无差别全给。
- `task_desc`：给一个具体、能真实命中这个技能的典型任务描述（创建可用原始 `task_desc` 或简化版；更新应包含新变体场景，验证修订后仍能命中并真正覆盖新变体；场景 B 可用用户采访里给的例子），并告知 subagent 现在有一个名为 `<name>` 的可用技能，任务需要时用 `skill_load` 加载它。subagent 是独立上下文，不能依赖主对话里已经读过的内容，task_desc 要自包含。
- `check_standard`：依据 skill.md 里定义的产出/步骤要求来写验收标准；更新场景增补"覆盖新变体"的验收点，确认修订不是只改了字面而新变体未被真正覆盖。

## 判断环节（不能省略）

`subagent_create` 返回的 `result` 是 subagent 自己对自己的检查，不是标准答案，**不要把这个原始 result 直接转发给用户**。拿到结果后：

1. 主 agent 自己对照最初的 `task_desc`/`check_standard`，以及这个技能本应达到的效果，做出"通过/不通过"的判断
2. 用 `ask_user_question` 向用户汇报判断结论（通过或不通过）+ 理由摘要，并等待用户确认下一步——**不管判断结果是哪一种，都必须走这一步**，不能因为自己判断通过了就自主认为任务完成、自主关闭流程

## 不通过时怎么办

和用户讨论具体哪里不对（素材不够、步骤有遗漏、触发描述不准等），回到"起草与确认"重新修改 skill.md 草稿，再走一遍确认→写盘→测试→判断的循环。判断为不通过时不要只字面上改一两个词就直接改判为通过。

## 判断通过后的收尾（仅场景 A）

判断为通过、且用户确认后，场景 A（无论创建还是更新）必须再做一步写回，否则 memory_pipeline 下次识别到同一批相似任务会**重复提示**：

- 调用 `skill_finish(task_id, skill_name)`，其中 `task_id` 取自最初 attachment 里的"任务id"，`skill_name` 是技能目录名（创建时是刚写盘的新目录名，更新时是已有技能目录名，与 frontmatter `name` 一致）。
- 该工具会从 `skill/<name>/skill.md` 的 frontmatter 读 description 作为 skill_desc，写回 `advanced_task_node.json`：给对应 `task_id` 的 node 补/更新 `skill_info`、把 `task_desc` 更新为 skill_desc、把原 `task_slices_nodes` 固化进 `skill_info.skill_source_nodes`（更新时追加进已有来源，不丢旧来源）后清空。
- 写回成功后该 node 带上 `skill_info` 标记且 `task_slices_nodes` 清空，后续再有相似 slice 匹配进来只从 0 重新累积来源，累积达 3 个新变体才会再次触发"更新"提示，不会重复打扰。

场景 B（用户主动要求创建）没有 `task_id`，不调用 `skill_finish`，判断通过即结束。