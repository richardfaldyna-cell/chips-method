"""Tests for tools/chip_install.py and the contract of the review-loop sources (chip 33)."""

from __future__ import annotations

import contextlib
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import chip_install  # noqa: E402

SOURCES = ROOT / "integrations" / "claude-code"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InstallCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="chips-install-"))
        self.target = self.tmp / "claude"
        self.lines: list[str] = []

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_install(self, **kwargs) -> int:
        self.lines = []
        return chip_install.install(self.target, out=self.lines.append, **kwargs)

    def installed(self) -> list[Path]:
        if not self.target.exists():
            return []
        return sorted(p for p in self.target.rglob("*") if p.is_file())


class TestInstall(InstallCase):
    def test_installs_exactly_the_three_files(self) -> None:
        self.assertEqual(self.run_install(), 0)
        rel = sorted(p.relative_to(self.target).as_posix() for p in self.installed())
        self.assertEqual(rel, sorted(chip_install.FILES))

    def test_placeholder_is_rendered_to_this_clones_tools(self) -> None:
        self.run_install()
        tools = (ROOT / "tools").resolve().as_posix()
        for path in self.installed():
            with self.subTest(file=path.name):
                self.assertNotIn(chip_install.PLACEHOLDER, path.read_text(encoding="utf-8"))
        skill = self.target / "skills" / "chip-review-loop" / "SKILL.md"
        self.assertIn(f"{tools}/chip_review.py", skill.read_text(encoding="utf-8"))

    def test_second_run_writes_nothing(self) -> None:
        self.run_install()
        before = {p: sha(p) for p in self.installed()}
        self.assertEqual(self.run_install(), 0)
        self.assertFalse([l for l in self.lines if "written" in l and "0 written" not in l])
        self.assertEqual(before, {p: sha(p) for p in self.installed()})

    def test_differing_file_is_refused_and_left_alone(self) -> None:
        self.run_install()
        edited = self.target / "agents" / "chip-judge.md"
        edited.write_text("my own judge\n", encoding="utf-8")
        before = sha(edited)
        self.assertEqual(self.run_install(), 1)
        self.assertEqual(sha(edited), before)
        self.assertTrue(any("--force" in l for l in self.lines))

    def test_force_overwrites_a_differing_file(self) -> None:
        self.run_install()
        edited = self.target / "agents" / "chip-judge.md"
        edited.write_text("my own judge\n", encoding="utf-8")
        self.assertEqual(self.run_install(force=True), 0)
        expected = chip_install.stamped(chip_install.render(
            (SOURCES / "agents" / "chip-judge.md").read_text(encoding="utf-8")))
        self.assertEqual(edited.read_text(encoding="utf-8"), expected)

    def test_old_unedited_copy_is_updated_without_force(self) -> None:
        # Simulate `git pull` of CHIPS: install from an older source, then from the current one.
        older = self.tmp / "older-source"
        shutil.copytree(SOURCES, older)
        judge = older / "agents" / "chip-judge.md"
        judge.write_text(judge.read_text(encoding="utf-8") + "\nold rule\n", encoding="utf-8")
        chip_install.install(self.target, source_dir=older, out=self.lines.append)
        self.assertEqual(self.run_install(), 0)
        self.assertTrue(any("older version" in l for l in self.lines))
        self.assertNotIn("old rule", (self.target / "agents" / "chip-judge.md")
                         .read_text(encoding="utf-8"))

    def test_edited_body_with_intact_stamp_is_still_refused(self) -> None:
        self.run_install()
        path = self.target / "agents" / "chip-critic.md"
        path.write_text(path.read_text(encoding="utf-8").replace("CRITIC", "CRITTER", 1),
                        encoding="utf-8")
        before = sha(path)
        self.assertEqual(self.run_install(), 1)
        self.assertEqual(sha(path), before)

    def test_crlf_copy_counts_as_up_to_date(self) -> None:
        self.run_install()
        path = self.target / "agents" / "chip-critic.md"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(self.run_install(check=True), 0)

    def test_missing_source_fails_without_writing(self) -> None:
        empty_source = self.tmp / "no-sources"
        empty_source.mkdir()
        code = chip_install.install(self.target, source_dir=empty_source,
                                    out=self.lines.append)
        self.assertEqual(code, 1)
        self.assertEqual(self.installed(), [])


