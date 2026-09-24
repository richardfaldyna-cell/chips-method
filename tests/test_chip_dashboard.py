"""Testy stavové desky (`chip_dashboard.py`).

Jádro chipu je jediné tvrzení: **karta ukazuje stav z worktree, ne z hlavního
stromu**. Za běhu chipu se v hlavním stromě nehýbe nic, takže dashboard, který
by četl jeho briefy, by ukazoval včerejšek a tvářil se přitom jako živá data.
Proto tu fixture staví skutečné git repo se skutečnými worktree (`git worktree
add`) — nasimulovat se to nedá, právě rozdíl mezi kopiemi je předmětem testu.

Zbytek je rozdělený podle toho, co se smí pokazit: parsování gitového výstupu
(čisté funkce), vykreslení HTML (čistá funkce nad `Deska`), odolnost proti
chybějícímu a rozbitému worktree, a záruka „jen pro čtení".

Jen standardní knihovna, každý test si uklidí po sobě, `chip_common.CHIPS_DIR`
se v cleanupu vrací.
"""

from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import chip_common                                                   # noqa: E402
import chip_dashboard as dash                                        # noqa: E402

BRIEF = """---
chip: {id}
nazev: {nazev}
stav: {stav}
zavisi_na: {zavisi}
repo: {repo}
vetev: {vetev}
worktree: ../{worktree}
---

# CHIP {id} — {nazev}

## Issues

{issues}

## Dotčené soubory

```
tools/soubor_{id}.py    # nový
```

## Definition of done

- [ ] projde brána

## Ověření (brána)

```bash
python -m unittest discover -s tests
```

## Log

| Datum | Stav | Poznámka |
|---|---|---|
{log}
"""


def git(repo: Path, *args: str) -> None:
    """Git v testu selhat nesmí — `check=True`, ať se chyba neschová."""
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True)


def _povol_zapis(funkce, cesta, _chyba) -> None:
    """`rmtree` na Windows padá na read-only souborech v `.git/worktrees`."""
    os.chmod(cesta, stat.S_IWRITE)
    funkce(cesta)


def uklid(cesta: Path) -> None:
    handler = "onexc" if sys.version_info >= (3, 12) else "onerror"
    shutil.rmtree(cesta, ignore_errors=True, **{handler: _povol_zapis})


def snapshot(koren: Path) -> dict[str, bytes]:
    """Obsah všech souborů pod `koren` mimo `.git` — pro důkaz, že se nezapisuje."""
    out: dict[str, bytes] = {}
    for p in sorted(koren.rglob("*")):
        rel = p.relative_to(koren)
        if p.is_file() and ".git" not in rel.parts:
            out[str(rel)] = p.read_bytes()
    return out


def deska(*karty: dash.Karta, **kw) -> dash.Deska:
    """Deska bez I/O — vstup pro testy vykreslování."""
    kw.setdefault("ted", 1_700_000_000)
    return dash.Deska(karty=list(karty), **kw)


def karta(cislo: str = "01", **kw) -> dash.Karta:
    kw.setdefault("nazev", "pokus")
    kw.setdefault("stav", "running")
    return dash.Karta(id=cislo, **kw)


class TestParsujStatus(unittest.TestCase):
    """`git status --porcelain` → co má agent rozeditované."""

    def test_prazdny_vystup_je_cisty_strom(self) -> None:
        self.assertEqual(dash.parsuj_status(""), [])

    def test_zmeneny_a_netrackovany_soubor(self) -> None:
        z = dash.parsuj_status(" M tools/a.py\n?? tests/b.py\n")
        self.assertEqual([(x.kod, x.cesta) for x in z],
                         [(" M", "tools/a.py"), ("??", "tests/b.py")])

    def test_prejmenovani_bere_novou_cestu(self) -> None:
        # zajímá „kde agent je", ne odkud soubor přišel
        z = dash.parsuj_status("R  tools/stary.py -> tools/novy.py\n")
        self.assertEqual(z[0].cesta, "tools/novy.py")

    def test_cesta_v_uvozovkach_se_odbali(self) -> None:
        z = dash.parsuj_status('?? "tools/s mezerou.py"\n')
        self.assertEqual(z[0].cesta, "tools/s mezerou.py")

    def test_cesta_s_mezerou_bez_uvozovek_zustane_cela(self) -> None:
        z = dash.parsuj_status(" M docs/plan 1.md\n")
        self.assertEqual(z[0].cesta, "docs/plan 1.md")

    def test_hlavicka_branch_se_preskoci(self) -> None:
        # `--porcelain -b` přidá `## main...origin/main` — není to změna
        z = dash.parsuj_status("## main...origin/main\n M a.py\n")
        self.assertEqual(len(z), 1)

    def test_smeti_neshodi_parsovani(self) -> None:
        self.assertEqual(dash.parsuj_status("\n\nx\n  \n"), [])

    def test_oba_sloupce_stavu_se_zachovaji(self) -> None:
        # `MM` = změna v indexu i ve stromě; kód nese informaci, nesmí se slít
        self.assertEqual(dash.parsuj_status("MM a.py\n")[0].kod, "MM")


