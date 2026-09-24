"""Testy nezávislé kontroly chipu (`chip_review.py`).

Nástroj má jednu tvrdou pravomoc — kontrolu rozsahu (exit 1) — a zbytek jsou
podklady. Testuje se proto hlavně to, KDY nález vznikne a kdy ne: falešný nález
by z podkladů udělal bránu, přehlédnutý by z kontroly udělal razítko.

Od chipu 21 se stejně tvrdě testuje i DRUH signálu. Otázka vypsaná jako nález
je falešný poplach, který si vychová čtenáře přeskakujícího celou sekci, a
nález schovaný mezi otázkami je razítko — obojí je tady zamčené testem.

Fixture je skutečné git repo v `tempfile` (numstat se nedá věrohodně nasimulovat)
a vlastní adresář s chipy; `chip_common.CHIPS_DIR` se v tearDown vrací.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import chip_common                                                    # noqa: E402
import chip_review                                                    # noqa: E402

BRIEF = """---
chip: {cislo}
nazev: pokus
stav: running
zavisi_na:
repo: {repo}
vetev: chip/{cislo}-pokus
worktree: ../x-chip-{cislo}
---

# CHIP {cislo}

## Issues

- [x] #1 — něco
- [ ] #2 — něco dalšího

## Dotčené soubory

```
tools/novy.py         # nový
tests/test_novy.py    # nový
```

## Definition of done

- [x] testy projdou
- [ ] dokumentace

## Ověření (brána)

