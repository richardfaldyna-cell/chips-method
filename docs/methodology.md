# The CHIPS methodology

A procedure for parallel development with AI agents. The goal is not speed —
the goal is that parallelisation **does not lower quality** compared to serial
work.

> This is the English translation of [metodika.md](metodika.md), which is the
> source of truth. Tool flags, brief section names and file names are kept in
> their original Czech form and glossed on first use; the README has a full
> glossary.

---

## 1. Vocabulary

| Term | Meaning |
|---|---|
| **chip** | a self-contained packet of work: a list of issues + boundaries + definition of done |
| **window** | a separate Claude Code session with its own context and limits |
| **orchestrator** | the main loop in a window; hands work to subagents and merges |
| **subagent** | a secondary instance with an isolated context (Agent tool) |
| **gate** | an automated check without which nothing may be merged |
| **T3** | a decision a chip must not make on its own (see §6) |

Mind the layers — they get confused:

```
you  ──►  chip brief  ──►  window (orchestrator)  ──►  subagents  ──►  gate  ──►  merge
          file             session                   Agent tool      tests
```

---

## 2. Slicing work into chips

**The only criterion is file disjointness.** Not the age of the issues, not
priority, not topic. Two chips that touch the same file will collide — no
matter how well they are described.

Procedure:

1. **List the issues** and for each one estimate which files it will change.
   For unclear ones find out (grep, read the issue) — guessing doesn't pay here.
2. **Group by files**, not by topic. Issues touching the same module belong in
   one chip even if they are thematically unrelated.
3. **Verify disjointness** — `python tools/chip_lint.py` walks all briefs and
   reports any file claimed by two chips.
4. **What can't be sliced, do serially.** When three quarters of the issues
   fight over one central file, parallelisation won't help you. Make that file
   chip #1 and start the others only after its merge.

### How to write a file claim

Paths in the "Dotčené soubory" (files touched) section are **relative to
`repo:`** from the frontmatter. An absolute path or `..` is an error — the
claim can then not be compared with other chips.

| Notation | Meaning |
|---|---|
| `src/parser.py` | a specific file, must exist in the repo |
| `src/` | the whole directory including its subtree |
| `src/report_*.py` | a pattern; expanded to real files for collision checking |
| `src/new.py  # nový` | a file the chip will create — the existence check is skipped |

In the `ready` state lint verifies that the claimed paths **really exist** in
the repo. A claim on a non-existent file is either a typo or a stale brief —
and in both cases the chip's slice is built on something that isn't there. The
`# nový` (new) marker is the only exception and is deliberately explicit: you
have to write it, not rely on it.

> A pattern also covers files that don't exist yet. `src/*.py` in one chip
> therefore collides with `src/new.py  # nový` in another, even though that file
> doesn't exist yet.

### Dependencies and waves

File disjointness is not enough when one chip builds the foundation the others
need before they can start (the skeleton of a repo, lookup tables that
migrations reference). That is what `zavisi_na:` (depends on) in the frontmatter
is for — a list of chips that must be `merged` first.

Chips with the same dependency depth form a **wave** and run in parallel:

```
wave 0:  00                    ← serial, blocks everything
wave 1:  01                    ← foundation for the migrations
wave 2:  02  03  04  07  09    ← in parallel, independent
wave 3:  05  06  08  10        ← build on wave 2
```

`chip_lint.py` checks that a dependency exists, is not cyclic, and that a
running chip has its ancestors in the `merged` state. **The width of a wave, not
the number of chips, determines how many windows it makes sense to open** — ten
chips in four waves means at most five windows at once.

### Chip ceiling

| Metric | Recommendation | Why |
|---|---|---|
| issues | 10–20 | more won't fit into one context |
| files touched | ~15 | above that the chance of a collision with another chip grows |
| run time | a few hours | a longer run = a bigger loss on failure |
| **independent fixes with proof** | **~2–3** | four hit the ceiling of a single response |