class TestParsujCommity(unittest.TestCase):

    def radek(self, sha="abc123def", kratky="abc123d", autor="agent",
              cas="1700000000", predmet="CHIP 01: něco") -> str:
        return dash.ODDELOVAC.join([sha, kratky, autor, cas, predmet]) + "\n"

    def test_jeden_commit(self) -> None:
        c = dash.parsuj_commity(self.radek(), chip="07")[0]
        self.assertEqual((c.sha, c.kratky, c.autor, c.cas, c.chip),
                         ("abc123def", "abc123d", "agent", 1700000000, "07"))

    def test_prazdny_vystup(self) -> None:
        self.assertEqual(dash.parsuj_commity(""), [])

    def test_oddelovac_v_predmetu_neurizne_zbytek(self) -> None:
        c = dash.parsuj_commity(self.radek(predmet="a" + dash.ODDELOVAC + "b"))[0]
        self.assertEqual(c.predmet, "a" + dash.ODDELOVAC + "b")

    def test_necitelny_radek_se_zahodi(self) -> None:
        self.assertEqual(dash.parsuj_commity("úplně jiný text\n"), [])

    def test_necislny_cas_se_zahodi(self) -> None:
        # bez timestampu se commit nedá zařadit do osy — lepší vynechat
        self.assertEqual(dash.parsuj_commity(self.radek(cas="včera")), [])

    def test_vic_commitu_drzi_poradi(self) -> None:
        vystup = self.radek(sha="a", cas="2") + self.radek(sha="b", cas="1")
        self.assertEqual([c.sha for c in dash.parsuj_commity(vystup)], ["a", "b"])


class TestOcasLogu(unittest.TestCase):

    LOG = ("| Datum | Stav | Poznámka |\n|---|---|---|\n"
           "| 2026-07-01 | ready | první |\n"
           "| 2026-07-02 | running | druhá |\n"
           "| 2026-07-03 | running | třetí |\n")

    def test_vraci_posledni_radky(self) -> None:
        self.assertEqual(dash.ocas_logu(self.LOG, 2),
                         [["2026-07-02", "running", "druhá"],
                          ["2026-07-03", "running", "třetí"]])

    def test_hlavicka_ani_oddelovac_se_nevraci(self) -> None:
        for radek in dash.ocas_logu(self.LOG, 10):
            self.assertNotIn("Poznámka", radek)
            self.assertNotIn("---", radek[0])

    def test_prazdna_tabulka_da_prazdno(self) -> None:
        self.assertEqual(dash.ocas_logu("| Datum | Stav |\n|---|---|\n"), [])

    def test_sekce_bez_tabulky(self) -> None:
        self.assertEqual(dash.ocas_logu("\nžádná tabulka\n"), [])

    def test_prazdny_vstup(self) -> None:
        self.assertEqual(dash.ocas_logu(""), [])

    def test_text_kolem_tabulky_se_ignoruje(self) -> None:
        self.assertEqual(len(dash.ocas_logu("úvod\n" + self.LOG + "\nzávěr\n", 9)), 3)


