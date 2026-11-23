"""Tests for tools/chip_init.py - deploying CHIPS into a repo with one command (chip 34)."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import chip_init  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InitCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="chips-init-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.home = self.tmp / "home-claude"
        self.settings = self.repo / ".claude" / "settings.json"
        self.lines: list[str] = []

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_init(self, **kwargs) -> int:
        self.lines = []
        kwargs.setdefault("review", False)
        return chip_init.init(self.repo, global_dir=self.home, out=self.lines.append, **kwargs)

    def chips_hooks(self, path: Path | None = None) -> list[dict]:
        data = json.loads((path or self.settings).read_text(encoding="utf-8"))
        return [h for block in data["hooks"]["PreToolUse"] for h in block["hooks"]
                if chip_init.HOOK_NAME in h["command"]]


class TestDeploy(InitCase):
    def test_fresh_repo_gets_briefs_dir_and_hook(self) -> None:
        self.assertEqual(self.run_init(), 0)
        self.assertTrue((self.repo / "chips").is_dir())
        self.assertEqual(len(self.chips_hooks()), 1)

    def test_hook_path_is_relative_and_resolves_to_the_real_hook(self) -> None:
        self.run_init()
        command = self.chips_hooks()[0]["command"]
        self.assertIn("$CLAUDE_PROJECT_DIR/", command)
        rel = command.split("$CLAUDE_PROJECT_DIR/", 1)[1].split('"', 1)[0]
        resolved = (self.repo / rel).resolve()
        self.assertEqual(resolved, chip_init.HOOK.resolve())
        self.assertTrue(resolved.is_file())

    def test_hook_block_shape(self) -> None:
        self.run_init(timeout=777)
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        block = data["hooks"]["PreToolUse"][0]
        self.assertEqual(block["matcher"], "Bash|PowerShell")
        hook = block["hooks"][0]
        self.assertEqual((hook["type"], hook["shell"], hook["timeout"]), ("command", "bash", 777))

    # chip 35 #6 - the hook must stop the gate before Claude Code kills it
    def test_command_carries_budget_below_timeout(self) -> None:
        self.run_init(timeout=777)
        command = self.chips_hooks()[0]["command"]
        self.assertTrue(command.endswith(" --budget 717"), command)

    def test_global_command_carries_budget_too(self) -> None:
        self.run_init(use_global=True)
        command = self.chips_hooks(self.home / "settings.json")[0]["command"]
        self.assertTrue(command.endswith(f" --budget {chip_init.DEFAULT_TIMEOUT - 60}"), command)

    def test_too_short_timeout_is_refused_and_writes_nothing(self) -> None:
        self.assertEqual(self.run_init(timeout=chip_init.MIN_TIMEOUT - 1), 2)
        self.assertFalse(self.settings.exists())
        self.assertFalse((self.repo / "chips").exists())

    def test_cli_rejects_too_short_timeout(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                chip_init.main([str(self.repo), "--hook-timeout", "30", "--no-review"])
        self.assertEqual(cm.exception.code, 2)
        self.assertFalse(self.settings.exists())

    def test_legacy_registration_without_budget_gets_a_note(self) -> None:
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": 'python "$CLAUDE_PROJECT_DIR/../CHIPS/tools/hook_chip_gate.py"'}
        ]}]}}), encoding="utf-8")
        self.run_init(check=True)
        self.assertTrue(any("without --budget" in line for line in self.lines), self.lines)

    def test_second_run_changes_nothing(self) -> None:
        self.run_init()
        before = sha(self.settings)
        self.assertEqual(self.run_init(), 0)
        self.assertEqual(sha(self.settings), before)
        self.assertEqual(len(self.chips_hooks()), 1)

    def test_existing_settings_are_merged_not_replaced(self) -> None:
        self.settings.parent.mkdir()
        foreign = {"type": "command", "command": "python lint_hook.py"}
        self.settings.write_text(json.dumps({
            "permissions": {"allow": ["Bash(git status:*)"]},
            "hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [foreign]}],
                      "Stop": [{"hooks": [{"type": "command", "command": "echo done"}]}]},
        }), encoding="utf-8")
        self.assertEqual(self.run_init(), 0)
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["permissions"], {"allow": ["Bash(git status:*)"]})
        self.assertIn(foreign, data["hooks"]["PreToolUse"][0]["hooks"])
        self.assertEqual(data["hooks"]["Stop"][0]["hooks"][0]["command"], "echo done")
        self.assertEqual(len(self.chips_hooks()), 1)

    def test_already_registered_by_hand_is_not_doubled(self) -> None:
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": 'python "$CLAUDE_PROJECT_DIR/../CHIPS/tools/hook_chip_gate.py"'}
        ]}]}}), encoding="utf-8")
        before = sha(self.settings)
        self.assertEqual(self.run_init(), 0)
        self.assertEqual(sha(self.settings), before)

    def test_invalid_json_is_left_alone(self) -> None:
        self.settings.parent.mkdir()
        self.settings.write_text("{ not json", encoding="utf-8")
        before = sha(self.settings)
        self.assertEqual(self.run_init(), 1)
        self.assertEqual(sha(self.settings), before)

    def test_hooks_of_wrong_type_are_refused(self) -> None:
        self.settings.parent.mkdir()
        self.settings.write_text(json.dumps({"hooks": "nope"}), encoding="utf-8")
        before = sha(self.settings)
        self.assertEqual(self.run_init(), 1)
        self.assertEqual(sha(self.settings), before)

    def test_not_a_git_repo_writes_nothing(self) -> None:
        plain = self.tmp / "plain"
        plain.mkdir()
        code = chip_init.init(plain, global_dir=self.home, review=False, out=self.lines.append)
        self.assertEqual(code, 1)
        self.assertEqual(list(plain.iterdir()), [])

    def test_chips_repo_itself_is_refused(self) -> None:
        code = chip_init.init(ROOT, global_dir=self.home, review=False, check=True,
                              out=self.lines.append)
        self.assertEqual(code, 1)

    def test_global_registers_absolute_path_in_home(self) -> None:
        self.assertEqual(self.run_init(use_global=True), 0)
        hooks = self.chips_hooks(self.home / "settings.json")
        self.assertEqual(len(hooks), 1)
        self.assertNotIn("$CLAUDE_PROJECT_DIR", hooks[0]["command"])
        self.assertIn(chip_init.HOOK.resolve().as_posix(), hooks[0]["command"])
        self.assertFalse(self.settings.exists())

    def test_review_loop_is_installed_into_the_given_home(self) -> None:
        self.assertEqual(self.run_init(review=True), 0)
        self.assertTrue((self.home / "agents" / "chip-critic.md").is_file())
        self.assertTrue((self.home / "skills" / "chip-review-loop" / "SKILL.md").is_file())


class TestCheck(InitCase):
    def test_check_on_fresh_repo_fails_and_writes_nothing(self) -> None:
        self.assertEqual(self.run_init(check=True, review=True), 1)
        self.assertFalse((self.repo / "chips").exists())
        self.assertFalse(self.settings.exists())
        self.assertFalse(self.home.exists())

    def test_check_after_deploy_passes(self) -> None:
        self.run_init(review=True)
        self.assertEqual(self.run_init(check=True, review=True), 0)


class TestSelfTest(InitCase):
    def test_real_hook_denies_a_chip_branch_in_a_deployed_repo(self) -> None:
        (self.repo / "chips").mkdir()
        self.assertTrue(chip_init.hook_denies(self.repo, "git merge ai/chip-99/does-not-exist"))

    def test_real_hook_lets_an_ordinary_branch_through(self) -> None:
        (self.repo / "chips").mkdir()
        self.assertFalse(chip_init.hook_denies(self.repo, "git merge some-ordinary-branch"))

    def test_self_test_failure_is_reported(self) -> None:
        silent = self.tmp / "silent_hook.py"
        silent.write_text("import sys\nsys.stdin.read()\n", encoding="utf-8")
        self.assertEqual(self.run_init(hook=silent), 1)
        self.assertTrue(any("FAILED" in l and "NOT denied" in l for l in self.lines))


class TestCli(unittest.TestCase):
    def test_help(self) -> None:
        done = subprocess.run([sys.executable, str(ROOT / "tools" / "chip_init.py"), "--help"],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("--check", done.stdout)

    def test_missing_repo_argument_is_a_usage_error(self) -> None:
        with self.assertRaises(SystemExit) as raised, contextlib.redirect_stderr(io.StringIO()):
            chip_init.main([])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
