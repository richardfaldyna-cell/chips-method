"""Testy brány (`chip_gate.py`) a PreToolUse hooku (`hook_chip_gate.py`).

Hook je jediné tvrdé vynucení pravidla „merge až po zelené bráně" — když
tiše přestane blokovat, metodika se rozpadne a nikdo si toho nevšimne.
Proto se tu testuje hlavně to, KDY hook mlčí a KDY zamítá.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import chip_common                                                    # noqa: E402
import chip_gate                                                      # noqa: E402
import hook_chip_gate as hook                                         # noqa: E402

BRIEF = """---
chip: {cislo}
nazev: pokus
stav: ready
zavisi_na:
repo: {repo}
vetev: chip/{cislo}-pokus
worktree: ../x-chip-{cislo}
---

# CHIP {cislo}

## Issues

- [ ] #1 — něco

## Dotčené soubory

```
a.txt
```

## Definition of done

- [ ] projde

## Ověření (brána)

```bash
{prikazy}
```
"""


def zavolej_hook(prikaz: str, cwd: str) -> tuple[int, str]:
    """Spustí `hook.main()` s podstrčeným stdin; vrací (návratový kód, stdout).

    Prázdný stdout = hook mlčel, tedy merge povolil.
    """
    vstup = json.dumps({"tool_name": "Bash", "cwd": cwd,
                        "tool_input": {"command": prikaz}})
    buf = io.StringIO()
    with patch.object(sys, "stdin", io.StringIO(vstup)), redirect_stdout(buf):
        kod = hook.main()
    return kod, buf.getvalue()


def uloz_brief(chips: Path, cislo: str, repo: Path, prikazy: str) -> Path:
    p = chips / f"{cislo}-pokus.md"
    p.write_text(BRIEF.format(cislo=cislo, repo=repo.as_posix(), prikazy=prikazy),
                 encoding="utf-8")
    return p


class Zaklad(unittest.TestCase):
    """Dočasné repo s adresářem chips/ a obnova globálního CHIPS_DIR."""

    @classmethod
    def setUpClass(cls) -> None:
        # Hook od chipu 14 zjišťuje stav worktree přes `git status --porcelain`,
        # takže fixture potřebuje skutečné git stromy, ne jen adresáře.
        if shutil.which("git") is None:                       # pragma: no cover
            raise unittest.SkipTest("git není na PATH")

    def setUp(self) -> None:
        self.puvodni_dir = chip_common.CHIPS_DIR
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        self.chips = self.repo / "chips"
        self.chips.mkdir(parents=True)
        (self.repo / ".git").mkdir()
        (self.repo / "a.txt").write_text("x", encoding="utf-8")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(self._vrat_dir)

    def _vrat_dir(self) -> None:
        chip_common.CHIPS_DIR = self.puvodni_dir

    def nacti(self, cislo: str = "01", prikazy: str = "python -c \"pass\""):
        uloz_brief(self.chips, cislo, self.repo, prikazy)
        chip_common.nastav_chips_dir(self.chips)
        return chip_gate.najdi_chip(cislo, None)

    def worktree(self, cislo: str = "01") -> Path:
        """Čistý git strom tam, kam ukazuje `worktree:` briefu chipu.

        Prázdné `git init` stačí: `git status --porcelain` v něm nic nevypíše,
        takže strom je z pohledu hooku čistý. Skutečné repo (ne jen adresář) je
        nutné — nad ne-git adresářem hook merge zamítá, protože o jeho stavu
        vůči commitnutému tipu nic neví.
        """
        wt = self.tmp / f"x-chip-{cislo}"
        wt.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q", str(wt)], check=True, capture_output=True)
        return wt


class TestIdZVetve(unittest.TestCase):
    """Oba tvary větve. Když tenhle překlad selže, brána nemá co spustit."""

    # --- nová konvence `ai/chip-NN/nazev` ---------------------------------
    def test_nova_konvence(self) -> None:
        self.assertEqual(chip_gate.id_z_vetve("ai/chip-08/nazvy-vetvi"), "08")

    def test_nova_konvence_jednociferne_se_doplni(self) -> None:
        self.assertEqual(chip_gate.id_z_vetve("ai/chip-5/x"), "05")

    def test_nova_konvence_s_remote_prefixem(self) -> None:
        self.assertEqual(chip_gate.id_z_vetve("origin/ai/chip-08/nazvy-vetvi"), "08")

    def test_nova_konvence_nespadne_do_stareho_vzoru(self) -> None:
        """Číslo musí přijít z `chip-08`, ne odjinud z řetězce.

        Kdyby se `ai/chip-08/…` chytalo starým vzorem `chip/(\\d+)`, vzalo by se
        číslo z názvu za lomítkem — a brána by běžela nad cizím briefem.
        """
        self.assertEqual(chip_gate.id_z_vetve("ai/chip-08/oprava-chip/09"), "08")

    # --- starý tvar `chip/NN-nazev` (v repu jsou starší větve) ------------
    def test_bezna_vetev(self) -> None:
        self.assertEqual(chip_gate.id_z_vetve("chip/05-oprava-brany"), "05")

    def test_jednociferne_se_doplni(self) -> None:
        self.assertEqual(chip_gate.id_z_vetve("chip/5-x"), "05")

    # --- co chip větev NENÍ -----------------------------------------------
    def test_neni_chip_vetev(self) -> None:
        self.assertIsNone(chip_gate.id_z_vetve("feature/neco"))

    def test_prazdny_retezec(self) -> None:
        self.assertIsNone(chip_gate.id_z_vetve(""))

    def test_adresar_chips_neni_vetev(self) -> None:
        """`chips/08-x.md` je cesta k briefu, ne název větve."""
        self.assertIsNone(chip_gate.id_z_vetve("chips/08-nazvy-vetvi.md"))

    def test_ai_bez_chipu(self) -> None:
        self.assertIsNone(chip_gate.id_z_vetve("ai/oprava-neceho"))


class TestPrikazy(Zaklad):
    def test_vytahne_prikazy_z_bloku(self) -> None:
        c = self.nacti(prikazy="pytest -q\npython -m build")
        self.assertEqual(chip_gate.prikazy(c), ["pytest -q", "python -m build"])

    def test_preskoci_komentare_a_prazdne(self) -> None:
        c = self.nacti(prikazy="# komentář\n\npytest -q\n")
        self.assertEqual(chip_gate.prikazy(c), ["pytest -q"])

    def test_bez_bloku_prazdny_seznam(self) -> None:
        uloz_brief(self.chips, "02", self.repo, "x")
        p = self.chips / "02-pokus.md"
        p.write_text(p.read_text(encoding="utf-8")
                     .replace("```bash\nx\n```", "žádný blok"), encoding="utf-8")
        chip_common.nastav_chips_dir(self.chips)
        self.assertEqual(chip_gate.prikazy(chip_gate.najdi_chip("02", None)), [])


class TestSpust(Zaklad):
    def test_uspech_vraci_nulu(self) -> None:
        kod, _ = chip_gate.spust(self.repo, 'python -c "pass"')
        self.assertEqual(kod, 0)

    def test_neuspech_vraci_kod_a_vystup(self) -> None:
        kod, vystup = chip_gate.spust(self.repo, 'python -c "import sys; sys.exit(3)"')
        self.assertEqual(kod, 3)
        self.assertIsInstance(vystup, str)

    def test_bezi_v_korenu_repa(self) -> None:
        kod, vystup = chip_gate.spust(self.repo, 'python -c "import os; print(os.getcwd())"')
        self.assertEqual(kod, 0)
        self.assertEqual(Path(vystup.strip()).resolve(), self.repo.resolve())


class TestBrana(Zaklad):
    def test_zelena(self) -> None:
        c = self.nacti(prikazy='python -c "pass"')
        ok, hlaseni = chip_gate.brana(c, self.repo)
        self.assertTrue(ok)
        self.assertTrue(any("OK" in r for r in hlaseni))

    def test_cervena(self) -> None:
        c = self.nacti(prikazy='python -c "import sys; sys.exit(1)"')
        ok, _ = chip_gate.brana(c, self.repo)
        self.assertFalse(ok)

    def test_zastavi_se_na_prvnim_neuspechu(self) -> None:
        """Druhý příkaz už se nesmí spustit — běžel by nad rozbitým stavem."""
        stopa = self.repo / "stopa.txt"
        c = self.nacti(prikazy='python -c "import sys; sys.exit(1)"\n'
                               f'python -c "open(r\'{stopa}\',\'w\').write(\'x\')"')
        ok, _ = chip_gate.brana(c, self.repo)
        self.assertFalse(ok)
        self.assertFalse(stopa.exists())

    def test_chip_bez_brany_neprojde(self) -> None:
        uloz_brief(self.chips, "03", self.repo, "x")
        p = self.chips / "03-pokus.md"
        p.write_text(p.read_text(encoding="utf-8")
                     .replace("```bash\nx\n```", ""), encoding="utf-8")
        chip_common.nastav_chips_dir(self.chips)
        ok, hlaseni = chip_gate.brana(chip_gate.najdi_chip("03", None), self.repo)
        self.assertFalse(ok)
        self.assertIn("nemerguje", " ".join(hlaseni))


class TestNajdiChip(Zaklad):
    def test_podle_cisla(self) -> None:
        self.nacti("07")
        self.assertEqual(chip_gate.najdi_chip("07", None).id, "07")

    def test_podle_vetve(self) -> None:
        self.nacti("07")
        self.assertEqual(chip_gate.najdi_chip(None, "chip/07-pokus").id, "07")

    def test_neexistujici(self) -> None:
        self.nacti("07")
        self.assertIsNone(chip_gate.najdi_chip("99", None))


class TestCilovéRepo(Zaklad):
    def test_git_c(self) -> None:
        prikaz = f'git -C "{self.repo}" merge chip/01-pokus'
        self.assertEqual(hook.cilove_repo(prikaz, None).resolve(), self.repo.resolve())

    def test_cd(self) -> None:
        prikaz = f'cd "{self.repo}" && git merge chip/01-pokus'
        self.assertEqual(hook.cilove_repo(prikaz, None).resolve(), self.repo.resolve())

    def test_fallback_na_cwd(self) -> None:
        self.assertEqual(hook.cilove_repo("git merge chip/01-x", str(self.repo)),
                         Path(str(self.repo)))

    # --- `-C` patřící jinému volání než merge ------------------------------
    def test_git_c_jineho_volani_se_ignoruje(self) -> None:
        """`git -C jinde status && git merge …` merguje v cwd, ne v `jinde`.

        Dřív se bral první `git -C` v příkazu. Když ukazoval mimo CHIPS repo,
        hook tam nenašel `chips/`, mlčel — a červený merge prošel.
        """
        jine = self.tmp / "jine"
        jine.mkdir()
        prikaz = f'git -C "{jine}" status && git merge chip/01-pokus'
        self.assertEqual(hook.cilove_repo(prikaz, str(self.repo)).resolve(),
                         self.repo.resolve())

    def test_git_c_u_merge_se_bere(self) -> None:
        jine = self.tmp / "jine"
        jine.mkdir()
        prikaz = f'git -C "{jine}" status && git -C "{self.repo}" merge chip/01-pokus'
        self.assertEqual(hook.cilove_repo(prikaz, str(self.tmp)).resolve(),
                         self.repo.resolve())

    # --- relativní cesty proti cwd session, ne proti cwd procesu -----------
    def test_relativni_git_c_proti_cwd_z_payloadu(self) -> None:
        """`git -C repo merge …` se skládá s `cwd` z payloadu, ne s cwd hooku."""
        self.assertEqual(hook.cilove_repo("git -C repo merge chip/01-pokus",
                                          str(self.tmp)).resolve(),
                         self.repo.resolve())

    def test_relativni_cd_proti_cwd_z_payloadu(self) -> None:
        self.assertEqual(hook.cilove_repo("cd repo && git merge chip/01-pokus",
                                          str(self.tmp)).resolve(),
                         self.repo.resolve())

    def test_retez_cd_se_sklada(self) -> None:
        """Druhé `cd` je relativní vůči tomu, kam došlo první."""
        prikaz = f'cd "{self.tmp}" && cd repo && git merge chip/01-pokus'
        self.assertEqual(hook.cilove_repo(prikaz, None).resolve(),
                         self.repo.resolve())


class TestCislaChipu(Zaklad):
    """Z jakého místa příkazu se bere název mergované větve."""

    def test_holy_merge(self) -> None:
        self.assertEqual(hook.cisla_chipu("git merge ai/chip-05/x"), ["05"])

    def test_prepinace_se_preskoci(self) -> None:
        self.assertEqual(hook.cisla_chipu("git merge --no-ff --squash chip/7-x"), ["07"])

    def test_zprava_prepinace_neni_vetev(self) -> None:
        """`-m "…"` bere hodnotu jako samostatný token — nesmí se plést s větví."""
        self.assertEqual(
            hook.cisla_chipu('git merge -m "merge ai/chip-04/x" ai/chip-05/y'), ["05"])

    def test_vetev_mimo_merge_se_nepocita(self) -> None:
        self.assertEqual(hook.cisla_chipu("git branch -d ai/chip-04/x && git status"), [])

    def test_bere_argument_merge_ne_prvni_token_v_prikazu(self) -> None:
        self.assertEqual(
            hook.cisla_chipu("git branch -d ai/chip-04/x && git merge ai/chip-05/y"),
            ["05"])

    def test_octopus_vrati_obe(self) -> None:
        self.assertEqual(hook.cisla_chipu("git merge ai/chip-04/x ai/chip-05/y"),
                         ["04", "05"])

    def test_merge_v_ceste_neni_merge(self) -> None:
        """`merge` jako část cesty nespouští merge — jinak by se bral cizí token."""
        self.assertEqual(hook.cisla_chipu("git -C /x/merge/y status ai/chip-04/z"), [])


class TestGitKoren(Zaklad):
    def test_git_jako_adresar(self) -> None:
        self.assertEqual(hook.git_koren(self.chips), self.repo.resolve())

    def test_git_jako_soubor_worktree(self) -> None:
        wt = self.tmp / "wt"
        (wt / "chips").mkdir(parents=True)
        (wt / ".git").write_text("gitdir: ../repo/.git/worktrees/wt", encoding="utf-8")
        self.assertEqual(hook.git_koren(wt / "chips"), wt.resolve())

    def test_mimo_git(self) -> None:
        mimo = self.tmp / "mimo"
        mimo.mkdir()
        self.assertIsNone(hook.git_koren(mimo))


class TestHook(Zaklad):
    """Kdy hook mlčí a kdy zamítá — jádro celého vynucení."""

    def setUp(self) -> None:
        super().setUp()
        # Chipy 01 a 02 mají v testech existující ČISTÝ worktree. Od chipu 14
        # hook bez worktree zamítá, takže bez téhle přípravy by každý test
        # skončil na „NEJDE OVĚŘIT" a netestoval by to, co má.
        self.wt01 = self.worktree("01")
        self.wt02 = self.worktree("02")

    def zavolej(self, prikaz: str, cwd: str | None = None) -> tuple[int, str]:
        return zavolej_hook(prikaz, cwd or str(self.repo))

    def test_neni_merge_mlci(self) -> None:
        kod, out = self.zavolej("git status")
        self.assertEqual((kod, out), (0, ""))

    def test_merge_ale_ne_chip_vetev_mlci(self) -> None:
        kod, out = self.zavolej("git merge feature/neco")
        self.assertEqual((kod, out), (0, ""))

    def test_repo_bez_chips_mlci(self) -> None:
        jine = self.tmp / "jine"
        jine.mkdir()
        (jine / ".git").mkdir()
        kod, out = self.zavolej(f'cd "{jine}" && git merge chip/01-pokus')
        self.assertEqual((kod, out), (0, ""))

    def test_chybejici_brief_zamita(self) -> None:
        self.nacti("01")
        kod, out = self.zavolej(f'git -C "{self.repo}" merge chip/42-neexistuje')
        self.assertEqual(kod, 0)
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"],
                         "deny")

    def test_cervena_brana_zamita(self) -> None:
        self.nacti("01", prikazy='python -c "import sys; sys.exit(1)"')
        kod, out = self.zavolej(f'git -C "{self.repo}" merge chip/01-pokus')
        self.assertEqual(kod, 0)
        vystup = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(vystup["permissionDecision"], "deny")
        self.assertIn("NEPROŠLA", vystup["permissionDecisionReason"])

    def test_zelena_brana_pousti(self) -> None:
        self.nacti("01", prikazy='python -c "pass"')
        kod, out = self.zavolej(f'git -C "{self.repo}" merge chip/01-pokus')
        self.assertEqual((kod, out), (0, ""))

    def test_rozbity_vstup_neprekazi(self) -> None:
        buf = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO("{tohle není JSON")), \
             redirect_stdout(buf):
            kod = hook.main()
        self.assertEqual((kod, buf.getvalue()), (0, ""))

    def test_chybejici_command_neprekazi(self) -> None:
        buf = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO(json.dumps({"tool_name": "Bash"}))), \
             redirect_stdout(buf):
            kod = hook.main()
        self.assertEqual((kod, buf.getvalue()), (0, ""))

    def test_merge_v_slozenem_prikazu_se_chyti(self) -> None:
        """`cd X && git merge …` musí spadnout do brány stejně jako holý merge."""
        self.nacti("01", prikazy='python -c "import sys; sys.exit(1)"')
        kod, out = self.zavolej(f'cd "{self.repo}" && git merge --no-ff chip/01-pokus')
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"],
                         "deny")

    # ------------------------------------------------------------------
    # Nová konvence `ai/chip-NN/nazev` — regresní pojistka proti tichému
    # vypnutí brány. Kdyby hook nový tvar nepoznal, mlčel by a merge s
    # červenou bránou by prošel: brána by vypadala, že funguje, a nefungovala.
    # ------------------------------------------------------------------
    def test_nova_konvence_cervena_brana_zamita(self) -> None:
        self.nacti("01", prikazy='python -c "import sys; sys.exit(1)"')
        kod, out = self.zavolej(f'git -C "{self.repo}" merge ai/chip-01/pokus')
        self.assertEqual(kod, 0)
        self.assertTrue(out, "hook na větev 'ai/chip-01/pokus' MLČEL — nepoznal ji "
                             "jako chip větev a merge s červenou bránou by prošel")
        vystup = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(vystup["permissionDecision"], "deny")
        self.assertIn("NEPROŠLA", vystup["permissionDecisionReason"])

    def test_nova_konvence_ve_slozenem_prikazu_zamita(self) -> None:
        self.nacti("01", prikazy='python -c "import sys; sys.exit(1)"')
        kod, out = self.zavolej(f'cd "{self.repo}" && git merge --no-ff ai/chip-01/pokus')
        self.assertTrue(out, "hook mlčel u 'cd … && git merge ai/chip-01/pokus'")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"],
                         "deny")

    def test_nova_konvence_zelena_brana_pousti(self) -> None:
        self.nacti("01", prikazy='python -c "pass"')
        kod, out = self.zavolej(f'git -C "{self.repo}" merge ai/chip-01/pokus')
        self.assertEqual((kod, out), (0, ""))

    def test_nova_konvence_chybejici_brief_zamita(self) -> None:
        self.nacti("01")
        kod, out = self.zavolej(f'git -C "{self.repo}" merge ai/chip-42/neexistuje')
        self.assertTrue(out, "hook mlčel u větve bez briefu — merge by prošel neověřený")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"],
                         "deny")

    # ------------------------------------------------------------------
    # Složené příkazy: větev i cílové repo se musí číst z toho místa
    # příkazu, které merge doopravdy spouští. Oba scénáře níž pouštěly na
    # původní verzi hooku merge s ČERVENOU bránou — hook mlčel.
    # ------------------------------------------------------------------
    def test_vetev_se_bere_z_argumentu_merge_ne_z_okoli(self) -> None:
        """`git branch -d <zelený chip> && git merge <červený chip>`.

        Dřív se bral první chip token v příkazu, takže se ověřila brána chipu
        01 (zelená) a merge chipu 02 (červený) prošel.
        """
        self.nacti("01", prikazy='python -c "pass"')
        self.nacti("02", prikazy='python -c "import sys; sys.exit(1)"')
        kod, out = self.zavolej(f'git branch -d ai/chip-01/pokus && '
                                f'git -C "{self.repo}" merge ai/chip-02/pokus')
        self.assertTrue(out, "hook mlčel — ověřil bránu chipu 01 místo mergovaného 02 "
                             "a pustil merge s červenou bránou")
        vystup = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(vystup["permissionDecision"], "deny")
        self.assertIn("chipu 02", vystup["permissionDecisionReason"])

    def test_chip_ve_zprave_prepinace_neni_mergovana_vetev(self) -> None:
        self.nacti("01", prikazy='python -c "pass"')
        self.nacti("02", prikazy='python -c "import sys; sys.exit(1)"')
        kod, out = self.zavolej(f'git -C "{self.repo}" merge '
                                f'-m "merge ai/chip-01/pokus" ai/chip-02/pokus')
        self.assertTrue(out, "hook vzal chip ze zprávy `-m` a pustil červený merge")
        self.assertIn("chipu 02",
                      json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_octopus_zamita_na_cervene_druhe_vetvi(self) -> None:
        self.nacti("01", prikazy='python -c "pass"')
        self.nacti("02", prikazy='python -c "import sys; sys.exit(1)"')
        kod, out = self.zavolej(f'git -C "{self.repo}" merge '
                                f'ai/chip-01/pokus ai/chip-02/pokus')
        self.assertTrue(out, "hook ověřil jen první větev octopus merge")
        self.assertIn("chipu 02",
                      json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_git_c_jineho_volani_neodvede_branu_jinam(self) -> None:
        """`git -C jinde status && git merge …` — `-C` nepatří merge.

        Dřív hook hledal `chips/` v `jinde`, nenašel ho a mlčky pustil dál.
        """
        jine = self.tmp / "jine"
        jine.mkdir()
        (jine / ".git").mkdir()
        self.nacti("01", prikazy='python -c "import sys; sys.exit(1)"')
        kod, out = self.zavolej(f'git -C "{jine}" status && git merge ai/chip-01/pokus',
                                cwd=str(self.repo))
        self.assertTrue(out, "hook hledal repo podle cizího `git -C` a mlčel")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"],
                         "deny")

    def test_relativni_cesta_se_resolvuje_proti_cwd_z_payloadu(self) -> None:
        """`git -C repo merge …` z cwd session, ne z cwd hook procesu.

        Hook běží tam, kde ho spustil Claude Code — relativní cesta z příkazu
        se proti tomu adresáři nesmí skládat. Dřív se `repo` nenašlo a hook
        mlčel.
        """
        self.nacti("01", prikazy='python -c "import sys; sys.exit(1)"')
        kod, out = self.zavolej("git -C repo merge ai/chip-01/pokus",
                                cwd=str(self.tmp))
        self.assertTrue(out, "hook resolvoval relativní `git -C repo` proti cwd "
                             "procesu, repo nenašel a červený merge pustil")
        self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"],
                         "deny")

    def test_hook_a_brana_poznaji_stejne_vetve(self) -> None:
        """Vzor v hooku je kopie toho v `chip_gate` — nesmí se rozejít.

        Hook si `chip_gate` schválně neimportuje dřív, než projdou levné
        podmínky (běží před každým příkazem shellu), takže vzor existuje
        dvakrát. Tenhle test je jediné, co drží obě kopie u sebe.
        """
        vzorky = ["ai/chip-08/nazvy-vetvi", "ai/chip-8/x", "chip/05-oprava-brany",
                  "chip/5-x", "origin/ai/chip-08/nazvy-vetvi",
                  "feature/neco", "ai/oprava-neceho", "chips/08-nazvy-vetvi.md", ""]
        for v in vzorky:
            with self.subTest(vetev=v):
                m = hook.VETEV.search(v)
                self.assertEqual(m.group(1).zfill(2) if m else None,
                                 chip_gate.id_z_vetve(v))

        # Vzor je jen půlka shody — hook ho od chipu 13 pouští na argument za
        # `merge`, ne na celý příkaz. Porovnává se rozpoznání NÁZVU VĚTVE:
        # co brána pozná jako chip, to hook musí poznat i v příkazu.
        for v in vzorky:
            with self.subTest(vetev=v, cesta="cisla_chipu"):
                cisla = hook.cisla_chipu(f"git merge {v}")
                self.assertEqual(cisla[0] if cisla else None,
                                 chip_gate.id_z_vetve(v))


if __name__ == "__main__":
    unittest.main()


class TestKdeJsouBriefy(Zaklad):
    """Podmínka 3: podle čeho hook pozná, že repo řídí CHIPS.

    Dokud byl jediným signálem adresář `chips/`, vylučovala se tvrdá brána
    s nulovou stopou v cizím repu — briefy uložené mimo repo hook neviděl
    a **mlčky pouštěl červené merge**. Tahle třída hlídá, že se ta díra
    nevrátí a že se novými signály zároveň nerozšířila na cizí projekty.
    """

    def setUp(self) -> None:
        super().setUp()
        self.venku = self.tmp / "briefy"          # briefy mimo repo (režim --dir)
        self.venku.mkdir()

    def bez_chips(self) -> Path:
        """Repo bez `chips/` — stav cizího repa, kam metodika nesmí sáhnout."""
        shutil.rmtree(self.chips)
        return self.repo

    def marker(self, obsah: str) -> None:
        (self.repo / hook.MARKER).write_text(obsah, encoding="utf-8")

    def kde(self, koren: Path | None = None) -> Path | None:
        return hook.kde_jsou_briefy(koren or self.repo, chip_common)

    def test_vlastni_chips_ma_prednost_pred_markerem(self) -> None:
        """Co je v repu, ví o repu víc než cokoli vedle něj."""
        self.marker(str(self.venku))
        self.assertEqual(self.kde(), self.repo / "chips")

    def test_marker_ukazuje_na_briefy_mimo_repo(self) -> None:
        self.bez_chips()
        self.marker(str(self.venku))
        self.assertEqual(self.kde(), self.venku)

    def test_relativni_cesta_v_markeru_je_od_korene_repa(self) -> None:
        self.bez_chips()
        self.marker("../briefy")
        self.assertEqual(self.kde().resolve(), self.venku.resolve())

    def test_marker_ignoruje_komentare(self) -> None:
        """Kdo marker najde, má z něj poznat, co to je."""
        self.bez_chips()
        self.marker(f"# chip briefy pro tohle repo (CHIPS)\n\n{self.venku}\n")
        self.assertEqual(self.kde(), self.venku)

    def test_prazdny_marker_zamita(self) -> None:
        self.bez_chips()
        self.marker("# jen komentář\n")
        with self.assertRaises(hook.NeniKdeOverit) as ctx:
            self.kde()
        self.assertIn("neobsahuje cestu", str(ctx.exception))

    def test_marker_na_neexistujici_cestu_zamita(self) -> None:
        """Překlep v cestě nesmí skončit mlčením — to je zpátky ta díra."""
        self.bez_chips()
        self.marker(str(self.tmp / "nikde"))
        with self.assertRaises(hook.NeniKdeOverit) as ctx:
            self.kde()
        self.assertIn("není adresář", str(ctx.exception))

    def test_env_plati_pro_sve_repo(self) -> None:
        self.bez_chips()
        uloz_brief(self.venku, "01", self.repo, "x")
        with patch.dict(os.environ, {"CHIPS_DIR": str(self.venku)}):
            self.assertEqual(self.kde(), self.venku)

    def test_env_cizi_projekt_mlci(self) -> None:
        """Globální proměnná nesmí rozhodovat o merge v jiném projektu."""
        self.bez_chips()
        cizi = self.tmp / "cizi"
        (cizi / ".git").mkdir(parents=True)
        uloz_brief(self.venku, "01", cizi, "x")
        with patch.dict(os.environ, {"CHIPS_DIR": str(self.venku)}):
            self.assertIsNone(self.kde())

    def test_env_na_neexistujici_adresar_mlci(self) -> None:
        self.bez_chips()
        with patch.dict(os.environ, {"CHIPS_DIR": str(self.tmp / "nikde")}):
            self.assertIsNone(self.kde())

    def test_bez_signalu_mlci(self) -> None:
        self.bez_chips()
        with patch.dict(os.environ, {"CHIPS_DIR": ""}):
            self.assertIsNone(self.kde())

    def test_hledani_nezmeni_globalni_chips_dir(self) -> None:
        """`z_env` briefy načítá, tedy CHIPS_DIR přepíná — musí ho vrátit."""
        self.bez_chips()
        uloz_brief(self.venku, "01", self.repo, "x")
        chip_common.nastav_chips_dir(self.tmp / "puvodni")
        pred = chip_common.CHIPS_DIR
        with patch.dict(os.environ, {"CHIPS_DIR": str(self.venku)}):
            self.kde()
        self.assertEqual(chip_common.CHIPS_DIR, pred)


class TestHookMimoRepo(Zaklad):
    """Hook nad repem, které briefy nemá — konec „tvrdá brána NEBO nulová stopa"."""

    def setUp(self) -> None:
        super().setUp()
        self.venku = self.tmp / "briefy"
        self.venku.mkdir()
        self.wt = self.worktree("01")
        shutil.rmtree(self.chips)                 # cizí repo: žádné `chips/`

    def priprav(self, prikazy: str) -> None:
        uloz_brief(self.venku, "01", self.repo, prikazy)

    def merge(self, env: dict[str, str] | None = None) -> tuple[int, str]:
        with patch.dict(os.environ, env or {"CHIPS_DIR": ""}):
            return zavolej_hook(f'git -C "{self.repo}" merge chip/01-pokus',
                                str(self.repo))

    def duvod(self, out: str) -> str:
        vystup = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(vystup["permissionDecision"], "deny")
        return vystup["permissionDecisionReason"]

    def test_bez_signalu_hook_mlci(self) -> None:
        """Beze změny chování tam, kde CHIPS opravdu neběží."""
        self.priprav('python -c "import sys; sys.exit(1)"')
        self.assertEqual(self.merge(), (0, ""))

    def test_marker_vrati_hooku_cervenou_branu(self) -> None:
        self.priprav('python -c "import sys; sys.exit(1)"')
        (self.repo / hook.MARKER).write_text(str(self.venku), encoding="utf-8")
        kod, out = self.merge()
        self.assertEqual(kod, 0)
        self.assertIn("NEPROŠLA", self.duvod(out))

    def test_marker_a_zelena_brana_pousti(self) -> None:
        self.priprav('python -c "pass"')
        (self.repo / hook.MARKER).write_text(str(self.venku), encoding="utf-8")
        self.assertEqual(self.merge(), (0, ""))

    def test_rozbity_marker_zamita_misto_mlceni(self) -> None:
        self.priprav('python -c "pass"')
        (self.repo / hook.MARKER).write_text("", encoding="utf-8")
        kod, out = self.merge()
        self.assertEqual(kod, 0)
        self.assertIn("nejde najít", self.duvod(out))

    def test_env_vrati_hooku_cervenou_branu(self) -> None:
        self.priprav('python -c "import sys; sys.exit(1)"')
        kod, out = self.merge({"CHIPS_DIR": str(self.venku)})
        self.assertEqual(kod, 0)
        self.assertIn("NEPROŠLA", self.duvod(out))

    def test_env_cizi_projekt_do_merge_nemluvi(self) -> None:
        cizi = self.tmp / "cizi"
        (cizi / ".git").mkdir(parents=True)
        uloz_brief(self.venku, "01", cizi, 'python -c "import sys; sys.exit(1)"')
        self.assertEqual(self.merge({"CHIPS_DIR": str(self.venku)}), (0, ""))