When the ceiling doesn't fit, slice the chip. Two smaller chips are always
better than one that doesn't finish.

**Besides consumption there is a second limit: assignment density.**
Consumption (~100k tokens per chip) watches itself and shows up as a warning.
Density doesn't — a chip with four independent fixes, each with a regression
proof, hits the limit of **one response** and dies without warning in the
middle of the work (chip 10, wave 4).

**Slice by the nature of the work, not by the number of issues.** Chip 10 was
split into "where the tool takes its input from" (parsing) and "when it should
reject" (decision rules) — not into "the first two findings" and "the other
two". Mechanical splitting forces the agent to switch between two modes of
reasoning inside one chip, which is exactly the density the slicing is meant to
avoid.

**Beware of naming sliced chips.** The expected choice `10a`/`10b` would break
the gate here: both the hook and `chip_gate` match the chip number as `(\d+)`,
so branch `ai/chip-10a/…` is recognised as **chip 10** and someone else's brief
gets verified. New numbers at the end of the sequence are safer — naming adapts
to the tool, because the tool is the enforcement point.

---

## 3. Isolation: a worktree, not a folder

The most common mistake is to run N sessions over the same working tree. The
result isn't git conflicts (you'd at least see those) but **silently lost
changes** — two sessions read a file, both write it, the second write wipes out
the first.

The fix is `git worktree`: one repository, N independent checkouts.

```bash
git worktree add ../repo-chip-01 -b ai/chip-01/parser-refactor
```

Every window works in its own folder, on its own branch, with its own index.
Merging happens at the end and git handles any conflict normally and visibly.

Claude Code has `EnterWorktree` for this (for a session) and subagents take the
`isolation: "worktree"` parameter. `tools/chip_run.py` does it for you.

**A dependent chip branches from its predecessor, not from HEAD.** When chip B
builds on the work of chip A that isn't merged yet, branching from HEAD would
take away exactly what it is supposed to build on:

```bash
python tools/chip_run.py 02 --od ai/chip-01/base    # --od = --from
```

The agent of such a chip gets an extra sentence in its assignment: someone
else's unfinished code lies under its work — **it neither edits nor fixes it**;
a finding in it belongs in the Log. Without that it would treat the
predecessor's unfinished code as part of the main branch and "repair" it,
producing exactly the collision between packets that chips exist to prevent.
Lint lets a dependent pair through and only reminds you of the merge order — a
`gated` ancestor is a warning, a `blocked` or unfinished ancestor remains an
error.

**Greenfield: the first chip in a project that doesn't exist yet.** A freshly
`init`ed repo has no `HEAD` for `worktree add` to branch from, and lint fails
on the non-existent repo and on the claimed paths. Both are solved by an
explicit declaration, not a softer default:

```yaml
greenfield: ano      # in the brief's frontmatter — the repo is yet to be created
```

```bash
python tools/chip_run.py 01 --zaloz-repo    # git init + empty root commit
```

Over a repo that already has history `--zaloz-repo` **does nothing** and says
so; `greenfield: ano` is reported there as a stale flag to delete. The check of
the path *shape* (relative, no `..`) is never switched off, flag or not — it is
the input to the disjointness comparison, so softening it would mean softening
disjointness.

> **Cleanup:** `python tools/chip_run.py 01 --uklid` — **only after the
> merge**, otherwise you accumulate dozens of dead checkouts. The tool refuses to
> clean up an unmerged branch (see below); consciously abandoning a chip is
> `--uklid --presto` (cleanup, force).

A worktree isn't just a working folder, it is **the only place where a chip's
gate can run**. That's why the tools treat it as a tree owned by somebody else
in each phase:

| Phase | Who writes into the worktree | What must NOT touch the main tree |
|---|---|---|
| before launch | `chip_run.py` (creates it, rewrites `stav:`) | nothing — the main tree stays clean |
| chip running | the agent (code, Log, checkboxes) | the agent doesn't touch the main tree at all |
| merge | git | — |
| after merge | `chip_run.py --uklid` (deletes it) | — |

