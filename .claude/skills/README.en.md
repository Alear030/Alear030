# Collaboration Skills Catalog

[中文](README.md) · **English**

← [Collaboration notes](../../COLLABORATION.en.md) · [Back to README](../../README.en.md)

This directory holds the fourteen skills I use when working with coding agents — 1406 lines in total, all under version control, and you can open any of them directly.

They aren't configuration, they're **sediment**. Behind every one of them is an occasion when it got something wrong, or when I failed to explain something clearly — step on a rake once, write down a rule. So this catalog is less a feature list than an incident log for this project.

The format of a skill is simple: one directory holding one `SKILL.md`, with `name` and `description` in YAML frontmatter and the body underneath. Thirteen of these fourteen have exactly those two fields in frontmatter; only `alear030-worktree-change-guard` has one extra, `user-invocable`. Triggering is mainly by `description` — the agent reads it and decides for itself whether this is the moment to use it; I can also name one directly and tell it to use that. This design is the same one Alear030's own runtime skill system uses, and that part is written up in the [collaboration notes](../../COLLABORATION.en.md).

---

## Summary Table

| Skill | Lines | In one line |
|------|------|--------|
| [`alear030-verify`](alear030-verify/SKILL.md) | 128 | This project's verification doesn't work like a normal Python project's |
| [`alear030-worktree-change-guard`](alear030-worktree-change-guard/SKILL.md) | 34 | After changing production code in a worktree, you must read it back and confirm |
| [`alear030-commit-message`](alear030-commit-message/SKILL.md) | 131 | The fixed format for commit messages |
| [`alear030-push-merge`](alear030-push-merge/SKILL.md) | 199 | After a commit: push and open a PR, stop for review, merge only after approval |
| [`alear030-changelog-refresh`](alear030-changelog-refresh/SKILL.md) | 120 | The fixed format for CHANGELOG version blocks |
| [`alear030-style-notes`](alear030-style-notes/SKILL.md) | 72 | The taste for writing comments in my code |
| [`alear030-issue-mark`](alear030-issue-mark/SKILL.md) | 86 | Label taxonomy and body conventions for issues |
| [`alear030-doc-drift-check`](alear030-doc-drift-check/SKILL.md) | 43 | Read-only drift check of docs against the code, reporting without fixing |
| [`alear030-pr-review`](alear030-pr-review/SKILL.md) | 105 | Read-only pre-merge review of an open PR: three reconciliation passes and one exit criterion |
| [`alear030-issue-pretodoHandle`](alear030-issue-pretodoHandle/SKILL.md) | 66 | The full flow from claiming an issue off the board to wrapping up |
| [`alear030-issue-fix`](alear030-issue-fix/SKILL.md) | 52 | The pipeline from pulling an issue through locating, plan sign-off, fixing, testing, review to commit |
| [`alear030-scan-claude-markers`](alear030-scan-claude-markers/SKILL.md) | 52 | Scan the @claude to-do markers I leave in the code |
| [`alear030-multitask-pipeline`](alear030-multitask-pipeline/SKILL.md) | 210 | The dispatch protocol for four-role parallel changes |
| [`alear030-multitask-code`](alear030-multitask-code/SKILL.md) | 108 | The three-stage discipline for changing production code |

Every name carries the `alear030-` prefix. Early on only the project-specific ones did — format rules like `commit-message` did not — but those hold only inside this project too, so the presence or absence of a prefix marked no real distinction while implying one. They were unified afterwards, turning the convention into a rule with no exceptions.

By the kind of knowledge they encode, they fall into four groups.

---

## 1. Counterintuitive Pitfalls Specific to This Project

What this group has in common: **doing it the way general experience says will go wrong**, and once it goes wrong the cause isn't easy to see.

### `alear030-verify` (128 lines)

Verification in this project has several counterintuitive spots, and applying general Python-project experience directly will trip you:

- `python main.py` in the main repo is **not** a side-effect-free smoke test — it writes session files and may call the model API. But in a development worktree with the memory pipeline turned off, you can run it freely. So step one is working out which checkout you're in, then deciding how tight to be.
- Verification scripts have to be invoked with `python -m` dotted paths; running `python test/xxx/script.py` directly raises `ModuleNotFoundError`.
- `unittest discover` must not be given `-s test`, or `test/loop/__init__.py` shadows the top-level `loop` package and it raises `ImportError`.

There's also a Windows-specific one, written like this in the original:

> On Windows, reading and writing the project's Chinese JSON/text files with `Path.read_text()`/`write_text()` requires passing `encoding='utf-8'` explicitly; without it you get the system default GBK code page and Chinese content raises `UnicodeDecodeError` outright. This pitfall has come up more than once at file read/write points in the prompt/memory modules.

