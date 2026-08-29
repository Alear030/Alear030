# Docs Index

[中文](index.md) · **English**

← [Back to README](../README.en.md)

This is the entry page for `docs/`, not the repo homepage — the project intro and quickstart live in the root [README](../README.en.md).

## Four tiers

Documents under `docs/` are organized into four tiers by content type; new documents should fit one of them:

- **Overview docs** (`docs/` root): cross-module explanations, for someone reading the project for the first time
- **Module mechanism docs** (`docs/modules/<module>.md`): what a single module looks like right now, named after the module in [CLAUDE.md](../CLAUDE.md)'s stable module map
- **Design narrative docs** (`docs/design/<topic>.md`): why a single mechanism ended up shaped this way, decoupled from the mechanism doc
- **Research docs** (`docs/research/<topic>.md`): a question that is **not settled yet** — hypotheses, measured data, conclusions, plus the hypotheses that got falsified and the conclusions that got retracted

The first three tiers describe things already built; research docs describe things still being investigated. That makes them different in two ways: they **may have no conclusion**, and they **keep the wrong turns in**. Falsified hypotheses and retracted conclusions stay in the text rather than being edited away — how a conclusion was reached matters as much as the conclusion.

Once a research thread settles, it either spawns a change-type issue to act on, or gets folded into the corresponding design narrative or module mechanism doc. A research doc never carries the burden of describing what the current implementation looks like.

Only documents with actual content are listed below; modules that don't have a write-up yet don't get a placeholder link.

## Overview

- [Architecture](ARCHITECTURE.en.md) — directory tree, startup/shutdown flow, per-module responsibilities, core design decisions
- [Configuration](CONFIGURATION.en.md) — `.env`, MCP setup, runtime constants
- [Extending](EXTENDING.en.md) — how to add a tool/hook/prompt chunk/skill

## Module mechanisms

- [Memory system](modules/memory.en.md) — the full mechanism: slicing, classification, dedup, profiling, cross-session timeline, semantic recall

## Design narratives

- [Memory ideas & design](design/memory.en.md) — why the memory system ended up shaped this way

## Research

- [LLM cache research notes](research/llm-cache.md) — *in progress, accumulating, Chinese only* · currently focused on prompt cache reuse across sessions: why a fresh session's first request only hits 14%; the original hypothesis was falsified, the real culprit turned out to be 12.7K of tool schema invalidated by a single timestamp, and one conclusion was retracted after the tokenizer used to measure it proved to be the wrong ruler

Research threads are tracked on GitHub under the [`research` label](https://github.com/Alear030/Alear030/issues?q=is%3Aissue+label%3Aresearch); the ones written up appear above.