From this also follows **which copy of the brief `--stav` may rewrite**: the one
in the worktree, not in the main tree. The brief is a versioned file, so the
worktree has its own copy — and writing into the main tree would leave an
uncommitted change there in a file the merge rewrites. `git merge` refuses such
a merge (`Your local changes … would be overwritten`). The rule "don't touch
the brief of a running chip" applies to tools too, not just to people.

---

## 4. The gate: where quality is decided

The sentence "be thorough and check everything carefully" has no enforcement
power. It is a wish. Only something that **fails on its own** when something is
wrong has power.

Gate = a sequence of commands that must pass, otherwise nothing is merged:

```bash
pytest -q                    # tests
python -m build              # build
python smoke_test.py         # smoke test against real data
```

Three levels of enforcement, weakest to strongest:

| Level | Mechanism | Can it be bypassed? |
|---|---|---|
| instruction in the prompt | "check it" | yes, even unintentionally |
| skill (`/chip`, `/ship`) | a procedure the agent loads | yes, when it doesn't call it |
| **hook** | the harness runs it itself before the merge | **no** |

The third level has been in place since 2026-07-26: `tools/hook_chip_gate.py`
hangs on PreToolUse and **rejects `git merge` of a chip branch until the gate
is green**. It has no command list of its own — it takes the "Ověření (brána)"
(verification / gate) section from the brief of the chip whose branch is being
merged. So it enforces exactly what the chip promised itself, and works in any
repo.

To stay out of the way elsewhere its scope is narrow — the hook speaks up only
when everything holds: the command runs `git merge`, the merged branch is
`ai/chip-NN/...` (or the older `chip/NN-...`), and chip briefs can be found for
the target repo. Otherwise it silently lets the command through.

**Briefs don't have to live in the repo.** As long as the `chips/` directory
was the only signal, two things that shouldn't be mutually exclusive were: a
hard gate and zero footprint in a third-party repo. Whoever kept the briefs
elsewhere (`--dir`, typically a client repo) got a hook that **silently let red
merges through** — and the gate looked like it worked. So there are three
signals, from the most specific to the most general:

| Signal | When it applies | What it's for |
|---|---|---|
| `chips/` in the repo | the directory exists | the default case, your own projects |
| `.chips` marker | the file exists; its first non-empty line is the path to the briefs | a repo where the method must leave no trace |
| env `CHIPS_DIR` | points to the briefs of **this** repo (`repo:`) | a session over one project |

The marker just has to stay untracked (`.git/info/exclude`) — one dotfile is a
footprint you can live with even in a third-party repo; a directory with a dozen
briefs isn't. And because nobody creates the marker by accident, **a broken
marker rejects** instead of staying silent: a typo in the path would otherwise
switch off the gate exactly where the user explicitly wanted it.

With `CHIPS_DIR` it is the other way round — it is a global variable, not a
registration of a specific repo. It is accepted only when it contains a brief
that claims this repo; otherwise a variable set for project A would decide
merges in project B.

**The branch is taken from the argument after `merge`, not from anywhere in the
command.** A compound command `git branch -d ai/chip-04/x && git merge
ai/chip-05/y` would otherwise verify the gate of chip 04 and let the merge of
chip 05 through. The same holds for `git -C` — only the one belonging to the
merge itself is taken. For an octopus merge (`git merge A B`) the gate of
**every** branch must pass.

**When there is nowhere to verify the gate, the hook rejects** — it doesn't
verify a substitute tree:

| Situation | Why reject |
|---|---|
| the chip's worktree doesn't exist | a gate in the main tree would verify code **without the chip's changes** and return a false green |
| there are uncommitted changes in the worktree | the merge takes the committed tip, so the gate would measure a different state than the one being merged |
| the state of the worktree can't be determined | not knowing what is in the tree is, for the gate's purposes, the same as not having it |

