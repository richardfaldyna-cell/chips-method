"""Deploy the CHIPS method into a repository with one command.

Deploying CHIPS by hand is four steps (README, "Deploy into your repository"), and the one people
skip is the one that matters: without the registered PreToolUse hook the gate looks like it exists
and never runs.
This tool does all four and then proves the hook rejects:

  1. `<repo>/chips/`               - where the briefs live (created when missing, never emptied)
  2. hook registration             - `<repo>/.claude/settings.json`, merged into what is there;
                                     the path is `$CLAUDE_PROJECT_DIR/<relative path>`, so it works
                                     on every machine with the same folder layout
  3. review loop                   - chip-critic, chip-judge, /chip-review-loop into ~/.claude
  4. self-test                     - the hook must deny `git merge ai/chip-99/does-not-exist` in
                                     that repo and must let an ordinary branch through

Usage:
    python tools/chip_init.py <repo>                  # deploy (idempotent)
    python tools/chip_init.py <repo> --check          # report each step, write nothing
    python tools/chip_init.py <repo> --global         # register the hook in ~/.claude/settings.json
    python tools/chip_init.py <repo> --no-review      # skip the review loop
    python tools/chip_init.py <repo> --hook-timeout 900

The self-test calls the hook script directly. Whether Claude Code actually runs it is only proven
inside a session: restart it in the repo and try `git merge ai/chip-99/does-not-exist`.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import chip_install

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = REPO_ROOT / "tools" / "hook_chip_gate.py"
HOOK_NAME = "hook_chip_gate.py"
MATCHER = "Bash|PowerShell"
DEFAULT_TIMEOUT = 600
# The hook gets `--budget timeout - BUDGET_MARGIN`: it must stop the gate and deny
# before Claude Code kills it, because an expired hook lets the command through.
BUDGET_MARGIN = 60
MIN_TIMEOUT = BUDGET_MARGIN + 30


class InitError(RuntimeError):
    """A step cannot be done safely; the message says why. Nothing further is written."""


def git_root(path: Path) -> Path | None:
    done = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        return None
    return Path(done.stdout.strip()).resolve()


def hook_command(repo: Path, use_global: bool, hook: Path = HOOK,
                 timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str | None]:
    """The command string for the registration, plus a warning when it is not portable."""
    budget = f" --budget {timeout - BUDGET_MARGIN}"
    if not use_global:
        try:
            rel = Path(os.path.relpath(hook.resolve(), repo.resolve())).as_posix()
            return f'python "$CLAUDE_PROJECT_DIR/{rel}"{budget}', None
        except ValueError:            # Windows: repo and CHIPS on different drives
            pass
        warning = ("repo and CHIPS are on different drives - the path is absolute and will not "
                   "work on another machine; consider --global")
        return f'python "{hook.resolve().as_posix()}"{budget}', warning
    return f'python "{hook.resolve().as_posix()}"{budget}', None


def load_settings(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InitError(f"{path} is not valid JSON ({exc}) - fix it first, nothing was changed")
    if not isinstance(data, dict):
        raise InitError(f"{path} does not hold a JSON object - nothing was changed")
    return data


def registered_commands(settings: dict) -> list[str]:
    """Commands of every PreToolUse hook that runs hook_chip_gate.py."""
    found: list[str] = []
    hooks = settings.get("hooks")
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    for block in pre if isinstance(pre, list) else []:
        inner = block.get("hooks") if isinstance(block, dict) else None
        for hook in inner if isinstance(inner, list) else []:
            if isinstance(hook, dict) and HOOK_NAME in str(hook.get("command", "")):
                found.append(str(hook.get("command", "")))
    return found


def registered(settings: dict) -> bool:
    """Is any PreToolUse hook already running hook_chip_gate.py?"""
    return bool(registered_commands(settings))


def with_hook(settings: dict, command: str, timeout: int) -> dict:
    """A copy of the settings with the CHIPS hook appended; every other key is kept."""
    merged = json.loads(json.dumps(settings))
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise InitError("`hooks` in settings.json is not an object - nothing was changed")
    pre = hooks.setdefault("PreToolUse", [])
    if not isinstance(pre, list):
        raise InitError("`hooks.PreToolUse` in settings.json is not a list - nothing was changed")
    pre.append({
        "matcher": MATCHER,
        "hooks": [{
            "type": "command",
            "command": command,
            "shell": "bash",
            "timeout": timeout,
            "statusMessage": "CHIPS: verifying the gate before merge...",
        }],
    })
    return merged


def hook_denies(repo: Path, command: str, hook: Path = HOOK) -> bool:
    """Feed the hook a PreToolUse payload the way Claude Code does and read its decision."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                          "cwd": str(repo)})
    done = subprocess.run([sys.executable, str(hook)], input=payload, capture_output=True,
                          text=True, encoding="utf-8", cwd=str(repo))
    try:
        out = json.loads(done.stdout) if done.stdout.strip() else {}
    except json.JSONDecodeError:
        return False
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"