class TestKdeOverit(Zaklad):
    """Brána musí běžet ve stromě chipu — v hlavním jeho práce ještě není."""

    def test_worktree_ma_prednost(self) -> None:
        wt = self.tmp / "x-chip-01"
        wt.mkdir()
        c = self.nacti("01")
        self.assertEqual(hook.kde_overit(c, self.repo), wt)

    def test_bez_worktree_selze(self) -> None:
        """Dřív se spadlo na hlavní strom („lepší ověřit něco než nic").

        Test se změnou obrátil právem: hlavní strom je cíl merge, práci chipu
        z definice nemá — zelená odtamtud je zelená nad starým kódem.
        """
        c = self.nacti("01")            # ../x-chip-01 neexistuje
        with self.assertRaises(hook.NeniKdeOverit):
            hook.kde_overit(c, self.repo)

    def test_prazdne_worktree_v_briefu_selze(self) -> None:
        uloz_brief(self.chips, "05", self.repo, 'python -c "pass"')
        p = self.chips / "05-pokus.md"
        p.write_text(p.read_text(encoding="utf-8").replace("worktree: ../x-chip-05",
                                                           "worktree:"),
                     encoding="utf-8")
        chip_common.nastav_chips_dir(self.chips)
        with self.assertRaises(hook.NeniKdeOverit):
            hook.kde_overit(chip_gate.najdi_chip("05", None), self.repo)

    def test_worktree_ukazujici_na_cilovy_strom_selze(self) -> None:
        """`worktree:` mířící tam, kam se merguje, je táž falešná zelená.

        Hlavní strom `CHIPS` je sám git worktree a v provozu bývá špinavý —
        kdyby se tenhle případ pustil dál, rozhodovala by o něm až kontrola
        necommitnutých změn a hláška by mířila vedle.
        """
        uloz_brief(self.chips, "06", self.repo, 'python -c "pass"')
        p = self.chips / "06-pokus.md"
        p.write_text(p.read_text(encoding="utf-8")
                     .replace("worktree: ../x-chip-06", f"worktree: {self.repo.as_posix()}"),
                     encoding="utf-8")
        chip_common.nastav_chips_dir(self.chips)
        with self.assertRaises(hook.NeniKdeOverit):
            hook.kde_overit(chip_gate.najdi_chip("06", None), self.repo)

    def test_absolutni_worktree(self) -> None:
        wt = self.tmp / "jinde"
        wt.mkdir()
        uloz_brief(self.chips, "02", self.repo, 'python -c "pass"')
        p = self.chips / "02-pokus.md"
        p.write_text(p.read_text(encoding="utf-8")
                     .replace("worktree: ../x-chip-02", f"worktree: {wt.as_posix()}"),
                     encoding="utf-8")
        chip_common.nastav_chips_dir(self.chips)
        self.assertEqual(hook.kde_overit(chip_gate.najdi_chip("02", None), self.repo), wt)

    def test_brana_bezi_ve_worktree_ne_v_hlavnim(self) -> None:
        """Důkaz: příkaz vypíše cwd; musí to být worktree."""
        wt = self.tmp / "x-chip-01"
        wt.mkdir()
        c = self.nacti("01", prikazy='python -c "import os,sys; '
                                     'sys.exit(0 if \'x-chip-01\' in os.getcwd() else 1)"')
        ok, _ = chip_gate.brana(c, hook.kde_overit(c, self.repo))
        self.assertTrue(ok)


