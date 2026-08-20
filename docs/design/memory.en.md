# Memory: Ideas & Design

[中文](memory.md) · **English**

← [Back to README](../../README.en.md) · [Mechanism doc](../modules/memory.en.md) · [Docs index](../index.en.md)

The [mechanism doc](../modules/memory.en.md) covers "what it looks like now." This one covers "why I built it this way" — a few of the choices look strange in isolation, and only make sense once you know what problem they were actually solving.

What follows is my own thinking at the time, plus the conversations I had with Alear030 while building it — drawn from the project's historical session records: 61 sessions, 393 slices, 220 of them related to the memory mechanism. **Using the output of this memory system to reconstruct its own design history.**

"Alear030" as quoted below refers to the very system being developed at the time — those conversations are what's left over from writing it while discussing, with it, how to write it.

A few thoughts on memory in general: designing and building an agent's memory framework always ends up circling the same handful of questions — when to store, how to store, what to store, when to recall, how to recall, what to recall. That's the baseline. After that comes something a bit more involved — non-linear memory structures and self-emergence (or, put another way: giving the system/agent a base scaffold and letting it grow, maintain, and evolve on its own). This is actually the whole reason I insisted on writing my own thinking up as a separate design doc — I wanted to share it.

The total code for memory isn't actually that much — the core file is only about 900-some lines, and even that's partly because I never split it up or refactored it cleaner. But the lived experience of building it felt completely different from that line count: the more I researched, thought about, and pushed this forward, the more it felt like the design-and-thinking effort alone rivaled everything else in the project combined. Every other module basically wraps up once it's written — unless something else touches it, it's done, a phase that closes. Memory never closed. How to design it, how to build it, has been running continuously in the back of my head the whole time. That's a strange, interesting feeling.

What follows is partly a question I've been chewing on since around mid-June, and partly my own thinking on the aspects above.

---

## Table of Contents