def init(repo: Path, *, check: bool = False, use_global: bool = False, review: bool = True,
         timeout: int = DEFAULT_TIMEOUT, global_dir: Path | None = None,
         hook: Path = HOOK, out=print) -> int:
    """Run (or check) every step. Returns the process exit code."""
    if timeout < MIN_TIMEOUT:
        out(f"! hook timeout {timeout} s is too short - at least {MIN_TIMEOUT} s "
            f"({BUDGET_MARGIN} s of it is the margin between the gate's budget and the timeout)")
        return 2
    global_dir = global_dir or chip_install.default_target()
    root = git_root(repo)
    if root is None:
        out(f"! {repo} is not a git repository - nothing was changed")
        return 1
    if root == REPO_ROOT:
        out("! this is the CHIPS repo itself - it ships its own registration in .claude/settings.json")
        return 1

    problems = 0

    # 1) briefs directory
    chips = root / "chips"
    if chips.is_dir():
        out(f"  ok       briefs directory {chips}")
    elif check:
        out(f"  missing  briefs directory {chips}")
        problems += 1
    else:
        chips.mkdir()
        out(f"  created  briefs directory {chips}")

    # 2) hook registration
    settings_path = (global_dir if use_global else root / ".claude") / "settings.json"
    try:
        settings = load_settings(settings_path)
    except InitError as exc:
        out(f"! {exc}")
        return 1
    command, warning = hook_command(root, use_global, hook, timeout)
    if registered(settings):
        out(f"  ok       gate hook registered in {settings_path}")
        if not any("--budget" in c for c in registered_commands(settings)):
            out("  note     registered without --budget - the hook uses its default budget "
                "(240 s); keep the hook's timeout above that")
    elif check:
        out(f"  missing  gate hook in {settings_path}")
        problems += 1
    else:
        try:
            merged = with_hook(settings, command, timeout)
        except InitError as exc:
            out(f"! {exc}")
            return 1
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8", newline="\n")
        out(f"  added    gate hook to {settings_path}")
        out(f"           {command}  (timeout {timeout} s)")
    if warning:
        out(f"  warning  {warning}")

    # 3) review loop
    if review:
        lines: list[str] = []
        code = chip_install.install(global_dir, check=check, out=lines.append)
        state = "ok      " if code == 0 else ("missing " if check else "refused ")
        out(f"  {state} review loop in {global_dir} (chip-critic, chip-judge, /chip-review-loop)")
        if code != 0:
            problems += 1
            for line in lines:
                if line.strip():
                    out(f"           {line.strip()}")

    # 4) self-test of the hook against this repo
    denied = hook_denies(root, "git merge ai/chip-99/does-not-exist", hook)
    passed = not hook_denies(root, "git merge some-ordinary-branch", hook)
    if denied and passed:
        out("  ok       hook self-test: chip branch denied, ordinary branch let through")
    else:
        out("  FAILED   hook self-test: "
            + ("chip branch was NOT denied" if not denied else "ordinary branch was denied"))
        problems += 1

    if problems:
        out(f"\n  {problems} step(s) not in place" +
            ("" if check else " - see the lines above"))
        return 1
    if not check:
        tools = (REPO_ROOT / "tools").as_posix()
        out("\n  CHIPS is deployed. Next:")
        out("    1. restart the Claude Code session in the repo (hooks and agents load at start)")
        out("    2. live check in that session: git merge ai/chip-99/does-not-exist  -> must be rejected")
        out(f"    3. first chip: python {tools}/chip_new.py 01 <name> --repo \"{root.as_posix()}\" "
            f"--dir \"{chips.as_posix()}\"")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Deploy the CHIPS method into a repository: briefs directory, gate hook, "
                    "review loop, and a self-test that the hook rejects.")
    ap.add_argument("repo", help="the repository to deploy CHIPS into")
    ap.add_argument("--check", action="store_true", help="report each step, write nothing")
    ap.add_argument("--global", dest="use_global", action="store_true",
                    help="register the hook in ~/.claude/settings.json with an absolute path")
    ap.add_argument("--no-review", dest="review", action="store_false",
                    help="do not install the review loop")
    ap.add_argument("--hook-timeout", type=int, default=DEFAULT_TIMEOUT, metavar="SECONDS",
                    help=f"timeout of the gate hook (default {DEFAULT_TIMEOUT}, minimum "
                         f"{MIN_TIMEOUT}); the hook's own budget is {BUDGET_MARGIN} s less")
    args = ap.parse_args(argv)
    if args.hook_timeout < MIN_TIMEOUT:
        ap.error(f"--hook-timeout must be at least {MIN_TIMEOUT} seconds")
    return init(Path(args.repo).expanduser().resolve(), check=args.check,
                use_global=args.use_global, review=args.review, timeout=args.hook_timeout)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
