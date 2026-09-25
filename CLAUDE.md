# CLAUDE.md — CHIPS

Methodology + tools for parallel development with AI agents. Work is sliced
into self-contained packets ("chips"), each runs in an isolated git worktree
and is merged only after passing an automated gate. Origin and rationale:
`docs/konverzace-2026-07-25.md` (Czech).

**Language:** the tools' flags, messages, identifiers, the chip briefs and the
pilot write-ups are in Czech and stay that way — tests assert on them and the
briefs are a historical record. `README.md` and `docs/methodology.md` are
English; `README.cs.md` and `docs/metodika.md` are their Czech originals. When
a rule changes, change **both** language versions of the methodology.

## What applies here

- **The methodology lives in `docs/metodika.md`** (source of truth) and its
  English translation `docs/methodology.md` — when a rule changes, it changes
  there, not in the README or the template. The README is only a signpost.
- **`chips/TEMPLATE.md` is the source of truth for the brief structure.** When
  a section is added there, add it to `POVINNE` in `tools/chip_lint.py` too —
  otherwise it isn't checked and rots over time.
- **Tools have no external dependencies** except `markdown` (only
  `md2html.py`). Chip briefs are parsed by the mini-parser in
  `chip_common.py`, not PyYAML.
- **Every `.md` has a `.html` next to it** (workspace convention):
  `python tools/md2html.py --all`. Regenerate before committing.
- `chip_lint.py` returns **exit 1 on a finding** — it is a gate, not advice.
  Don't put anything in it that could be "just ignored".
- **Tests: `python -m unittest discover -s tests -v`**, stdlib `unittest`, no
  pytest. Every test builds its own `tempfile` fixture and cleans up after
  itself; `chip_common.CHIPS_DIR` is global state, restore it in `tearDown`.
  A new function without a test doesn't get in — the suite is the only thing
  that keeps the gate honest.
- Supported Python: 3.10+. Don't use APIs newer than that without a fallback
  (e.g. `shutil.rmtree(onexc=…)` is 3.12+, see `chip_run.RMTREE_HANDLER`).

## When you run this project as the orchestrator

- **Commit before `chip_run.py`** — the worktree branches from HEAD, not from
  the working tree.
- **Don't touch the brief of a running chip.** It is a file the agent edits at
  the same time (Log, checkboxes) — rewrite the state before launch or only
  after the merge (`chip_common.prepis_stav`).
- **Verify the gate yourself** (`chip_gate.py NN`), independently of what the
  agent wrote in its summary. The PreToolUse hook runs it once more at merge —
  if you want to bypass it, stop and ask the user. After every merge run the
  whole suite on the main branch — green in isolation is not green together.
- You switch the chip's state, not the agent. The chip's mandate is the Log
  and the checkboxes.

## What to stick to content-wise

The project exists because of three specific failures of parallel development.
When a feature is added, it must serve at least one of them:

1. N sessions over one working tree → silently lost changes (→ worktree)
2. autonomous merge without verification → "I checked it" as the model's own
   claim (→ gate)
3. unclear boundaries between packets → collisions (→ disjointness +
   `chip_lint.py`)

What does **not** belong here: multi-model voting as a substitute for a
decision, automatic merge without a gate, soft rule wording like "be careful".

## Git / security

- **Push only to your own branch and via PR**, never straight to `master`.
- **The repo is public.** Briefs, logs, docs and commits must not contain
  absolute local paths (write `repo:` relative to the briefs directory,
  typically `..`), names of company repos, or secrets. Describe a third-party
  project generically ("a company ERP project"), not by name.
