# 协作技能目录

**中文** · [English](README.en.md)

← [协作说明](../../COLLABORATION.md) · [返回 README](../../README.md)

这个目录下是我和 coding agent 协作时用的十四个技能，一共 1406 行，全部进了版本控制，可以直接点开看。

它们不是配置，是**沉淀**。每一个背后都有一次它做错了、或者我讲不清楚的经历——踩一次坑，写一条规矩。所以这份目录与其说是功能清单，不如说是这个项目的事故记录。

技能本身的格式很简单：一个目录一个 `SKILL.md`，YAML frontmatter 里写 `name` 和 `description`，后面跟正文。这十四个里有十三个的 frontmatter 就这两个字段，只有 `alear030-worktree-change-guard` 多一个 `user-invocable`。触发主要靠 `description`——agent 读到它自己判断这次该不该用；我也可以直接点名让它用哪个。这套设计和 Alear030 自己的运行时技能系统是同一套，那部分写在[协作说明](../../COLLABORATION.md)里。

---

## 总表

| 技能 | 行数 | 一句话 |
|------|------|--------|
| [`alear030-verify`](alear030-verify/SKILL.md) | 152 | 这个项目的验证方式和常规 Python 项目不一样 |
| [`alear030-worktree-change-guard`](alear030-worktree-change-guard/SKILL.md) | 34 | 在 worktree 改完生产代码必须回读确认 |
| [`alear030-commit-message`](alear030-commit-message/SKILL.md) | 131 | commit message 的固定格式 |
| [`alear030-push-merge`](alear030-push-merge/SKILL.md) | 199 | commit 之后 push、开 PR，停下评审，放行后才合并 |
| [`alear030-changelog-refresh`](alear030-changelog-refresh/SKILL.md) | 120 | CHANGELOG 版本块的固定格式 |
| [`alear030-style-notes`](alear030-style-notes/SKILL.md) | 74 | 往我的代码里写注释的口味 |
| [`alear030-issue-mark`](alear030-issue-mark/SKILL.md) | 86 | issue 的标签体系与正文规范 |
| [`alear030-doc-drift-check`](alear030-doc-drift-check/SKILL.md) | 43 | 文档与代码现场的只读漂移体检，只汇报不修复 |
| [`alear030-pr-review`](alear030-pr-review/SKILL.md) | 105 | 已开 PR 的 merge 前只读审查，三道对账加一条退出标准 |
| [`alear030-issue-pretodoHandle`](alear030-issue-pretodoHandle/SKILL.md) | 66 | 从看板认领一个 issue 到收尾的完整流程 |
| [`alear030-issue-fix`](alear030-issue-fix/SKILL.md) | 52 | issue 从拉取定位到方案拍板、修复、测试、review、commit 的流水线 |
| [`alear030-scan-claude-markers`](alear030-scan-claude-markers/SKILL.md) | 52 | 扫描我留在代码里的 @claude 待办标记 |
| [`alear030-multitask-pipeline`](alear030-multitask-pipeline/SKILL.md) | 210 | 四角色并行改动的派发协议 |
| [`alear030-multitask-code`](alear030-multitask-code/SKILL.md) | 108 | 改生产代码的三段纪律 |

名字全部带 `alear030-` 前缀。早期只有项目特有的几个带，`commit-message` 这类「格式规范」没带——但它们同样只在这个项目里成立，前缀的有无并不表示任何区别，反而会让人以为有。所以后来统一加上了，规则变成一条没有例外的规则。

按它们编码的知识类型，可以分成四组。

---

## 一、项目特有的反直觉坑

这一组的共同点是：**按常规经验做就会出事**，而且出事之后不容易看出原因。

### `alear030-verify`（152 行）

这个项目的验证方式有几个反直觉的地方，凭通用 Python 项目的经验直接套会踩：

- `python main.py` 在主仓库**不是**无副作用的冒烟测试——它会写 session 文件、可能调模型 API。但在关掉了 memory pipeline 的开发 worktree 里可以放开跑。所以第一步是先分清自己在哪个 checkout，再决定松紧。
- 验证脚本必须用 `python -m` 的点号路径调用，直接 `python test/xxx/script.py` 会报 `ModuleNotFoundError`。
- `unittest discover` 不能带 `-s test` 参数，否则 `test/loop/__init__.py` 会遮蔽顶层的 `loop` 包，报 `ImportError`。

还有一条 Windows 特有的，原文是这么写的：

> 在 Windows 上用 `Path.read_text()`/`write_text()` 读写项目里的中文 JSON/文本文件时必须显式传 `encoding='utf-8'`；不传会走系统默认 GBK 码页，遇到中文内容直接 `UnicodeDecodeError`。这个坑在 prompt/memory 相关模块的文件读写点上出现过不止一次。