class TestZkratACas(unittest.TestCase):

    def test_kratky_text_zustane(self) -> None:
        self.assertEqual(dash.zkrat("krátká poznámka", 50), "krátká poznámka")

    def test_dlouhy_text_dostane_vypustku(self) -> None:
        out = dash.zkrat("a" * 100, 20)
        self.assertEqual(len(out), 20)
        self.assertTrue(out.endswith("…"))

    def test_zalomeni_se_slije_do_mezery(self) -> None:
        self.assertEqual(dash.zkrat("a\n b\tc", 50), "a b c")

    def test_neznamy_cas_je_pomlcka(self) -> None:
        self.assertEqual(dash.format_casu(0), "—")
        self.assertEqual(dash.stari(0, 1), "—")

    def test_stari_v_jednotkach(self) -> None:
        ted = 1_000_000
        for odchylka, cekano in ((30, "před 30 s"), (600, "před 10 min"),
                                 (7200, "před 2 h"), (3 * 86400, "před 3 d")):
            with self.subTest(odchylka=odchylka):
                self.assertEqual(dash.stari(ted - odchylka, ted), cekano)

    def test_budouci_cas_nedela_zaporne_stari(self) -> None:
        # hodiny se ve worktree i v repu můžou rozejít; „před -5 s" je nesmysl
        self.assertEqual(dash.stari(1_000_100, 1_000_000), "před 0 s")

    def test_format_casu_je_citelny(self) -> None:
        self.assertRegex(dash.format_casu(1_700_000_000),
                         r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


class TestSestavHtml(unittest.TestCase):
    """Vykreslení je čistá funkce nad `Deska` — žádný git, žádný disk."""

    def test_je_to_samostatny_html_dokument(self) -> None:
        out = dash.sestav_html(deska(karta()))
        self.assertTrue(out.startswith("<!DOCTYPE html>"))
        self.assertIn("<style>", out)
        self.assertIn("</html>", out)

    def test_zadny_externi_zdroj(self) -> None:
        """DoD: soubor musí fungovat offline — nesmí odkázat ven."""
        out = dash.sestav_html(deska(
            karta("01", zmeny=[dash.Zmena(" M", "tools/a.py")], zmen_celkem=1,
                  log=[["2026-07-01", "running", "poznámka"]],
                  posledni=dash.Commit("a" * 40, "abc1234", "agent",
                                       1_699_999_000, "CHIP 01: start", "01")),
            karta("02", stav="merged", poznamka="worktree není"),
            commity=[dash.Commit("b" * 40, "bbb1111", "agent", 1_699_999_500,
                                 "CHIP 02: konec", "02")]))
        for zakazane in ("http://", "https://", "src=", "<link", "<script",
                         "@import", "url("):
            with self.subTest(zakazane=zakazane):
                self.assertNotIn(zakazane, out)

    def test_karta_ma_stav_nazev_i_progress(self) -> None:
        out = dash.sestav_html(deska(karta("07", nazev="deska", stav="gated",
                                           hotovo=3, celkem=4)))
        self.assertIn(">07<", out)
        self.assertIn(">deska<", out)
        self.assertIn(">gated<", out)
        self.assertIn("issues 3/4 (75 %)", out)
        self.assertIn("width:75%", out)

    def test_chip_bez_worktree_rekne_proc(self) -> None:
        """Issue #6: chybějící data se nesmí vydávat za nulu."""
        out = dash.sestav_html(deska(
            karta("05", stav="merged", poznamka="worktree x na disku není")))
        self.assertIn("bez živých dat — worktree x na disku není", out)
        self.assertNotIn("živá data z worktree", out)

    def test_bezici_chip_bez_worktree_je_varovani(self) -> None:
        out = dash.sestav_html(deska(karta("05", stav="running", varovani=True,
                                           poznamka="worktree chybí")))
        self.assertIn("zdroj spatne", out)
        self.assertIn("pozor: chip 05 (running) — worktree chybí", out)

    def test_rozeditovane_soubory_jsou_videt(self) -> None:
        out = dash.sestav_html(deska(karta(
            zmeny=[dash.Zmena(" M", "tools/a.py"), dash.Zmena("??", "tests/b.py")],
            zmen_celkem=2, brief_z_worktree=True)))
        self.assertIn("rozeditováno (2)", out)
        self.assertIn("tools/a.py", out)
        self.assertIn("tests/b.py", out)

    def test_useknuty_seznam_rekne_kolik_chybi(self) -> None:
        out = dash.sestav_html(deska(karta(
            zmeny=[dash.Zmena(" M", f"a{i}.py") for i in range(3)],
            zmen_celkem=10, brief_z_worktree=True)))
        self.assertIn("… a další 7", out)

    def test_cisty_strom_se_rekne_nahlas(self) -> None:
        out = dash.sestav_html(deska(karta(brief_z_worktree=True)))
        self.assertIn("pracovní strom je čistý", out)

    def test_karta_bez_kopie_briefu_to_prizna(self) -> None:
        # živý worktree, ale brief jen z hlavního stromu — čísla nejsou živá
        out = dash.sestav_html(deska(karta(brief_z_worktree=False)))
        self.assertIn("brief jen z hlavního stromu", out)

    def test_vlny_maji_vlastni_nadpis_a_poradi(self) -> None:
        out = dash.sestav_html(deska(karta("03", vlna=1), karta("01", vlna=0),
                                     karta("02", vlna=0)))
        self.assertLess(out.index("vlna 0"), out.index("vlna 1"))
        self.assertLess(out.index(">01<"), out.index(">02<"))
        self.assertLess(out.index(">02<"), out.index(">03<"))

    def test_cyklicka_vlna_je_az_nakonec(self) -> None:
        out = dash.sestav_html(deska(karta("01", vlna=None), karta("02", vlna=2)))
        self.assertLess(out.index("vlna 2"), out.index("vlna neurčená"))

    def test_casova_osa_ma_commity_serazene(self) -> None:
        d = deska(karta(), commity=[
            dash.Commit("a" * 40, "aaa", "x", 1_699_999_900, "novější", "02"),
            dash.Commit("b" * 40, "bbb", "x", 1_699_999_000, "starší", "01")])
        out = dash.sestav_html(d)
        self.assertLess(out.index("novější"), out.index("starší"))

    def test_prazdna_osa_to_rekne(self) -> None:
        self.assertIn("žádné commity na chip větvích",
                      dash.sestav_html(deska(karta())))

    def test_watch_vlozi_meta_refresh(self) -> None:
        out = dash.sestav_html(deska(karta(), interval=15))
        self.assertIn('<meta http-equiv="refresh" content="15">', out)
        self.assertIn("obnova každých 15 s", out)

    def test_bez_watch_zadny_refresh(self) -> None:
        self.assertNotIn("refresh", dash.sestav_html(deska(karta())))

    def test_html_v_datech_se_escapuje(self) -> None:
        out = dash.sestav_html(deska(karta(nazev="<script>zle()</script>")))
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_dlouha_bunka_logu_se_uskrne(self) -> None:
        out = dash.sestav_html(deska(karta(log=[["d", "s", "x" * 500]])))
        self.assertNotIn("x" * 300, out)
        self.assertIn("…", out)

    def test_neznamy_stav_dostane_neutralni_tridu(self) -> None:
        # neplatný stav hlásí chip_lint; deska na něm nesmí spadnout
        self.assertIn("stav-jiny", dash.sestav_html(deska(karta(stav="vymyslený"))))

    def test_souhrn_scita_stavy_i_issues(self) -> None:
        text = dash.souhrn([karta("01", stav="running", hotovo=1, celkem=4),
                            karta("02", stav="merged", hotovo=3, celkem=3,
                                  poznamka="bez worktree")])
        self.assertIn("2 chipy", text)
        self.assertIn("running 1", text)
        self.assertIn("merged 1", text)
        self.assertIn("issues 4/7", text)
        self.assertIn("živá data z 1 worktree", text)

    def test_html_je_dobre_utvorene(self) -> None:
        """Párové značky sedí — bez toho by se v prohlížeči rozsypalo rozvržení."""
        prazdne = {"meta", "br", "hr", "img", "input", "link"}
        stack: list[str] = []

        class Kontrola(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag not in prazdne:
                    stack.append(tag)

            def handle_endtag(self, tag):
                if tag in prazdne:
                    return
                assert stack and stack[-1] == tag, f"{tag} vs {stack[-3:]}"
                stack.pop()

        Kontrola().feed(dash.sestav_html(deska(
            karta("01", zmeny=[dash.Zmena(" M", "a.py")], zmen_celkem=1,
                  log=[["d", "s", "p"]], brief_z_worktree=True,
                  posledni=dash.Commit("a" * 40, "abc", "x", 1_699_000_000, "s", "01")),
            karta("02", stav="merged", poznamka="bez worktree"),
            interval=10,
            commity=[dash.Commit("b" * 40, "bbb", "x", 1_699_000_000, "s", "02")])))
        self.assertEqual(stack, [])

    def test_skloneni_za_cislovkou(self) -> None:
        """Sdílené `chip_status._chipu` — dvě kopie pravidla by se rozešly."""
        for pocet, tvar in ((1, "1 chip "), (2, "2 chipy "), (5, "5 chipů ")):
            with self.subTest(pocet=pocet):
                karty = [karta(f"{i:02d}") for i in range(pocet)]
                self.assertIn(tvar, dash.souhrn(karty))
                self.assertIn(tvar, dash.sestav_html(deska(*karty)))

    def test_prazdna_deska_se_vykresli(self) -> None:
        out = dash.sestav_html(deska())
        self.assertIn("0 chipů", out)
        self.assertIn("</html>", out)

    def test_chip_bez_issues_nedeli_nulou(self) -> None:
        out = dash.sestav_html(deska(karta(hotovo=0, celkem=0)))
        self.assertIn("issues: žádné", out)
        self.assertIn("width:0%", out)


class ZakladRepo(unittest.TestCase):
    """Skutečné git repo + skutečné worktree — rozdíl mezi kopiemi je předmět testu."""

    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("git") is None:                       # pragma: no cover
            raise unittest.SkipTest("git není na PATH")

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="chip-dashboard-test-"))
        self.addCleanup(uklid, self.tmp)
        self.addCleanup(chip_common.nastav_chips_dir, chip_common.CHIPS_DIR)
        self.repo = self.tmp / "repo"
        self.chips = self.repo / "chips"
        self.chips.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "hlavni", str(self.repo)],
                       check=True, capture_output=True)
        git(self.repo, "config", "user.name", "test")
        git(self.repo, "config", "user.email", "test@test")
        git(self.repo, "config", "commit.gpgsign", "false")
        chip_common.nastav_chips_dir(self.chips)

    # -- stavba fixture -----------------------------------------------------

    def brief(self, cislo: str, *, nazev: str = "pokus", stav: str = "ready",
              issues: int = 4, hotovo: int = 0, zavisi: str = "",
              logu: int = 1, repo: str | None = None,
              kam: Path | None = None) -> Path:
        radky = "\n".join(f"- [{'x' if i < hotovo else ' '}] #{i + 1} — issue {i + 1}"
                          for i in range(issues)) or "- [ ] #1 — nic"
        log = "\n".join(f"| 2026-07-0{i + 1} | {stav} | poznámka {i + 1} |"
                        for i in range(logu))
        p = (kam or self.chips) / f"{cislo}-{nazev}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(BRIEF.format(
            id=cislo, nazev=nazev, stav=stav, zavisi=zavisi,
            repo=self.repo.as_posix() if repo is None else repo,
            vetev=f"ai/chip-{cislo}/{nazev}", worktree=f"repo-chip-{cislo}",
            issues=radky, log=log), encoding="utf-8")
        return p

    def commit(self, zprava: str = "chip") -> None:
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", zprava)

    def worktree(self, cislo: str, nazev: str = "pokus") -> Path:
        """Založí skutečný worktree chipu tam, kam ukazuje jeho frontmatter."""
        cesta = self.tmp / f"repo-chip-{cislo}"
        git(self.repo, "worktree", "add", "-q", str(cesta), "-b",
            f"ai/chip-{cislo}/{nazev}")
        return cesta

    def prepis(self, worktree: Path, cislo: str, **kw) -> Path:
        """Přepíše KOPII briefu ve worktree — hlavní strom zůstane, jak byl."""
        return self.brief(cislo, kam=worktree / "chips", **kw)

    def commit_ve_worktree(self, worktree: Path, zprava: str) -> None:
        git(worktree, "add", "-A")
        git(worktree, "commit", "-q", "-m", zprava)

    # -- spuštění -----------------------------------------------------------

    def sber(self, **kw) -> dash.Deska:
        return dash.posbirej(chip_common.nacti_vse(), ted=1_700_000_000,
                             chips_dir=str(self.chips), **kw)

    def karty(self, **kw) -> dict[str, dash.Karta]:
        return {k.id: k for k in self.sber(**kw).karty}

    def spust(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            kod = dash.main(["--dir", str(self.chips), *argv])
        return kod, buf.getvalue()


class TestZivaDataZWorktree(ZakladRepo):
    """Jádro chipu: čísla na kartě jsou z worktree, ne z hlavního stromu."""

    def test_progress_je_z_worktree_ne_z_hlavniho_stromu(self) -> None:
        self.brief("01", issues=4, hotovo=0)
        self.brief("02", issues=4, hotovo=0)
        self.commit()
        self.prepis(self.worktree("01"), "01", issues=4, hotovo=3)
        self.prepis(self.worktree("02"), "02", issues=4, hotovo=1)

        karty = self.karty()
        self.assertEqual((karty["01"].hotovo, karty["01"].celkem), (3, 4))
        self.assertEqual((karty["02"].hotovo, karty["02"].celkem), (1, 4))
        self.assertTrue(all(k.brief_z_worktree for k in karty.values()))
        # kontrola, že to opravdu není z hlavního stromu: ten pořád tvrdí nulu
        self.assertEqual(sum(len(c.hotove_issues())
                             for c in chip_common.nacti_vse()), 0)

    def test_stav_se_bere_z_worktree(self) -> None:
        # `chip_run.py --stav` přepisuje kopii ve worktree; hlavní strom
        # u běžícího chipu pořád tvrdí 'ready'
        self.brief("01", stav="ready")
        self.commit()
        self.prepis(self.worktree("01"), "01", stav="running")
        self.assertEqual(self.karty()["01"].stav, "running")

    def test_ocas_logu_je_z_worktree(self) -> None:
        self.brief("01", logu=1)
        self.commit()
        self.prepis(self.worktree("01"), "01", stav="running", logu=3)
        log = self.karty()["01"].log
        self.assertEqual(len(log), 3)
        self.assertEqual(log[-1][-1], "poznámka 3")

    def test_rozeditovane_soubory_z_git_status(self) -> None:
        self.brief("01")
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "stary.py").write_text("x = 0\n", encoding="utf-8")
        self.commit()
        w = self.worktree("01")
        (w / "tools" / "stary.py").write_text("x = 1\n", encoding="utf-8")
        (w / "tools" / "novy.py").write_text("y = 2\n", encoding="utf-8")
        k = self.karty()["01"]
        podle_cesty = {z.cesta: z.kod for z in k.zmeny}
        self.assertEqual(podle_cesty.get("tools/stary.py"), " M")
        self.assertEqual(podle_cesty.get("tools/novy.py"), "??")
        self.assertEqual(k.zmen_celkem, len(k.zmeny))

    def test_cisty_worktree_nema_zadne_zmeny(self) -> None:
        self.brief("01")
        self.commit()
        self.worktree("01")
        k = self.karty()["01"]
        self.assertTrue(k.zivo)
        self.assertEqual(k.zmeny, [])

    def test_seznam_zmen_se_useka_ale_pocet_zustane(self) -> None:
        self.brief("01")
        self.commit()
        w = self.worktree("01")
        for i in range(6):
            (w / f"soubor{i}.txt").write_text("x", encoding="utf-8")
        k = self.karty(limit_zmen=2)["01"]
        self.assertEqual(len(k.zmeny), 2)
        self.assertEqual(k.zmen_celkem, 6)

    def test_posledni_commit_na_vetvi_chipu(self) -> None:
        self.brief("01")
        self.commit()
        w = self.worktree("01")
        (w / "a.txt").write_text("x", encoding="utf-8")
        self.commit_ve_worktree(w, "CHIP 01: první kus")
        k = self.karty()["01"]
        self.assertIsNotNone(k.posledni)
        self.assertEqual(k.posledni.predmet, "CHIP 01: první kus")
        self.assertTrue(k.vetev_existuje)

    def test_casova_osa_ma_commity_chipu(self) -> None:
        self.brief("01")
        self.brief("02")
        self.commit()
        w1 = self.worktree("01")
        (w1 / "a.txt").write_text("x", encoding="utf-8")
        self.commit_ve_worktree(w1, "CHIP 01: krok")
        self.worktree("02")
        osa = self.sber().commity
        self.assertEqual([(c.chip, c.predmet) for c in osa],
                         [("01", "CHIP 01: krok")])

    def test_osa_neopakuje_spolecny_zaklad(self) -> None:
        # commity už obsažené v HEAD jsou společný základ, ne práce chipu
        self.brief("01")
        self.brief("02")
        self.commit()
        self.worktree("01")
        self.worktree("02")
        self.assertEqual(self.sber().commity, [])

    def test_cerstvy_worktree_ukazuje_jen_spolecny_zaklad(self) -> None:
        """Zděděný commit se nesmí tvářit jako práce chipu.

        Větev čerstvého worktree zdědí historii hlavní větve, takže „poslední
        commit" existuje hned — ale agent zatím nic neodevzdal.
        """
        self.brief("01")
        self.commit("společný základ")
        self.worktree("01")
        k = self.karty()["01"]
        self.assertTrue(k.vetev_existuje)
        self.assertEqual(k.posledni.predmet, "společný základ")
        self.assertFalse(k.posledni_je_chipu)

    def test_po_commitu_ve_worktree_je_posledni_prace_chipu(self) -> None:
        self.brief("01")
        self.commit("společný základ")
        w = self.worktree("01")
        (w / "a.txt").write_text("x", encoding="utf-8")
        self.commit_ve_worktree(w, "CHIP 01: odevzdáno")
        k = self.karty()["01"]
        self.assertTrue(k.posledni_je_chipu)
        self.assertEqual(k.posledni.predmet, "CHIP 01: odevzdáno")


