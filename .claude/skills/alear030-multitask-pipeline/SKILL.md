---
name: alear030-multitask-pipeline
description: >-
  Alear030 的 Multitask 四段工作流（plan → executor → style∥review → 协调合并）。
  较大特性、跨模块改动、机制路径变更、或用户明确要求走四段流水线 / Multitask 协作时使用。
  与 explore→plan→execute→verify 对齐；小改用轻量路径（executor + 轻 review）。
  触发词：四段流水线、Multitask、满配四段、plan_agent、executor_agent、style_agent、review_agent。
---

# Alear030 Multitask 四段流水线

把「探索→规划→执行→验收」落到可派发的四段角色。主对话是**协调者**：派发、等人拍板、合并 style+review、决定是否回 executor 修。不另起炉灶。改代码三段纪律（Plan→Execute→Review / 风格 rule）见 `$alear030-multitask-code`。

## 何时满配 / 何时轻量

| 路径 | 启用条件 | 段落 |
|------|----------|------|
| **满配四段** | 跨模块；改权威路径/生产者消费者/生命周期；新机制或替换旧路径；用户点名「四段 / Multitask」 | plan →（拍板）→ executor → style∥review → 合并 |
| **轻量** | 无行为影响的纯文本改动：改错字、加日志、重命名、单点注释 | 跳过独立 plan；executor 直接做 + 轻 review（可自审）；style 可选 |

拿不准时问用户一句「满配还是轻量」，架构稳定期内默认建议满配，用户明确要求才降级；改动触碰任何机制/权威路径/调用链/共享事实源/多模块联动时必走满配。

**硬约束（两路径共用）**

- 先预览后落盘：拟议 diff 轮廓经用户确认再写盘（用户明确「直接改」除外）
- 数据安全：不删/不清/不批量覆盖 `session_detail`、`session_plan`、`memory_storage`、`memory_config`、`memory_log`、`local_model`
- 验证用 `$alear030-verify`；**不跑有副作用的 `python main.py`，除非用户批准**
- 不 commit，除非用户明确要求
- `.claude/` 是本地协作资产，不强制进 git

## 角色与协调

