---
name: changelog-refresh
description: "刷新 Alear030 项目的 CHANGELOG.md：把近期一批 git 提交归纳成新版本块，或审查修正历史版本块。当用户说'刷新/更新/整理/补 changelog'、'把这批改动写进 changelog'、'changelog 该更新了'，或完成一个功能批次准备记录变更日志时使用。注意和 commit-message 区分：后者生成单次提交的 message，本 skill 把一批提交归纳成 CHANGELOG 里的版本块。这个项目的 CHANGELOG 有固定格式（版本块 + 中文类型标签 + 契机/验证/对应提交/后续计划），不要用通用的 Keep a Changelog 英文分类或随意流水账写法，必须走这个 skill 生成符合项目规范的版本块。"
---

# Alear030 CHANGELOG 刷新

这个项目的 CHANGELOG 不是 commit 流水账，是按主题归纳的版本叙事。格式要同时满足五个维度：信息量、正规、版本控制、内容留存、易读性。核心张力在于：信息量/内容留存要求细粒度（每次提交都留得下），易读性要求粗粒度（能快速扫读）。解法是分层--版本块负责易读（按主题归纳），"对应提交"索引负责留存（每个 commit 都有 hash 可回溯）。所以照抄格式就行，不要自由发挥成流水账，也不要过度精简丢信息。

## 刷新前先做的事

1. 跑 `git log --oneline -20`（或对应范围）看这批提交，确认批次边界：是一个主题统一的工作批次，还是跨了多个主题。主题统一归一个版本块；主题切换才升版本。
2. 判断版本号：新增能力/结构性重构记 `minor`，bug 修复/小改进记 `patch`，架构级破坏性里程碑记 `major`（项目当前未用过，预留）。
3. 核对三类常见问题（见下方"常见坑"）：有没有重复记录、有没有遗漏提交、有没有架构动作被功能条目吸收。
4. 日期取批次的实际时间跨度：单天标 `YYYY-MM-DD`，跨天标 `YYYY-MM-DD ~ YYYY-MM-DD`（如 `2026-07-08 ~ 2026-07-14`）。

## 版本块格式

```
## YYYY-MM-DD[ ~ YYYY-MM-DD] · vX.Y.Z - 主题(动词+对象+价值)

契机：<为什么改/根因。仅重大改动写，小修省略整段>

变更：
- [类型] <对象>：<做了什么>；<关键参数/机制>
- ...

验证：<过程性声明，如 REPL/AST/探针验证。仅重大改动写>

对应提交：<hash>(<一句话>) · <hash>(<一句话>) · ...

后续计划：<下一步打算>
```

## 各字段说明

- **标题**：`## 日期 · 版本 - 主题`。主题用"动词+对象+价值"一句话（如"记忆系统闭环：任务经验技能化、跨会话时间线与可恢复压缩"）。注意标题里的 `-` 是 **em dash（—，U+2014）**，不是普通连字符 `-`--项目所有版本标题都是 em dash，保持一致。
- **契机**：讲清楚"为什么改"和"根因是什么"。仅重大改动写，小修省略整段（连"契机："这行都不写）。这是留给未来自己的决策脉络，省了日后回看难理解决策动机。
- **变更**：每条 `[类型] 对象：做了什么；关键参数`。分号分隔"做了什么"和"关键参数"。按变更类型分点，**不按 commit 分点**--一个 commit 的内容可拆成多条，多个 commit 的同类内容可合并。
- **验证**：过程性声明（如"三轮 REPL 验证""AST+探针确认"）。仅重大改动写，和功能结果分开，让读者能区分"做了什么"和"验证了什么"。
- **对应提交**：列出本批次每个 commit 的短 hash + 一句话。这是"内容留存"的关键--细节被归纳进条目没关系，hash 索引保证能回溯到 commit 原文。changelog 自身的提交（如补 changelog 的那次）不列入，它是元操作。
- **后续计划**：下一步打算。不能省略，是留给未来自己的路标。

## 类型标签（中文前缀）

| 标签 | 用于 |
|---|---|
| `[新增]` | 新功能/新模块/新工具 |
| `[迭代]` | 既有功能改进扩展（非全新也非修 bug） |
| `[修复]` | bug 修复 |
| `[重构]` | 结构性重构，行为基本不变 |
| `[收口]` | 机制收敛、消除双源/平行路径、职责归一（项目特有，呼应"机制先收敛再扩展"） |
| `[清理]` | 版本控制治理、死代码移除、文档同步 |
| `[删除]` | 移除功能/文件 |

## 内容留存核心规则

**架构动作必须独立成 `[收口]` 条目，不能被功能条目吸收蒸发。** 这是本格式最重要的规则。例如"timeline 渲染注入收口到 memory"是个架构动作，如果塞进"重写 compress"条目里一句带过，读者会以为只是 compress 的附庸，丢失了"消除双源漂移"这个独立决策。架构动作单独立条，才能保留决策痕迹。

## 真实例子

**重大改动（完整字段）--v0.5.0：**

