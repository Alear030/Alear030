# Security

[中文](SECURITY.md) · **English**

Alear030 is an experimental Agent Harness for single-user local use. It **runs commands, reads and writes files, and accesses the network** on your machine. This document states how far its protections go, and what you should not expect from them.

## Threat Model: Stop Model Slips, Not a Sandbox

The `command` tool has a security gate, but its assumption is that **the model may casually emit irreversible operations during a normal task** (for example, turning “clean up the build directory” into a recursive delete) — not that **someone is deliberately crafting commands to bypass it**.

Concretely:

- The gate is a **destructive blocklist**, not an allowlist. `COMMAND_WHITELIST` is only a classification table; unlisted commands are marked `unknown` and still allowed. What actually blocks are `DESTRUCTIVE_COMMANDS` and `BLOCKING_PATTERNS`
- Commands are split on `&&`, `||`, `&`, `;`, `|` and checked piece by piece. Interpreter payloads such as `bash -c` / `python -c` / `powershell -Command` are extracted and run through the gate again (one nesting level only; `-EncodedCommand` is rejected outright because it cannot be checked statically)
- Dangerous paths (system directories, drive roots, and similar) are judged by command category; write operations check the target path

**If you truly need isolation, use a container or a VM — do not rely on this layer.** It can stop slips; it cannot stop deliberate bypass.

## File Access Is Asymmetric

This is easy to misunderstand, so it gets its own section:

- **Write**: target paths for `file_write` and `file_edit` must fall under `workspace/` or `skill/`, or they are refused
- **Read**: `file_read`, `file_grep`, and `file_glob` **can read any absolute path on disk**; they only require the path to be absolute

In other words, the model cannot write outside the workspace, but it can read any file it has permission to read on your machine. If the machine holds content you do not want read, keep that in mind.

## Other Boundaries Worth Knowing

- **Runtime temporary subagents default to read-only authorization** (`basic_tool` / `file_read_tool` / `memory_tool` / `web_tool`), but the caller can replace that entire grant via the `tool_autho` parameter, including granting `command_tool` and `file_write_tool`
- **Cross-session memory persists conversation content** under `session/session_detail/` and `memory/`. Those directories are in `.gitignore`, but if you share the repo or take screenshots, remember they hold real dialogue
- **The MCP client connects to external servers configured in `mcp_client/mcp.json`** and registers remote tools into the tool table. Credentials appear in config only as `${VAR}` placeholders; real values live in `.env`. Confirm for yourself that any server you connect is trustworthy
- **Do not run this project in multi-tenant environments, or in scenarios that accept untrusted input.** It was not designed for that

Full implementation notes for the security gate are in [Architecture](docs/ARCHITECTURE.en.md#core-design-decisions).

## Reporting Security Issues

Please submit via GitHub **private vulnerability reporting** (repository page → Security → Report a vulnerability). Do not open a public issue.

This is a single-maintainer experimental project. There is no committed response SLA and no security update cadence — treat it as “source you can read, but should not entrust important data to.”
