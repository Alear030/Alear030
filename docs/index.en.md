# Docs Index

[中文](index.md) · **English**

← [Back to README](../README.en.md)

This is the entry page for `docs/`, not the repo homepage — the project intro and quickstart live in the root [README](../README.en.md).

## Genres

Documents under `docs/` fall into three groups: **four ascending tiers** about this project, and **two side branches** — one about systems outside it, one about the road a single change travelled. Place a new document before writing it.

### Four tiers (the subject is Alear030 itself)

- **Overview docs** (`docs/` root): cross-module explanations, for someone reading the project for the first time
- **Module mechanism docs** (`docs/modules/<module>.md`): what a single module looks like right now, named after the module in the [architecture doc](ARCHITECTURE.en.md)'s directory structure
- **Design narrative docs** (`docs/design/<topic>.md`): why a single mechanism ended up shaped this way, decoupled from the mechanism doc
- **Research docs** (`docs/research/<topic>.md`): a question that is **not settled yet** — hypotheses, measured data, conclusions, plus the hypotheses that got falsified and the conclusions that got retracted

The first three tiers describe things already built; research docs describe things still being investigated. That makes them different in two ways: they **may have no conclusion**, and they **keep the wrong turns in**. Falsified hypotheses and retracted conclusions stay in the text rather than being edited away — how a conclusion was reached matters as much as the conclusion.

Once a research thread settles, it either spawns a change-type issue to act on, or gets folded into the corresponding design narrative or module mechanism doc. A research doc never carries the burden of describing what the current implementation looks like.

### Side branch: observation docs (the subject is an external system)

- **Observation docs** (`docs/observations/<topic>.md`): **how someone else's system solves a problem I am also solving**

This is not a fifth tier. The four tiers share one axis — the subject is always this project, ordered by "what it is → why → not settled yet". Observations change the *subject*, not the degree of certainty.

Three admission criteria, all required: the subject is outside the project; there is first-hand evidence reproducible on my own machine, not something relayed in a chat; and it has comparative value, i.e. it solves a problem I am also solving. Merely interesting sightings without comparative value do not belong in `docs/`.

Observations also carry one constraint the four tiers do not: **there is no "the code is the source of truth" fallback** — the evidence lives outside this repo, and the observed system changes on its own. Three things stand in for it: state the observation date and the observed version, put *how* it was observed into the text so a reader can reproduce it, and grade every claim — first-hand (a file or reproducible behaviour on my machine) / second-hand (the observed system's own account of itself, which **is not verification**) / inferred.

Like research docs, they may have no conclusion and they keep the wrong guesses in. The difference is the exit: research that settles has to land as an issue or get folded into another doc, whereas **an observation only records — it never opens work**. If an observation prompts a change here, that change goes through its own issue or design narrative; the observation doc does not carry it.

### Side branch: retrospectives (the subject is the road a change travelled)

- **Retrospectives** (`docs/retrospective/<topic>.md`): **how one thing turned into another — where it started, what it dragged in along the way, and what actually shipped**

This is not a fifth tier either. The four tiers take this project as their subject and observations take someone else's system; a retrospective takes *the process itself*. A design narrative explains why one mechanism ended up shaped the way it is and stays with that mechanism; a retrospective follows one chain of changes across however many modules it crossed — and its endpoint is often not the same thing as its starting point.

Why this deserves its own genre: the real cost of a change is rarely in its own few lines, it is in what the change drags in. That information belongs to no single module, so it fits badly into any mechanism doc — and it is exactly the part that is hardest to reconstruct later.

Three admission criteria, all required: it records how the chain moved rather than how a mechanism works (mechanism belongs in a design narrative); it hangs on traceable evidence — commits, issues, specific lines — rather than abstract lessons; and it **keeps at least one judgement that was overturned along the way**. Without that last one it becomes retroactive justification in which every step looks shrewd, which is neither how it went nor any use for seeing where the road actually turned.

Like observations, the exit is: **a retrospective only records — it never opens work.** Anything it turns up goes through its own issue.

Only documents with actual content are listed below; modules that don't have a write-up yet don't get a placeholder link.

## Overview

- [Architecture](ARCHITECTURE.en.md) — directory tree, startup/shutdown flow, per-module responsibilities, core design decisions
- [Configuration](CONFIGURATION.en.md) — `.env`, MCP setup, runtime constants
- [Extending](EXTENDING.en.md) — how to add a tool/hook/prompt chunk/skill

## Module mechanisms

- [Memory system](modules/memory.en.md) — the full mechanism: slicing, classification, dedup, profiling, cross-session timeline, semantic recall
- [MCP client](modules/mcp_client.md) — *Chinese only* · the four layers, the asyncio isolation and its cancel-scope constraint, runtime tool-table refresh, credential placeholders
- [TUI](modules/tui.md) — *Chinese only* · event flow, threading model, the two registries (widgets and events), Textual pitfalls

## Design narratives

- [Memory ideas & design](design/memory.en.md) — why the memory system ended up shaped this way
- [Loop ideas & trade-offs](design/loop.md) — *Chinese only* · why Loop knows nothing about plan, plus four decisions: forced wrap-up by withholding tools, mode detection by diff, one error boundary, streaming accumulation

## Research

- [LLM cache research notes](research/llm-cache.md) — *main thread settled, accumulating, Chinese only* · prompt cache reuse across sessions: why a fresh session's first request only hits 14%; the original hypothesis was falsified, the real culprit turned out to be 12.7K of tool schema invalidated by a single timestamp, one conclusion was retracted after the tokenizer used to measure it proved to be the wrong ruler, and the attribution itself was corrected once more at closing time

Research threads are tracked on GitHub under the [`research` label](https://github.com/Alear030/Alear030/issues?q=is%3Aissue+label%3Aresearch); the ones written up appear above.

## Observations

- [Observing ZCode's memory system](observations/zcode-memory.md) — *accumulating, observed 2026-09-03, Chinese only* · reverse-engineering a cross-session memory mechanism from its file structure: three choices identical to my own, two places I guessed wrong, and one gap its designers never guarded against in the rules — stale conclusions propagating silently through the auto-loaded index

## Retrospectives

- [From eval to architecture](retrospective/eval-to-architecture.md) — *2026-08-25 ~ 2026-09-06, Chinese only* · it began as wanting eval, which meant building trace first. The first real data trace produced exposed the prompt-cache problem, and fixing that required moving where prompts belong — from there it stopped being "fix one metric" and became a second look at module boundaries, construction order and cross-cutting concerns