class TestOdolnost(ZakladRepo):
    """Chybějící ani rozbitý worktree nesmí shodit desku (issue #6 a #11)."""

    def test_chip_bez_worktree_ma_kartu_a_duvod(self) -> None:
        self.brief("01", stav="merged", hotovo=4)
        self.commit()
        k = self.karty()["01"]
        self.assertFalse(k.zivo)
        self.assertIn("na disku není", k.poznamka)
        self.assertFalse(k.varovani)
        # karta pořád nese čísla z hlavního stromu — jen se ví, odkud jsou
        self.assertEqual((k.hotovo, k.celkem), (4, 4))
        self.assertFalse(k.brief_z_worktree)

    def test_bezici_chip_bez_worktree_je_varovani(self) -> None:
        self.brief("01", stav="running")
        self.commit()
        self.assertTrue(self.karty()["01"].varovani)

    def test_adresar_bez_git_neni_worktree(self) -> None:
        # bez `.git` by se git zeptal nadřazeného adresáře a odpověděl za cizí repo
        self.brief("01")
        self.commit()
        (self.tmp / "repo-chip-01").mkdir()
        k = self.karty()["01"]
        self.assertFalse(k.zivo)
        self.assertIn("chybí .git", k.poznamka)

    def test_rozbity_worktree_neshodi_zbytek_desky(self) -> None:
        self.brief("01")
        self.brief("02")
        self.commit()
        self.worktree("02")
        rozbity = self.tmp / "repo-chip-01"
        rozbity.mkdir()
        (rozbity / ".git").write_text("gitdir: /nikam/nevede\n", encoding="utf-8")

        karty = self.karty()
        self.assertIn("selhal", karty["01"].poznamka)
        self.assertTrue(karty["02"].zivo)          # zbytek se vykreslí
        self.assertIn("selhal", dash.sestav_html(self.sber()))

    def test_brief_bez_repa_to_prizna(self) -> None:
        self.brief("01", repo="")
        self.commit()
        k = self.karty()["01"]
        self.assertIn("repo:", k.poznamka)
        self.assertFalse(k.vetev_existuje)

    def test_worktree_bez_kopie_briefu(self) -> None:
        """Živý worktree, ale brief se do něj nedostal — čísla nejsou živá."""
        self.brief("01")
        self.commit()
        w = self.worktree("01")
        (w / "chips" / "01-pokus.md").unlink()
        k = self.karty()["01"]
        self.assertTrue(k.zivo)
        self.assertFalse(k.brief_z_worktree)
        self.assertIn("brief jen z hlavního stromu", dash.sestav_html(self.sber()))

    def test_nectitelny_brief_ve_worktree_neshodi_kartu(self) -> None:
        # agent do briefu právě píše; karta si nechá čísla z hlavního stromu
        self.brief("01", hotovo=2)
        self.commit()
        self.worktree("01")
        with patch.object(dash, "parse", side_effect=OSError("právě se zapisuje")):
            k = self.karty()["01"]
        self.assertTrue(k.zivo)
        self.assertFalse(k.brief_z_worktree)
        self.assertEqual(k.hotovo, 2)

    def test_cely_dashboard_nad_repem_bez_chipu(self) -> None:
        d = self.sber()
        self.assertEqual(d.karty, [])
        self.assertIn("0 chipů", dash.sestav_html(d))