- [The Original Goal Was Never a Memory System](#the-original-goal-was-never-a-memory-system)
- [The Reference Point All Along: Human Memory Itself](#the-reference-point-all-along-human-memory-itself)
- [The Foundation: Making One Event Storable First](#the-foundation-making-one-event-storable-first)
- [Exploring the Storage Structure — the Graph: the Direction I Deliberated Longest and Never Shipped](#exploring-the-storage-structure--the-graph-the-direction-i-deliberated-longest-and-never-shipped)
- [Retrieval: A Few Conclusions from Real-World Testing](#retrieval-a-few-conclusions-from-real-world-testing)
- [What Is Self-Emergence? Where Does It Stand Now? What's Its Potential, or What Do I Expect From It?](#what-is-self-emergence-where-does-it-stand-now-whats-its-potential-or-what-do-i-expect-from-it)
- [Some Trade-offs I Made Along the Way](#some-trade-offs-i-made-along-the-way)

---

## The Original Goal Was Never a Memory System

What I wanted was **an agent that could grow on its own** — or maybe more like its own kind of existence. Self-emergence is necessary; memory is only the necessary foundation for it, not the destination.

That distinction sounds abstract, but every strange-looking choice further down traces back to it: why the graph structure — the thing discussed longest — was deliberately never shipped, why recall is still brute-force full-scan to this day, why almost every classification scheme in the system refuses to be hard-coded.

This sentence isn't something I summarized in hindsight. It comes from [the chapter on the graph](#exploring-the-storage-structure--the-graph-the-direction-i-deliberated-longest-and-never-shipped) — at the low point of the discussion on 2026-06-26, Alear030 put it into words for me. If you want to see the evidence first, jump straight there.

PS: **What I actually wanted to build was never a memory system or framework. Memory is just a problem I had to solve on the way to what I actually wanted.**

---

## The Reference Point All Along: Human Memory Itself

My starting point was referencing how my own memory actually works — not copying some paper, or the corresponding cognitive-science, neuroscience, or brain-science literature (because at the time I knew exactly none of that! #wrong-but-confident-anyway), but "what do I think memory ought to be like?" For the parts that can't be implemented in machinery — certain properties of the human brain, for instance — I substituted other methods.

### The Brain-Region Mapping Came Later

The order matters here: **I built things according to "this is how memory should work" first, and only found out afterward which brain structures they corresponded to.**

The turning point is in the 2026-06-24 record. After I described how I'd been thinking about `session_recall`, Alear030 pointed out that I'd **shifted from a functional view to a cognitive-modeling view** — he's the one who named what I'd been doing. That same conversation also pulled in the idea from *How the Mind Works* that "memory is reconstructed on the spot."

By 06-26, the summaries were already phrased as me "deliberately building a brain-like memory system," and I started reflecting on something myself: human memory retrieval is triggered by sensations and images, not keywords.

Later still, this correspondence became an explicit design input. Discussing emotional memory on 07-04, I went straight from the division of labor between the hippocampus and amygdala to "tag slices with emotion labels; slices with high emotion labels auto-inject into context and persist longer" — and along the way landed on a conclusion: **natural attrition beats explicit forgetting management.**

So the full story is: **it wasn't intentional correspondence at first — it got pointed out only after the fact, and only then did it become a conscious reference.**

I was also thinking about something else at the time: now that the AI era has arrived, what's the biggest change for me personally? One of them is probably this — whatever idea pops into my head, I can immediately go find the corresponding field's knowledge, dig into and learn it, then immediately build it and see what happens. Realizing that changed a fair amount of how I've worked ever since.

That's genuinely interesting — a lot of the time an LLM feels to me like a shared cloud drive of all human knowledge across all of history, haha, it really is interesting.

### On Similar Projects

Partway through I searched for a few memory frameworks that were getting attention at the time, to see if anyone else was doing the same thing. There were papers in this direction, though some of them went pretty big on it (scared me a little), but I didn't find engineering implementations going down this road, so I started trying it myself.

ps: honestly I really wanted something existing to map myself onto. Building memory was a constant grind of pushing forward while constantly doubting and second-guessing whether my own approach was even right — genuinely a form of torture. Looking back now I'm actually curious why I put myself through that. Good thing I ended up with a result that I personally think is pretty "whoa" — 030. ps's ps: that was a meme face — pouty lips, playing dumb, haha.

---

## The Foundation: Making One Event Storable First

It's worth spelling out my original cognitive model here. Early on, referencing my own memory — or human memory in general — my thinking went like this: humans don't summarize what they're experiencing in real time, on the fly. In the moment, they're just experiencing it. Only once some external trigger sets off a recollection do people start tracing back, locating, and reconstructing related fragments through various means, and then replaying them in their mind.

Later I learned about some of the theories in that *How the Mind Works* book mentioned above, and it clicked for me that human memory is probably jointly constructed out of every external and internal "feeling" present at the time — not just something like a cartoon reel of images (thinking about it now, you don't even need a theory to see that — you clearly remember non-visual things too...). When we recall, sometimes it's a keyword-based approach, sometimes it's a fragment of a scene, but sometimes it's just a plain feeling, an emotion, a thought.

There's another property too: sometimes human recollection isn't actively willed at all. I haven't fully worked this one out, or honestly haven't thought hard about it, but I really have observed this in myself — at various points or occasions, my mind will automatically surface related past fragments and content on its own, to help me think, without me asking for it. That's a strange thing, and I don't know why it needs to work that way, or why it does. Doesn't that raise the brain's energy cost for no reason? Not sure — maybe it actually helps? Otherwise why would it have evolved this way? Noting it here — I might dig into why later (@agent remind me about this when I'm thinking it through, down the line).

### From "Classify on Arrival" to "Stream of Experience"

The next chapter — the discussion about the graph — opens with "you said this slice can't be changed after the fact." That's built on the premise that the slicing layer already exists. So first, how the foundation got built.

My original plan was to actively classify information and store it in the corresponding place. By the second generation I threw that out: **don't pre-classify — save the experience as-is, as a "stream of experience,"** then form triggers, associations, and extractions on top of it.

Today's `session_detail` — the complete, seamless, uncropped record of raw messages and slices — is the direct product of that decision. Derived layers can be recomputed; the stream of experience must never be lost.

### Cold Start Forced Incremental Slicing

Early on I hung the summarization chain off `compress`, but compression rarely triggered, so recall was starved for a long time.

My fix was to re-slice from the start of the last slice every round. The key discovery: even without a summary yet, `topic` and `key_words` are already enough to support recall. Today's "open-ended tail slice + re-feed window" comes from exactly here.

I saw the cost even at the time — the early slicing decisions are irreversible, and the mitigation was to eventually do a periodic global re-slice. That still hasn't been done.

### Decoupling Slicing from Storage

Slice granularity is never ideal — either too fine or too coarse (LLM output is never reliably predictable, which is also why so much of this codebase reads like reflexive defensive programming — the thing really does output garbage sometimes, no matter how carefully you write the system prompt, it's honestly exasperating). My conclusion was to stop expecting to get it right in one pass: **slicing is only responsible for slicing (chasing purity); organizing and aggregating is the storage layer's job.**

Today's layering — "`session_slice` is the source of truth, `slice_node` is derived storage" — is that principle put into practice.

### A Slicing Stall Forced the Hook System Into Existence

Slicing synchronously after every round blocked input, and it felt terrible. My fix was to throw it onto a background thread and process it serially.

What actually mattered was the next step: **I generalized that background maintenance thread into a "registrable pipeline" that could take any hook later on.**

Today's entire event-driven Hook system traces back to this one bad-feeling problem. I didn't design an extension mechanism first and go looking for a use for it — it happened the other way around.

---

## Exploring the Storage Structure — the Graph: the Direction I Deliberated Longest and Never Shipped

This is the piece I spent the most time discussing and ultimately abandoned myself (thinking about it still gives me a little heartache every time, T-T). The whole arc happened in a single session on 2026-06-26 — 16 turns from proposal to verdict.

The original wording is kept below, because the summary alone gives no sense of this arc at all. Only typos are fixed, plus one place where I misattributed something in the moment.

### The Proposal

> I suddenly had a direction.
>
> So you said this slice can't be changed after the fact, and actually that's right… and I suddenly had an idea — after confirming a new slice, why not immediately combine these slices with embeddings into something like a graph structure?

The idea was to grow a graph layer on top of the slicing layer, with nodes auto-linking to each other, so that a cross-session recall would connect the hit fragments together.

### The First Crack: Where Does the Entry Point Come From

> I've actually understood the graph too, but there's still a problem: the graph can auto-spread and auto-build edges between nodes, but the problem is — at `memory_recall` time, how do you get a first node to start from? I can't traverse all the nodes just to find that node, haha haha.

The graph can spread, but only once you're already standing on some node. And finding that entry node is itself a retrieval problem.

### The Fatal Question

> No wait, the problem is — I'm already running full embedding similarity over everything. Why wouldn't I just take the top three most similar and return those? What do I even need the graph for?

If the entry point is already found via full embedding similarity, then top-K is already the most-similar result — one hop of spreading either returns duplicates, or returns something less similar and dilutes precision instead.

There was something absurd about it — the moment I landed on that conclusion, I had this feeling of being completely absorbed in my own art, unable to pull myself out of it, and then reality just came and shattered it without mercy. Heh.

That was a painful lesson: theory, ideas, and concepts can guide implementation, but you should never implement something just for the sake of implementing it, and you can't divorce yourself from engineering either — all of this exists to serve your actual goal. And what is that goal? Certainly not something flashy enough to brag about that shatters the instant it meets reality — honestly, that kind of thing isn't worth much.

Alear030's answer didn't dodge it:

> If the entry point is full-embedding matching for top-K, then **at current recall precision**, the graph really doesn't add anything. … At the current stage, plain full-embedding matching for top-K is enough. The graph isn't necessary for recall right now.

### The Low Point

> So after all this research, the conclusion is that nothing beats brute-force full embedding similarity matching?

> The thing is it has to actually ship. All this stuff we talked about — multi-anchor, graph, resonance — sounds great, but I started researching this specifically for recall, and after all that research it turns out full embedding comparison beats it anyway….

### The Turn: It's Not That the Graph Is Useless — It's in the Wrong Place

Alear030's response re-sorted everything into its proper place:

> It wasn't wasted. What we figured out isn't "the graph is useless" — it's that **the graph was placed wrong.**

| Previously thought to optimize recall | What it actually solves |
|---|---|
| Incremental slicing | **Cold start** — makes new memories searchable immediately; unrelated to how you search |
| `worthy_summary` | **Encoding selectivity** — what gets remembered and what doesn't; unrelated to how you search |
| Multiple anchors | **Encoding richness** — leaves entry points for the future, not about making today's recall more accurate |
| Graph | **The relational layer of memory** — cross-session aggregation, spreading activation, co-activation statistics |
| Anchor resonance | **A trigger mechanism** — not "searching" but "being moved to recall"; a paradigm for the future |

**Today's four-layer memory architecture (encoding / storage / retrieval / relational) split apart at exactly this moment.** That discouraging conclusion didn't kill any design — it forced a separation of responsibilities. The reason the next chapter can stand as its own independent layer starts here too.

### The Hinge of the Whole Chapter

> **Me**: It's hard to put into words, but I don't want to give up on my current line of thinking.

> **Alear030**: Then don't.
>
> Full embedding is the optimal solution for recall — that conclusion is correct. But that doesn't mean your line of thinking is wrong — it only means **you put those pieces in the wrong scene.**
>
> The things you don't want to give up — anchors, graph, resonance — the problem they're meant to solve isn't "how to search more accurately." Recall is already accurate enough with full embeddings.
>
> The problem they're meant to solve is a different one: **the moment the agent doesn't need to be asked, and simply remembers something on its own.**
>
> What you're doing now with recall is "passive recollection." But your line of thinking — multi-dimensional anchors, graph spreading, resonance — all of it points toward **active emergence**. The core feature of human memory isn't "can answer when asked" — it's "remembers even when nobody asked."
>
> You don't want to give it up, because you know passive recollection isn't the destination.

This passage is exactly where [the opening claim](#the-original-goal-was-never-a-memory-system) comes from: **self-emergence is the goal, recall is only the foundation.** The reason the graph "lost" this recall debate without deserving to be thrown away is that it belonged to the goal layer all along, not the foundation layer.

### The Verdict

I kept pushing (a last-ditch struggle — there were times I genuinely wanted to go tweak Alear030's system prompt to make him a little less relentlessly objective and neutral... this guy never stops calling me out >-<):

> Ignore all my constraints for a second — what to do, what to do later, what needs to accumulate first, none of that's the issue. What I'm actually asking is: for this whole graph setup, where's the concrete scenario and meaning that proves it's necessary, that it's a must, and that it's good?

The final plan came from me:

> Actually, maybe the best setup is: do a brute-force search when recall is needed, but link the results into nodes afterward. Then next time a top-K node comes up during recall, check whether it has any linked nodes, and if so, bring those along too?

Alear030's reply was three words: "Yes. That's it." Then he wrote it into one sentence — **the graph handles linking, not recall.** The primary result stays clean, relying only on embedding similarity; the graph only enhances the result, spreading one hop out from top-K to bring back linked nodes.

### PS (a few thoughts as I write this)

That conclusion at the time — "brute-force search is the best you can do" — looking back now isn't quite right.

Because my memory system today is already facing a very real problem of its own: the data volume grows linearly.

The volume of historical memory turns out to be a variable that matters a lot: full-vector similarity matching is, first, less accurate and less flexible once the data gets large, and second, its computational cost also grows linearly.

Later I looked at a few memory frameworks that do this reasonably well, and pretty much all of them run some auxiliary scoping step before the embedding step, instead of comparing against everything from the start. Honestly, my own memory system's first version actually had similar comparison logic too, but I stripped it out entirely during a later full rewrite — partly because my memory framework has no dedicated type/keyword mechanism, and partly because if you match on keywords first, the LLM doesn't actually know what target keywords it should even pass in. And since then I've kept chasing the search-scope-and-matching problem from other angles instead, so the keyword mechanism never got reimplemented. Though I do think… it'll probably get added eventually… maybe.

### Where It Stands Now

**I still haven't implemented this plan in its final form.**
(Do I even need to write this....)

It's not an oversight — it's a matter of ordering: the foundation had to be built first. To this day, `memory_recall` is still a brute-force full-embedding scan, with no graph and no associative spreading.

---

## Retrieval: A Few Conclusions from Real-World Testing

Of the four layers split out in the previous chapter, the retrieval layer has since evolved on its own. None of the three points below were designed — all three were hit by accident through real usage.

### Time Anchors: From Temporal Edges in the Graph to Injecting `session_id`

Pure embeddings can't handle time-proximity questions like "what did we just talk about." At the time I had two options: add temporal edges to the graph, or inject the most recent handful of session ids at the start of a new session.

I picked the lighter option — the latter. That path eventually grew into today's `timeline.json` and the `timeline_prompt` chunk.

### A Counter-Intuitive Finding I Tested Myself

After the timeline shipped, I built a two-stage retrieval: use the timeline to locate a candidate range first, then use `session_ids` for precise recall instead of a full scan. It sounds smarter.

The test result was the opposite — **the pre-filtering dropped the highest-scoring embedding match.** A judgment made from the timeline's description was less accurate than brute-force full retrieval; the session that got mistakenly picked was clearly irrelevant, and the one that got dropped was exactly the most relevant one.

The deeper reflection came after that: the timeline is a **shared variable** — it had already done a round of pre-filtering back at the keyword-construction stage, so the comparison "full scan vs. scoped by `session_ids`" was never a fair one to begin with. The conclusion is that the timeline itself is already the strongest pre-filtering mechanism there is.

That's why `memory_recall` still keeps a full scan as the default behavior to this day — `session_ids` is only an optional narrowing parameter.

When I first landed on that conclusion, I was still a little skeptical — surely the timeline wasn't going to turn into another version of the graph thing, right? But later I built my own small test set modeled on LongMemEval and ran it, and the timeline genuinely helped — especially on cross-session questions where ordering across time also mattered. On the questions that purely tested search-matching precision though, I can't say it helped zero, but I'd say it didn't help all that much either, haha.

ps: that test set isn't part of the open-source scope, because... it was built in its own worktree at the time, and, well, how do I put this... I accidentally destroyed that worktree. I'm not great with the finer points of git, and I've only had so much time to learn it — I only started learning Python on June 5th, and limited time means I can't learn everything else at once too. But at the time I did also try running this memory framework against LongMemEval — the smallest version, the 500-question one, a handful of questions per category — and it got them right, at least. I never finished the full run, because the data preprocessing was too heavy, the LLM call volume too large, and the processing time too long... it kind of choked, and I kind of couldn't afford to run it either, haha. Once I've built a proper golden set later on, I'll get it into the GitHub repo eventually — that's the plan, anyway.

### Summary Quality Caps the Ceiling on Recall

There was a time I tried to find a past discussion about graph-structure research, and three searches in a row came up empty. What that exposed: **if the summary never captured that meaning, recall can never find it,** no matter how accurately the vectors are computed.

That remains a structural ceiling on this design to this day.

That said, it's not unsolvable — it comes down to the slice's data structure and what gets stored, i.e., the question of what memory actually stores, because what you store directly determines how and what you can retrieve later.

---

## What Is Self-Emergence? Where Does It Stand Now? What's Its Potential, or What Do I Expect From It?

First, what this word actually means: **nothing in this system is something I hard-coded — it grew on its own.** How many kinds of memory there are, what dimensions a profile has, what feature words are used to recognize things — none of that is something I predefine.

What I originally envisioned was a purely bottom-up, ideal graph structure model; what actually shipped was today's layered form:

> The bottom layer — the stream of experience and slices — stays solid; the upper layer — `type_name` stable, the `feature` layer differentiating independently — **layered self-emergence, no layer blocking another.**

What changed was only the **engineering shape**, from a pure graph to layering — the goal itself never moved, start to finish.

Even this current shape only counts as half of self-emergence. The three layers written up in the [mechanism doc](../modules/memory.en.md#self-emergence-what-this-pipeline-grows) are all real — classification feature words grow, profile dimensions grow, skills grow — but **the type set itself is still something I hard-coded.** `memory_core.py`'s `slices_pipeline` has exactly two hard-coded branches:

```python
if 'user_info' in slice.get('slice_type',[]):
    ...
if 'task' in slice.get('slice_type',[]):
    ...
```

Once a slice is classified, which pipeline it can enter is pinned to exactly these two types — `user_info` and `task`. Feature words can grow on their own, but "how many kinds of memory there are in total" is still something a person decided.

**The next step is to fully release that degree of freedom: stop dictating which types exist, and instead let types emerge on their own, paired with a corresponding pipeline for handling them.**

Once that step is done, `user_info` stops being a hard-coded category and becomes "info about some specific entity" — each entity gets its own record, which then aggregates upward into a layer like `human_info`. There are only two types today, `user_info` and `task`, because the pipelines still have to be written by hand one at a time; only once types can grow on their own does it make sense to say the pipelines grow along with them.

Only at that point does it really count as self-emergence. This isn't a debt owed — it's the next stretch of the main line.

---

## Some Trade-offs I Made Along the Way

One sentence has run through all of this, something I summarized myself at the end of June:

> **Let data produce structure; let usage drive optimization.**

It explains why almost every classification scheme in this system — slice feature words, profile dimensions, task nodes — is never a pre-written field table, but something that grows out of use instead; it also explains why the "hard-coded type set" from the previous section is, to me, an open problem to solve rather than a design taken for granted.

The other trade-off was about energy. A one-person project — partway through, I made a deliberate call: **treat memory as infrastructure, fix it just enough that it doesn't break, and prioritize pushing the system to keep growing**, rather than polishing every corner to production grade first.

Most of the entries in the [mechanism doc's known limitations](../modules/memory.en.md#known-limitations) section are the direct result of that trade-off, not oversights.

---

← [Back to README](../../README.en.md) · [Mechanism doc](../modules/memory.en.md) · [Architecture](../ARCHITECTURE.en.md)