class TestCheck(InstallCase):
    def test_check_on_empty_target_fails_and_writes_nothing(self) -> None:
        self.assertEqual(self.run_install(check=True), 1)
        self.assertFalse(self.target.exists())

    def test_check_after_install_passes(self) -> None:
        self.run_install()
        self.assertEqual(self.run_install(check=True), 0)

    def test_check_detects_a_stale_file(self) -> None:
        self.run_install()
        (self.target / "skills" / "chip-review-loop" / "SKILL.md").write_text(
            "old skill\n", encoding="utf-8")
        self.assertEqual(self.run_install(check=True), 1)
        self.assertTrue(any(chip_install.EDITED in l for l in self.lines))

    def test_check_reports_an_old_copy_and_writes_nothing(self) -> None:
        older = self.tmp / "older-source"
        shutil.copytree(SOURCES, older)
        skill = older / "skills" / "chip-review-loop" / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\nold step\n", encoding="utf-8")
        chip_install.install(self.target, source_dir=older, out=self.lines.append)
        before = {p: sha(p) for p in self.installed()}
        self.assertEqual(self.run_install(check=True), 1)
        self.assertTrue(any(chip_install.OLD in l for l in self.lines))
        self.assertEqual(before, {p: sha(p) for p in self.installed()})

    def test_cli_check_and_force_exclude_each_other(self) -> None:
        with self.assertRaises(SystemExit) as raised, \
                contextlib.redirect_stderr(io.StringIO()):
            chip_install.main(["--check", "--force", "--target", str(self.target)])
        self.assertEqual(raised.exception.code, 2)

    def test_cli_runs_as_a_script(self) -> None:
        done = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "chip_install.py"),
             "--target", str(self.target)],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(self.installed()), 3)


def frontmatter(path: Path) -> dict[str, str]:
    text = chip_install.normalize(path.read_text(encoding="utf-8"))
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise AssertionError(f"{path} has no frontmatter")
    pairs = (line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    return {k.strip(): v.strip() for k, v in pairs}


class TestSourceContract(unittest.TestCase):
    """The sources are the product: a role that can write is not a reviewer any more."""

    def test_every_managed_source_exists(self) -> None:
        for rel in chip_install.FILES:
            with self.subTest(rel=rel):
                self.assertTrue((SOURCES / rel).is_file())

    def test_agent_name_matches_file_name(self) -> None:
        for rel in ("agents/chip-critic.md", "agents/chip-judge.md"):
            with self.subTest(rel=rel):
                self.assertEqual(frontmatter(SOURCES / rel)["name"], Path(rel).stem)

    def test_skill_name_matches_directory(self) -> None:
        skill = SOURCES / "skills" / "chip-review-loop" / "SKILL.md"
        self.assertEqual(frontmatter(skill)["name"], "chip-review-loop")

    def test_judge_cannot_write_or_run_commands(self) -> None:
        tools = frontmatter(SOURCES / "agents" / "chip-judge.md")["tools"]
        self.assertEqual({t.strip() for t in tools.split(",")}, {"Read", "Grep", "Glob"})

    def test_critic_cannot_edit_files(self) -> None:
        tools = {t.strip() for t in
                 frontmatter(SOURCES / "agents" / "chip-critic.md")["tools"].split(",")}
        self.assertFalse(tools & {"Write", "Edit", "NotebookEdit"})

    def test_skill_checks_the_worktree_after_the_critic(self) -> None:
        text = (SOURCES / "skills" / "chip-review-loop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("git -C <worktree> status --porcelain", text)

    def test_skill_never_merges(self) -> None:
        text = (SOURCES / "skills" / "chip-review-loop" / "SKILL.md").read_text(encoding="utf-8")
        # `merge-base` is fine (it only reads); a bare `git merge` is not.
        self.assertNotRegex(text, r"git\s+(-C\s+\S+\s+)?merge(?![-\w])")
        self.assertIn("Do not merge", text)

    def test_judge_detects_persistence_by_status_not_by_id(self) -> None:
        # Review round 1 of chip 33 (B-1): ids are never reused, so "the same id accepted
        # again" can never fire; an unfixed finding is only visible as `persists` in `previous`.
        text = (SOURCES / "agents" / "chip-judge.md").read_text(encoding="utf-8")
        self.assertIn("`persists` or `regressed`", text)
        self.assertNotIn("id was already accepted in the previous round", text)
        complete = next(l for l in text.splitlines() if "`COMPLETE`:" in l)
        following = text[text.index(complete):].split("- `CONTINUE`", 1)[0]
        self.assertIn("unfixed accepted finding", following)

    def test_skill_cap_on_persistence_reads_the_status(self) -> None:
        text = (SOURCES / "skills" / "chip-review-loop" / "SKILL.md").read_text(encoding="utf-8")
        caps = text.split("## 4. Caps", 1)[1].split("## 5.", 1)[0]
        self.assertIn("`persists`", caps)

    def test_skill_keeps_round_log_out_of_the_tracked_brief(self) -> None:
        # Review round 1 of chip 33 (B-2): a per-round edit of the brief left the worktree dirty
        # and failed the skill's own clean-tree check in the next round.
        text = (SOURCES / "skills" / "chip-review-loop" / "SKILL.md").read_text(encoding="utf-8")
        log = text.split("## 5. Log and report", 1)[1]
        self.assertIn("chips-review/NN/log.md", log)
        self.assertNotIn("Add one row per round to the Log of the brief", log)
        self.assertRegex(log, r"git -C <worktree> commit .*-- <brief>")

    def test_skill_uses_the_placeholder(self) -> None:
        text = (SOURCES / "skills" / "chip-review-loop" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(chip_install.PLACEHOLDER + "/chip_review.py", text)


if __name__ == "__main__":
    unittest.main()
