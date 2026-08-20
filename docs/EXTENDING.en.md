# Alear030 Extending Guide

[中文](EXTENDING.md) · **English**

← [Back to README](../README.en.md)

How to add a tool, a Hook, a Prompt block, or a skill to Alear030. Each section is a minimal "copy and it runs" skeleton plus the easy pitfalls.

Architecture background: [Architecture](ARCHITECTURE.en.md). Config items: [Configuration](CONFIGURATION.en.md).

---

## Contents

- [First: three discovery depths](#first-three-discovery-depths)
- [Add a tool](#add-a-tool)
- [Add a Hook](#add-a-hook)
- [Add a Prompt block](#add-a-prompt-block)
- [Add a skill](#add-a-skill)
- [Verify your change](#verify-your-change)

---

## First: three discovery depths

Hook, Prompt, and Tool all rely on the side effect of "import runs decorator registration", but **scan depth differs** — this is the most common pitfall:

| System | What it scans | Meaning |
|---|---|---|
| Hook | Recursive `hook/hooks/**/hook.py` | Any nesting depth works, but the file must be named `hook.py` |
| Prompt | Only **one-level directories** under `prompt/prompts/`, loading fixed `prompt.py` | No nesting; `prompt/prompts/a/b/prompt.py` is not discovered |
| Tool | Only **one-level packages** under `tool/tools/` | A nested `tool.py` is not registered just by existing; the package `__init__.py` must explicitly import it |

All three skip directories that start with an underscore (`_experiment/`, `__pycache__/`). To temporarily disable a module, prefix the directory name with an underscore.

---

## Add a tool

### Directory skeleton

```text
tool/tools/my_tool/
├── __init__.py        # must explicitly import, or it will not register
├── tool.py            # implementation
└── tool_prompt.md     # optional: detailed usage notes for this tool
```

`__init__.py`:

```python
from .tool import my_tool
```

> **This line is the easiest to miss in the whole flow.** `tool/__init__.py` only imports one-level packages under `tool/tools/`; it does not care whether the package exposes the implementation. Miss this line and the tool silently fails to register — the model side shows no error.

### Implementation

```python
from pathlib import Path

from tool.tool_core import register_tool, tool_call_processing

tool_desc = 'One-line description of what this tool does; goes into the tool_prompt tool list'

# Read tool_prompt.md if present, else None. Common template shared by tools
tool_prompt_file = Path(__file__).parent / 'tool_prompt.md'
if tool_prompt_file.exists():
    content = tool_prompt_file.read_text(encoding='utf-8').strip()
    tool_prompt = content if content else None
else:
    tool_prompt = None


@register_tool(
    tool_name='my_tool',
    tool_desc=tool_desc,
    tool_prompt=tool_prompt,
    tool_enabled=True,
    tool_autho='basic_tool',
)
def my_tool(query: str, limit: int = 10, **kwargs) -> str:
    # Unified call accounting; almost every tool starts with this
    tool_call_processing(kwargs.get('tcr', None), kwargs.get('emit', None))

    # Validate with "return an error string", not raise — the string goes into tool_result so the model can revise
    if limit <= 0:
        return f'错误:limit 必须大于 0,收到的是 {limit}'

    return '结果文本'
```

### Five constraints

**1. The function signature is the parameter contract the model sees.** Schema is derived automatically from `inspect.signature`; you do not hand-write JSON Schema, and you must not maintain a parallel schema per tool. Derivation excludes `self`, `agents`, `session`, `memory`, and `**kwargs`.

**2. Keep `**kwargs`.** `inject_import_args` on `pre_toolUse` unconditionally injects `agents` / `session` / `hooks` / `Loop` / `memory` into **every** tool; without catching them you get `TypeError`. If you need one, take it with `kwargs.get('session')`; if not, let it be swallowed.

**3. When taking injected objects, null-check with "return an error", not silent skip:**

```python
session = kwargs.get('session')
if session is None:
    return '错误:该工具需要 session,但未被注入'
```

**4. `tool_autho` decides who can use it.** The value must be an authorization category already in `agents.yaml` (`basic_tool` / `file_read_tool` / `file_write_tool` / `command_tool` / `memory_tool` / `plan_tool` / `subagent_tool` / `web_tool` / `skill_tool` / `interaction_tool` / `mcp_tool`). To open a new category, also add the key for the relevant Agents in `agents.yaml` — **writing only the tool without changing yaml makes the tool invisible to every Agent**.

**5. Outputs need a cap.** Tool results go into the session as a whole; unbounded output can blow a model request in one shot. Follow existing tools: `file_read` has line / per-line / total-character triple caps and reuses the `offset` continue-read protocol; `command` has head-and-tail truncation with `MAX_OUTPUT_CHARS`. When truncating, **always explain in the text how to get the rest**, or the model will retry in place.

---

## Add a Hook

### Directory skeleton

```text
hook/hooks/<hook_point>/my_hook/
├── __init__.py     # may be empty
└── hook.py         # filename must be hook.py
```

Current hook points: `before_session`, `pre_toolUse`, `after_round`, `after_session`.

> The `before_session` directory exists and `main.py` triggers it, but no hook is registered there today — the trigger is a no-op.

### Implementation

```python
from hook.hook_core import hooks


@hooks.register(hook_point='after_round', background=True, enabled=True)
def my_hook(session=None, memory=None, hooks=None, **kwargs):
    # Declare parameters as needed with defaults: what the trigger passes is decided by hooks.trigger(...) call sites;
    # declaring a parameter the other side does not pass yields TypeError immediately
    if session is None:
        return
    ...
```

Four parameters of `@hooks.register`:

| Parameter | Notes |
|---|---|
| `hook_point` | Which event point to attach to |
| `background` | `True` runs on a background thread pool without waiting; `False` runs synchronously and the main loop waits for return |
| `match` | `None` always fires; `{'tool': 'file_write'}` only when context matches; a list means any one group is enough |
| `enabled` | Master switch; `False` still registers but never fires |

### Three constraints

**1. Sync vs background depends on whether the main loop needs the result.** If you need the result immediately to decide the next step (e.g. `session_compress` must finish before the next round), use sync; if it is slow and does not affect the main path (e.g. slice + embed), use background. **Background hooks are waited on at exit via `hooks.wait_all()`** — do not put unbounded blocking work inside them.

**2. `pre_toolUse` can rewrite tool inputs**, returning `HookResult(modify_input=tool_args)`:

```python
from hook.hook_core import hooks, HookResult


@hooks.register(hook_point='pre_toolUse')
def my_injector(tool_args, agents, session, hooks, Loop, memory=None):
    tool_args['extra'] = '...'
    return HookResult(modify_input=tool_args)
```

**3. Do not rely on registration order.** Auto-discovery imports by path sort, but that is not a dependable contract. If two things have an order dependency, put them in one function and run in sequence — that is what `memory_pipeline` does: it merges "slice" and "feed slices into memory" into one hook, structurally preventing the old bug where two async hooks happened to serialize by registration order and read stale data.

---

## Add a Prompt block

### Directory skeleton

```text
prompt/prompts/my_prompt/
└── prompt.py        # filename must be prompt.py, and only under a one-level directory
```

No `__init__.py` needed.

### Implementation

```python
from prompt.prompt_register import register_prompt


@register_prompt(
    prompt_name='my_prompt',
    order=25,
    condition=lambda agent: agent.agent_name == 'main',
    enabled=True,
)
def build(agent) -> str:
    return '#我的分块' + '\n\n' + '正文内容'
```

`build_prompt(agent)` concatenates by ascending `order`, filters out `enabled=False` and blocks whose `condition` is false, and **also skips blocks whose content is the empty string** — so "do not inject this time" can simply return `''` without an extra switch.

### Current order layout

When picking an order, use this table and insert into a gap:

```text
system_prompt      0
attachment_prompt  5
tool_prompt       10
skill_prompt      20
session_recent    30
timeline_prompt   30
memory_prompt     35
agent_prompt      40
basic_prompt      50
```

### Two constraints

**1. The system prompt is a startup snapshot.** Block functions run once at Agent init; later disk writes in the same process do not refresh the prompt. To read data that changes at runtime, use attachment or tools — do not rely on prompt blocks.

**2. `condition` receives the agent object.** Common filters are by name (`agent.agent_name == 'main'`) or by authorization (`'skill_tool' in agent.tool_autho`).

---

## Add a skill

Skills are pure Markdown — no code.

```text
skill/<skill-name>/skill.md
```

```markdown
---
name: my-skill
description: "When to use this skill. Spell out trigger scenarios; this text goes into the main agent system prompt so the model can decide whether to load it."
---

# my-skill

Body: how this skill actually works.

## Steps

1. ...
2. ...
```

**YAML frontmatter is required** — the `skill_prompt` block recursively scans `skill/**/skill.md`, skips every file that does not start with `---`, then reads only `name` and `description` into the system prompt. The body is read only when the model calls `skill_load`.

So `description` decides whether the skill gets recalled; write it carefully: include trigger scenarios and typical phrasings, not just "use this for X".

---

## Verify your change

```bash
python main.py
```

If something new does not take effect after startup, debug in this order:

1. **Tool**: Did `tool/tools/<name>/__init__.py` import the implementation? Is the `tool_autho` category `true` for the target Agent in `agents.yaml`?
2. **Hook**: Is the filename `hook.py`? Is any path segment underscore-prefixed?
3. **Prompt**: Is it under a second-level directory? Is the filename `prompt.py`? Did `condition` filter out the target agent?
4. **Skill**: Does `skill.md` start with `---`?

> `python main.py` really calls the model API and writes session files — it is not a side-effect-free smoke test. To only confirm "did it register?", querying the registry is much faster than a full run:

```bash
python -c "import tool; from tool.tool_core import _register; print(sorted(_register.tool_list))"
```

Same idea for Hook and Prompt: inspect `hook.hook_core.hooks._hooks` and `prompt.prompt_register._register.prompt_list`.