class TestJenProCteni(ZakladRepo):
    """Issue #10: nástroj nesmí zapsat nikam než do výstupního HTML."""

    def test_zapisujici_git_prikaz_je_odmitnut(self) -> None:
        for prikaz in ("commit", "add", "checkout", "worktree", "merge"):
            with self.subTest(prikaz=prikaz):
                with self.assertRaises(dash.ChybaJenCteni):
                    dash._git(self.repo, prikaz)

    def test_vsechny_git_prikazy_pri_sberu_jsou_ctouci(self) -> None:
        self.brief("01")
        self.commit()
        self.worktree("01")
        volani: list[list[str]] = []
        puvodni = subprocess.run

        def zaznam(cmd, *a, **kw):
            volani.append(list(cmd))
            return puvodni(cmd, *a, **kw)

        with patch.object(dash.subprocess, "run", zaznam):
            self.sber()
        self.assertTrue(volani, "sběr nespustil git — test by nic neověřil")
        for cmd in volani:
            self.assertEqual(cmd[:2], ["git", "-C"], cmd)
            self.assertIn(cmd[3], dash.POVOLENE_GIT, cmd)

    def test_beh_nezmeni_nic_krome_vystupu(self) -> None:
        """Snímek stromu před a po. `.git` se vynechává schválně.

        Tam sahá git sám: i `git status` si osvěží svůj `index`. Tvrzení
        „nástroj nezapisuje" se týká pracovních souborů, ne interní cache gitu.
        """
        self.brief("01", stav="running")
        self.commit()
        w = self.worktree("01")
        (w / "rozdelano.txt").write_text("x", encoding="utf-8")
        cil = self.tmp / "dashboard.html"

        pred = snapshot(self.tmp)
        kod, _ = self.spust("--out", str(cil))
        po = snapshot(self.tmp)

        self.assertEqual(kod, 0)
        self.assertEqual(set(po) - set(pred), {"dashboard.html"})
        self.assertEqual(set(pred) - set(po), set())
        zmenene = [c for c in pred if pred[c] != po[c]]
        self.assertEqual(zmenene, [])

    def test_chybejici_adresar_vystupu_se_nezaklada(self) -> None:
        self.brief("01")
        self.commit()
        cil = self.tmp / "nova" / "slozka" / "d.html"
        kod, out = self.spust("--out", str(cil))
        self.assertEqual(kod, 1)
        self.assertIn("neexistuje", out)
        self.assertFalse(cil.parent.exists())


