# CHIPS

**A methodology for parallel development with AI agents.** You slice the work
into self-contained packets ("chips"), each one gets its own isolated window,
runs autonomously, and may be merged only after it passes an automated gate.

> **CHIP** = **C**ontained **H**ands-off **I**ssue **P**acket
> (a backronym coined in this project — nobody outside it uses the word, see
> [docs/konverzace-2026-07-25.md](docs/konverzace-2026-07-25.md), in Czech)

> 🇨🇿 Czech version: [README.cs.md](README.cs.md) · Methodology in English:
> [docs/methodology.md](docs/methodology.md)
>
> **Language note.** The methodology and this README are available in English.
> The tools' command-line flags, messages and identifiers, the chip briefs in
> `chips/` and the pilot write-ups in `docs/` are in Czech — they are the
> historical record of the pilots that shaped the method. A glossary of the
> flags you will meet is at the end of this file.

---

## The problem it solves

You have 100 issues and one Claude. Serially that takes weeks. Run ten windows
in parallel and you get three new problems:

1. **Ten sessions writing into one working tree** → they overwrite each other's
   files. Not a git conflict — silently lost changes.
2. **Autonomous merge without a gate** → "I checked it thoroughly" is a claim
   the model makes about itself, not a verified fact.
3. **Unclear boundaries** → two packets touch the same file and the last one
   wins.

CHIPS is a set of rules that fixes these three things *before* you open the
first window.

---

## Six rules

| # | Rule | Why |
|---|---|---|
| 1 | **One chip = one git worktree = one branch** | isolation at the filesystem level, not the trust level |
| 2 | **Two chips must never touch the same file** | the only criterion the work is sliced by |
| 3 | **Merge only through a green gate** (tests + build + smoke) | autonomy is granted by verification, not by a prompt |
| 4 | **Definition of done written up front and measurable** | "done" must be checkable by a command, not an opinion |
| 5 | **Escalate instead of guessing** — anything T3 ends as a PR + a question | a model that isn't sure must not merge |
| 6 | **A chip has a ceiling** (≤ 20 issues, ≤ ~15 files) | a bigger packet won't finish in one context |

Rules 1 and 3 are not optional. Without them it isn't orchestration, it's
managed chaos whose output you still have to read in full.

---

## Quick start

**Requirements:** Python 3.10+ and git. The tools are stdlib only; `md2html.py`
additionally needs `pip install markdown`.

```bash
# 1) create a chip from the template
python tools/chip_new.py 01 parser-refactor

# 2) fill in chips/01-parser-refactor.md
#    → mainly: Issues, Files touched, Definition of done, Verification (gate)

# 3) check that chips don't step on each other's files
python tools/chip_lint.py

# 4) run the chip in an isolated worktree
python tools/chip_run.py 01 --dry-run     # show the commands
python tools/chip_run.py 01 --stav        # create worktree + branch, set state to 'running'
python tools/chip_run.py 01 --spustit     # additionally launch Claude Code in the worktree
python tools/chip_run.py 02 --od ai/chip-01/base   # dependent chip: branch from its predecessor
python tools/chip_run.py 01 --zaloz-repo  # greenfield: the repo doesn't exist yet

# 5) overview: who is in which state, what may run in parallel
python tools/chip_status.py          # from the briefs in the main tree
python tools/chip_dashboard.py       # LIVE from the worktrees of running chips (+ --watch)

# 6) verify the gate by hand before merging (the PreToolUse hook runs it once more)
python tools/chip_gate.py 01         # runs in the chip's worktree, not in the main tree

# 7) ONLY AFTER THE MERGE clean up the worktree — earlier and the hook rejects the merge
#    (the tool refuses to clean up an unmerged branch; abandoned chip: --uklid --presto)
python tools/chip_run.py 01 --uklid
```

Without `--spustit` you open the created worktree in a new Claude Code window
yourself and paste in the printed assignment. Details:
[docs/methodology.md](docs/methodology.md).

**In a third-party repo that must stay clean**, keep the briefs elsewhere
(`--dir <path>` or `CHIPS_DIR`) and register the repo with the gate through a
single untracked file:

```bash
echo /path/to/briefs > <repo>/.chips
echo .chips >> <repo>/.git/info/exclude
```

Without that signal the hook cannot find the briefs and **silently lets a red
merge through** — the `chips/` directory, the `.chips` marker and `CHIPS_DIR`
are the only three ways to tell it that CHIPS governs this repo.

Two more tools that aren't used every round:

```bash
# slices a ready list of issues (TODO.md, JSON) into chip proposals
python tools/chip_slice.py --todo TODO.md --zapsat chips/

# material for an independent reviewer of a finished chip
python tools/chip_review.py 01
```

---

## Layout