「出现过不止一次」——这就是它为什么会变成一条规矩。

这是被引用最多的一个技能，另外三个（`alear030-issue-pretodoHandle`、`alear030-multitask-code`、`alear030-multitask-pipeline`）都在自己的验证环节指向它。

### `alear030-worktree-change-guard`（34 行）

最短的一个，也是唯一一个标了 `user-invocable: false` 的——意思是它不出现在我的手动菜单里，指望 agent 改完代码之后自己想起来用。

这里得说清楚一件事：**没有任何东西强制它执行。** 仓库里没有配 hook 给它托底，所以它是一条强建议，不是一道闸门。「写进技能」和「机制上保证」是两回事，这个区别我以前没分清楚。

它防的现象是这样的：在 worktree 里用 Edit 改生产代码，改动落到了主仓库，worktree 那边没变。测试跑的是 worktree 的代码（没改），于是一直崩，而代码看起来明明改了——排查很久。真实的例子是 `memory_core.py` 那次。

**根因没追出来。** 当时没留下足够证据，不清楚是路径解析、工作目录还是别的原因。所以这条规矩干脆不解释原因，只要求结果：在 worktree 改完非 `test/` 的文件，回读一遍目标 worktree 的绝对路径，核对 diff。

---

## 二、格式规范

这一组约束的是产出物长什么样。它们存在的理由都一样：**通用做法在这个项目里会丢掉某种我需要的东西。**

### `alear030-commit-message`（131 行）

格式是 `YYYYMMDD_HHMMSS <一句话主题>` + 空行 + 正文，正文分「当前进度 / 后续计划」。标题限 50 字内。

那个 50 字的限制是有来历的：

> 早期这个项目把全部内容挤在一行,结果整条两千字的 message 都成了标题——

后果是 `git log --oneline` 撑满终端没法扫，GitHub 提交列表和 blame 悬浮提示全是截断的一坨，**恰好把时间戳前缀本该提供的「按时间线回溯」能力废掉了**。本来是为了方便回溯才加的前缀，结果因为标题太长反而让回溯变得不可能。

技能里还有一条分界线：**只记改动本身，不记协作编排过程。**「派了几个子代理」「先探索再规划」属于生产过程，不属于改动内容。commit 的署名是我，不该出现 agent 的自述。

### `alear030-changelog-refresh`（120 行）

版本块的固定格式（标题 / 契机 / 变更 / 验证 / 对应提交 / 后续计划）加 7 种中文类型标签，不用通用的 Keep a Changelog 英文分类。

它记的坑里有一个特别阴：**em dash 陷阱**。版本块标题里的那个破折号是 em dash（—，U+2014），不是普通连字符。用 Edit 工具替换历史版本块时，`old_string` 里必须也是 em dash 否则匹配失败——而 Read 和 Grep 渲染出来视觉完全相同，肉眼分不出来。技能里给了一条看字节的命令来确认。

另一个是重复记录：一个 commit 只能归一个版本块，实际发生过 patch 修复被同时记进两个版本的情况。

### `alear030-style-notes`（74 行）

往我的代码里写注释时的口味：中文、极简、动词或动作导向，禁止空标签注释（那种只是把函数名翻译一遍的）。

还有三条是关于改我的代码的：保留我原有的标识符命名、优先用同文件里已有的 helper、先讲清楚再改。最后一条尤其重要——我需要知道改了什么、为什么改，不然这段代码就从「我的」变成「不知道谁的」了。

### `alear030-issue-mark`（86 行）

技术债 issue 的规范：统一用 `tech-debt` 标签（不用 GitHub 默认的 bug/enhancement），严重度写成标题前缀 `[高]`/`[中]`/`[低]`，正文走三段式——issue背景（现状+风险）/ issue功能（目标+建议方案）/ issue检查（验收标准）。证据必须给到 `文件:行号`。

写这份协作文档的过程中就用它记了 5 条，都是顺手做模块耦合普查时发现的。

---

## 三、多步工作流

这一组是流程编排：步骤多、有先后依赖、中间有需要我拍板的闸门。

### `alear030-issue-pretodoHandle`（66 行）

从 GitHub Projects 看板的 `pre-todo` 列认领一个 issue，然后：开分支 → 规划（**停下来等我确认**）→ 开发 → 验证 → 自检 → 合并（交给 `alear030-push-merge`）→ 把看板推到 done → 问我要不要接下一个。

