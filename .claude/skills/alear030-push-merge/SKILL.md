---
name: alear030-push-merge
description: "commit 之后把分支发出去，分两段：第一段 push + 开 PR 就停下（当用户说'推上去'、'开个 PR'、'发出去'时用）；第二段合并进 master 并清理分支、同步本地 master，只在用户明确说'可以合了'、'合并这个 PR' 时才跑。**PR 是评审闸门，开完必须停下交回用户，绝不自动合并。** 这个项目走 GitHub PR 而不是本地 merge，且常驻分支（master / Alear030_dev）永不删除——不要凭通用 git 经验直接 checkout master && merge，也不要合完就删当前分支。"
---

# Alear030 分支收尾：push → PR ⏸ 评审 → merge → 清理

## 两段式，中间必须停

```text
第一段(说"推上去/开个 PR"时跑)   : 前置检查 → push → 开 PR → 报告链接 → 停
        ⏸  用户自己读,或交给 GitHub Copilot review
第二段(说"可以合了"时才跑)       : 合并 → 清理分支/worktree → 同步本地 master
```

**开完 PR 必须停下把链接交回用户,绝不顺手合并。** 这条不是流程洁癖:在这个项目里 PR 的全部
价值就是「有一个可以停下来看的东西」——用户要自己读一遍,或者交给 GitHub Copilot 去 review。
如果开完就合,PR 几秒钟后就没了,评审窗口等于不存在,那还不如直接本地 merge。

写这条是因为踩过:早先版本把 push、开 PR、合并串成一条无人值守的流水线,PR 开出来当场就被
合掉了。用户选择「走 PR 而不是本地 merge」时,要的就是那个停顿。

要不要请 Copilot review、怎么请,由用户自己触发,本技能不代劳。

## 职责边界

**从「已经 commit 完」开始，到「分支收拾干净」结束。**

不生成 commit message,那是 `alear030-commit-message` 的事;不做代码验证,那是 `alear030-verify` 的事。
调用本技能时默认改动已经落成 commit——如果工作区还有未提交内容,先停下问,不要顺手 add 进去。

## 常驻分支名单（写死,不靠推断）

```
master
Alear030_dev
```

这两个**永不删除**。除此之外的分支（`feat/issue-*`、研究分支、实验分支等）都算临时分支。

不要靠「看起来像不像长期分支」来判断——判断错了就是一次不可逆的删除。名单里没有的一律当临时分支处理,
而临时分支的删除还要再问一次(见下)。

## 流程

## 第一段：push + 开 PR

### 1. 前置检查

```bash
git branch --show-current          # 当前分支;若是 master 直接停下报告
git status --short                 # 工作区是否干净
git log --oneline origin/master..HEAD   # 本批要发的 commit
```

- 当前分支是 `master` → 停下。本技能不处理直接在 master 上开发的情况。
- 工作区还有改动 → **点名列出**,问用户这些是不是本次的一部分,不要自己判断着 add。
  常见的是运行时产物(`local_model/**/.msc` 之类)和别的任务的半成品,它们不该被裹进来。
- `origin/master..HEAD` 为空 → 没东西可发,停下。

### 2. push

```bash
git push -u origin <branch>
```

### 3. 开 PR

```bash
gh pr create --base master --head <branch> --title "<主题>" --body "<正文>"
```

**标题**:本批 commit 的共同主题,一句话,**不带时间戳**——时间戳是 commit message 的格式要求,PR 标题不需要它。
分支含多个 commit 时不要直接抄最后一个 commit 的标题,那会漏掉前面的改动。

**正文**:先一段总体说明(这批改动整体在做什么、为什么),再逐条列出本批每个 commit 的一句话主题:

```markdown
<一段总体说明>

本批提交:
- <commit 1 的一句话主题>
- <commit 2 的一句话主题>
```

仓库已公开,PR 列表本身就是对外可读的开发记录,所以正文和 commit message 遵守同一条纪律:
**只记改动本身,不记协作编排过程**。

### 4. 停下,把 PR 交回用户

第一段到此为止。报告 PR 编号与链接、本批 commit 清单、工作区剩下哪些未提交内容,然后**结束**。

不要接着合并,也不要问「要我合并吗」之后自己判断答案——等用户下一条明确指令。

---

## 第二段：合并 + 清理

