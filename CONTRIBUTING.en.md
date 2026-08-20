# How to Contribute

[中文](CONTRIBUTING.md) · **English**

To set expectations up front: Alear030 is an experimental project I build on my own. The architecture is still moving, and I set the direction myself.

## Pull Requests

**PRs are not accepted for now.** That is not a lack of welcome — at this stage, the cost of merging external changes outweighs the benefit. Many areas are about to be rewritten; the part you spent time on may be gone next week.

## Issues Are Welcome

Feel free to open an issue for any of the following:

- **Bugs**: it does not run, behavior is wrong, or an error message is unclear
- **Questions**: something the docs leave unclear — I will fold the answer back into the docs
- **Design discussion**: a different take on a trade-off in some mechanism, or you are building something similar and want to talk — I am interested

The repository has two issue templates (tech debt / feature request). You can also skip the templates and just describe the issue.

Please report security issues through the private channel described in [SECURITY.en.md](SECURITY.en.md), not as a public issue.

## Worth Reading First

- [README](README.en.md) — what the project is and how to run it
- [Configuration](docs/CONFIGURATION.en.md) — `.env`, MCP setup, runtime constants
- [Architecture](docs/ARCHITECTURE.en.md) — module layout and core design decisions
- [Memory](docs/modules/memory.en.md) — mechanism details, with known limitations listed honestly at the end

For “it will not run” issues, include OS, Python version, model provider, and the full error — that saves a round trip.