class TestNecommitnute(Zaklad):
    """Rozpoznání špinavého stromu. Merge bere commitnutý tip, brána working tree."""

    def git(self, wt: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(wt), *args], check=True, capture_output=True)

    def s_commitem(self, cislo: str = "01") -> Path:
        wt = self.worktree(cislo)
        (wt / "a.txt").write_text("x", encoding="utf-8")
        self.git(wt, "add", "a.txt")
        self.git(wt, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
        return wt

    def test_cisty_strom_je_prazdny_seznam(self) -> None:
        self.assertEqual(hook.necommitnute(self.s_commitem()), [])

    def test_zmeneny_soubor_se_pozna(self) -> None:
        wt = self.s_commitem()
        (wt / "a.txt").write_text("zmena", encoding="utf-8")
        self.assertTrue(any("a.txt" in r for r in hook.necommitnute(wt)))

    def test_netrackovany_soubor_se_pocita(self) -> None:
        """Co není v commitu, to se nemerguje — brána nad tím projít nesmí."""
        wt = self.s_commitem()
        (wt / "novy.py").write_text("x", encoding="utf-8")
        self.assertTrue(any("novy.py" in r for r in hook.necommitnute(wt)))

    def test_ignorovany_soubor_strom_nespini(self) -> None:
        """`__pycache__` po běhu brány nesmí zablokovat další merge."""
        wt = self.s_commitem()
        (wt / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        self.git(wt, "add", ".gitignore")
        self.git(wt, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "ign")
        (wt / "__pycache__").mkdir()
        (wt / "__pycache__" / "x.pyc").write_text("x", encoding="utf-8")
        self.assertEqual(hook.necommitnute(wt), [])

    def test_ne_git_adresar_selze(self) -> None:
        """Nevědět, co ve stromě je, se pro potřeby brány rovná nemít ho."""
        mimo = self.tmp / "mimo-git"
        mimo.mkdir()
        with self.assertRaises(hook.NeniKdeOverit):
            hook.necommitnute(mimo)


class TestHookNejdeOverit(Zaklad):
    """#1 a #2: hook nesmí ověřit něco jiného, když nemůže ověřit mergovaný stav.

    Obě situace na verzi před chipem 14 vracely ZELENOU: chybějící worktree
    spadl na hlavní strom (starý kód) a špinavý worktree se ověřil, jak leží,
    ne jak se merguje. Oba testy musí na té verzi selhat.
    """

    def zavolej(self, prikaz: str, cwd: str | None = None) -> tuple[int, str]:
        return zavolej_hook(prikaz, cwd or str(self.repo))

    def duvod(self, out: str) -> str:
        self.assertTrue(out, "hook MLČEL — merge by prošel bez ověření")
        vystup = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(vystup["permissionDecision"], "deny")
        return vystup["permissionDecisionReason"]

    # --- #1 chybějící worktree -------------------------------------------
    def test_chybejici_worktree_zamita(self) -> None:
        """Brána chipu je zelená, ale v hlavním stromě — a tam chip není.

        Dřív se `kde_overit()` vrátilo na hlavní strom, brána nad starým kódem
        prošla a hook mlčel: merge se pustil úplně neověřený.
        """
        self.nacti("01", prikazy='python -c "pass"')          # ../x-chip-01 chybí
        _, out = self.zavolej(f'git -C "{self.repo}" merge ai/chip-01/pokus')
        duvod = self.duvod(out)
        self.assertIn("NEJDE OVĚŘIT", duvod)
        self.assertIn("worktree", duvod)

    def test_hlaska_o_chybejicim_worktree_rika_co_delat(self) -> None:
        self.nacti("01", prikazy='python -c "pass"')
        _, out = self.zavolej(f'git -C "{self.repo}" merge ai/chip-01/pokus')
        self.assertIn("chip_run.py", self.duvod(out))

    def test_worktree_ukazujici_na_cilovy_strom_zamita(self) -> None:
        """Past: hlavní strom je sám worktree a v provozu bývá špinavý.

        Kdyby se tenhle případ pustil dál, rozhodla by o něm až kontrola
        necommitnutých změn — a ta by v běžném provozu hlásila „špinavý
        worktree" tam, kde je problém úplně jinde (v `worktree:` briefu).
        """
        uloz_brief(self.chips, "01", self.repo, 'python -c "pass"')
        p = self.chips / "01-pokus.md"
        p.write_text(p.read_text(encoding="utf-8")
                     .replace("worktree: ../x-chip-01",
                              f"worktree: {self.repo.as_posix()}"),
                     encoding="utf-8")
        chip_common.nastav_chips_dir(self.chips)
        _, out = self.zavolej(f'git -C "{self.repo}" merge ai/chip-01/pokus')
        self.assertIn("PŘED mergem", self.duvod(out))

    def test_octopus_zamita_hned_na_prvni_neoveritelne_vetvi(self) -> None:
        """Druhá větev se už nesmí ověřovat — celý merge stejně neprojde."""
        stopa = self.tmp / "stopa.txt"
        self.nacti("01", prikazy='python -c "pass"')          # bez worktree
        self.worktree("02")
        self.nacti("02", prikazy=f'python -c "open(r\'{stopa}\',\'w\').write(\'x\')"')
        _, out = self.zavolej(f'git -C "{self.repo}" merge '
                              f'ai/chip-01/pokus ai/chip-02/pokus')
        self.assertIn("chipu 01", self.duvod(out))
        self.assertFalse(stopa.exists(), "brána chipu 02 se spustila i po zamítnutí 01")

    # --- #2 špinavý worktree ---------------------------------------------
    def test_spinavy_worktree_zamita(self) -> None:
        """Brána je zelená, ale nad stavem, který v commitu není.

        Dřív hook ověřil working tree a mlčel — verdikt platil o jiném stavu,
        než jaký se merguje.
        """
        wt = self.worktree("01")
        (wt / "rozdelane.txt").write_text("necommitnuto", encoding="utf-8")
        self.nacti("01", prikazy='python -c "pass"')
        _, out = self.zavolej(f'git -C "{self.repo}" merge ai/chip-01/pokus')
        duvod = self.duvod(out)
        self.assertIn("necommitnuté změny", duvod)
        self.assertIn("rozdelane.txt", duvod)

    def test_hlaska_o_spinavem_worktree_rika_co_delat(self) -> None:
        wt = self.worktree("01")
        (wt / "rozdelane.txt").write_text("x", encoding="utf-8")
        self.nacti("01", prikazy='python -c "pass"')
        _, out = self.zavolej(f'git -C "{self.repo}" merge ai/chip-01/pokus')
        self.assertIn("commitni", self.duvod(out))

    def test_spinavy_worktree_zamita_i_kdyz_je_brana_cervena(self) -> None:
        """Mýlí se to v obou směrech — červená nad nemergovaným experimentem.

        Hláška musí říct pravdu (necommitnuté změny), ne obviňovat bránu.
        """
        wt = self.worktree("01")
        (wt / "experiment.txt").write_text("x", encoding="utf-8")
        self.nacti("01", prikazy='python -c "import sys; sys.exit(1)"')
        _, out = self.zavolej(f'git -C "{self.repo}" merge ai/chip-01/pokus')
        duvod = self.duvod(out)
        self.assertIn("necommitnuté změny", duvod)
        self.assertNotIn("NEPROŠLA", duvod)

    def test_brana_se_nad_spinavym_stromem_vubec_nespusti(self) -> None:
        stopa = self.tmp / "stopa.txt"
        wt = self.worktree("01")
        (wt / "rozdelane.txt").write_text("x", encoding="utf-8")
        self.nacti("01", prikazy=f'python -c "open(r\'{stopa}\',\'w\').write(\'x\')"')
        self.zavolej(f'git -C "{self.repo}" merge ai/chip-01/pokus')
        self.assertFalse(stopa.exists(), "brána běžela nad stromem, který se nemerguje")

    # --- co se zamítat NESMÍ ----------------------------------------------
    def test_cisty_worktree_se_zelenou_branou_projde(self) -> None:
        self.worktree("01")
        self.nacti("01", prikazy='python -c "pass"')
        self.assertEqual(self.zavolej(f'git -C "{self.repo}" merge ai/chip-01/pokus'),
                         (0, ""))

    def test_spinavy_hlavni_strom_merge_neblokuje(self) -> None:
        """Zjišťuje se stav STROMU CHIPU, ne cílového repa.

        Hlavní strom `CHIPS` je sám git worktree a při běžné práci v něm
        rozeditované soubory jsou. Kdyby se kontrola pouštěla na cíl merge,
        zablokovala by každý merge v denním provozu — to je falešný poplach,
        ne přísnost.
        """
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True,
                       capture_output=True)
        (self.repo / "rozeditovane.md").write_text("x", encoding="utf-8")
        self.worktree("01")
        self.nacti("01", prikazy='python -c "pass"')
        self.assertEqual(self.zavolej(f'git -C "{self.repo}" merge ai/chip-01/pokus'),
                         (0, ""))


# Příkaz brány, který dopadne PODLE STROMU, ve kterém běží: projde jen tam, kde
# leží `znak.txt`. Jinak by z výsledku nešlo poznat, kde se brána doopravdy
# spustila — a přesně to je vada, kterou chip 19 opravuje.
ZNAK = 'python -c "import os,sys; sys.exit(0 if os.path.exists(\'znak.txt\') else 1)"'


class ZakladCLI(Zaklad):
    """Fixture pro `chip_gate.main()` — brief se `stav:`/`worktree:` na míru."""

    def spust_main(self, *argv: str) -> tuple[int, str]:
        """`main()` s podstrčeným `--dir`; vrací (návratový kód, stdout)."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            kod = chip_gate.main([*argv, "--dir", str(self.chips)])
        return kod, buf.getvalue()

    def uprav_brief(self, cislo: str, co: str, cim: str,
                    prikazy: str = 'python -c "pass"'):
        """Brief chipu s jednou přepsanou hodnotou frontmatteru."""
        uloz_brief(self.chips, cislo, self.repo, prikazy)
        p = self.chips / f"{cislo}-pokus.md"
        p.write_text(p.read_text(encoding="utf-8").replace(co, cim), encoding="utf-8")
        chip_common.nastav_chips_dir(self.chips)
        return chip_gate.najdi_chip(cislo, None)

    def s_worktree(self, cislo: str, hodnota: str,
                   prikazy: str = 'python -c "pass"'):
        return self.uprav_brief(cislo, f"worktree: ../x-chip-{cislo}",
                                f"worktree: {hodnota}", prikazy)


class TestKdeSpustit(ZakladCLI):
    """Podle čeho CLI vybírá strom. `repo:` z briefu to být nesmí."""

    def vysledek(self, funkce, chip) -> tuple:
        """`('chyba',)` nebo `('ok', cesta)` — porovnatelný verdikt obou kopií."""
        try:
            return ("ok", funkce(chip, self.repo).resolve())
        except (chip_gate.NeniKdeSpustit, hook.NeniKdeOverit):
            return ("chyba",)

    def test_default_je_worktree_chipu(self) -> None:
        wt = self.worktree("01")
        c = self.nacti("01")
        self.assertEqual(chip_gate.kde_spustit(c, self.repo).resolve(), wt.resolve())

    def test_relativni_worktree_lezi_vedle_repa(self) -> None:
        """Stejné čtení hodnoty jako `chip_run.cesty()` — jen jméno adresáře.

        Kdyby se relativní cesta skládala s cwd, ukazovala by tatáž hodnota
        jinam podle toho, odkud se nástroj pustí.
        """
        wt = self.worktree("01")
        c = self.s_worktree("01", "./nekde/hloub/x-chip-01")
        self.assertEqual(chip_gate.kde_spustit(c, self.repo).resolve(), wt.resolve())

    def test_absolutni_worktree_plati_jak_je(self) -> None:
        jinde = self.tmp / "jinde"
        jinde.mkdir()
        c = self.s_worktree("02", jinde.as_posix())
        self.assertEqual(chip_gate.kde_spustit(c, self.repo).resolve(),
                         jinde.resolve())

    def test_nevyplnene_worktree_selze(self) -> None:
        """Tichý fallback na `repo:` je celá vada chipu 19."""
        c = self.s_worktree("03", "")
        with self.assertRaises(chip_gate.NeniKdeSpustit) as ctx:
            chip_gate.kde_spustit(c, self.repo)
        self.assertIn("worktree", str(ctx.exception))

    def test_chybejici_worktree_na_disku_selze(self) -> None:
        c = self.nacti("01")                       # ../x-chip-01 neexistuje
        with self.assertRaises(chip_gate.NeniKdeSpustit) as ctx:
            chip_gate.kde_spustit(c, self.repo)
        self.assertIn("chip_run.py", str(ctx.exception))

    def test_worktree_stejny_jako_repo_selze(self) -> None:
        """Táž falešná zelená, jen zapsaná v briefu (viz `hook.kde_overit`)."""
        c = self.s_worktree("04", self.repo.as_posix())
        with self.assertRaises(chip_gate.NeniKdeSpustit) as ctx:
            chip_gate.kde_spustit(c, self.repo)
        self.assertIn("PŘED mergem", str(ctx.exception))

    def test_relativni_worktree_bez_repa_selze(self) -> None:
        """Bez `repo:` není u relativní cesty podle čeho worktree umístit."""
        c = self.nacti("01")
        with self.assertRaises(chip_gate.NeniKdeSpustit) as ctx:
            chip_gate.kde_spustit(c, None)
        self.assertIn("repo:", str(ctx.exception))

    def test_relativni_cesta_sedne_s_chip_run(self) -> None:
        """#5: tutéž hodnotu musí `chip_run` i brána umístit na totéž místo.

        `chip_run.cesty()` worktree ZAKLÁDÁ, brána ho HLEDÁ — kdyby se rozešly,
        brána by nenašla strom, který sama metodika před chvílí vytvořila.
        """
        import chip_run

        self.worktree("01")
        c = self.s_worktree("01", "../x-chip-01")
        _, _, wt = chip_run.cesty(c)
        self.assertEqual(chip_gate.kde_spustit(c, self.repo).resolve(),
                         wt.resolve())

    def test_absolutni_cesta_sedne_s_chip_run(self) -> None:
        """Srovnáno chipem 24 (nález chipu 19, dřív očekávané selhání).

        U ABSOLUTNÍ hodnoty `worktree:` bralo `chip_run.cesty()` jen jméno
        adresáře a kladlo ho vedle repa, kdežto brána i `hook.kde_overit()` ji
        respektují, jak je — worktree tak vznikal jinde, než kam se brána
        dívá. Od chipu 24 čte `chip_run` absolutní zápis stejně jako brána:
        platí, jak je v briefu.
        """
        import chip_run

        hloub = self.tmp / "hloub"
        hloub.mkdir()
        wt_abs = hloub / "x-chip-01"
        wt_abs.mkdir()
        c = self.s_worktree("01", wt_abs.as_posix())
        _, _, wt = chip_run.cesty(c)
        self.assertEqual(chip_gate.kde_spustit(c, self.repo).resolve(),
                         wt.resolve())

    def test_brana_a_hook_resi_worktree_stejne(self) -> None:
        """CLI a hook nesmí o témž briefu rozhodnout jinak.

        Pravidlo je v projektu zapsané dvakrát (hláška musí radit podle
        kontextu — merge vs. `--repo`). Tenhle test je jediné, co obě kopie
        drží u sebe: rozejít se smí text, ne verdikt ani vybraný strom.
        """
        jinde = self.tmp / "jinde"
        jinde.mkdir()
        pripady = {
            "existující relativní": "../x-chip-01",
            "chybějící na disku": "../x-chip-99",
            "nevyplněné": "",
            "míří na repo": self.repo.as_posix(),
            "absolutní existující": jinde.as_posix(),
        }
        self.worktree("01")
        for popis, hodnota in pripady.items():
            with self.subTest(pripad=popis):
                c = self.s_worktree("01", hodnota)
                self.assertEqual(self.vysledek(chip_gate.kde_spustit, c),
                                 self.vysledek(hook.kde_overit, c))

    def test_run_brana_i_hook_umisti_worktree_stejne(self) -> None:
        """#5 chipu 24: tři místa, jeden brief, jedna cesta.

        `chip_run.cesty()` worktree ZAKLÁDÁ, `chip_gate.kde_spustit()` a
        `hook.kde_overit()` ho HLEDAJÍ — kdyby se kterékoli z nich rozešlo,
        vznikne strom, do kterého se brána nedívá. Shoda tří míst je vlastní
        obsah chipu 24; test výš drží u sebe jen bránu s hookem.
        """
        import chip_run

        jinde = self.tmp / "jinde"
        jinde.mkdir()
        self.worktree("01")
        pripady = {
            "relativní": "../x-chip-01",
            "relativní hluboká": "./nekde/hloub/x-chip-01",
            "absolutní": jinde.as_posix(),
        }
        for popis, hodnota in pripady.items():
            with self.subTest(pripad=popis):
                c = self.s_worktree("01", hodnota)
                _, _, wt_run = chip_run.cesty(c)
                self.assertEqual(chip_gate.kde_spustit(c, self.repo).resolve(),
                                 wt_run.resolve())
                self.assertEqual(hook.kde_overit(c, self.repo).resolve(),
                                 wt_run.resolve())


class TestMainStrom(ZakladCLI):
    """Jádro chipu 19: `chip_gate.py NN` bez `--repo` měří worktree chipu.

    Doloženo ve vlně 5: brána chipu 18 hlásila zelenou v hlavním stromě (454
    testů), zatímco ve worktree jich bylo 481. Testy níž na verzi před chipem
    19 selžou — tam se měřilo `repo:`.
    """

    def test_verdikt_podle_worktree_ne_podle_repa(self) -> None:
        """Worktree zelený, `repo:` červené → CLI musí vrátit ZELENOU."""
        wt = self.worktree("01")
        (wt / "znak.txt").write_text("x", encoding="utf-8")
        self.nacti("01", prikazy=ZNAK)
        kod, out = self.spust_main("01")
        self.assertEqual(kod, 0, f"brána měřila jiný strom než worktree:\n{out}")

    def test_zelena_v_repu_nezachrani_cerveny_worktree(self) -> None:
        """Opačný směr — tenhle je ta nebezpečná polovina.

        `repo:` projde (starý kód), worktree ne. Kdyby se měřilo repo, vyšla by
        zelená nad něčím, co se nemerguje.
        """
        self.worktree("01")
        (self.repo / "znak.txt").write_text("x", encoding="utf-8")
        self.nacti("01", prikazy=ZNAK)
        kod, out = self.spust_main("01")
        self.assertEqual(kod, 1, f"brána vrátila zelenou z hlavního stromu:\n{out}")

    def test_hlavicka_rekne_ve_kterem_stromu_bezela(self) -> None:
        wt = self.worktree("01")
        self.nacti("01")
        _, out = self.spust_main("01")
        self.assertIn(str(wt), out)
        self.assertIn("worktree", out)

    # --- selhání místo tichého fallbacku ----------------------------------
    def test_bez_worktree_selze_a_nespusti_ani_jeden_prikaz(self) -> None:
        stopa = self.tmp / "stopa.txt"
        self.s_worktree("01", "", prikazy=f'python -c "open(r\'{stopa}\',\'w\')"')
        kod, out = self.spust_main("01")
        self.assertEqual(kod, 1)
        self.assertFalse(stopa.exists(), "brána běžela, i když nebylo kde")
        self.assertIn("není kde spustit", out)

    def test_chybejici_worktree_selze_a_poradi_cim_ho_obnovit(self) -> None:
        self.nacti("01")                           # ../x-chip-01 neexistuje
        kod, out = self.spust_main("01")
        self.assertEqual(kod, 1)
        self.assertIn("chip_run.py", out)

    def test_worktree_mirici_na_repo_selze(self) -> None:
        self.s_worktree("01", self.repo.as_posix())
        kod, out = self.spust_main("01")
        self.assertEqual(kod, 1)
        self.assertIn("PŘED mergem", out)

    # --- stav `merged`: worktree po mergi neexistuje ----------------------
    def test_merged_chip_bez_worktree_neprojde_mlcky(self) -> None:
        """Rozhodnutí issue #8 (viz Log briefu 19): odmítnout, ne spadnout na repo.

        Po mergi je hlavní větev směs všech chipů — zelená odtamtud neplatí
        o tomhle chipu. Kdyby CLI mlčky přešlo na `repo:`, je to zpátky ta
        falešná zelená, jen u jiného stavu.
        """
        self.uprav_brief("01", "stav: ready", "stav: merged")
        kod, out = self.spust_main("01")
        self.assertEqual(kod, 1)
        self.assertIn("merged", out)
        self.assertIn("--repo", out)

    def test_merged_chip_jde_overit_pres_repo(self) -> None:
        self.uprav_brief("01", "stav: ready", "stav: merged")
        kod, _ = self.spust_main("01", "--repo", str(self.repo))
        self.assertEqual(kod, 0)


class TestMainRepoPrepinac(ZakladCLI):
    """Regrese: `--repo` je vědomá výjimka a chová se jako dřív."""

    def jinde(self) -> Path:
        p = self.tmp / "jinde"
        p.mkdir(exist_ok=True)
        return p

    def test_zelena_v_zadanem_stromu(self) -> None:
        (self.jinde() / "znak.txt").write_text("x", encoding="utf-8")
        self.nacti("01", prikazy=ZNAK)
        kod, out = self.spust_main("01", "--repo", str(self.jinde()))
        self.assertEqual(kod, 0, out)
        self.assertIn("ZELENÁ", out)

    def test_cervena_v_zadanem_stromu(self) -> None:
        self.nacti("01", prikazy=ZNAK)
        kod, out = self.spust_main("01", "--repo", str(self.jinde()))
        self.assertEqual(kod, 1)
        self.assertIn("ČERVENÁ", out)

    def test_repo_prebije_i_existujici_worktree(self) -> None:
        """Přednost má `--repo` — jinak by výjimka nebyla k ničemu."""
        wt = self.worktree("01")
        (wt / "znak.txt").write_text("x", encoding="utf-8")
        self.nacti("01", prikazy=ZNAK)
        self.assertEqual(self.spust_main("01", "--repo", str(self.jinde()))[0], 1)

    def test_repo_funguje_i_kdyz_worktree_neni_vyplneny(self) -> None:
        """Rozbitý brief nesmí zablokovat vědomé spuštění jinde."""
        self.s_worktree("01", "")
        self.assertEqual(self.spust_main("01", "--repo", str(self.repo))[0], 0)

    def test_neexistujici_repo_selze(self) -> None:
        self.nacti("01")
        kod, out = self.spust_main("01", "--repo", str(self.tmp / "nikde"))
        self.assertEqual(kod, 1)
        self.assertIn("neexistuje", out)

    def test_repo_na_hlavni_strom_z_briefu_se_oznaci(self) -> None:
        """Vědomá výjimka projde, ale hlavička musí říct, co se doopravdy měří."""
        self.worktree("01")
        self.nacti("01")
        kod, out = self.spust_main("01", "--repo", str(self.repo))
        self.assertEqual(kod, 0)
        self.assertIn("POZOR", out)

    def test_chip_nenalezen_vraci_jednicku(self) -> None:
        self.nacti("01")
        kod, out = self.spust_main("99")
        self.assertEqual(kod, 1)
        self.assertIn("nenalezen", out)