Practical consequence: **worktree cleanup belongs after the merge.** Whoever
cleans up earlier doesn't merge — and the only way out is to bypass your own
gate. That's why it isn't just advice: `chip_run.py NN --uklid` **refuses** to
clean up an unmerged branch (`merge-base --is-ancestor`, so a fast-forward
passes too). An abandoned chip is cleaned up consciously via `--uklid --presto`.

You run the same gate by hand with `python tools/chip_gate.py NN` — **also in
the chip's worktree**, not in the main tree. Until 2026-07-28 the CLI did the
opposite, silently: the gate of chip 18 reported green over the main tree with
454 tests, while the worktree had 481. The 27-test difference was exactly the
work the gate was supposed to decide on. When `worktree:` is missing or empty,
the tool now **fails** — the silent fallback to the main tree was the whole
defect.

**While a wave runs, `chip_status.py` lies to you.** It reads the briefs in the
main tree, where nothing moves while a chip runs — checkboxes and files change
in the worktree. The live state comes from `python tools/chip_dashboard.py`: it
reads from every chip's worktree and from git, i.e. from hard sources, not from
what the agent wrote in its summary. In wave 6 the difference was 37 ticked
issues and five states.

**When the gate fails, the chip doesn't end in a merge but in an open PR.**
That is the whole difference between "autonomous" and "unsupervised".

---

## 5. Definition of done

It must be verifiable by a command, not by an opinion. The test:

| ❌ not measurable | ✅ measurable |
|---|---|
| "the parser is refactored" | "`pytest tests/test_parser.py` passes, `parser.py` < 300 lines" |
| "the code is cleaner" | "`ruff check` reports nothing" |
| "it works" | "the smoke test on `data/sample.xlsx` returns 42 rows" |

When the DoD can't be written as a command, the chip isn't ready to launch yet.

### Measurable ≠ strong

A command is a necessary condition, not a sufficient one. **A DoD of the form
"the tool returns 0 errors" is weak if it doesn't prove that the check ran at
all.** Chip 11 had "lint over the ERP briefs returns 0 errors" in its DoD; it
returned 0 before the fix too, because all 11 briefs were in the `draft` state
and the path check doesn't run on those. The agent discovered this itself and
replaced it with a direct measurement of the fixed function's return value.

The strength test: **would this DoD pass on the broken version too?** If yes, it
measures the presence of a tool, not behaviour. A strong DoD compares **a
specific value before and after**, not an exit code.

---

## 6. Escalation — what a chip must not decide on its own

Mark up front what is **T3** (critical). Typically:

- a change to a public API or a data format
- a schema migration / an irreversible operation on data
- anything in `patients/` (sensitive data) and in company projects
- a new dependency, a licence change
- a security decision

When a chip hits T3, **it stops and opens a PR with a question**. It doesn't
guess, it doesn't vote.

### Why not "let it consult another model"

It's tempting: when unsure, let Codex/Gemini/Grok decide and carry on. It
doesn't work, because:

- those models **don't see your repo, its history or earlier decisions**;
- agreement of three models isn't truth, it's the average of three guesses;
- the result then gets merged **without your knowledge** — the uncertainty
  vanished from the log.

The second opinion in code is **tests and the build**, not another model.
Cross-model consultation makes sense for the *design* (before writing starts),
not as a substitute for your decision.

---

## 7. Chip lifecycle

```
draft ──► ready ──► running ──► gated ──┬─► merged
                                        └─► blocked (PR + question)
```

| State | Means |
|---|---|
| `draft` | the brief is being written, boundaries aren't certain yet |
| `ready` | brief filled in, `chip_lint.py` clean → may be launched |
| `running` | running in a worktree |
| `gated` | work finished, waiting for the gate |
| `merged` | gate green, merged, worktree cleaned up |
| `blocked` | hit T3 or the gate failed → waiting for you |

Keep the state in the brief's header (`chips/NN-*.md`, field `stav:`), not in
your head.

---

## 8. Recommended ramp-up

