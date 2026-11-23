"""Install the CHIPS review loop (chip-critic, chip-judge, /chip-review-loop) for Claude Code.

The sources live in `integrations/claude-code/` of this repo. Claude Code discovers subagents
and skills in `~/.claude/` (every session on this machine) or in `<project>/.claude/` (one
project). This tool copies the three files there and replaces the placeholder `{{CHIPS_TOOLS}}`
with the absolute path of this clone's `tools/` directory, so the skill can call
`chip_review.py` and `chip_gate.py` from any project.

Every installed file ends with a stamp line holding the hash of its content. That is how the
tool tells two cases apart that look identical otherwise:
  - an old copy nobody touched (stamp matches the body) -> updated silently after `git pull`
  - a copy someone edited (stamp does not match)       -> refused unless you pass --force
`--check` writes nothing and exits 1 when a file is missing, old or edited.

Usage:
    python tools/chip_install.py                    # install / update in ~/.claude
    python tools/chip_install.py --target <dir>     # install into <dir> (e.g. <repo>/.claude)
    python tools/chip_install.py --check            # report missing / old / edited files
    python tools/chip_install.py --force            # also overwrite edited files
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "integrations" / "claude-code"
TOOLS_DIR = REPO_ROOT / "tools"
PLACEHOLDER = "{{CHIPS_TOOLS}}"

# Relative paths, identical under the source dir and under the target dir.
FILES = (
    "agents/chip-critic.md",
    "agents/chip-judge.md",
    "skills/chip-review-loop/SKILL.md",
)

MISSING = "missing"
OLD = "old"          # an unedited copy of an earlier source version - safe to update
EDITED = "edited"    # differs from the source and its stamp does not match - someone changed it
CURRENT = "up to date"

STAMP = re.compile(r"\n<!-- chips-install sha256:([0-9a-f]{64}) -->\n\Z")


@dataclass(frozen=True)
class Entry:
    """One managed file: where it goes, what it should contain and its current state."""

    rel: str
    target: Path
    content: str
    state: str


def render(text: str, tools_dir: Path = TOOLS_DIR) -> str:
    """Replace the placeholder with the absolute tools path (forward slashes work everywhere)."""
    return text.replace(PLACEHOLDER, tools_dir.resolve().as_posix())


def normalize(text: str) -> str:
    """Line endings are not a difference worth refusing over (git may convert them)."""
    return text.replace("\r\n", "\n")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stamped(body: str) -> str:
    """The exact text written to the target: the rendered body plus its stamp."""
    body = normalize(body)
    if not body.endswith("\n"):
        body += "\n"
    return f"{body}\n<!-- chips-install sha256:{digest(body)} -->\n"


def is_unedited(text: str) -> bool:
    """True when the file carries a stamp and its body still matches it."""
    text = normalize(text)
    match = STAMP.search(text)
    return bool(match) and digest(text[:match.start()]) == match.group(1)


def classify(target: Path, content: str) -> str:
    if not target.is_file():
        return MISSING
    current = normalize(target.read_text(encoding="utf-8"))
    if current == content:
        return CURRENT
    return OLD if is_unedited(current) else EDITED


def plan(target_dir: Path, source_dir: Path = SOURCE_DIR,
         tools_dir: Path = TOOLS_DIR) -> list[Entry]:
    """Compare every managed file with its rendered source; touches nothing."""
    entries = []
    for rel in FILES:
        source = source_dir / rel
        if not source.is_file():
            raise FileNotFoundError(f"source file missing: {source}")
        content = stamped(render(source.read_text(encoding="utf-8"), tools_dir))
        target = target_dir / rel
        entries.append(Entry(rel, target, content, classify(target, content)))
    return entries


def install(target_dir: Path, force: bool = False, check: bool = False,
            source_dir: Path = SOURCE_DIR, tools_dir: Path = TOOLS_DIR,
            out=print) -> int:
    """Install (or check) the managed files. Returns the process exit code."""
    try:
        entries = plan(target_dir, source_dir, tools_dir)
    except FileNotFoundError as exc:
        out(f"! {exc}")
        return 1

    written = refused = 0
    for entry in entries:
        if check or entry.state == CURRENT:
            out(f"  {entry.state:<11} {entry.rel}")
            continue
        if entry.state == EDITED and not force:
            out(f"  {entry.state:<11} {entry.rel}  (changed by hand - not overwritten, use --force)")
            refused += 1
            continue
        entry.target.parent.mkdir(parents=True, exist_ok=True)
        entry.target.write_text(entry.content, encoding="utf-8", newline="\n")
        out(f"  written     {entry.rel}" + ("  (was an older version)" if entry.state == OLD else ""))
        written += 1

    problems = [e for e in entries if e.state != CURRENT]
    if check:
        out(f"\n  {target_dir}: {len(entries) - len(problems)}/{len(entries)} up to date")
        if problems:
            out("  run: python tools/chip_install.py" + _target_flag(target_dir))
        return 1 if problems else 0

    out(f"\n  {target_dir}: {written} written, {refused} refused, "
        f"{len(entries) - written - refused} already up to date")
    if written:
        out("  restart the Claude Code session, then check /agents for chip-critic and chip-judge")
    return 1 if refused else 0


def default_target() -> Path:
    return Path.home() / ".claude"


def _target_flag(target_dir: Path) -> str:
    return "" if target_dir == default_target() else f' --target "{target_dir}"'


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Install the CHIPS review loop (chip-critic, chip-judge, "
                    "/chip-review-loop) into ~/.claude or a project's .claude.")
    ap.add_argument("--target", metavar="DIR",
                    help="directory to install into (default: ~/.claude)")
    ap.add_argument("--check", action="store_true",
                    help="write nothing; exit 1 when a file is missing, old or edited")
    ap.add_argument("--force", action="store_true",
                    help="also overwrite files that were changed by hand")
    args = ap.parse_args(argv)
    if args.check and args.force:
        ap.error("--check and --force exclude each other")
    target = Path(args.target).expanduser().resolve() if args.target else default_target()
    return install(target, force=args.force, check=args.check)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
