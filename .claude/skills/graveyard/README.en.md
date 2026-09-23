# Skill Graveyard

[中文](README.md) · **English**

← [Skills directory](../README.en.md)

Deleted skills are buried here. Each headstone records four things: dates, life, cause of death, and legacy. Epitaphs state only facts that can be checked; the birth date is the day the skill entered the repository — how long it lived locally before that is unknown.

When a skill is deleted, add a headstone at the top, newest first.

---

## `alear030-worktree-change-guard`

**2026-08-19 — 2026-09-23 · 35 days in the repository**

**Life**: After production code was changed in a worktree, it read back the target worktree's absolute path and checked the diff. It guarded against a strange failure: an Edit landing in the main repo while the worktree stayed untouched and the tests kept failing. It was a strong recommendation all its life; no hook ever backed it.

**Cause of death**: First, the underlying cause was never traced, so it could demand an outcome but never explain one. Second, its remedy — overwriting the whole file in the worktree from Python — cost more when it went wrong than the ailment it treated.

**Legacy**: One line under "Counter-intuitive traps" in CLAUDE.md: when editing inside a worktree, use the worktree's own path.

---

## `alear030-multitask-pipeline`

**2026-08-19 — 2026-09-11 · 23 days in the repository**

**Life**: Migrated from another project to split large tasks and dispatch them in parallel.

**Cause of death**: Not called once in 129 sessions. The final checkup also found claims that contradicted the repository: the `alear-executor` subagent type it relied on did not exist, and it described `AGENTS.md` as a local file although Git had always tracked it.

**Legacy**: None. The `alear-executor` it relied on was removed from CLAUDE.md on 2026-09-23 as well, so the two rest together.

---

## `alear030-multitask-code`

**2026-08-19 — 2026-09-11 · 23 days in the repository**

**Life**: Sibling of `multitask-pipeline`, in charge of coding discipline during parallel changes.

**Cause of death**: Likewise never called; it pointed its authority at `.cursor/rules/*.mdc`, which Claude Code does not load automatically.

**Legacy**: "Preview before writing, no drive-by refactors" was inlined into `alear030-issue-fix` and lived twelve more days; on 2026-09-23 it was rewritten to defer to the "Scope of change" section of CLAUDE.md.