1. **One chip entirely by hand**, so you know what good output looks like and
   how much it costs.
2. **Three chips in parallel** — this is where it shows whether the slice fits
   and where it grinds.
3. **Only then ten.** Ten windows at max effort plus subagents is enormous
   consumption; you'll hit the limits before the results.

Between steps always evaluate: how many chips ended `blocked`, how many times
the gate caught an error, how many times you had to step in. When there are
many interventions, the fault is almost always in the **slice** (chips stepping
on each other) or in the **DoD** (it wasn't measurable) — not in the model.

---

## 9. What the pilot showed (2026-07-26)

The first live run: six chips in two waves over this repo, each in its own
worktree with its own window. Result: 6/6 merged, zero `blocked`, zero edits
outside the claimed files, zero merge conflicts, 0 → 201 tests.

**What worked as designed**

- **Slicing by files holds.** Not one of the six agents reached outside its
  claim, although they had the opportunity (they lacked functions they had to
  write locally). Instead they wrote it in the Log — five findings went
  upstream.
- **Escalation instead of guessing.** All six independently refused to switch
  `stav:` in the frontmatter: a chip's mandate is the Log and the checkboxes,
  the state is the orchestrator's decision.
- **`expectedFailure` as a channel for findings.** A chip that found a bug in
  code outside its claim didn't fix it — it pinned it with a test marked
  `@unittest.expectedFailure` and sent it upstream. The bug thereby survived the
  merge **visibly**, and the fixing chip had to un-mark it, otherwise the suite
  would fail on `unexpected success`.

**What had to be added**

| Finding | Consequence for the method |
|---|---|
| The brief is a file shared by the orchestrator and the chip | The orchestrator **must not** edit the brief of a running chip. Switch the state before launch or after the merge. |
| `git worktree add` branches from HEAD, not from the working tree | Commit work in progress **before** creating the worktree, otherwise the chip gets old code. |
| Lint checked claims against the main tree, not the worktree | Path existence must be verified where the chip really works. |
| File disjointness ≠ disjointness of consequences | A chip may own a shared base (`chip_common.py`) but not rename things in it. A boundary the path list can't express, write in words in the Escalation section. |
| Green in isolation ≠ green together | After **every** merge run the whole suite on the main branch, not just the chip's gate. |

**Consumption.** One chip = roughly 80–110k tokens (6 chips ≈ 550k). That is
a hard ceiling on wave width: ten chips at once is half a million tokens in one
wave, before you verify anything.

### Second pilot: a third-party repo and the reviewer role (2026-07-26)

Seven chips over a live company repo (0 → 235 tests). It brought two things
the first pilot couldn't show.

**A reviewer is to the gate what a worktree is to isolation.** The gate is only
as strict as the tests — and those are written by the same model that wrote the
code. So we deployed **an independent agent that didn't write the code**, with a
single mandate: report, don't fix. Its method is **mutation testing** — break
the code and measure how many mutations the suite kills. Result: in chip 05 it
found two substantive gaps, in chip 06 a silent failure (`exit 0` even though
not a single file could be read) and three unlocked boundaries. The gate caught
none of it, because everything was consistent *inside* the author's reasoning.

The `chip_review.py` tool does the mechanical part (the scope of changes
against the claim, tests without asserts, the DoD against the gate commands) and
`--zadani` (assignment) prints the brief for the agent. **It gives no verdict** —
it collects material.

**Where to stop.** The chain chip → review → chip → review → chip is serial by
nature and took over an hour. Each layer found something new, but the yield
falls: the third chip was already half just locking in correct behaviour. It is
cheaper to **bundle the review findings into one chip** than to handle them one
by one.

**Dependent chips went unaddressed for a long time.** A chip that builds on an
unmerged predecessor has to branch from its branch — `chip_run.py` could only
branch from HEAD, so the worktree was created by hand, and `chip_lint` reported
the unmet dependency as an error. Solved in wave 5 (2026-07-28): `chip_run.py
--od <ref>` and the distinction of ancestor states in lint, see §3. Merging the
descendant still brings the predecessor's work too — that's a property, not a
defect, and that's why merging happens in order.

**`chip_run.py --stav` violated its own rule.** It rewrote `stav:` in the brief
in the main tree while the agent edited the same file in the worktree → the
merge ended in a conflict. The rule "don't touch the brief of a running chip"
must apply to tools too, not just to people. Fixed 2026-07-28: the write goes to
the copy in the worktree, the main tree stays clean (§3).

**Limits of the pilot.** CHIPS on itself is a favourable case — a small repo,
clean Python, no external dependencies, issues written by the same person who
sliced them. Before you trust it on a big repo, repeat it on someone else's
code.

### Wave 4: what survives an interruption (2026-07-27)

The wave fixed 10 findings from an external code review. All three agents died
in the middle of the work on account limits — **not on the code**. After the
reset it was completed in full: 10/10 findings, 366 → 413 tests, 4/4 green
gate.

**Isolation held even through a triple crash.** The main tree stayed clean and
untouched; the work of two agents was in git on their branches and could be
finished. The chip that hadn't started was simply re-sliced and launched again.

**Before you put an agent on a "half-done" chip, read the diff — not the note
about it.** The rescue note claimed nobody knew what was done in chip 12; in
fact it was completely finished including the Log and the ticked DoD. Chip 11
had all four fixes coded and covered by 13 tests. Had I trusted the note, the
agents would have rewritten finished work.

**A chip sees things the assignment doesn't know.** The agent of chip 13,
while fixing "take the branch from the argument after `merge`", discovered a
finding the code review had missed: an octopus merge (`git merge A B`) verified
the gate of the first branch only and let the second one through unchecked. It
followed from the fix — once branches are taken from the arguments, it's
visible that there can be several. **A good assignment opens a view, it
doesn't just delimit work.**

**Worktree cleanup belongs after the merge.** Since chip 14 the hook rejects a
merge when the chip's worktree is missing — there is nowhere to verify the
gate. Whoever cleans up earlier doesn't merge. Since 2026-07-28 `--uklid` itself
guards this too: it refuses to clean up an unmerged branch.

**A rule that holds only in documentation gets broken by a tool.** All three
fixes of 2026-07-28 (the cleanup order, the target of the `--stav` write, the
brief lookup) had the same shape: the rule was written correctly in the
methodology and the tool violated it. When a rule appears in the project, ask
straight away **which code can violate it** — not just who should read it.

Wave 6 added three more cases of the same pattern: a gate run by hand measured
the main tree, `chip_status.py` showed dead data about running chips, and the
reviewer reported as a finding something that is the normal state. **The most
common form of this defect is "the tool reads the main tree, but the truth is in
the worktree".** It appeared four times in one day in four different files.

### A false signal is a defect even when it is true

A tool that reports noise trains a reader who skips it — and that reader then
misses the report that is genuine. Chip 15 dealt with this for placeholders in
lint, chip 21 for the reviewer. Both ended the same way: **the solution isn't
to mute the message but to narrow it to the cases where it really hurts**, or
to rephrase it as what it really is.

Hence a dividing rule worth keeping in every tool of the project:

| | means | belongs where |
|---|---|---|
| **finding** | "this is wrong" | the tool has complete data and can decide |
| **question** | "verify this yourself" | the tool has nothing to decide with, but knows where to look |
| **data** | an inventory | neither — it is material, not a verdict |

---

## 10. Antipatterns

| Antipattern | What happens |
|---|---|
| N windows over one working tree | silently lost changes |
| "be autonomous and thorough" without a gate | the model confirms to itself that it checked |
| slicing by topic instead of by files | collisions, the last merge wins |
| model voting instead of escalation | the uncertainty vanishes from the log, nobody knows about it |
| a chip without a measurable DoD | "done" can't be verified, you have to read everything |
| ten chips straight away without a pilot | you hit the limits and don't know why |