两个设计点：一是**看板状态就是事实源**，不靠对话记忆判断做到哪一步了；二是单槽——一次只处理一个，不并发认领。

### `alear030-issue-fix`（52 行）

不带号时拉取 tech-debt 的 open issue 清单（时间正序）供我挑，带号直接进：定位（只读）→ 提方案（**停下来等拍板**）→ 修 → 测 → 派 review subagent → commit，**止于 commit**。

它和 pretodoHandle 是显式分工：看板认领、开分支、PR 合并归那个，这个在当前 checkout 直接修、不开分支不 push。里面有一条从 #8 学来的教训进了正文：**issue 会过时**——立项时"无隔离"的前提被 #5 合入改变，差点照着过时前提再修一遍；所以定位步骤强制先复核前提还成不成立。

### `alear030-push-merge`（199 行）

commit 之后的收尾，**分两段，中间必须停**：

```text
第一段：前置检查 → push → 开 PR → 报告链接 → 停
      ⏸  我自己读，或交给 GitHub Copilot review
第二段：合并 → 清理分支/worktree（常驻分支除外） → 同步本地 master
```

这个停顿是这个技能最重要的部分，而它是补上去的。第一版把 push、开 PR、合并串成一条无人值守的流水线，结果 PR 开出来几秒钟就被自己合掉了——**我选「走 PR 而不是本地 merge」，要的就是那个可以停下来看的东西；开完就合，PR 等于不存在**，那还不如直接本地 merge。

同理，它和 `alear030-commit-message` 分开也是为了留复查窗口：commit 完再读一遍，发现问题还能改。所以「commit一下」不会顺带推上去，「推上去」也不会顺带合并。一句话里明确说了「推上去并合并」才连着跑，且要在报告里点出这次跳过了评审。

里面写死了三件不能靠推断的事：

- **常驻分支名单**（`master`、`Alear030_dev`）永不删除。不靠「看起来像不像长期分支」判断——判断错了就是一次不可逆的删除。名单外的一律当临时分支，而临时分支还要再问一次才删。
- **走 GitHub PR，不走本地 merge。** 这条是从矛盾里长出来的：`alear030-issue-pretodoHandle` 原先写的是 `git checkout master && git merge`，而实际上每次都是开 PR 合的。规矩和习惯对不上，规矩就是废的。顺带说，squash 也被明确禁掉了——它会把一批 commit 压成一条，那些 message 里的「当前进度/后续计划」就此消失，而它们是这个项目的开发日志。
- **清理要三样一起做**：本地分支、远端分支、worktree。漏一样就留残留。分支上有不打算合并的提交时，删之前得先说清楚哪些东西会跟着消失。

还有一条是被 worktree 坑出来的：PR 在 GitHub 上合并之后，主仓库那个 checkout 的本地 `master` 仍然停在旧提交，**而它看起来一切正常**。下次在主仓库做事就是从一个落后的 master 出发。所以同步本地 master 被写成了收尾的固定动作，不靠记性。

### `alear030-scan-claude-markers`（52 行）

扫描我留在代码注释里的待办标记。三种语义要分清：`@claude` 是给它的任务、`done(@claude): 做了什么` 是已完成的痕迹（保留但不再捡起）、`@claude(ignore)` 是我给自己的备注不许动。

仓库里没有提供自动扫描机制，所以这个技能就是现成的扫描入口——我随时可以喊一声。想让它每次会话开始自动扫一遍，得自己另配一个 SessionStart hook，会不会随仓库分发取决于配置放在哪里。

用技能而不是让 agent 自己去 grep，是因为自己 grep 的结果每次都不一样：漏目录、把 `done(@claude)` 当成待办、或者去动了 `@claude(ignore)`。

### `alear030-doc-drift-check`（43 行）

每天早上九点的定时任务沉淀成的技能：逐篇核对核心文档与代码现场，三种口径——结构性漂移（引用的文件/入口/计数已不存在）、行为描述漂移（断言与代码矛盾）、笔误过期。两条铁律：先机械核对再下结论（压误报）；判定依赖未提交代码的一律跳过进警示区，不猜。全程只读，报告完把决定权交回。

### `alear030-pr-review`（105 行）

和上一个同属只读汇报类，但对象不同：那个查文档与代码的日常漂移，这个查一批已开 PR 的改动在 merge 之前有没有真的收口。

它的来历是一次外部 agent 做的 review：四轮才挖到位，最贵的一条（落盘语义反转）是我自己点破的，而同一个 PR 另一个 agent 很快就看见了。差别不在谁更懂这个项目，在提问方式——一个问「代码怎么写」，一个问「数据变成什么样」。