"More than once" — that's exactly why it became a rule.

This is the most-referenced skill of the set; the other three (`alear030-issue-pretodoHandle`, `alear030-multitask-code`, `alear030-multitask-pipeline`) all point at it from their own verification stages.

### `alear030-worktree-change-guard` (34 lines)

The shortest one, and the only one marked `user-invocable: false` — meaning it doesn't show up in my manual menu, and the hope is that the agent remembers to use it after changing code.

One thing has to be said plainly here: **nothing forces it to run.** There's no hook configured in the repo to back it up, so it's a strong recommendation, not a gate. "Written into a skill" and "guaranteed by the mechanism" are two different things, and that's a distinction I hadn't drawn clearly before.

The phenomenon it guards against goes like this: you use Edit to change production code inside a worktree, the change lands in the main repo, and the worktree copy doesn't change. The tests run the worktree code (unchanged), so they keep failing, while the code visibly looks changed — and you spend a long time hunting it. The real instance was that `memory_core.py` occasion.

**The root cause never got traced.** Not enough evidence was kept at the time, so it's unclear whether it was path resolution, working directory, or something else. So the rule simply doesn't explain the cause and only demands the outcome: after changing a non-`test/` file in a worktree, read back the target worktree's absolute path and check the diff.

---

## 2. Format Conventions

This group constrains what the output looks like. They all exist for the same reason: **the general approach loses something I need in this project.**

### `alear030-commit-message` (131 lines)

The format is `YYYYMMDD_HHMMSS <one-line subject>` + blank line + body, with the body split into "current progress / next steps." The subject is capped at 50 characters.

That 50-character cap has a history:

> Early on this project crammed everything onto one line, and the result was that an entire two-thousand-character message became the subject —

The consequence was that `git log --oneline` filled the terminal and couldn't be skimmed, and GitHub's commit list and blame hover tips were all one truncated blob — **which is precisely what killed the "walk back along the timeline" ability the timestamp prefix was supposed to provide**. The prefix was added to make retracing easy, and an over-long subject made retracing impossible instead.

The skill also draws one boundary: **record the change itself, not the collaboration choreography.** "Dispatched several subagents" and "explored first, then planned" belong to the production process, not to the change. The commit is signed by me; an agent's account of itself shouldn't appear in it.

### `alear030-changelog-refresh` (120 lines)

The fixed format for version blocks (title / trigger / changes / verification / corresponding commits / next steps), plus 7 Chinese type labels, instead of the generic Keep a Changelog English categories.

One of the pitfalls it records is particularly nasty: **the em dash trap**. The dash in a version-block title is an em dash (—, U+2014), not a regular hyphen. When replacing historical version blocks with the Edit tool, `old_string` must also use an em dash or the match fails — and Read and Grep render them identically, so you can't tell by eye. The skill gives a command for checking the raw bytes to confirm.

The other one is duplicate recording: a commit belongs to exactly one version block, and there was a real case of a patch fix being recorded into two versions at once.

### `alear030-style-notes` (72 lines)

The taste for writing comments in my code: Chinese, minimal, verb- or action-oriented, and no empty-label comments (the kind that just restate the function name).

There are three more about changing my code: keep my existing identifier naming, prefer helpers that already exist in the same file, and explain before changing. That last one matters most — I need to know what changed and why, otherwise that stretch of code goes from "mine" to "no idea whose."

### `alear030-issue-mark` (86 lines)

