---
name: alear030-multitask-code
description: >-
  Alear030 Multitask 改代码纪律：Plan → Execute → Review。
  写/改生产代码、派 executor、Multitask Mode 落盘、或用户提 Plan Execute Review /
  四段约定 / 先预览后落盘时使用。与 alear030-multitask-pipeline（满配四段角色）互补：
  本 skill 管写法与验收纪律；pipeline 管角色派发。触发：Multitask 改代码、
  Plan Execute Review、生产代码落盘前、协调者派 executor 前。
---

# Alear030 Multitask 改代码（Plan → Execute → Review）

改生产代码时的**三段纪律**。满配四段角色派发见 `$alear030-multitask-pipeline`；本 skill 不取代它。alwaysApply 摘要见 `.cursor/rules/multitask-code-change-workflow.mdc`。

协调者派 executor 前必须先完 Phase 1。Review 没过 ≠ 完成。

## 项目风格 rule 对齐

Plan/Execute **必须对照**；Review **必须检查**有无违反。要点 checklist，全文不粘贴：

| Rule / Skill | 路径（相对仓库根） | 本流程怎么用 |
|--------------|-------------------|--------------|
| coding-conventions | `.cursor/rules/coding-conventions.mdc` | Execute 写法权威：命名、紧凑风、注释、注册器、最小 diff、锁纪律 |
| architecture-first-extension | `.cursor/rules/architecture-first-extension.mdc` | Plan 架构归位；禁平行注册表/存储/总线/widget |
| minimal-disable-preserve-body | `.cursor/rules/minimal-disable-preserve-body.mdc` | 临时截断只入口 guard，不删函数体 |
| multitask-code-change-workflow | `.cursor/rules/multitask-code-change-workflow.mdc` | 同主题 alwaysApply 摘要；本 skill 更完整 |
| multitask-pipeline-judge | `.cursor/rules/multitask-pipeline-judge.mdc` | 满配 vs 轻量；大改走 pipeline，小改轻量 |
| alear030-style-notes | `$alear030-style-notes` / 全局同名 | 注释与改用户代码：禁空标签、先教后改、保留标识符 |

**coding-conventions 执行要点（对照 rule，不复述全文）**

- [ ] 变量 `snake_case`、中文直译直观；方法动词+名词（`get_`/`_build_`/`match_`…）
- [ ] 类 `PascalCase`+职责后缀；常量 `UPPER_SNAKE` 进 `config.py`
- [ ] 紧凑风跟核心模块（参数贴紧、注解贴紧）；注释中文、动作导向、整行 `#`
- [ ] 扩展走既有注册器（tool/hook/prompt/widget），不新建平行体系
- [ ] 最小 diff：不重排方法、不顺手清死代码、不擅自重命名
- [ ] 临时截断只 guard；锁纪律 / 单事实源 / 数据安全见 rule 对应节

**Review 风格违规速查**

- [ ] 擅自重命名用户标识符
- [ ] 为拆而拆新文件 / 平行模块 / 微 helper 堆
- [ ] 空标签注释（`# 题干`）或签名式参数清单注释
- [ ] 用删实现代替临时截断
- [ ] 语义相同却新建平行路径

---

## Phase 1 — Plan（默认不落盘）

**禁止写盘**，除非用户明确「直接改」。

- [ ] **拟议写法轮廓**：文件 / 函数 / 分支级，不是愿景
- [ ] **架构归位**：扩展既有 tool/hook/prompt/widget；见 `architecture-first-extension.mdc`
- [ ] **明确不改什么**：边界、不顺手重构、不删实现
- [ ] **命名**：保留用户已有标识符；同文件 `_helper` 优先；对照 `coding-conventions.mdc` + 用户当场命名
- [ ] **非 trivial**：先预览 diff 轮廓 → 用户拍板 → 再进 Execute（「直接改」可跳过预览，不可偷工减料）

**轻量路径**：错字 / 纯注释 / 单点日志 → 可跳过独立 plan 文档，执行前口头点明改哪几行；Phase 3 Review **仍要**。

满配 vs 轻量判断：`multitask-pipeline-judge.mdc` + `$alear030-multitask-pipeline`。

---

## Phase 2 — Execute

- [ ] 只改拍板范围；模糊则停，不猜着写
- [ ] 派发指令**自包含**（目标、路径、边界、验收）
- [ ] 保留用户标识符；禁止擅自重命名 / 跨文件搬家
- [ ] 同文件 `_helper` 优先；禁止拆新文件、微 helper 堆
- [ ] 最小 diff；临时截断只入口 guard（`minimal-disable-preserve-body.mdc`）
- [ ] 注释走 `$alear030-style-notes`：禁空标签，说清意图
- [ ] **数据安全**：不删/不清/不批量覆盖 `session_detail`、`session_plan`、`memory_storage`、`memory_config`、`memory_log`、`local_model`
- [ ] 用户在自己写时：**先教后改**；明确「接进去 / 同步 / 改」才落盘

---

## Phase 3 — Review（强制）

对照 **Plan + 用户原话** 验收，不是对照「审计 agent 说可砍」。

- [ ] 逻辑 / 崩溃 / 并发 / Windows；满配可 ‖ style（`$alear030-multitask-pipeline`）
- [ ] **UI/结构契约**：砍「None 占位 / 无用别名」≠ 砍可见结构（序号、pointer、行布局）。不确定就问，不许默认删
- [ ] **答问范围**：用户问 A 别扯 B（例：问 helper 清完没，别主动端到端汇报除非被问）
- [ ] 验证：`$alear030-verify`；**禁止擅自 `python main.py`**（除非用户批准）
- [ ] worktree 改生产代码后按 `$alear030-worktree-change-guard` 确认改在 worktree
- [ ] 阻塞项回 Execute 修；不凭「做好了」收口；**不 commit** 除非用户要求
- [ ] 再跑一遍上方「Review 风格违规速查」

---

## Hard lessons（必须遵守）

1. **先预览后落盘**；「直接改」≠ 可偷工减料（仍要最小 diff、风格、Review）
2. **禁无必要抽象**（一次性别名、对称 None 填充），但**必要结构必须留**（可见布局/序号/pointer 契约）
3. **先教后改**（用户在写时）；明确「接进去/同步/改」才落盘
4. **履行约定**：Plan→Execute→Review；Review 没过不算完成
5. **与 pipeline 分工**：满配四段用 `$alear030-multitask-pipeline`；本 skill 是改代码时三段纪律（协调者派 executor 前也要完 Plan）

---

## 协调者 checklist

| 阶段 | 通过标准 |
|------|----------|
| Plan | diff 轮廓 + 不改清单 + 架构归位 +（非 trivial）用户已拍板 |
| Execute | 仅拍板范围；标识符/风格/截断纪律未漂 |
| Review | 有验证输出；无未处理阻塞；风格违规已扫 |