```
CHIPS/
├── chips/              # briefs of individual packets (TEMPLATE.md + 01-*.md …)
├── docs/
│   ├── methodology.md  # the whole method in English: slicing, isolation, gate, escalation
│   ├── metodika.md     # the same, in Czech (source of truth)
│   ├── konverzace-2026-07-25.md   # origin of the project, the original discussion (Czech)
│   └── vlna-4-preruseno.md        # what survives an interrupted wave (Czech)
├── tests/              # 695 tests, stdlib unittest
└── tools/
    ├── chip_new.py     # creates a chip from the template
    ├── chip_slice.py   # slices a list of issues into chip proposals
    ├── chip_lint.py    # file disjointness + existence of claimed paths
    ├── chip_run.py     # worktree + branch + optionally launches a window
    ├── chip_status.py  # overview of chips, waves and states (from the main tree)
    ├── chip_dashboard.py  # live board: reads the worktrees of running chips and git
    ├── chip_gate.py    # runs a chip's gate in its worktree
    ├── hook_chip_gate.py  # PreToolUse hook: merge only after a green gate
    ├── chip_review.py  # material for an independent reviewer
    ├── chip_common.py  # brief parser (shared base)
    └── md2html.py      # .md → .html (workspace convention)
```

Tests: `python -m unittest discover -s tests -v`

---

## Status

The methodology has been validated by **two pilot runs and one repair wave**.

| | result |
|---|---|
| chips in total | 24/24 merged, 0 `blocked` |
| tests | 0 → **695** |
| edits outside the claimed files | 0 |
| merge conflicts | 0 (one caused by a tool, not by a chip) |
| findings escalated instead of silently fixed | 10 |

**Pilot 1 — on this repo (2026-07-26).** Six chips in two waves, each in its
own worktree with its own window, merged only after a green gate.

**Pilot 2 — a third-party repo (2026-07-26).** Seven chips, 0 → 235 tests,
7 fixes in the write path of a reporting tool. That the main tree stayed
untouched is documented by a manifest of 6037 files before and after.

**Wave 4 — external code review (2026-07-27).** 30 agents with adversarial
verification found 10 defects in CHIPS's own tools, including four ways to
silently bypass the gate. All 10 fixed; the course and lessons are in
[docs/vlna-4-preruseno.md](docs/vlna-4-preruseno.md) (Czech).

**Wave 5 — subagents instead of windows (2026-07-28).** Three chips in
parallel, for the first time handled by subagents in one session instead of
three windows. 3/3 merged, 0 edits outside the claim, 454 → 523 tests. The test
count after every merge added up exactly (476 → 496 → 523), so no collision
arose between the chips. Two findings went upstream instead of being silently
fixed.

**Wave 6 — five chips at once (2026-07-28).** 5/5 merged, 0 edits outside the
claim, 523 → 676 tests. Again the count added up after every merge
(548 → 562 → 585 → 590 → 676). The wave fixed three defects in the project's own
tools, and each had the same shape: **the rule was written correctly and the
tool violated it.** `chip_dashboard.py` was born and immediately proved why it
was needed — over five running chips it reported 177/192 issues done where
`chip_status.py`, reading the main tree, saw 140/192.

What this means for your own slicing is in
[docs/methodology.md](docs/methodology.md), section "What the pilot showed".

**Next step:** deployment on a real company project.

---

## Glossary of Czech flags and terms

The tools keep their original Czech interface so that the briefs, tests and
pilot records stay consistent. What you will meet:

| Czech | English |
|---|---|
| `--stav` | `--state` — set the brief's state to `running` when the worktree is created |
| `--spustit` | `--launch` — also start Claude Code in the worktree |
| `--od <ref>` | `--from <ref>` — branch from a predecessor instead of HEAD |
| `--zaloz-repo` | `--init-repo` — greenfield: `git init` + empty root commit |
| `--uklid` / `--presto` | `--cleanup` / `--force` — remove the worktree (only after merge / abandon consciously) |
| `--zapsat` | `--write` — write the sliced chips into a directory |
| `--zadani` | `--assignment` — print the brief for the reviewer agent |
| `--dir` | directory with the briefs (when they don't live in the repo) |
| `stav:` | `state:` — frontmatter field (`draft`, `ready`, `running`, `gated`, `merged`, `blocked`) |
| `zavisi_na:` | `depends_on:` — list of chips that must be `merged` first |
| `worktree:` / `vetev:` / `repo:` | worktree path / branch / target repo |
| `greenfield: ano` | `greenfield: yes` |
| `Dotčené soubory` | "Files touched" — the section with the chip's file claim |
| `Ověření (brána)` | "Verification (gate)" — the commands the hook runs before merge |
| `Definition of done` | same |
| `Eskalace` | "Escalation" — what the chip must not decide by itself (T3) |
| `Log` | same — the chip's running record |
| `# nový` | `# new` — marks a claimed file the chip will create |
| `vlna` | wave — chips with the same dependency depth, run in parallel |
| `brána` | gate |
| `nález` / `otázka` | finding / question (see methodology §9) |

---

## License

[MIT](LICENSE) © 2026 Richard Faldyna