class TestMain(ZakladRepo):
    """CLI: `--out`, `--dir`, `--watch`, `--interval`, `--opakovat`."""

    def setUp(self) -> None:
        super().setUp()
        self.cil = self.tmp / "dashboard.html"

    def test_vygeneruje_soubor_a_vrati_nulu(self) -> None:
        self.brief("01", nazev="deska", stav="running")
        self.commit()
        self.worktree("01", "deska")
        kod, out = self.spust("--out", str(self.cil))
        self.assertEqual(kod, 0)
        self.assertTrue(self.cil.exists())
        html = self.cil.read_text(encoding="utf-8")
        self.assertIn("deska", html)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("1 chip ", out)

    def test_vystup_nema_odkaz_ven(self) -> None:
        """DoD: hotový soubor musí fungovat offline."""
        self.brief("01", stav="running", hotovo=2)
        self.commit()
        w = self.worktree("01")
        (w / "rozdelano.txt").write_text("x", encoding="utf-8")
        self.commit_ve_worktree(w, "CHIP 01: krok")
        self.spust("--out", str(self.cil))
        html = self.cil.read_text(encoding="utf-8")
        for zakazane in ("http://", "https://", "src=", "<link", "<script"):
            with self.subTest(zakazane=zakazane):
                self.assertNotIn(zakazane, html)

    def test_watch_vlozi_meta_refresh(self) -> None:
        self.brief("01")
        self.commit()
        self.spust("--out", str(self.cil), "--watch", "--interval", "7")
        self.assertIn('<meta http-equiv="refresh" content="7">',
                      self.cil.read_text(encoding="utf-8"))

    def test_bez_watch_neni_refresh(self) -> None:
        self.brief("01")
        self.commit()
        self.spust("--out", str(self.cil), "--interval", "7")
        self.assertNotIn("refresh", self.cil.read_text(encoding="utf-8"))

    def test_nulovy_interval_je_chyba(self) -> None:
        kod, out = self.spust("--out", str(self.cil), "--interval", "0")
        self.assertEqual(kod, 1)
        self.assertIn("--interval", out)
        self.assertFalse(self.cil.exists())

    def test_opakovat_generuje_dokola_dokud_neprijde_ctrl_c(self) -> None:
        self.brief("01")
        self.commit()
        spanky = {"n": 0}

        def falesny_spanek(_sekund) -> None:
            spanky["n"] += 1
            if spanky["n"] >= 2:
                raise KeyboardInterrupt

        with patch.object(dash.time, "sleep", falesny_spanek):
            kod, out = self.spust("--out", str(self.cil), "--watch",
                                  "--opakovat", "--interval", "1")
        self.assertEqual(kod, 0)
        self.assertEqual(spanky["n"], 2)
        self.assertEqual(out.count(str(self.cil)), 2)   # dvě generování
        self.assertIn("Ctrl+C", out)

    def test_bez_opakovat_se_negeneruje_znovu(self) -> None:
        self.brief("01")
        self.commit()
        with patch.object(dash.time, "sleep",
                          side_effect=AssertionError("nemá se spát")):
            self.assertEqual(self.spust("--out", str(self.cil))[0], 0)

    def test_dir_umi_cizi_adresar_s_briefy(self) -> None:
        """Issue #9: nástroj jde pustit nad chipy mimo tenhle repo."""
        cizi = self.tmp / "cizi-chipy"      # briefy úplně mimo repo
        cizi.mkdir()
        self.brief("09", nazev="cizak", kam=cizi)
        buf = io.StringIO()
        with redirect_stdout(buf):
            kod = dash.main(["--dir", str(cizi), "--out", str(self.cil)])
        self.assertEqual(kod, 0)
        self.assertIn("cizak", self.cil.read_text(encoding="utf-8"))
        self.assertIn(str(cizi), self.cil.read_text(encoding="utf-8"))

    def test_prazdny_adresar_s_briefy_neshodi_beh(self) -> None:
        kod, out = self.spust("--out", str(self.cil))
        self.assertEqual(kod, 0)
        self.assertIn("žádné chipy", out)
        self.assertIn("0 chipů", self.cil.read_text(encoding="utf-8"))

    def test_sablona_se_nepocita_mezi_chipy(self) -> None:
        (self.chips / "TEMPLATE.md").write_text("# šablona\n", encoding="utf-8")
        kod, out = self.spust("--out", str(self.cil))
        self.assertEqual(kod, 0)
        self.assertIn("žádné chipy", out)

    def test_opakovany_beh_prepise_stejny_soubor(self) -> None:
        self.brief("01")
        self.commit()
        self.spust("--out", str(self.cil))
        prvni = self.cil.read_text(encoding="utf-8")
        self.brief("02")
        self.commit()
        self.spust("--out", str(self.cil))
        druhy = self.cil.read_text(encoding="utf-8")
        self.assertNotEqual(prvni, druhy)
        self.assertIn("2 chipy", druhy)

    def test_karty_jsou_serazene_podle_id(self) -> None:
        for cislo in ("03", "01", "02"):
            self.brief(cislo, nazev=f"chip{cislo}")
        self.commit()
        self.spust("--out", str(self.cil))
        html = self.cil.read_text(encoding="utf-8")
        self.assertLess(html.index("chip01"), html.index("chip02"))
        self.assertLess(html.index("chip02"), html.index("chip03"))

    def test_vlny_se_pocitaji_ze_zavislosti(self) -> None:
        self.brief("01")
        self.brief("02", zavisi="01")
        self.commit()
        html_text = (self.spust("--out", str(self.cil)),
                     self.cil.read_text(encoding="utf-8"))[1]
        self.assertIn("vlna 0", html_text)
        self.assertIn("vlna 1", html_text)
