---
name: chip-review-loop
description: Independent review loop for one finished CHIPS chip - machine evidence from chip_review.py, then a fresh chip-critic subagent, then a fresh chip-judge subagent, repeated for at most 3 rounds until the judge says COMPLETE, CONTINUE runs out or a human decision is needed. Use when the user says "/chip-review-loop NN", "review chip NN", "pust na chip critica a judge", or a chip is gated and should be reviewed before its merge. It never merges and never switches a brief's status.
---

# CHIPS review loop

Tools of this CHIPS clone: `{{CHIPS_TOOLS}}`
(if the line above shows a placeholder in double curly braces instead of a path, this file
was not installed by `chip_install.py` - use the `tools/` directory of the CHIPS repo instead).

Invocation: `/chip-review-loop NN [--dir <briefs dir>] [--max-rounds N]` (default 3, never more
than 3 without the user saying so). `--dir` is needed whenever the briefs are not in `./chips`
of the current repo; pass the same `--dir` to every CHIPS tool below.

The loop decides one thing: whether a chip goes back for fixes. The merge stays with the gate,
the PreToolUse hook and the human. Nothing in this skill merges, pushes, switches `stav:` in
a brief, or touches a file outside the chip's claim.

## 0. Resolve and check preconditions
1. `python {{CHIPS_TOOLS}}/chip_run.py NN --dry-run [--dir D]` - read the worktree path and the
   branch from the printed assignment. The brief path is printed there too.
2. The worktree must exist and be committed: `git -C <worktree> status --porcelain` prints
   nothing. Otherwise stop: the review would measure a state that is not the one being merged.
3. `python {{CHIPS_TOOLS}}/chip_gate.py NN [--dir D]` must be green. A red gate is not a review
   question - stop and report it; the chip fixes the gate first.
4. `base` = `git -C <worktree> merge-base HEAD <main branch>`, where the main branch is the
   branch checked out in the chip's `repo:` (`git -C <repo> rev-parse --abbrev-ref HEAD`).

## 1. Run directory (outside the repo, survives cleanup)
`<common>` = `git -C <worktree> rev-parse --path-format=absolute --git-common-dir`.
Run directory: `<common>/chips-review/NN/`. It is inside `.git`, so it is never committed and
survives `chip_run.py --uklid`. The round number K = number of existing `round-*-judge.json`
files + 1, so an interrupted loop resumes where it stopped. Write `history` from those files.

## 2. One round
1. **Evidence:** `python {{CHIPS_TOOLS}}/chip_review.py NN --repo <worktree> --commit <base>..HEAD [--dir D]`
   -> save the full output to `round-K-evidence.txt`. If it exits 1 (a file outside the claim -
   the one hard rule it enforces), do not call the critic: verdict ESCALATE, go to step 4.
2. **Critic:** start a fresh subagent `chip-critic` (if that agent type is missing, a
   general-purpose subagent with the full text of `chip-critic.md` as its instructions). Give it
   only: `brief`, `worktree`, `base`, `evidence` (the file path), `previous_findings` (path of
   `round-(K-1)-critic.json` or "none"). Never your own opinion of the chip. Save its JSON to
   `round-K-critic.json`.
3. **Clean-tree check (machine, not trust):** `git -C <worktree> status --porcelain` must print
   nothing and `git -C <worktree> rev-parse HEAD` must equal the HEAD from before the critic.
   If not, restore with `git -C <worktree> checkout -- .` only when every changed path is a
   tracked file the critic mutated; otherwise stop and ask the user. Record `worktree_clean: false`
   for the judge either way.
4. **Judge:** start a fresh subagent `chip-judge` (fallback as above). Give it `brief`, `worktree`,
   `base`, `evidence`, `critic` (the JSON path), `round` = K, `max_rounds`, `history`. Save its
   JSON to `round-K-judge.json`.
5. **Queue:** append the judge's `queue` items (class C) to `<common>/chips-review/NN/queue.md`.

## 3. Act on the verdict
- **COMPLETE** - report: chip NN passed review in K rounds; it is ready for
  `chip_gate.py NN` and the merge by the orchestrator. Do not merge.
- **CONTINUE** - the accepted A/B findings (verbatim, nothing else) go to whoever owns the chip:
  its own session in the worktree, or you when the user asked you to fix it. Fixes stay inside
  the claim, add or change a test that fails without the fix, end with a commit, and the gate
  must be green again. Then run the next round. Do not fix rejected findings or the queue.
- **ESCALATE / IMPOSSIBLE** - stop. Tell the user the judge's reason and `escalate_to_human`
  in one or two sentences each. Suggest the orchestrator set the brief to `blocked`; do not set
  it yourself.

## 4. Caps (stop conditions, enforced by you, not by the judge alone)
- at most `max_rounds` rounds (default 3)
- the worktree HEAD equals the previous round's -> ESCALATE (no progress)
- a finding accepted in an earlier round comes back in the critic's `previous` list with status
  `persists` or `regressed` -> ESCALATE (ids are never reused, so check the status, not the id)
- `chip_review.py` exits 1 -> ESCALATE without a critic
- each subagent gets a turn cap in its prompt: at most 20 turns

## 5. Log and report
During the loop, append one line per round to `<common>/chips-review/NN/log.md`, never to the
brief: an uncommitted edit of a tracked file would fail the next clean-tree check.
`review round K: critic N A / M B / P C, judge <verdict>, accepted <ids>`.
When the loop ends (any verdict), add **one** row summing up the rounds to the Log of the brief
in the worktree (the chip's mandate; `stav:` unchanged) and commit it on its own:
`git -C <worktree> commit -m "chip NN: Log - review <verdict>" -- <brief>`. The worktree is clean
again, which the gate and the merge hook require.
Finish with a short report to the user: verdict, rounds, accepted and rejected findings, and
where the queue for a follow-up chip is.