```
## 2026-07-19 · v0.5.0 - 记忆系统闭环：任务经验技能化、跨会话时间线与可恢复压缩

契机：v0.4.0 的 memory 管线已能从 slice 涌现 user_info，但 task 类经验仍随会话消散；旧 compress 几乎不触发（计数只算尾片+system 严重低估），且压缩后丢失首轮注入的 timeline。本版本闭合 task->skill 经验链路，并让 compress 真正可触发、可恢复。

变更：
- [新增] task memory pipeline：定型 slice 按 `user_info`/`task` 分类；task 经 normal/advanced 两级节点聚合，三态契约 `merged`/`no_match`/`failed` 路由，累积达阈值产出 skill candidate
- [新增] Session 归属的纯内存 Attachment：`interrupt`（候选确认）/`notification`（自动注入），渲染后即清空，不写入 session 事实数据
- [新增] skill 创建与更新闭环：`create-skill` 从来源 slice 回溯素材，`skill_finish` 写回 advanced task node（append 不丢旧来源），支持已固化 node 累积新变体后产更新 candidate
- [新增] session timeline：after_session 提炼 worthy slice 为 `thread`/`summary`/`keywords`；before_session 按 token 预算经 attachment 注入，辅助 `memory_recall` 收窄 session_ids
- [新增] timeline fallback：提炼失败以 slice 的 `summary_detail`/`topic`/`key_words` 降级构造可追溯 entry（source=fallback），空 summary 渲染兼容
- [重构] session compress：计数改为 main agent 全量 `message_list`（修旧计数只算尾片致几乎不触发）；超阈值 `250000` 后保留 system+最后切片原始消息，attachment 注入更早切片摘要并恢复跨会话 timeline
- [收口] timeline 渲染与注入统一收口到 `memory.inject_timeline_attachment`，`session_timeline_inject` hook 与 `session_compress` 共用同一入口，消除分层双源漂移
- [修复] `file_edit`/`file_write` 的 `path.absolute()` 误用改为 `is_absolute()`（原写法恒真致路径校验失效）
- [清理] `test/` 与运行时 session/memory 数据纳入 .gitignore；CLAUDE.md 正式纳入版本跟踪（供并行 worktree 共享项目约定）

验证：三轮真实 REPL 确认压缩后可由摘要恢复首轮唯一标记；AST + `_emit`/`_update` 分叉探针确认 skill candidate 产出逻辑。

对应提交：`103b444`(四大模块落地) · `645c6ee`(skill更新闭环) · `e3e749c`(compress落地) · `af29115`(timeline fallback) · `05dc5c5`(阈值250000) · `57511e5`(合并+端到端验证) · `6785b16`(CLAUDE.md纳入跟踪) · `1d30e8c`(test纳入gitignore) · `bc236e8`(bench_secret)

后续计划：跑通 LongMemEval benchmark basic 四格；观察真实会话 compress 触发频率、压缩后衔接质量与 timeline fallback 召回效果。
```

**小修补（无契机/无验证）--v0.3.1：**

```
## 2026-07-05 · v0.3.1 - 切片可靠性与命令白名单修复

变更：
- [重构] slice agent 边界提示词：以"自包含最小单元"同时约束过拆和过合；key_words 改为随信息密度自适应
- [修复] 切片 JSON markdown 围栏致解析失败：输出补 markdown 去壳；切片输入保留 tool_calls/tool_result 供切片及 task 提炼消费
- [修复] Windows 风格 / flag 白名单大小写匹配：/flag 统一转大写比对；command prompt 从白名单唯一来源动态生成可用命令清单

对应提交：`5571fb6`(slice agent重写+去壳) · `ba39d40`(命令白名单大小写+动态清单)

后续计划：推进 memory 消费端(slice 分类/task 提炼)链路。
```

可以看到：重大改动写契机和验证，小修补只写变更+对应提交+后续计划，不硬凑契机。

## 常见坑

1. **em dash 陷阱**：标题的 `-` 是 em dash（—，U+2014），不是普通连字符 `-`。用 Edit 工具替换历史版本块时，old_string 里的标题必须用 em dash，否则匹配失败。Read 和 Grep 渲染出来视觉相同，无法肉眼区分，必要时用 `python -c "d=open('CHANGELOG.md','rb').read(); print(repr(d.split(b'\n')[8][:60]))"` 看字节确认（`\xe2\x80\x94` 即 em dash）。
2. **重复记录**：一个 commit 只能归一个版本块。写新版本块前，检查该 commit 是否已被前一个版本块记过。典型情况：patch 修复被误记进下一个 minor 版本（如命令白名单修复被同时记进 v0.3.1 和 v0.4.0）。
3. **遗漏提交**：有治理意义的提交（如 CLAUDE.md 纳入版本跟踪、.gitignore 整理）容易被漏记。对照 `git log` 逐条确认本批次每个 commit 都有归属。
4. **架构动作被吸收蒸发**：见上方"内容留存核心规则"。`[收口]` 必须独立成条，不能塞进功能条目一句带过。

## 边界情况

- 这批改动很琐碎（单个 typo/小修复）：只写变更条目+对应提交+后续计划，省略契机和验证，版本号记 patch。
- 这批改动跨多个主题：拆成多个版本块，不要硬塞进一个版本。
- 用户明确要求不用这个格式（如临时想用英文 Keep a Changelog）：尊重用户临时指令，不要强套。
- 修正历史版本块（而非新增）：同样按本格式重写，重点查重复记录和遗漏提交；用 Edit 时注意 em dash，old_string 标题必须用 em dash（—），new_string 标题也保持 em dash。

## 衔接 commit-message

刷新产生的 CHANGELOG.md 改动，用 commit-message skill 提交。commit message 的“当前进度”可写“CHANGELOG 补 vX.Y 版本块”之类。注意：这次 changelog 自身的 commit 不列入版本块的“对应提交”（它是元操作，见“各字段说明”）。
