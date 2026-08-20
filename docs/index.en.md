# Docs Index

[中文](index.md) · **English**

← [Back to README](../README.en.md)

This is the entry page for `docs/`, not the repo homepage — the project intro and quickstart live in the root [README](../README.en.md).

## Three tiers

Documents under `docs/` are organized into three tiers by content type; new documents should fit one of them:

- **Overview docs** (`docs/` root): cross-module explanations, for someone reading the project for the first time
- **Module mechanism docs** (`docs/modules/<module>.md`): what a single module looks like right now, named after the module in [CLAUDE.md](../CLAUDE.md)'s stable module map
- **Design narrative docs** (`docs/design/<topic>.md`): why a single mechanism ended up shaped this way, decoupled from the mechanism doc, not required to have an English version

Only documents with actual content are listed below; modules that don't have a write-up yet don't get a placeholder link.

## Overview

- [Architecture](ARCHITECTURE.en.md) — directory tree, startup/shutdown flow, per-module responsibilities, core design decisions
- [Configuration](CONFIGURATION.en.md) — `.env`, MCP setup, runtime constants
- [Extending](EXTENDING.en.md) — how to add a tool/hook/prompt chunk/skill

## Module mechanisms

- [Memory system](modules/memory.en.md) — the full mechanism: slicing, classification, dedup, profiling, cross-session timeline, semantic recall

## Design narratives

- [Memory ideas & design](design/memory.md) *(Chinese)* — why the memory system ended up shaped this way