**只在用户明确表示可以合并时才进入这一段**(「可以合了」「合并吧」「merge 掉」之类)。
用户没说,就停在第一段。

### 5. 合并

```bash
gh pr merge <n> --merge
```

用 `--merge` 保留 merge commit,和仓库现有的 PR 记录一致;**不要用 `--squash` 或 `--rebase`**——
squash 会把本批 commit 压成一条,那些 commit message 里的「当前进度/后续计划」就此丢失,
而它们是这个项目的开发日志。

合并冲突或 PR 检查未通过 → 停下报告,不强解。

### 6. 收尾（按分支类别分叉）

先 `git fetch --prune` 刷新引用,否则本地看到的还是合并前的状态。

**常驻分支**(在上面名单里):

- **不删分支。**
- 把本地 `master` 同步到远端:

  ```bash
  git -C <主仓库路径> checkout master && git pull
  ```

  这一步容易漏:用 worktree 开发时,PR 在 GitHub 上合并之后,主仓库那个 checkout 的本地 `master`
  仍然停在旧提交上,而它看起来一切正常。下次在主仓库做事就是从一个落后的 master 出发。

- **同步前先查主仓库工作区,脏则停下报告,不要自动 stash。**

  ```bash
  git -C <主仓库路径> status --short
  ```

  主仓库很可能摊着 memory 运行时数据——`memory/memory_config/memory_configs/user_info.json`
  这类被 git 跟踪、又会被管线改写的文件。stash 它们风险太大,该由用户决定怎么处理。

  报告时要给出**真正的阻塞交集**,而不是笼统一句「工作区脏」。多数未提交文件根本不在 pull 的
  更新路径上,不影响同步:

  ```bash
  comm -12 <(git diff --name-only <本地master> origin/master | sort) <(git diff --name-only | sort)
  ```

  实际撞到过一次:主仓库有 5 个未提交文件,但 `git pull` 要更新的 21 个文件里只和 `.gitignore`
  有交集,两边改的还是不同的行。说清这一点,用户才好判断是先提交、只 stash 那一个文件,
  还是干脆先不同步。

**临时分支**:

- 合并成功后**先问用户再删**,不要自动删。
- 用户确认后,三样一起处理,漏一样就会留下残留:

  ```bash
  git worktree remove <path>              # 若该分支占着 worktree(占着时无法删分支)
  git branch -d <branch>                  # 本地分支
  git push origin --delete <branch>       # 远端分支
  git worktree prune
  ```

- 分支上有**不打算合并的提交**时(比如研究分支里的临时破坏性改动),删除前明确告诉用户
  哪些提交会随之消失,让用户决定是丢弃、只删本地保留远端,还是先打 tag 存档。

## 完成后报告

**第一段结束时**:

- PR 编号与链接(链接要能直接点开去评审)
- 本批 commit 清单
- 工作区剩下哪些未提交内容(那些是别的任务的,不该沉默带过)
- 明确说明**现在停在评审闸门**,等用户放行才继续

**第二段结束时**:

- 合并后的 `origin/master` 提交
- 本地 `master` 是否已同步(没同步要说清为什么,别沉默略过)
- 删了什么(分支/远端分支/worktree),或明确说明「按名单保留」

## 边界情况

- **没有 `gh` 或未登录** → 停下报告,不要退回本地 merge 顶替;本地 merge 会让 PR 记录消失,
  和这个项目的实际习惯不一致,该由用户决定怎么办。
- **用户明确要求本地 merge**(比如离线) → 尊重临时指令,但要说明这次**没有评审窗口**,
  且不会留下 PR 记录。
- **用户一句话说了「推上去并合并」** → 这是明确指令,可以连着跑两段;但要在报告里点出
  这次跳过了评审窗口。默认(只说「推上去」)一律停在第一段。
- **PR 已存在** → 不重复创建,复用已有 PR;若该 PR 还没被评审过,同样停在第一段。

## 衔接

- 上游:`alear030-commit-message` 生成 message 并 commit,到此为止。
- 本技能第一段:从 commit 之后接手,到 PR 开好为止。
- ⏸ 用户评审(自己读或交给 Copilot),本技能不代劳、不催促。
- 本技能第二段:用户放行后合并并清理干净。
- `alear030-issue-pretodoHandle` 的「合并」步骤直接引用本技能,不另写一套合并流程。