所以这个技能不装知识，装接线：靶子分类直接用[那篇复盘](../../docs/retrospective/eval-to-architecture.md)已有的四类，机制事实一律写成探针指回 `docs/`（只给查法不给答案，答案会过期，而过期的答案比没有答案更糟），技能自己只留三道对账、分流纪律，和一条退出标准。

**退出标准是这里唯一算新增的东西**：不是「diff 读完了」就算完，是三道对账过完、每条数据流的生产者—消费者—可达性都有结论才算完。漏掉的东西通常不是看不懂，是停太早。

写它的过程里差点栽一次：我本来要往探针表里塞几个具体函数名，让 review 时 grep 一遍完事。拦下来的理由是——**写死名字的查法在改名之后不会报错，它照样返回一批结果**，跑完看到有命中，就以为这一项查过了，于是真正新增的那条路径被静默跳过。所以探针腐烂不是失灵，是**变成一个假的通过**，比没有这条探针更危险。判据因此定成一句：一条探针能进表，当且仅当它不会因为改名、新增实现或重构而变成静默通过；做不到就升到属性层，或者至少加一句失效自检。

同一个理由也否掉了「给持久化入口统一打标记」这个更彻底的方案——那等于断言「持久化入口」已经是个稳定类别，可它现在还在这批改动里被反复挪动。给一份能随时重算的清单建缓存、再承担同步成本，正是这个项目自己的第二类靶子。所以清单改成每次 review 现列、并作为必交产物写进报告；等几次列出来的结果稳定一致了，再谈要不要固化。

---

## 四、派发协议

这一组是项目体量变大之后才出现的，处理的是「一个改动大到需要拆给多个 agent 并行做」的情况。

### `alear030-multitask-pipeline`（210 行）

最长的一个。四段流水线：plan → executor → style ∥ review → 协调合并，四个角色各有各的输出模板。

关键不在角色划分，在**判断标准**：什么时候值得走满配四段、什么时候轻量路径（executor + 轻 review）就够了。跨模块、机制路径变更走满配，小改走轻量。判断错了两头都亏——小改走满配是浪费，大改走轻量是失控。

### `alear030-multitask-code`（108 行）

和上一个互补：pipeline 管角色怎么派，这个管**代码怎么写、怎么验**。

三段纪律：Plan（先规划，**不落盘**）→ Execute（只改拍板范围内的东西）→ Review（强制，不过不算完成）。带一张对照 `.cursor/rules/` 五条规则的 checklist，还有一节叫「Hard lessons」——名字就说明了它是怎么来的。

「先预览后落盘」这条是我反复强调过的：我要先看到要改成什么样，再决定让不让改。

---

## 它们不是十四个孤立的文件

这十四个技能之间有引用关系：

- `alear030-verify` 是基础层，被 `alear030-issue-pretodoHandle`、`alear030-multitask-code`、`alear030-multitask-pipeline` 三个反向引用——凡是走到「验证」这一步的都指向它
- `alear030-commit-message` 和 `alear030-changelog-refresh` 互相衔接，因为一个管单次提交、一个把一批提交归纳成版本块，边界必须对齐
- `alear030-commit-message` → `alear030-push-merge` 是一条单向交接：前者到 commit 为止，后者从 commit 之后接手。`alear030-issue-pretodoHandle` 的合并步骤直接引用后者，不自己再写一套
- `alear030-issue-fix` 与 `alear030-issue-pretodoHandle` 声明分工：前者当前 checkout 修到 commit 为止，后者管看板认领、分支与 PR；修复/测试/提交环节分别指向 `alear030-multitask-code`、`alear030-verify`、`alear030-commit-message`，不复述
- `alear030-multitask-code` 与 `alear030-multitask-pipeline` 明确声明互补，各自不复述对方的内容
- `alear030-style-notes` 和 `alear030-multitask-code` 都指向 `.cursor/rules/coding-conventions.mdc`，避免同一套写法纪律被抄成三份
- `alear030-pr-review` 把这条反复述纪律用到了底：靶子分类指向 `docs/retrospective/`、机制事实指向 `docs/`、验证口径指向 `alear030-verify`、发现落盘指向 `alear030-issue-mark`，自己只留 review 时的提问顺序与退出标准。它卡在 `alear030-push-merge` 两段之间，与 `alear030-doc-drift-check` 声明分工：那个查文档漂移，这个查一批改动的机制收口

所以真正被沉淀下来的不只是十四条规矩，还有它们之间怎么分工——这本身也是一次收口。

---

← [协作说明](../../COLLABORATION.md) · [返回 README](../../README.md) · [参与方式](../../CONTRIBUTING.md)
