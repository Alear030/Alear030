# How I Work With Agents

[中文](COLLABORATION.md) · **English**

← [Back to README](README.en.md) · [Contributing](CONTRIBUTING.en.md) · [Docs index](docs/index.en.md)

This file answers the question "how did this thing actually get built, between me and the agents." Every other doc in the repo is about Alear030 itself — what mechanisms it has, why it ended up shaped this way. This one is about what happened between me and a few coding agents: how we split the work, how we work together, and which parts of the code came from whom.

---

## Contents

- [Why I Wrote This](#why-i-wrote-this)
- [The Start: Back Then I Wouldn't Let Anyone Else Write a Line](#the-start-back-then-i-wouldnt-let-anyone-else-write-a-line)
- [The Turn: Solo Development Hit a Complexity Ceiling](#the-turn-solo-development-hit-a-complexity-ceiling)
- [Where the Line Is Now: What I Wrote and What I Didn't](#where-the-line-is-now-what-i-wrote-and-what-i-didnt)
- [Why the Split Works at All](#why-the-split-works-at-all)
- [Which Agents I Use](#which-agents-i-use)
- [Those @claude / @codex / @cursor Markers in the Code](#those-claude--codex--cursor-markers-in-the-code)
- [Agreement Files: Why These Files Matter So Much](#agreement-files-why-these-files-matter-so-much)
- [About Skills](#about-skills)
- [The Rhythm of Working Together](#the-rhythm-of-working-together)
- [How I Check That What It Wrote Is Right](#how-i-check-that-what-it-wrote-is-right)
- [So How Should You Read This](#so-how-should-you-read-this)

---

## Why I Wrote This

After I uploaded the README I read it through from the top, and noticed one fact that doesn't come across: Alear030 is not a project where every line of code was written by me alone.

Or rather, not entirely — and not entirely not, either.

The truth has a line running through it: **the core framework I wrote myself, and a fair amount of the periphery I did not.** That line isn't something I casually planned out. It got forced out, bit by bit, by the tension between the project's complexity and how much one person can keep a grip on — and it's still shifting today.

I don't want people getting the wrong idea, so I'm saying it up front. Honestly I also don't want to pretend I'm some hotshot on my first open-source project; I'd rather let the project itself show. And rather than wait for someone to dig through the commit history and work it out for themselves (ps: I don't actually think anyone reads other people's commits... I wouldn't, but let's talk about it anyway), I've also open-sourced the various ways I work with agents, along with the skills that go with Alear030.

The process itself is genuinely interesting — full of compromises between personal boundaries and real engineering difficulty — and more interesting than either "I wrote all of it" or "the AI wrote all of it." So let me recount it.

PS: a bit of my background while I'm at it. Software engineering degree, a bottom-of-the-barrel competitive-programming guy, three years as a product manager after graduating (yes, I defected, hahaha 030). Started learning Python on June 5th, created this repo on June 11th. Everything below happened against that backdrop, which I should say up front, or some of these choices are going to make me look pretty stupid.

---

## The Start: Back Then I Wouldn't Let Anyone Else Write a Line

hermes kept me company for a long time at the beginning. I can't deny that my Alear030 carries its influence — not in the code, but in some of the thinking. The way skills get distilled, for instance, really did take inspiration from it. A very good harness.

What it did back then wasn't writing code, it was **guidance and teaching** — how to write Python, what agent development actually is, plus knowledge from other fields. We went through a lot together, and honestly, without that stretch I probably wouldn't have made it this far.

The concrete arrangement was this: **I have an idea, I don't know how to implement it in code, it writes me an example, I read it, I understand it, and then I write the corresponding thing into Alear030 myself.**

Why I wouldn't let it write directly is hard to explain. Put bluntly: back then I had an extremely strong sense of ownership over Alear030, and a serious case of code fastidiousness. How serious — if hermes ever slipped one or two lines of code straight into a file, I'd have it `git` revert them right away. Even if that change contained things I'd written myself that hadn't been saved, and I'd have to rewrite the whole stretch, I'd still do it.

Looking back on it now feels... I can't quite name the feeling. But that's genuinely how it was: **what I wanted was for every single place in Alear030 to have come from my own hand.**

Output was slow in that period, but I have to say, that's the stretch that made me really understand every core module of agent development.

All of June has only 7 commits; July has 54, August has 64. That curve isn't my programming getting better — mostly the division of labour changed, and later on there was far less 0->1 greenfield work or big-module rewriting.

---

## The Turn: Solo Development Hit a Complexity Ceiling

Once the core engine modules were done, the sheer volume and complexity of Alear030 gradually went past what I personally could keep a grip on.

Once it got big, a problem I hadn't anticipated showed up: **a change in one place tends to cut across a lot of modules. Sometimes writing two lines of code means opening a whole pile of files.**

A real example. The slicing logic was mounted under the session module — there was no memory module at that point (all of this is tech debt; memory is going to need a rewrite), so it naturally needed loop's state plus threading logic. On top of that, slicing originally had no isolated thread, so it blocked input and felt terrible; even the local embedding model was loaded blocking at startup. Moving it to the background touched more than just `session loop local_model`. Holding a change like that on your own means holding the state of several modules in your head at once.

It was already getting difficult at that point, never mind the memory module that came later — that one qualifies as a disaster. But that's also where my own engineering ability tops out.

At the same time something else was happening: **my ability to steer collaboration with agents was getting stronger.** I started to know what work could be handed off, how to hand it off, how much context to give it, and what I should verify once it was done.

I didn't have that early on — early on I struggled just to read the monstrous variable names it produced, so of course I could only write things myself.

The two things collided, and this is what came out...

What I want to be clear about: **agents writing Alear030's code was entirely forced on me. In the end I just stopped resisting, rather than being talked round.** It's not that one day I decided "letting AI write code is a more advanced way to develop" and opened the gates. I hit the wall first, and then found I could actually handle it.

That's roughly the order it happened in. It was a while ago now.

---

## Where the Line Is Now: What I Wrote and What I Didn't

| Part | Who put it on the page |
|------|----------|
| `loop/` `session/` `agent/` `memory/` `tui/`, plus the bulk of `tool/` | I wrote it myself |
| `hook/hook_core.py` | An agent wrote it; I copied it out by hand, because it's too important |
| `tool/tools/command/security.py` | An agent wrote the implementation — commands are too complex and too dangerous here; at the start I only dared ship a whitelist |
| `local_model/` `mcp_client/` | Agents integrated them; I didn't write a line |
| Odds and ends, plus complex but mechanical data processing (JSON regex extraction, for instance) | agent |

### Why the Core Doesn't Get Outsourced

Two reasons. The first one everybody can think of; the second one I think matters more.

**First, I think an engineer shouldn't lose their grip on the system.** 

Granted, agents are already very strong at writing code to solve a problem. But — whether it's a limitation in how I use them or something else, I don't know — I always get the feeling they fall short on anything that spans several major modules and has to establish consistency across the framework. Whichever agent it is, they're too eager to solve the one specific problem the user handed them, and they lose sight of the trade-offs a project has to make at the macro level.

Also, if the core logic isn't in my head, then every architectural judgement I make afterwards has nothing to stand on. I can't tell whether a design closes properly, whether it'll collide with some other mechanism, whether it's worth opening a new path for — because I have no idea what the existing paths look like. At that point it's hard to call myself the author of this project any more; I'd have turned into my day job — a product manager (hahahaha) — who knows the what but not the why.

**Second, a lot of my ideas come out while I'm in the middle of writing the code.**

This one sounds mystical, but for me it's completely concrete. A lot of things came out that way — including the memory module going from idea to implementation, and the whole ability to weigh grand ambition against real engineering constraints and compromise.

Take Alear030's memory module. The initial thinking sounded great: graphs, trees, forests, links between nodes inside a tree, links between nodes across trees, a network of root nodes — sounds like it's really something. Then I opened the IDE and discovered it was a disaster, and realized that if I didn't adapt at that point, I'd end up writing a monstrous data-structure algorithm for the sake of writing one. But is that what I should be doing?

So for me, **outsourcing the core modules means outsourcing the part where the ideas get generated, and the self-restraint mechanism along with it.** That's a price I'm unwilling to pay, and one I can't afford. An agent will complete your task, but when you've stubbornly made up your mind, all it will do is start from your idea and find some way to complete that task — the task that maybe shouldn't have been started in the first place.

### hook_core, the In-Between Case

`hook/hook_core.py` was written by an agent, but it's too important to this project — the entire event-driven scheduling rests on it.

The way I handled it: **I copied it out by hand.**

But what I found is that even after copying it out, it's hard to say the logic really went into my head. Things like how `trigger` matches, how background hooks get into `_pending`, what `wait_all` is waiting on at exit — if you asked me to rewrite them, I'd still have to go look at how the current code does it.

The cost is high.

### The command Safety Layer: I Set the Model, the Agent Implemented It

`tool/tools/command/security.py` is 1605 lines, the single largest file an agent has written for me — the whole `tool/` module is 3708 lines, so it accounts for over forty percent.

The earliest version was whitelist admission: any command not in the knowledge base was not allowed to run. Sounds safe; in practice it lost on both ends — across 49 real calls in real sessions it wrongly blocked 12, with `git -C`, `npm --prefix`, and `netstat -ano` all rejected; meanwhile commands after an `&` never went through validation at all, so the whitelist itself could be bypassed. It blocked what shouldn't be blocked and failed to block what should.

So I flipped the whole thing: **allow by default, hard-reject only operations that are irreversible and hard to recover from by hand.** The threat model is spelled out too — it's "stop the model from slipping," not "stop a deliberate human adversary." Those numbers and conclusions are written in the header comment of that file; go look for yourself.

So this is a third mode. Not me writing it (the `loop` kind), not me copying it out (the `hook_core` kind), but **me setting the model and the agent implementing it**.

Honestly this area is **extremely dangerous, extremely dangerous, extremely dangerous**. And I've also noticed that, whether it's the original whitelist or the blacklist that came later, if you don't restrict the agent's ability to write and run little scripts, most of it is self-deception.

But I haven't come up with a good way to do the screening without the user stepping in, because I don't really understand powershell or bash commands. The other path is running every single command past a subagent for a permissions and risk assessment and then having the user elevate — but that gets tangled up with permission modes, which is a more complicated thing.

If all you do is lean on the prompt, though, then good luck to you. Thinking that constraining it top to bottom in the prompt, repeating it in every location, will guarantee you can stop the agent's behaviour — let me think about that... you might honestly be better off shutting your eyes, clapping your little hands together, and sitting there praying that nobody is seriously studying how to punch through your armour.

ps: praying might genuinely be more effective, actually. When it comes to idealism, those people are the professionals 030.

So this needs serious security research, or sandbox isolation. Sandboxing is yet another area I don't understand; time has been too short and I can't cover everything, so all I can do is write out every danger and everything worth watching out for.

### local_model and mcp_client: I Didn't Write a Line

These two are pure external integration.

`local_model/` is the embedding worker — a separate process, model-weight downloads, inter-process communication. `mcp_client/` is wiring up the official MCP SDK, and the asyncio pitfalls there (cancel scopes having to enter and exit in the same task, that kind of thing) I still haven't fully absorbed.

What characterizes this kind of work: **the hard part lives in someone else's system, not in mine.** 

The infrastructure inside my system can support a clean hookup, so it'll do for now. MCP as it stands doesn't really match what I have in mind, but there's a practical reason here — I need to show what Alear030 can do together with MCP, so for now I had an agent install one for me and wire it into my tool_core system.

The price is real too: when something goes wrong in these two, I fix it slower than elsewhere, or I can't fix it at all and it becomes bug-driven development, with the agent going off to fix it. (Hahahaha, so much for test-driven, requirements-driven, user-driven, resource-driven — small, I was thinking too small! My guess is that as agents spread further, everyone's going to end up bug-driven hahahaha.)

---

## Why the Split Works at All

### Decoupling

The table above doesn't hold up because of discipline. If the modules were tangled together, "this bit follows one convention, that bit follows another" would be flatly unworkable — it changes one place and the effects spill somewhere else, and then I have to go back and read what it changed and tidy it up, at which point I may as well have written it myself.

So what actually makes this split possible is decoupling. But the decoupling isn't something I designed either. Like all those conventions above, it got forced out by problems.

### It Started With Circular Imports

At the start I wasn't decoupled like this (I just wanted the code to be a bit elegant, though I didn't know what elegant code was either). Then the modules multiplied, started importing each other back and forth, and the circular-import problem blew up.

At first I genuinely didn't understand why it happened... I just imported something, why is that a problem? Later I figured out, ah, this is a bit like referencing an undeclared variable and blowing out virtual memory.

Back then I didn't fix it at the level of the overall top-level module structure either — I was propping it up with lazy loading: put the `import` inside the function body so it only imports when it's used, and the circular import gets dodged.

Until later on, writing the `loop` part — the coupling was too deep, and I chased one circular-import error for a long, long time. Torture...

After chasing it down, I decided to pull it apart.

There was an easier road available at the time: keep using global lazy loading, change everywhere that broke into an `import` inside a `def`, and it would run just as well. But I thought, isn't that just... inelegant? Personally it felt like it would make a mess of things, so I figured I'd rather not. (Although my agent told me at the time that plenty of mature Python packages do exactly this — so this is only me explaining what I thought at the time, not a statement about whether I was right. It's a very personal thing.)

That decision is still verifiable today — across the whole project there are only 5 `import` statements inside function bodies, 4 of them in `local_model/embedding_worker.py` (lazily loading heavyweight model libraries inside the worker subprocess, a legitimate use), and 1 local `import re`. **Not a single instance of lazy loading written to dodge circular imports is left.**

### What Grew Out of Pulling It Apart

- **Three registration mechanisms**. Hook, Prompt, and Tool all rely on decorator registration plus auto-discovery at import time. In terms of handing out work, that means: give it the task of a new tool and it only touches `tool/tools/<name>/`, that one directory, three files — no changes to `loop`, no changes to the registry, no changes to `main.py`. **The blast radius is closed from the outset — if it gets it wrong, the damage is confined to that one directory.**
- **The engine doesn't branch on tool names**. Tool dispatch is entirely dictionary lookup; nowhere in the repo is there a hardcoded `tool_name == 'some tool'` check. So however tools get added or changed, none of it touches that engine. (The prompt text in `loop/orchestrator.py` does write out names like `plan_update` and `plan_mode_off`, but that's language aimed at the model, not a branch in the code.)
- **Plan orchestration pulled out wholesale**. In `loop/loop_core.py` all that's left of plan is a single line of delegation; multi-round driving, stall detection, and step-prompt assembly all live in `loop/orchestrator.py`.
- **Narrow facades**. Each module exposes only a handful of names.

### How Narrow the Facade Is Determines How Much I Dare Hand Over

This is the part of the whole thing that says the most:

| Module | Size | Exposed |
|------|------|----------|
| `local_model/` | 4 files / 611 lines | 8 names |
| `mcp_client/` | 5 files / 648 lines | 3 names |

In `main.py` there are four lines total about these two modules: `prewarm` on startup, `shutdown` on exit.

**The two blocks I didn't write a line of are precisely the two with the narrowest facades. That isn't a coincidence.** With the contract narrowed to three functions, I don't need to know how it's implemented inside — only when it starts and when it stops. The order is: decoupling first, then the confidence to hand the whole package over.

`tui/` works the same way: it has not one literal `import` of `loop`, `session`, or `memory` — everything is instances injected at construction time, and then it only calls a handful of public methods.

### The Price: What Got Decoupled Is the Imports, Not the Coupling

I have to walk this section back a bit, because the above sounds too pretty. If you actually follow the code, what you'll find is that the coupling merely moved from the surface to somewhere deeper. So writing a tool, a prompt, even a hook extension is still fairly easy — but if you want to touch anything closer to the core, you're in for a treat.

The dependency graph is broadly clean — `memory`, `hook`, and `tui`, those three top-level packages, are not directly imported by any other production module outside their own package; they're all assembled by `main.py`.

**The coupling hasn't disappeared, it just found somewhere else to hide**. Because every runtime object is injected, modules can depend on each other without any `import` at all — and that kind of dependency is invisible to static analysis:

- Background hooks in `hook` call `session._session_slice()` directly — an underscore-prefixed private method — and also parse the internal field structure of session's on-disk JSON, with three hooks repeating the same thing three times
- `memory` writes directly to `memory_agent.message_list`, which is the Agent's internal state
- `tool_core` calls `hooks.trigger(...)`, yet there isn't a single line of `import hook` anywhere in the `tool/` directory
- `loop` drives tool execution, while tools turn around and `import Loop` to construct new instances — at runtime that's a genuine bidirectional dependency, just not wired up with import statements

And the deadliest part: **when coupling is held together by convention, nothing errors out when the convention gets broken.**

Pretty magical effect, right, hahaha — the code logic may be wrong but it just runs, right up until the problem gets triggered... and then art is Patrick Star!!!

For instance. In `memory_core.py` I wrote myself a red-line comment, roughly: don't open a second parallel read path on the tool side, memory reads all have to funnel through the Memory class. And then the `memory_recall` tool does exactly that — it bypasses the injected memory object and goes and reads the session files and parses the slice fields itself. The red line is written on the memory side, the violation happens on the tool side, there's no import relationship in between, so nothing stopped it. The program runs perfectly happily. ps: another tech debt....

There are a few more like it: none of the three auto-discovery `import` loops has any exception handling, so any single broken plugin file can take down the whole startup; and the two registries silently overwrite on a name collision without a peep. I've filed all of these as issues and I'll pay them back gradually.

While I'm at it — that 900-plus-line memory core still hasn't been split up and rewritten. There's no deep reason; I just haven't done it yet... hehe

---

## Which Agents I Use

### hermes

The early teacher, as covered above. It was my guide over the stretch from "can't do this at all" to "can write it myself."

It kept me company through a good period.

### Claude Code

The current mainstay. `CLAUDE.md` and [the eleven skills under `.claude/skills/`](.claude/skills/README.en.md) are all for it. Cross-module mechanism changes, user-facing docs, the CHANGELOG, and commit messages basically all go through it.

I use it mainly because it's the only agent so far (of the ones I've used) that shows me a diff before editing a file and then asks me to approve. The others just hand me one of those giant reviews — and frankly, me saying that is me saying nothing, because who's going to actually read that giant review? And if one spot has a problem, do the other spots stay or go? Tsk...

That said, after trying cursor for a while I found it's not impossible to adapt to. It's fine for odds and ends; but for the core, every line has to have my authorization before it lands — even when I'm just too lazy to write it and let them do it, I still have to keep these agents on a leash!

### Cursor

The five rules under `.cursor/rules/` are for it.

The tab autocomplete is onto something, multitask is onto something, nicely done and convenient; that user_view interface for plan is well done, and I like the todo_list in it. Overall a decent IDE — but can it fully replace vscode?

If you lean heavily on autocomplete, then sure; if you don't, it's shaky. Because I don't know whether it's my machine not being great or what, but I found that even after I turned autocomplete off, the IDE's own built-in completion hints still felt very slow — or rather, slow enough that you can clearly feel yourself waiting on it for a while, and then your train of thought breaks. Ridiculous.

Maybe it's the autocomplete logic layered on top of vscode shadowing or overriding something. No idea.

### Codex

The `@codex` markers in the code are concentrated around the TUI period.

Not suited to being a code buddy; suited to being given a goal and sent off to run with it. I use it fairly often in my regular PM work, and it works well.

### Alear030 Itself

This one needs saying clearly on its own, or it gets confusing.

What I mean by "Alear030 itself takes part in development" is something else:

It isn't that it writes its own code, the way cc does dogfooding iterations. Because there's one thing — I know Alear030 can get things done, but the destructive potential is very large, and I don't have enough engineering confidence to backstop it.

(And here I have to mention the business with the eval worktree I destroyed. I'm a genius, honestly, unbelievable. At the time I didn't think much of the thing — I was just seeing whether my memory system, once built, was actually usable. I had no idea it would turn out to matter this much.)

So Alear030's file-editing ability is still under multiple restrictions right now (prompt guidance + hard path checks in the tools). Only once the permission mode has been fitted with file-writing TUI diff display and approve capability will I let it iterate on and develop itself. That was the plan I set from the beginning.

But that doesn't mean Alear030 hasn't helped me develop it. On the contrary, it has helped me a great deal in sorting out my thinking. My earliest conversation records with it should start somewhere around June 10-something, but early on I had no awareness of memory, so no corpus got kept — a real shame. The records that did survive are basically me writing something new and then asking it to take a look, hearing its thoughts and opinions, and having it help me think and research approaches.

ps: while I'm here, a word about Alear030's enormous plan. Every plan execution runs head-down for tens of minutes, and sometimes I genuinely don't understand what this kid is thinking, so I've been wanting to build something lighter along the lines of a todo_list.

I'm also weighing whether to keep the current plan state machine at all. Having that state machine is, to a large extent, excessive distrust of the model's own ability to constrain itself, plus a gap in equivalent capability.

Honestly a plan.md plus a todo_list, with round reminders and usage reminders added into the attachment, would solve this enormous state machine's problem in a very lightweight way. So I'll probably rewrite the plan area later, and possibly move it somewhere else to serve as the heavy machinery.

And then there's me writing while discussing how to write. [Thoughts and Design of the Memory System](docs/design/memory.en.md) came entirely out of that — the material for that piece was dug out of the project's own historical session records: 61 sessions, 393 slices. **Using the output of this memory system to reconstruct its own design history.**

That's probably the most interesting thing about this project, and also, I think, a big part of why agent-type projects are so appealing to individual developers. Maybe as the tech keeps developing, learning object-oriented programming will literally mean programming oriented toward an object hahahaha.

---

## Those @claude / @codex / @cursor Markers in the Code

Reading the code you'll run into things like this:

```python
self.length_end = False# @claude 后续需要添加流式长度，截断工具执行的逻辑
```

These are to-do markers I leave for agents. While writing code I think of something to do later, but I don't want to be interrupted right then — or I can't be bothered writing that bit of logic — so I leave a marker in place, and then: rise, my agent!

Three conventions:

- `@claude` / `@codex` / `@cursor` — a task for the corresponding agent
- `# done(@claude): what got done` — rewritten in place once finished, so the trace stays and it won't get picked up again by the next scan
- `@claude(ignore)` — a note to myself, not a task, hands off

Why not `TODO`? Because TODO is written for humans, and whether anyone reads it is anyone's guess. These markers have **a consumer** — there's a dedicated skill whose job is to scan them out, list them, and ask me one by one whether to do them. That's the difference. ps: the reasoning above was written for me by my agent. The real story is that todo just never occurred to me. My thinking was simple: if I want you to handle something, I'll just @ you and be done with it.

One clarification, though: the repo has no automatic scanning configured, so it only scans when I call for it. If you want it to run automatically at the start of every session, you need to set up a SessionStart hook yourself.

---

## Agreement Files: Why These Files Matter So Much

Three things in the repo are for agents to use, or get loaded into their context by default

- `CLAUDE.md` — project overview, stable module map, core runtime data flows, how we work together, data-safety red lines
- `.cursor/rules/` — 5 rules
- `.claude/skills/` — 11 skills, described one by one in the [skills catalog](.claude/skills/README.en.md)

I put them under version control not so humans can go in and study them — no need for that. It's because an agent's context is precious, and you can't have it going in blank every time and exploring the entire repo just to write some small thing. That would be too... how do I put it... too extravagant. Impressive!

**So the repo's conventions, structure, framework and ways of working — whatever can be fixed in place — need to be distilled hard and loaded by default**

ps: context management and cache management, those two gatekeepers — I think that in an agent project, only the engine matters more than those two.

And this definitely isn't only something the model side has to work on. The model side just receives the data you pass over, runs an enormous computation for you, and returns a result. It can cache what it has already computed from what you passed over, but it can't guarantee how you pass it over.

Alear030 covers part of this, but what's there right now isn't enough for me to write up separately, so that's for later. On model-related matters I actually don't know much, which frankly shouldn't be the case...

Also, I'd recommend the research from cc's evil butler crowd — everyone knows about it... but you also can't... right. I won't say too much. If you know, you know 030

Back to the point: what's actually more worth saying here is that **not one of these rules was designed by me sitting down to design it. They were all trodden out.** Behind every one of them is an occasion when it got something wrong.

Three examples.

**"Surgical changes"** — the scope of a change is set by what the mechanism needs in order to close properly, not minimized to the literal wording of the task.

This one runs backwards from intuition. At first I thought "minimal change" was a virtue, and then found it leaves a pile of half-finished states: the producer changed but not the consumer, a new path added but the old entry point not removed. So what's written now is: when a fix touches a call chain, actively widen the exploration and put the mechanism-level knock-on items into the plan; when the literal task isn't enough to achieve the goal, explicitly raise the out-of-scope items and let me decide — **raising something isn't overstepping; dodging it is.**

**"A temporary cutoff is not deleting the implementation"** — `.cursor/rules/minimal-disable-preserve-body.mdc`

This one is very specific, because it hurt in a very specific way. I said "turn this feature off for now," and the result was a function body emptied out with a single `return` left. Turning off and deleting are close in wording, but they're two completely different things. The good/bad `rich_print` example in that rule is the actual crime scene; I didn't convert it into an abstract example, I left it there as a memento. The self-check at the end of the rule is the key part: **"If the user removed this one return line, would the original functionality come back intact?"**

**"Same problem corrected more than twice → stop and start over"**

This one is for me, not for it. If I've corrected the same spot twice and it's still not right, that means it isn't that it didn't understand — it's that I didn't explain properly. Piling on more patches only makes it muddier. What to do at that point is stop, change the fundamental approach, or rewrite what's known into a clearer requirement.

There's also a whole set around data safety: `session/session_detail/`, `memory/memory_storage/` and the like hold real conversation and memory data, not temp files you can casually rebuild. The rules there are written hard — no deleting, clearing, or bulk-overwriting without my explicit authorization; when a clean environment is needed for verification, use a temp directory or a temp session id, and never wipe the real data to test; and when replaying real historical data for verification (testing a new prompt version, say), MD5 the relevant files before and after and compare, to prove the test script didn't write anything by accident.

---

## About Skills

ps: I lived through the wave of skill hype, and early on I even built myself an enormous PM skill set. Looking back, two things: what suits someone else doesn't necessarily suit you, and AI empowerment is a multiplier, not a flat addition.

The skill thing in this repo lives in two separate places.

One is `.claude/skills/`, the eleven skills I wrote for coding agents. The other is `skill/`, Alear030's own runtime skill system.

**The format is the same one.** Both are one directory holding one `.md` file, both write `name` and `description` in YAML frontmatter with a Markdown body underneath. Triggering in both cases is mainly `description` matching — whoever is reading looks at the description and decides for itself whether to use it this time, rather than me hardcoding into the flow when it gets called.

**The load path is isomorphic too.** On the Alear030 side, `prompt/prompts/skill_prompt/prompt.py` takes every skill's `name` and `description` from disk at Agent construction time and splices them into the system prompt (order 20, and only for agents holding `skill_tool` authorization); the model sees that list and decides for itself whether to call `skill_load` to pull the body in. On the coding-agent side it's also description first, full text loaded only on a hit. Same mechanism.

**The difference is who does the distilling.**

Some are produced by actively creating a skill: step on a rake once, or repeat something once, and out comes one. Eleven skills, 1198 lines, all accumulated that way.

The Alear030 side is automatic (only one so far has come out of an automatic proposal). When similar tasks accumulate past a threshold, the memory pipeline produces a skill candidate and interrupts the current conversation with an attachment: you've done this kind of thing several times, consider fixing it into a reusable skill. Then it goes through `create-skill` to draft, me to confirm, and landing on disk; finally `skill_finish` writes back to the task node and zeroes the accumulation counter, so it doesn't keep prompting for the same thing.

Writing this out is when it hit me that these two are actually the same thing. In [Thoughts and Design of the Memory System](docs/design/memory.en.md) I summed it up in one line — **"let the data produce the structure, let usage drive the optimization."** Skills are that line at its most surface-level, I suppose.

---

## The Rhythm of Working Together

The default flow has four stages: **explore → plan → execute → verify**.

1. **Explore** — read the code and establish what's actually there, change nothing, produce "the current state is X"
2. **Plan** — propose an approach, actively call out the trade-offs and risks, produce a plan I can edit and sign off on
3. **Execute** — only start after I've signed off
4. **Verify** — give test output or a working run, not the assertion "it's done"

Only **pure text changes with no behavioural impact** (typos, comments, renames I've explicitly specified) may skip the first two stages and go straight through. Anything touching behaviour, mechanisms, parameters, or call chains has to pass the planning gate first, even if it can be described in one sentence.

Why not go with "I give the requirement → it goes off and executes"? Because the requirements I give are frequently wrong. Not wrong in the wording — I just haven't thought it through yet. The real value of the explore stage isn't getting it familiar with the code; it's that reading its report on the current state makes me realize "oh, so that's how it is now — then what I actually want is a different thing."

Once the project got bigger, a few more got layered on top:

- **Sliced units of work** — big cross-module changes get cut into pieces that are independently committable and runnable, one closed loop per session, no half-finished work with known defects left behind
- **Verification first** — for mechanism-level changes, say up front how it gets verified quickly, then start; probes get fixed into `test/` where possible rather than thrown away after use
- **Parallel orchestration** — cross-module changes get several subagents exploring and reviewing in parallel; three gate levels: pure text goes straight through / single-module mechanism self-verified / cross-module runs the full flow

The division of responsibility is written into `CLAUDE.md`; roughly: direction, taste, north-star judgement, and the final call on "what counts as good enough" are mine; reading code, researching, laying out context, drafting approaches, implementing, and verifying are its. Proposing directions, surfacing mechanism-level root causes, and pointing out cross-module impact are part of its job — **proposing isn't overstepping; deciding is.**

There's one more I personally find quite important: **vague questions are legitimate, and actively encouraged.** Open questions are for creating together; I'm not required to arrive with a fully formed requirement every time. Plenty of times I've opened with nothing more than "something feels off here."

---

## How I Check That What It Wrote Is Right

This is the part of the whole collaboration that's easiest to overlook and that decides whether it works. If the work you hand off can't be verified, that's not collaboration, that's praying.

I use three layers, heaviest first:

**Copy it out by hand.** Only for critical paths; `hook_core` went through this.

**Run the verification.** This project's verification has a few counterintuitive pitfalls, so I wrote them into a skill: `python main.py` in the main repo is not a side-effect-free smoke test (it writes session files and calls the model API), verification scripts have to be invoked with `python -m` dotted paths, and `unittest discover` must not be given `-s test`. All of these were written down only after stepping on them.

**Look at the diff.** Once a change lands, go through `git diff` myself. This layer is the lightest, but it catches the "it changed something else along the way" class of problem.

Honestly though: **this setup is not foolproof.**

I still don't have a retained, purpose-built, complete eval set (the golden set is on the Roadmap and not done), which means for things like memory recall quality — which won't throw an error but will quietly get worse — all I can go on right now is how it feels.

---

## So How Should You Read This

Two sides to it:

**Architectural judgement, trade-offs, and direction are mine.** The core framework I wrote line by line, and the designs that look odd (forcing a final reply by physically withholding tools rather than writing a prompt for it, switching mode by diffing before and after rather than trusting the model to be honest about it, sealing MCP's asyncio inside one resident task) were all my calls.

**A fair amount of what actually got put on the page wasn't typed by me.** External integration barely passed through my hands, and the odds and ends and mechanical data processing got handed off too.

Those two sentences don't contradict each other, and I don't think the second one needs hiding, because that's simply how it is.

One last thing: this split is something I crashed my way into. It isn't necessarily right, and it isn't necessarily right for you. But it's real, and behind every one of these boundaries is a specific instance of pain. If you're also torn over "which parts should I write and which can I hand off," my answer is — **listen to your gut; when you feel like a part of it ought to be yours, try writing it yourself first, and you'll probably get something out of it**

---

← [Back to README](README.en.md) · [Contributing](CONTRIBUTING.en.md) · [Thoughts and Design of the Memory System](docs/design/memory.en.md)