Conventions for tech-debt issues: always the `tech-debt` label (not GitHub's default bug/enhancement), severity as a title prefix `[高]`/`[中]`/`[低]`, and a three-part body — background (current state + risk) / what to do (goal + proposed approach) / checks (acceptance criteria). Evidence has to go down to `file:line`.

It got used five times while writing this very collaboration document, all for things found in passing during a module-coupling survey.

---

## 3. Multi-Step Workflows

This group is process orchestration: many steps, ordering dependencies, and gates in the middle where I have to make the call.

### `alear030-issue-pretodoHandle` (66 lines)

Claim an issue from the `pre-todo` column of the GitHub Projects board, then: branch → plan (**stop and wait for my confirmation**) → develop → verify → self-check → merge (handed to `alear030-push-merge`) → push the board to done → ask me whether to take the next one.

Two design points: first, **the board state is the source of truth**, rather than judging from conversational memory how far along we are; second, single-slot — one at a time, no concurrent claiming.

### `alear030-issue-fix` (52 lines)

Without an issue number it pulls the open tech-debt list (oldest first) for me to pick from; with a number it goes straight in: locate (read-only) → propose a plan (**stop and wait for sign-off**) → fix → test → dispatch a review subagent → commit, **stopping at the commit**.

It divides work explicitly with pretodoHandle: board claiming, branching and PR merging belong to that one; this one fixes directly in the current checkout, no branch, no push. One lesson from #8 made it into the body: **issues go stale** — the "no isolation" premise at filing time had been changed by #5 landing, and it nearly got "fixed" again against the stale premise; so the locate step mandates re-checking whether the premise still holds.

### `alear030-push-merge` (199 lines)

The wrap-up after a commit, **in two stages with a mandatory stop between them**:

```text
Stage 1: pre-flight -> push -> open PR -> report the link -> stop
       (I read it myself, or hand it to GitHub Copilot for review)
Stage 2: merge -> clean up branch/worktree (permanent branches exempt) -> sync local master
```

That pause is the most important part of the skill, and it had to be added afterwards. The first version chained push, PR and merge into one unattended pipeline, so the PR was merged seconds after being opened — **choosing "PR rather than local merge" is a choice for something you can stop and look at; merging immediately means the PR never existed**, and a local merge would have been simpler.

The same reasoning keeps it separate from `alear030-commit-message`: committing leaves a window to read the change once more, while a fix is still cheap. So "commit this" never pushes, and "push this" never merges. Only an explicit "push and merge" runs both stages, and the report has to say the review window was skipped.

Three things are hard-coded in it, because none can safely be inferred:

- **The permanent-branch list** (`master`, `Alear030_dev`) is never deleted. Not judged by whether a branch "looks long-lived" — getting that judgement wrong is an irreversible deletion. Anything off the list counts as temporary, and even temporary branches get one more confirmation before removal.
- **Merges go through a GitHub PR, not a local merge.** This one grew out of a contradiction: `alear030-issue-pretodoHandle` prescribed `git checkout master && git merge`, while every real merge had gone through a PR. A rule that disagrees with the actual habit is a dead rule. Squash is explicitly ruled out too — it collapses a batch of commits into one, and the "progress / next steps" fields in those messages are this project's development log.
- **Cleanup means three things at once**: local branch, remote branch, worktree. Miss one and a remnant is left behind. If the branch carries commits that were never meant to be merged, what will disappear has to be spelled out before deleting.

One more came from a worktree trap: after a PR is merged on GitHub, the local `master` in the main checkout still sits on the old commit — **and it looks perfectly fine**. The next piece of work there starts from a stale base. So syncing local master became a fixed step of the wrap-up rather than something to remember.

### `alear030-scan-claude-markers` (52 lines)

Scans the to-do markers I leave in code comments. Three meanings have to be kept apart: `@claude` is a task for it, `done(@claude): what got done` is a completed trace (kept but not picked up again), and `@claude(ignore)` is a note to myself that must not be touched.

The repo provides no automatic scanning mechanism, so this skill is the ready-made entry point for scanning — I can call for it any time. If you want it to scan automatically at the start of every session, you have to set up a SessionStart hook separately, and whether that ships with the repo depends on where the configuration lives.

Using a skill rather than letting the agent grep for itself is because self-grepping gives a different result every time: directories missed, `done(@claude)` treated as a to-do, or `@claude(ignore)` getting touched.

### `alear030-doc-drift-check` (43 lines)

Sedimented from the scheduled task that fires at nine every morning: it checks the core docs one by one against the live code, through three lenses — structural drift (referenced files/entry points/counts that no longer exist), behavioural drift (assertions contradicting the code), and typos or stale wording. Two iron rules: verify mechanically before concluding (to keep false positives down); any judgement that depends on uncommitted code is skipped into the warning section, no guessing. Strictly read-only throughout — once the report is out, the decision returns to me.

### `alear030-pr-review` (105 lines)

Same read-only reporting family as the previous one, but pointed at a different object: that one checks docs against the code as routine hygiene, this one checks whether a batch of changes on an open PR has actually closed off before it gets merged.

It came out of a review done by an external agent: it took four rounds to get there, the most expensive finding (a reversal in what gets persisted) was one I pointed out myself, and a different agent on the same PR saw it almost immediately. The difference wasn't who knew the project better, it was the question being asked — one asks "is this code written correctly," the other asks "what does the data turn into."

So this skill carries no knowledge of its own, it carries wiring: the target categories point at [the retrospective](../../docs/retrospective/eval-to-architecture.md) that already names them, mechanism facts are written as probes pointing back into `docs/` (how to check, never the current answer — answers go stale, and a stale answer is worse than none), and the skill keeps only three reconciliation passes, the routing discipline, and one exit criterion.

**The exit criterion is the only genuinely new thing here**: "the diff has been read" doesn't mean done; done is when all three passes are complete and every data flow has a conclusion on its producer, its consumer, and its reachability. What gets missed usually isn't beyond understanding — it's stopping too early.

Writing it nearly went wrong once. I was about to put a few concrete function names into the probe table, so a review could just grep them and move on. What stopped it: **a check written against hard-coded names doesn't fail after a rename — it still returns a batch of results**, and whoever runs it sees hits and assumes that item is covered, so the genuinely new path gets skipped in silence. Probe rot isn't a probe going dead, it's a probe **turning into a false pass**, which is worse than not having it. Hence the admission rule: a probe belongs in that table only if it can't be turned into a silent pass by a rename, a new implementation, or a refactor; where that can't be met, it gets raised to the level of a property, or at minimum carries a self-check for its own staleness.

The same reasoning ruled out the more thorough option of tagging every persistence entry point with a marker. That would assert "persistence entry point" is already a settled category, while this very batch of changes keeps moving it. Caching a list that can be recomputed at any time, and paying the sync cost for it, is precisely this project's own second target category. So the list is derived fresh in each review and is a required deliverable of the report; once several independently derived lists agree, it's worth asking whether to freeze one.

---

## 4. Dispatch Protocols

This group only appeared once the project got larger, and it handles the case where "a change is big enough that it needs splitting across several agents in parallel."

### `alear030-multitask-pipeline` (210 lines)

The longest one. A four-stage pipeline: plan → executor → style ∥ review → coordinated merge, with each of the four roles having its own output template.

The key part isn't the role split, it's the **judgement criteria**: when the full four stages are worth it, and when a lightweight path (executor + light review) is enough. Cross-module and mechanism-path changes get the full set; small changes go light. Getting the judgement wrong loses on both ends — full set for a small change is waste, light path for a big change is loss of control.

### `alear030-multitask-code` (108 lines)

Complementary to the previous one: the pipeline governs how roles get dispatched, this one governs **how the code gets written and verified**.

Three stages of discipline: Plan (plan first, **nothing lands on disk**) → Execute (change only what was signed off) → Review (mandatory; not done until it passes). It carries a checklist cross-referencing the five rules under `.cursor/rules/`, and a section called "Hard lessons" — the name alone tells you where it came from.

"Preview before landing" is the one I've stressed repeatedly: I want to see what it's going to be changed into before I decide whether to allow the change.

---

## They Aren't Fourteen Isolated Files

There are reference relationships among these fourteen skills:

- `alear030-verify` is the base layer, referenced back by `alear030-issue-pretodoHandle`, `alear030-multitask-code`, and `alear030-multitask-pipeline` — anything that reaches a "verification" step points at it
- `alear030-commit-message` and `alear030-changelog-refresh` hand off to each other, because one governs a single commit and the other summarizes a batch of commits into a version block, so the boundary has to line up
- `alear030-commit-message` → `alear030-push-merge` is a one-way handoff: the first stops at the commit, the second takes over from there. `alear030-issue-pretodoHandle` points its merge step straight at the latter instead of writing its own
- `alear030-issue-fix` declares its division of work with `alear030-issue-pretodoHandle`: the former fixes to commit in the current checkout, the latter owns board claiming, branching and PRs; its fix/test/commit stages point at `alear030-multitask-code`, `alear030-verify` and `alear030-commit-message` respectively without restating them
- `alear030-multitask-code` and `alear030-multitask-pipeline` explicitly declare themselves complementary and don't restate each other's content
- `alear030-style-notes` and `alear030-multitask-code` both point at `.cursor/rules/coding-conventions.mdc`, so the same set of writing discipline doesn't get copied into three places
- `alear030-pr-review` takes that don't-restate discipline all the way: target categories point at `docs/retrospective/`, mechanism facts at `docs/`, verification at `alear030-verify`, and where findings land at `alear030-issue-mark`, keeping only the order of questions and the exit criterion for itself. It sits between the two stages of `alear030-push-merge`, and declares its division of work with `alear030-doc-drift-check`: that one checks doc drift, this one checks whether a batch of changes closed off

So what actually got distilled isn't just fourteen rules, it's how they divide the work among themselves — which is itself a piece of closing-off.

---

← [Collaboration notes](../../COLLABORATION.en.md) · [Back to README](../../README.en.md) · [Contributing](../../CONTRIBUTING.en.md)