```bash
python -m unittest discover -s tests
```
"""

TESTY_ZDROJ = '''\
import unittest


class Zaklad(unittest.TestCase):
    def pomocna(self):
        return 1


class TestPoctivy(Zaklad):
    def test_ma_assert(self):
        self.assertEqual(1, 1)

    def test_kontext(self):
        with self.assertRaises(ValueError):
            raise ValueError("x")

    def test_hole_assert(self):
        assert True

    def test_fail_vetev(self):
        if False:
            self.fail("nikdy")
        self.assertTrue(True)

    def pomocny_neni_test(self):
        pass


class TestPodezrely(unittest.TestCase):
    def test_bez_assertu(self):
        vysledek = 1 + 1
        print(vysledek)

    @unittest.skip("zatím ne")
    def test_preskoceny(self):
        self.assertTrue(True)

    @unittest.expectedFailure
    def test_ocekavany_pad(self):
        self.assertTrue(False)


class NeniTestCase:
    def test_vypada_jako_test(self):
        pass
'''

CISTY_ZDROJ = '''\
import unittest


class TestCisty(unittest.TestCase):
    def test_neco(self):
        self.assertEqual(1, 1)
'''


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class Zaklad(unittest.TestCase):
    """Skutečné git repo s jedním commitem + adresář chips/."""

    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("git") is None:                       # pragma: no cover
            raise unittest.SkipTest("git není na PATH")

    def setUp(self) -> None:
        self.puvodni_dir = chip_common.CHIPS_DIR
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "repo"
        self.chips = self.repo / "chips"
        (self.repo / "tools").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        self.chips.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(self._vrat_dir)

        subprocess.run(["git", "init", "-q", str(self.repo)], check=True,
                       capture_output=True)
        self.brief = self.uloz_brief("07")
        self.zapis("tools/novy.py", "def f():\n    return 1\n")
        self.zapis("tests/test_novy.py", TESTY_ZDROJ)
        self.commit()

    def _vrat_dir(self) -> None:
        chip_common.CHIPS_DIR = self.puvodni_dir

    def zapis(self, cesta: str, text: str) -> Path:
        p = self.repo / cesta
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def uloz_brief(self, cislo: str) -> Path:
        p = self.chips / f"{cislo}-pokus.md"
        p.write_text(BRIEF.format(cislo=cislo, repo=self.repo.as_posix()),
                     encoding="utf-8")
        return p

    def prepis_dod(self, dod: int, prikazy: int) -> None:
        """Brief s N odškrtnutými body DoD a M příkazy brány.

        Poměr bodů k příkazům je jádro chipu 21 — musí jít nastavit přesně,
        ne odhadem přes editaci jednotlivých řádků.
        """
        text = self.brief.read_text(encoding="utf-8")
        text = text.replace("- [x] testy projdou\n- [ ] dokumentace\n",
                            "".join(f"- [x] bod {i}\n" for i in range(1, dod + 1)))
        text = text.replace("python -m unittest discover -s tests\n",
                            "".join(f"python overeni{i}.py\n"
                                    for i in range(1, prikazy + 1)))
        self.brief.write_text(text, encoding="utf-8")

    def ciste_zmeny(self) -> None:
        """Commit, na kterém nemá nástroj co najít — oba nároky, poctivé testy."""
        self.zapis("tools/novy.py", "def f():\n    return 2\n")
        self.zapis("tests/test_novy.py", CISTY_ZDROJ)
        self.commit("cisty")

    def commit(self, zprava: str = "chip") -> None:
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@t",
            "-c", "commit.gpgsign=false", "commit", "-q", "-m", zprava)

    def chip(self, cislo: str = "07"):
        chip_common.nastav_chips_dir(self.chips)
        return next(c for c in chip_common.nacti_vse() if c.id == cislo)

    def spust(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            kod = chip_review.main(list(argv))
        return kod, buf.getvalue()


class TestNumstat(unittest.TestCase):
    """Parsování `git --numstat` — na něm stojí seznam souborů i poměr řádků."""

    def test_bezny_radek(self) -> None:
        z = chip_review.parsuj_numstat("12\t3\ttools/a.py\n")
        self.assertEqual((z[0].cesta, z[0].pridano, z[0].ubrano), ("tools/a.py", 12, 3))

    def test_binarni_soubor(self) -> None:
        z = chip_review.parsuj_numstat("-\t-\tdocs/obr.png\n")[0]
        self.assertTrue(z.binarni)
        self.assertEqual((z.pridano, z.ubrano), (0, 0))

    def test_prazdne_a_rozbite_radky_se_ignoruji(self) -> None:
        self.assertEqual(chip_review.parsuj_numstat("\n\nnesmysl\n1\t1\t\n"), [])

    def test_prejmenovani_slozenymi_zavorkami(self) -> None:
        self.assertEqual(chip_review.cesta_z_numstat("tools/{a.py => b.py}"),
                         "tools/b.py")

    def test_prejmenovani_bez_zavorek(self) -> None:
        self.assertEqual(chip_review.cesta_z_numstat("a.py => tools/b.py"),
                         "tools/b.py")

    def test_presun_do_jineho_adresare(self) -> None:
        self.assertEqual(chip_review.cesta_z_numstat("{ => tools}/b.py"), "tools/b.py")

    def test_ref_konce_rozsahu(self) -> None:
        self.assertEqual(chip_review.ref_konce("main..chip/07"), "chip/07")
        self.assertEqual(chip_review.ref_konce("HEAD"), "HEAD")


class TestZmeny(Zaklad):
    """Čtení commitu z opravdového repa (#1)."""

    def test_soubory_commitu(self) -> None:
        cesty = {z.cesta for z in chip_review.zmeny(self.repo)}
        self.assertIn("tools/novy.py", cesty)
        self.assertIn("tests/test_novy.py", cesty)

    def test_diff_stat_je_kladny(self) -> None:
        z = next(z for z in chip_review.zmeny(self.repo) if z.cesta == "tools/novy.py")
        self.assertEqual((z.pridano, z.ubrano), (2, 0))

    def test_rozsah_dvou_commitu(self) -> None:
        self.zapis("tools/novy.py", "def f():\n    return 2\n")
        self.commit("druhy")
        cesty = [z.cesta for z in chip_review.zmeny(self.repo, "HEAD~1..HEAD")]
        self.assertEqual(cesty, ["tools/novy.py"])

    def test_neznamy_ref_hlasi_chybu(self) -> None:
        with self.assertRaises(chip_review.GitChyba):
            chip_review.zmeny(self.repo, "neexistujici-ref")

    def test_obsah_z_pracovniho_stromu(self) -> None:
        self.assertIn("def f()", chip_review.obsah(self.repo, "tools/novy.py"))

    def test_obsah_smazaneho_souboru_z_commitu(self) -> None:
        (self.repo / "tools" / "novy.py").unlink()
        self.assertIn("def f()", chip_review.obsah(self.repo, "tools/novy.py"))

    def test_obsah_neexistujiciho_je_none(self) -> None:
        self.assertIsNone(chip_review.obsah(self.repo, "tools/nikdy.py"))


class TestRozsah(Zaklad):
    """Kontrola rozsahu (#2) — jediný tvrdý nález celého nástroje."""

    def test_narokovane_cesty_projdou(self) -> None:
        self.assertEqual(
            chip_review.mimo_narok(self.chip(), ["tools/novy.py", "tests/test_novy.py"]),
            [])

    def test_podstrceny_soubor_je_nalez(self) -> None:
        self.assertEqual(
            chip_review.mimo_narok(self.chip(), ["tools/chip_gate.py"]),
            ["tools/chip_gate.py"])

    def test_vlastni_brief_je_povoleny(self) -> None:
        self.assertEqual(chip_review.mimo_narok(self.chip(), ["chips/07-pokus.md"]), [])

    def test_html_vlastniho_briefu_je_povolene(self) -> None:
        self.assertEqual(chip_review.mimo_narok(self.chip(), ["chips/07-pokus.html"]), [])

    def test_cizi_brief_je_nalez(self) -> None:
        self.assertEqual(chip_review.mimo_narok(self.chip(), ["chips/08-jiny.md"]),
                         ["chips/08-jiny.md"])

    def test_adresarovy_narok_pokryje_soubor(self) -> None:
        self.brief.write_text(
            self.brief.read_text(encoding="utf-8").replace("tools/novy.py", "tools"),
            encoding="utf-8")
        self.assertEqual(chip_review.mimo_narok(self.chip(), ["tools/hluboko/x.py"]), [])

    def test_vzor_v_naroku_pokryje_soubor(self) -> None:
        self.brief.write_text(
            self.brief.read_text(encoding="utf-8").replace("tools/novy.py", "tools/*.py"),
            encoding="utf-8")
        self.assertEqual(chip_review.mimo_narok(self.chip(), ["tools/jiny.py"]), [])

    def test_nedotceny_narok_se_hlasi(self) -> None:
        self.assertEqual(chip_review.nedotcene_naroky(self.chip(), ["tools/novy.py"]),
                         ["tests/test_novy.py"])

    def test_soubor_mimo_narok_je_tvrdy_nalez(self) -> None:
        """Tvrdé pravidlo metodiky — nesmí zjemnět na otázku (eskalace T3)."""
        _, signaly = chip_review.sekce_rozsah(
            self.chip(), [chip_review.Zmena("tools/chip_gate.py", 1, 0)])
        tvrde = [s for s in signaly if s.tvrdy]
        self.assertEqual(len(tvrde), 1)
        self.assertEqual(tvrde[0].druh, chip_review.NALEZ)
        self.assertIn("MIMO NÁROK: tools/chip_gate.py", tvrde[0].text)

    def test_nedotceny_narok_je_nalez_ne_otazka(self) -> None:
        _, signaly = chip_review.sekce_rozsah(
            self.chip(), [chip_review.Zmena("tools/novy.py", 1, 0)])
        self.assertEqual([s.druh for s in signaly], [chip_review.NALEZ])
        self.assertFalse(signaly[0].tvrdy)

    def test_cisty_rozsah_nevyda_signal(self) -> None:
        _, signaly = chip_review.sekce_rozsah(
            self.chip(), [chip_review.Zmena("tools/novy.py", 1, 0),
                          chip_review.Zmena("tests/test_novy.py", 1, 0)])
        self.assertEqual(signaly, [])


class TestPodezreleTesty(unittest.TestCase):
    """Detekce testů, které nic neověřují (#3) — přes `ast`, ne regexem."""

    def nalezy(self, zdroj: str = TESTY_ZDROJ) -> str:
        return "\n".join(p for _, p in chip_review.podezrele_testy(zdroj, "t.py"))

    def test_metoda_bez_assertu(self) -> None:
        self.assertIn("TestPodezrely.test_bez_assertu", self.nalezy())

    def test_preskoceny_test(self) -> None:
        self.assertIn("@skip", self.nalezy())

    def test_expected_failure(self) -> None:
        self.assertIn("@expectedFailure", self.nalezy())

    def test_poctive_testy_se_nehlasi(self) -> None:
        nalezy = self.nalezy()
        for jmeno in ("test_ma_assert", "test_kontext", "test_hole_assert",
                      "test_fail_vetev"):
            self.assertNotIn(jmeno, nalezy)

    def test_podtrida_vlastniho_zakladu_se_kontroluje(self) -> None:
        """`class TestX(Zaklad)` je pořád TestCase — jinak by se dala schovat."""
        zdroj = ("import unittest\n"
                 "class Zaklad(unittest.TestCase):\n    pass\n"
                 "class TestX(Zaklad):\n    def test_nic(self):\n        pass\n")
        self.assertIn("TestX.test_nic", self.nalezy(zdroj))

    def test_trida_mimo_unittest_se_neresi(self) -> None:
        self.assertNotIn("NeniTestCase", self.nalezy())

    def test_pomocna_metoda_se_neresi(self) -> None:
        self.assertNotIn("pomocny_neni_test", self.nalezy())

    def test_assert_v_retezci_neplati(self) -> None:
        """Regex by na tomhle selhal — proto `ast`."""
        zdroj = ("import unittest\n"
                 "class TestX(unittest.TestCase):\n"
                 "    def test_nic(self):\n        s = 'self.assertEqual(1, 1)'\n")
        self.assertIn("žádný assert", self.nalezy(zdroj))

    def test_rozbita_syntaxe_je_nalez(self) -> None:
        self.assertIn("nelze naparsovat", self.nalezy("def ("))

    def test_cislo_radku_je_v_nalezu(self) -> None:
        radek = chip_review.podezrele_testy(TESTY_ZDROJ, "t.py")[0][0]
        self.assertGreater(radek, 0)

    def test_je_test_pozna_testovaci_soubory(self) -> None:
        self.assertTrue(chip_review.je_test("tests/test_x.py"))
        self.assertTrue(chip_review.je_test("tests/pomocnik.py"))
        self.assertFalse(chip_review.je_test("tools/chip_review.py"))
        self.assertFalse(chip_review.je_test("tests/data/vzorek.md"))


class TestDodAPomer(Zaklad):
    """DoD vedle brány (#4) a poměr řádků (#5)."""

    def test_dod_rozlisi_odskrtnute(self) -> None:
        self.assertEqual(chip_review.dod_body(self.chip()),
                         [(True, "testy projdou"), (False, "dokumentace")])

    def test_sekce_dod_ukaze_prikazy_brany(self) -> None:
        radky, _ = chip_review.sekce_dod(self.chip())
        self.assertIn("unittest discover", "\n".join(radky))
        self.assertIn("[x] testy projdou", "\n".join(radky))

    def test_pomer_dod_a_brany_je_otazka_ne_nalez(self) -> None:
        """Jádro chipu 21: 8 bodů proti 2 příkazům je normální stav, ne nález."""
        self.prepis_dod(dod=8, prikazy=2)
        _, signaly = chip_review.sekce_dod(self.chip())
        self.assertEqual(chip_review.vyber(signaly, chip_review.NALEZ), [])
        otazky = chip_review.vyber(signaly, chip_review.OTAZKA)
        self.assertEqual(len(otazky), 1)
        self.assertIn("8 odškrtnutých bodů DoD proti 2 příkazům", otazky[0].text)

    def test_otazka_o_dod_rika_co_overit(self) -> None:
        """Podnět bez pokynu je pořád jen šum — musí být poznat, co se má udělat."""
        self.prepis_dod(dod=8, prikazy=2)
        _, signaly = chip_review.sekce_dod(self.chip())
        self.assertIn("ověř", chip_review.vyber(signaly, chip_review.OTAZKA)[0].text)

    def test_vyrovnany_pomer_nevyda_zadny_signal(self) -> None:
        self.prepis_dod(dod=2, prikazy=2)
        _, signaly = chip_review.sekce_dod(self.chip())
        self.assertEqual(signaly, [])

    def test_brief_bez_bodu_dod_je_nalez(self) -> None:
        self.prepis_dod(dod=0, prikazy=2)
        _, signaly = chip_review.sekce_dod(self.chip())
        self.assertEqual([s.druh for s in signaly], [chip_review.NALEZ])
        self.assertIn("jediný bod", signaly[0].text)

    def test_brana_bez_prikazu_je_nalez(self) -> None:
        """Odškrtnutí, které nemá co ověřit, je vada — a hlásí se jen jednou."""
        self.prepis_dod(dod=3, prikazy=0)
        _, signaly = chip_review.sekce_dod(self.chip())
        self.assertEqual([s.druh for s in signaly], [chip_review.NALEZ])
        self.assertIn("nespouští jediný příkaz", signaly[0].text)

    def test_pomer_deli_radky_podle_typu(self) -> None:
        seznam = [chip_review.Zmena("tests/test_a.py", 40, 0),
                  chip_review.Zmena("tools/a.py", 20, 0),
                  chip_review.Zmena("chips/07.md", 5, 0)]
        self.assertEqual(chip_review.pomer(seznam), (40, 20, 5))

    def test_pomer_bez_kodu_nedeli_nulou(self) -> None:
        radky, signaly = chip_review.sekce_pomer(
            [chip_review.Zmena("tests/test_a.py", 40, 0)])
        self.assertIn("žádný přidaný řádek kódu", "\n".join(radky))
        self.assertEqual(signaly, [])


class TestSekceTesty(Zaklad):
    """Kdy je chybějící test nález a kdy se o něm nemá cenu zmiňovat."""

    def test_podezrely_test_je_nalez(self) -> None:
        radky, signaly = chip_review.sekce_testy(
            self.repo, [chip_review.Zmena("tests/test_novy.py", 1, 0)])
        nalezy = chip_review.vyber(signaly, chip_review.NALEZ)
        self.assertTrue(any("test_bez_assertu" in s.text for s in nalezy))
        self.assertNotIn("OK —", "\n".join(radky))

    def test_sekce_neni_nikdy_holy_nadpis(self) -> None:
        """Nadpis nad prázdnem je taky šum — sekce musí říct, co prošla."""
        for zmena in (chip_review.Zmena("tests/test_novy.py", 1, 0),
                      chip_review.Zmena("tools/novy.py", 1, 0),
                      chip_review.Zmena("docs/x.md", 1, 0)):
            radky, _ = chip_review.sekce_testy(self.repo, [zmena])
            self.assertGreater(len(radky), 1, zmena.cesta)

    def test_kod_bez_jedineho_testu_je_nalez(self) -> None:
        _, signaly = chip_review.sekce_testy(
            self.repo, [chip_review.Zmena("tools/novy.py", 5, 0)])
        self.assertEqual([s.druh for s in signaly], [chip_review.NALEZ])
        self.assertIn("tools/novy.py", signaly[0].text)

    def test_commit_jen_s_dokumentaci_nic_nehlasi(self) -> None:
        """Zúžení chipu 21: chip, který mění jen dokumentaci, testy měnit nemá proč."""
        radky, signaly = chip_review.sekce_testy(
            self.repo, [chip_review.Zmena("docs/metodika.md", 30, 2),
                        chip_review.Zmena("chips/07-pokus.html", 40, 0)])
        self.assertEqual(signaly, [])
        self.assertIn("nemění kód ani testy", "\n".join(radky))

    def test_neprecteny_soubor_je_otazka(self) -> None:
        """Nástroj nemá co posoudit — to není tvrzení o kódu, ale úkol pro čtenáře."""
        _, signaly = chip_review.sekce_testy(
            self.repo, [chip_review.Zmena("tests/test_chybi.py", 1, 0)])
        self.assertEqual([s.druh for s in signaly], [chip_review.OTAZKA])
        self.assertIn("nepodařilo přečíst", signaly[0].text)

    def test_kodove_soubory_vynechaji_testy_a_dokumentaci(self) -> None:
        seznam = [chip_review.Zmena("tests/test_a.py"), chip_review.Zmena("docs/x.md"),
                  chip_review.Zmena("chips/07.html"), chip_review.Zmena("tools/a.py")]
        self.assertEqual(chip_review.kodove_soubory(seznam), ["tools/a.py"])


class TestVypisSignalu(unittest.TestCase):
    """Rozdělení nález/otázka ve výpisu (#2, #5, #6) — na tom stojí čitelnost."""

    def vypis(self, *signaly) -> str:
        return "\n".join(chip_review.sekce_signaly(list(signaly)))

    def test_nalez_a_otazka_maji_vlastni_sekci(self) -> None:
        out = self.vypis(chip_review.nalez("něco chybí"),
                         chip_review.otazka("něco ověř"))
        self.assertLess(out.index("Nálezy"), out.index("něco chybí"))
        self.assertLess(out.index("Otázky"), out.index("něco ověř"))
        self.assertLess(out.index("něco chybí"), out.index("Otázky"))

    def test_souhrn_rozlisuje_pocty(self) -> None:
        out = self.vypis(chip_review.nalez("a"), chip_review.nalez("b"),
                         chip_review.otazka("c"))
        self.assertIn("Souhrn: 2 nálezy, 1 otázka.", out)

    def test_souhrn_sklonuje_podle_cislovky(self) -> None:
        out = self.vypis(*[chip_review.nalez(str(i)) for i in range(5)],
                         *[chip_review.otazka(str(i)) for i in range(5)])
        self.assertIn("Souhrn: 5 nálezů, 5 otázek.", out)

    def test_bez_signalu_jedna_veta_a_zadna_prazdna_sekce(self) -> None:
        out = self.vypis()
        self.assertEqual(len(out.splitlines()), 1)
        self.assertNotIn("Nálezy", out)
        self.assertNotIn("Otázky", out)

    def test_jen_otazky_nevypisou_sekci_nalezu(self) -> None:
        out = self.vypis(chip_review.otazka("ověř"))
        self.assertNotIn("Nálezy", out)
        self.assertIn("Souhrn: 0 nálezů, 1 otázka.", out)

    def test_tvrdy_nalez_ma_jinou_znacku(self) -> None:
        """`X` je porušení pravidla metodiky, `!` podklad — nesmí splynout."""
        out = self.vypis(chip_review.nalez("mimo", tvrdy=True),
                         chip_review.nalez("mekky"))
        self.assertIn("X  mimo", out)
        self.assertIn("!  mekky", out)

    def test_vyber_filtruje_podle_druhu(self) -> None:
        signaly = [chip_review.nalez("a"), chip_review.otazka("b")]
        self.assertEqual([s.text for s in
                          chip_review.vyber(signaly, chip_review.OTAZKA)], ["b"])


class TestZadani(Zaklad):
    """Zadání pro reviewer agenta (#6) musí být úplné — je to jediný jeho vstup."""

    def test_obsahuje_povinne_body(self) -> None:
        text = chip_review.zadani(self.chip(), self.repo)
        for fraze in ("CELÝ brief", "Definition of done", "NESMÍŠ", "mergovat",
                      "měnit brief", "hlásit"):
            self.assertIn(fraze, text)

    def test_odkazuje_na_konkretni_chip_a_repo(self) -> None:
        text = chip_review.zadani(self.chip(), self.repo)
        self.assertIn("07-pokus.md", text)
        self.assertIn(str(self.repo), text)

    def test_prepinac_zadani_vypise_text_a_nekontroluje(self) -> None:
        kod, out = self.spust("07", "--dir", str(self.chips), "--repo", str(self.repo),
                              "--zadani")
        self.assertEqual(kod, 0)
        self.assertIn("REVIEWER chipu 07", out)
        self.assertNotIn("Změněné soubory", out)


class TestMain(Zaklad):
    """Návratový kód (#7) a chování CLI včetně cizího repa (#8)."""

    def test_ciste_repo_vraci_nulu(self) -> None:
        kod, out = self.spust("07", "--dir", str(self.chips), "--repo", str(self.repo))
        self.assertEqual(kod, 0)
        self.assertIn("REVIEW chip 07", out)

    def test_soubor_mimo_narok_vraci_jednicku(self) -> None:
        self.zapis("tools/chip_gate.py", "# podstrčeno\n")
        self.commit("mimo narok")
        kod, out = self.spust("07", "--dir", str(self.chips), "--repo", str(self.repo))
        self.assertEqual(kod, 1)
        self.assertIn("MIMO NÁROK: tools/chip_gate.py", out)

    def test_podezrely_test_nezvedne_navratovy_kod(self) -> None:
        """Podklady nesmí blokovat merge — verdikt patří uživateli."""
        kod, out = self.spust("07", "--dir", str(self.chips), "--repo", str(self.repo))
        self.assertEqual(kod, 0)
        self.assertIn("test_bez_assertu", out)

    def test_repo_z_briefu_kdyz_chybi_prepinac(self) -> None:
        kod, out = self.spust("07", "--dir", str(self.chips))
        self.assertEqual(kod, 0)
        self.assertIn(str(self.repo.name), out)

    def test_cizi_repo_pres_prepinac(self) -> None:
        """`--repo` musí přebít `repo:` z briefu (pilot na cizím repu)."""
        cizi = self.tmp / "cizi"
        cizi.mkdir()
        subprocess.run(["git", "init", "-q", str(cizi)], check=True, capture_output=True)
        (cizi / "tools").mkdir()
        (cizi / "tools" / "novy.py").write_text("x = 1\n", encoding="utf-8")
        git(cizi, "add", "-A")
        git(cizi, "-c", "user.name=t", "-c", "user.email=t@t",
            "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x")
        kod, out = self.spust("07", "--dir", str(self.chips), "--repo", str(cizi))
        self.assertEqual(kod, 0)
        self.assertIn(str(cizi), out)

    def test_jednociferne_cislo_se_doplni(self) -> None:
        self.uloz_brief("08")
        _, out = self.spust("8", "--dir", str(self.chips), "--repo", str(self.repo))
        self.assertIn("REVIEW chip 08", out)

    def test_neznamy_chip_vraci_jednicku(self) -> None:
        kod, out = self.spust("99", "--dir", str(self.chips), "--repo", str(self.repo))
        self.assertEqual(kod, 1)
        self.assertIn("nenalezen", out)

    def test_neexistujici_repo_vraci_jednicku(self) -> None:
        kod, out = self.spust("07", "--dir", str(self.chips),
                              "--repo", str(self.tmp / "nikde"))
        self.assertEqual(kod, 1)
        self.assertIn("neexistuje", out)

    def test_rozbity_rozsah_vraci_jednicku(self) -> None:
        kod, out = self.spust("07", "--dir", str(self.chips), "--repo", str(self.repo),
                              "--commit", "nesmysl")
        self.assertEqual(kod, 1)
        self.assertIn("rozsah", out)

    def test_vypis_ma_vsechny_sekce(self) -> None:
        _, out = self.spust("07", "--dir", str(self.chips), "--repo", str(self.repo))
        for nadpis in ("Změněné soubory", "Rozsah proti nároku", "Podezřelé testy",
                       "Definition of done", "Přidané řádky"):
            self.assertIn(nadpis, out)

    def test_normalni_pomer_dod_nedela_nalez(self) -> None:
        """DoD chipu 21: 8 bodů, 2 příkazy, čistý commit → nula nálezů."""
        self.prepis_dod(dod=8, prikazy=2)
        self.ciste_zmeny()
        kod, out = self.spust("07", "--dir", str(self.chips), "--repo", str(self.repo))
        self.assertEqual(kod, 0)
        self.assertIn("Souhrn: 0 nálezů, 1 otázka.", out)
        self.assertNotIn("Nálezy", out)
        self.assertIn("odškrtnutých bodů DoD", out.split("Otázky")[1])

    def test_ciste_repo_rekne_jednou_vetou_ze_neni_nic(self) -> None:
        self.prepis_dod(dod=2, prikazy=2)
        self.ciste_zmeny()
        kod, out = self.spust("07", "--dir", str(self.chips), "--repo", str(self.repo))
        self.assertEqual(kod, 0)
        self.assertIn("Bez nálezů a bez otázek", out)
        self.assertNotIn("Souhrn:", out)
        self.assertNotIn("Otázky", out)

    def test_soubor_mimo_narok_zustava_nalezem(self) -> None:
        """Skutečný nález se nesmí ztratit mezi otázkami ani po přerovnání výpisu."""
        self.prepis_dod(dod=8, prikazy=2)
        self.zapis("tools/chip_gate.py", "# podstrčeno\n")
        self.commit("mimo narok")
        kod, out = self.spust("07", "--dir", str(self.chips), "--repo", str(self.repo))
        self.assertEqual(kod, 1)
        self.assertIn("MIMO NÁROK: tools/chip_gate.py", out.split("Nálezy")[1])
        self.assertNotIn("MIMO NÁROK", out.split("Otázky")[-1])


if __name__ == "__main__":
    unittest.main()
