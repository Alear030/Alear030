# Alear030 Configuration Guide

[中文](CONFIGURATION.md) · **English**

← [Back to README](../README.en.md)

To get running you only need the three model tiers in `.env`; everything else has defaults. This document lists every configurable item, including MCP integration that the README does not expand on.

---

## Contents

- [Required: three model tiers](#required-three-model-tiers)
- [Optional: network proxy](#optional-network-proxy)
- [Connecting an MCP server](#connecting-an-mcp-server)
- [Enabling the memory pipeline](#enabling-the-memory-pipeline)
  - [Profile-dimension seed files](#profile-dimension-seed-files)
- [Local embedding model](#local-embedding-model)
- [Runtime constants (config.py)](#runtime-constants-configpy)

---

## Required: three model tiers

Copy the template and edit:

```bash
cp .env.example .env
```

Alear030 splits models into three capability tiers, all over an OpenAI-compatible API. **All three tiers can point at the same provider with only `model_name` differing**; or each can use a different provider.

```dotenv
MAX_LEVEL_BASE_URL=https://api.deepseek.com
MAX_LEVEL_API_KEY=your-api-key
MAX_LEVEL_MODEL_NAME=deepseek-v4-pro

MEDIUM_LEVEL_BASE_URL=https://api.deepseek.com
MEDIUM_LEVEL_API_KEY=your-api-key
MEDIUM_LEVEL_MODEL_NAME=deepseek-v4-flash

LOW_LEVEL_BASE_URL=https://api.deepseek.com
LOW_LEVEL_API_KEY=your-api-key
LOW_LEVEL_MODEL_NAME=deepseek-v4-flash
```

Which Agent uses which tier is set by `agent_level` in `agent/agents.yaml`:

| Tier | Used by | Notes |
|---|---|---|
| `medium_level` | main, slice, summary, plan | Workhorse tier; almost all calls go here |
| `low_level` | memory | Only structured extraction such as slice classification; a cheap model is enough |
| `max_level` | No resident Agent uses it today | Reserved slot; still must be filled in config |

> `max_level` currently has no resident Agent, but `config.py` unconditionally reads all three variable groups; missing ones become `None`. Filling the same values as medium is fine.

**Model capability requirements**: main / plan use function calling, so the model must support tools; when tools are present, `loop._chat` always attaches `thinking: enabled` in `extra_body`. Providers that reject that field may require changes in `loop/loop_core.py`.

---

## Optional: network proxy

Only configure this when the `web_search` tool needs a proxy; leave blank for a direct connection:

```dotenv
HTTP_PROXY=
HTTPS_PROXY=
```

---

## Connecting an MCP server

Alear030 can act as an MCP client to external servers; both stdio and Streamable HTTP transports are supported. The config file is `mcp_client/mcp.json` (**not version-controlled**; the repo only ships `mcp.json.example`).

```bash
cp mcp_client/mcp.json.example mcp_client/mcp.json
```

### Config format

```jsonc
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "./workspace"],
      "env": {},
      "enabled": true
    },
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": "Bearer ${GITHUB_MCP_TOKEN}" },
      "timeout": 30,
      "enabled": false
    }
  }
}
```

The format is **copy-compatible** with Claude Code / Claude Desktop MCP config.

### Fields

| Field | Applies to | Notes |
|---|---|---|
| `type` | both | `stdio` or `http`. **Optional** — if omitted, inferred from whether `url` is present |
| `command` | stdio | Required. Executable that starts the server |
| `args` | stdio | Command-line argument array |
| `env` | stdio | Environment variables for the child process |
| `cwd` | stdio | Child process working directory |
| `url` | http | Required. Streamable HTTP endpoint |
| `headers` | http | Request headers; credentials usually go here |
| `timeout` | http | Seconds; default 30 |
| `sse_read_timeout` | http | Seconds; default 300 |
| `enabled` | both | Missing means enabled. `false` registers without connecting, to control schema bloat |

### Put credentials in .env, not in the config file

In config, credentials may only appear as `${VAR}` placeholders; real values go in `.env`:

```dotenv
GITHUB_MCP_TOKEN=ghp_xxxxxxxxxxxx
```

Placeholders are expanded when connecting. **If a placeholder cannot be resolved (unset or empty), that server is skipped and the reason is logged — it will not connect with an empty value.**

### After connecting

- Tool names are `mcp__{server_key}__{tool_name}`, prefixed with the config key rather than the server's self-reported name, so two servers reporting the same name do not collide
- Authorization uses the `mcp_tool` category, enabled for main and plan in `agents.yaml` and disabled for other Agents
- MCP servers are connected one by one on a background thread at startup; **a single server failure is only logged and does not block main program startup**
- The tool table is runtime-mutable: after a server connects, each Agent's `tool_list` is refreshed and visible on the next model call
- **But the system prompt is a startup snapshot and is not refreshed** — MCP tools appear only in the function-calling schema, not in the `tool_prompt` block's tool list
- A single MCP tool result longer than `MCP_TOOL_RESULT_MAX_CHARS` (default 4000 characters) is truncated, so an uncontrolled remote reply cannot blow up the session token budget

---

## Enabling the memory pipeline

`MEMORY_PIPELINE_ENABLED` in `config.py` defaults to `False`.

**Turning it off disables more than "writing to storage".** The `memory_pipeline` hook's null check runs before `session._session_slice()`, so with the default, slicing, summarization, slice classification, user profile, task nodes, and timeline **never run at all**. Keeping the default after a clone can look like the memory system is broken.

```python
# config.py
MEMORY_PIPELINE_ENABLED = True
```

Cost: once enabled, every dialogue round incurs extra model calls (one slice + one per pending summary slice + classification and profile extraction).

How the full pipeline works: **[Memory system](modules/memory.en.md)**.


### Profile-dimension seed files

Two runtime config files live under `memory/memory_config/memory_configs/` — `memory_type.json` (feature words for top-level classification) and `user_info.json` (the profile-dimension template). The pipeline rewrites both as it runs: classification grows new feature words, extraction grows new profile dimensions.

So the repository does **not** track those two files. It tracks same-named `.example.json` seeds instead:

```
memory_configs/
├── memory_type.example.json    ← tracked, minimal seed
├── memory_type.json            ← gitignored, your live file
├── user_info.example.json      ← tracked, minimal seed
└── user_info.json              ← gitignored, your live file
```

On first run `get_memory_config` finds the live file missing and copies the matching seed. **Nothing to do by hand.**

Seeding happens only when the live file is absent, and **never overwrites an existing one** — the dimensions you accumulate are not at risk of being flattened back to the seed. To reset, delete the live file and run again.

The seeds are deliberately minimal: `memory_type` carries only `task`, `user_info` only `identity` and `cognitive_style`. That is a floor rather than a preference — the worked examples in `memory_type.md` and `user_info.md` refer to those dimensions by name, so dropping them would hand the model a self-contradictory context. Everything else grows out of use, which is the point of the design.

---

## Local embedding model

Semantic recall for session slices uses a local Chinese GTE model and **needs no configuration**.

On the first `python main.py` run, weights (~195MB) are downloaded automatically from ModelScope into `local_model/`. Network access is required only the first time; afterward it works offline.

The model loads in a separate worker process and does not block TUI startup.

---

## Runtime constants (config.py)

`config.py` centralizes all paths and runtime constants. Read the comments there before changing anything — most constants explain why that value was chosen.

| Constant | Default | Role |
|---|---|---|
| `MEMORY_PIPELINE_ENABLED` | `False` | Master switch for the cross-session memory pipeline; see previous section |
| `MAX_TOOLCALLS` | 30 | Max tool calls per ReAct round; beyond this, forced final reply |
| `SUB_MAX_TOOLCALLS` | 15 | Cap for temporary subagents |
| `PLAN_STALL_LIMIT` | 3 | Plan stall fuse: exit after this many consecutive rounds on the same step |
| `MAX_SESSION_TOKEN` | 250000 | Session compress trigger threshold; leave headroom for the model context window |
| `STRUCTURED_API_TIMEOUT` | 60 | Timeout (seconds) for structured direct calls without tools (slice / summary) |
| `STRUCTURED_API_RETRIES` | 0 | Same path, retry count |
| `SLICE_TOOL_RESULT_MAX_CHARS` | 2000 | Per-tool_result character cap in the slice re-feed window |
| `MCP_TOOL_RESULT_MAX_CHARS` | 4000 | Per MCP tool result character cap |

### Two pitfalls: forced final reply and structured direct calls

**Hitting `MAX_TOOLCALLS` is not an error — it physically cuts tools off.** `_force_final_reply` issues one more request without tools so the model can only produce text. Raising this value allows longer tool chains and larger per-round token cost.

**slice / summary direct calls always disable thinking.** On the same ~4.2k-token slice request, with thinking enabled the call hung 61 seconds then was cut by the gateway; with it off, a normal return in 6.5 seconds. `STRUCTURED_API_TIMEOUT=60` is a ~9× margin on that baseline.

### Data paths

| Constant | Path |
|---|---|
| `SESSION_MEMORTY_DETAIL_PATH` | `session/session_detail/` |
| `SESSION_PLAN_FILE_PATH` | `session/session_plan/` |
| `MEMORY_STORAGE_PATH` | `memory/memory_storage/memory_storages/` |
| `MCP_CONFIG_PATH` | `mcp_client/mcp.json` |
| `LOCAL_EMBEDDING_MODEL` | `local_model/iic/nlp_gte_sentence-embedding_chinese-base` |
| `WORK_SPACE` | `workspace/` |

These directories hold real runtime data (session records, derived memory, model weights) and are all gitignored. Think before deleting — they are not casually rebuildable caches.