| 角色 | 职责 | 落盘？ |
|------|------|--------|
| **plan_agent** | 探查现状、权威路径、可拍板方案（取舍/风险/**拟议 diff 轮廓**） | **否** |
| **executor_agent** | 按已拍板 plan **自包含**执行 + 低副作用自测；模糊则停 | 是（仅拍板范围） |
| **style_agent** | 对照架构习惯与注释风格；列风格债；默认不改逻辑 | 默认否 |
| **review_agent** | 逻辑正确性/崩溃/并发/Windows；缺陷优先 | 否 |

协调者：

1. 选满配或轻量 → 派 plan（满配）或直接派 executor（轻量）
2. **等人拍板**后再派 executor；未拍板不落盘
3. executor 回报后 **并行**派 style∥review
4. 合并结果：阻塞项优先回 executor；风格债单独问是否修
5. 验收层走 `$alear030-verify`，不凭「做好了」收口

派发用 Cursor Multitask / Task 子代理时：每段指令必须自包含（对齐 alear-executor：上下文可自包含、不适合边写边理解模糊耦合）。当前会话无子代理能力时，协调者**串行扮演**各角色，仍用同一输出模板。

---

## 段 1 — plan_agent（不落盘）

**输入**：用户目标 + 相关路径提示  
**禁止**：写文件、跑有副作用命令、假装已拍板

### 输出模板

```markdown
## Plan

### 现状
- 权威路径 / 生产者 / 消费者 / 生命周期：...
- 关键相关代码：`path` — 一句话

### 方案（可拍板）
- 推荐：...
- 备选：...（若有）
- 取舍：...
- 风险：...

### 拟议 diff 轮廓
- `path/a.py`：改什么（函数/分支级，非愿景）
- `path/b.py`：改什么
- 不改：...（明确边界）

### 验收建议
- 验证层级（AST / 单测探针 / 需批准的 e2e）：...
- 数据安全注意：...

### 待拍板
- [ ] 采用推荐方案？
- [ ] 拟议 diff 范围 OK？
- [ ] 其他：...
```

计划若只有愿景没有「拟议 diff 轮廓」→ **不合格，补完再请拍板**。

---

## 段 2 — executor_agent

**输入**：用户已拍板的 plan（全文或等价约束）+ 工作树路径  
**模糊则停**：缺路径/缺拍板项/与盘上代码矛盾 → 回报阻塞，不猜着写

### 派发指令须自包含（模板）

```markdown
## Executor 任务
工作树：<绝对路径>
已拍板结论：<粘贴或摘要，含拟议 diff 轮廓>
允许改动的文件：...
禁止：超出范围重构；清生产数据；未批准跑 main.py；commit。但发现拍板范围与机制收口/整体架构矛盾（收口需清平行路径、方案漏掉跨模块调用链）时，必须停回报阻塞，不得照做不完整 plan

### 执行步骤
1. 按拟议 diff 落盘（外科手术式）
2. 低副作用自测（见 $alear030-verify：AST / python -m test...）
3. 按下方模板汇报；不要改 AGENTS.md（本地文件,不在仓库里）/.claude 除非任务写明
```

### 汇报模板

```markdown
## Executor 汇报
### 已做
- `path`：改动要点

### 自测
- 命令：...
- 结果：...

### 未做 / 偏离
- ...（无则写「无」）

### 请 style∥review
- 重点文件：...
```

---

## 段 3 — style_agent ∥ review_agent（并行）

两者**同时**派发；都只读（除非协调者另令 style 落盘修注释）。

### style 对照清单

- `$alear030-style-notes`（中文极简、动词向、不写签名式注释）
- 机制收口：一项关切一个权威表示；替换则同次收口旧入口
- 临时截断 ≠ 删实现（入口 return/guard，保留原函数体）
- 三套发现规则（Hook/Prompt/Tool）与新增模块落点
- 外科手术式：不顺手清理任务无关代码

### style 输出模板

```markdown
## Style 清单
### 必须对齐（建议修）
- `path:附近标识`：问题 → 建议

### 可选债
- ...

### 逻辑改动？
- 无（默认）/ 若认为必须改逻辑，标「升级 review」并说明
```

### review 输出模板

```markdown
## Review（缺陷优先）
### 阻塞（必须修）
- `path`：缺陷 / 崩溃 / 竞态 / Windows 路径或编码 → 复现或推理

### 非阻塞
- ...

### 数据与副作用
- 是否触碰受保护目录 / 是否有未批准的 main.py 风险：...
```

---

## 段 4 — 协调合并

```markdown
## 合并裁决
### 回 executor（阻塞优先）
1. ...

### 风格债
- 本轮修 / 记下以后再说：（问用户）

### 验收
- 已跑 / 待跑：...
- 是否需要批准 e2e main.py：是/否
```

阻塞项修完后可再跑一轮轻 review；不必每次重跑满配 plan。

---

## 与现有流程的映射

| 项目节奏 | 本流水线 |
|----------|----------|
| 探索 | plan 的「现状」 |
| 规划 | plan 的「方案 + 拟议 diff + 待拍板」 |
| 执行 | executor |
| 验收 | executor 自测 + review + `$alear030-verify` |
| 代码品味 | style（可 ‖ review） |

alear-executor / Task 子代理：只承接 executor 段（或只读的 style/review）；**plan 与拍板留在主对话**。

## 反模式

- plan 未拍板就开始落盘
- executor 指令只给愿景、不给文件级轮廓
- style 擅自改行为；review 只评风格不找缺陷
- 用删实现代替「临时禁用」
- 把 `python main.py` 当冒烟测试
