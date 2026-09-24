"""Testy pro tools/chip_slice.py — čtení fronty, řez na skupiny, stropy, zápis.

Těžiště: (a) skupiny se nesmí překrývat v souborech, (b) úkol bez uvedeného
souboru se nikam netipuje. Každý test si staví vlastní `tempfile` fixture
a uklidí po sobě; `chip_common.CHIPS_DIR` je globální stav, vrací se v cleanupu.
Jen standardní knihovna.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import chip_common          # noqa: E402
import chip_lint            # noqa: E402
import chip_slice           # noqa: E402


class Zaklad(unittest.TestCase):
    """Dočasné „repo" + návrat globálního CHIPS_DIR do původního stavu."""

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="chip-slice-test-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.addCleanup(chip_common.nastav_chips_dir, chip_common.CHIPS_DIR)

    def soubor(self, rel: str, obsah: str = "x\n") -> Path:
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(obsah, encoding="utf-8")
        return p

    def todo(self, text: str) -> Path:
        return self.soubor("TODO.md", text)

    def ukol(self, popis: str, *soubory: str) -> chip_slice.Ukol:
        return chip_slice.Ukol(id=f"#{popis[:4]}", popis=popis, soubory=list(soubory))

    def spust(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            kod = chip_slice.main(list(argv))
        return kod, buf.getvalue()


class TestNacitaniTodo(Zaklad):

    def test_nacte_neodskrtnute_odrazky(self) -> None:
        t = self.todo("# TODO\n\n- [ ] první\n- [ ] druhá\n")
        ukoly = chip_slice.nacti_todo(t, self.dir)
        self.assertEqual([u.popis for u in ukoly], ["první", "druhá"])
        self.assertEqual([u.id for u in ukoly], ["#1", "#2"])

    def test_odskrtnuty_ukol_se_neresi(self) -> None:
        """Hotová práce se neřeže — `- [x]` do fronty nepatří."""
        t = self.todo("- [x] hotovo v src/a.py\n- [ ] zbývá v src/b.py\n")
        ukoly = chip_slice.nacti_todo(t, self.dir)
        self.assertEqual(len(ukoly), 1)
        self.assertEqual(ukoly[0].soubory, ["src/b.py"])

    def test_pokracovaci_radek_se_pripoji(self) -> None:
        # cesta bývá až na zalomeném řádku; bez spojení by nárok zmizel
        t = self.todo("- [ ] něco dlouhého,\n      co pokračuje v tools/x.py\n")
        ukoly = chip_slice.nacti_todo(t, self.dir)
        self.assertEqual(len(ukoly), 1)
        self.assertEqual(ukoly[0].soubory, ["tools/x.py"])
        self.assertIn("pokračuje", ukoly[0].popis)

    def test_neodsazeny_radek_pokracovanim_neni(self) -> None:
        t = self.todo("- [ ] úkol\n\n## Nadpis se src/cizi.py\n")
        ukoly = chip_slice.nacti_todo(t, self.dir)
        self.assertEqual(len(ukoly), 1)
        self.assertEqual(ukoly[0].soubory, [])

    def test_prazdny_soubor_neda_zadne_ukoly(self) -> None:
        self.assertEqual(chip_slice.nacti_todo(self.todo(""), self.dir), [])


class TestCestyZTextu(Zaklad):

    def cesty(self, text: str, dohledat: bool = True) -> list[str]:
        return chip_slice.cesty_z_textu(text, self.dir, dohledat)[0]

    def test_cesta_s_adresarem_se_najde(self) -> None:
        self.assertEqual(self.cesty("oprav `tools/chip_slice.py` prosím"),
                         ["tools/chip_slice.py"])

    def test_cesta_bez_backticku_se_taky_najde(self) -> None:
        self.assertEqual(self.cesty("viz docs/metodika.md dole"), ["docs/metodika.md"])

    def test_vzor_v_ceste_projde(self) -> None:
        self.assertEqual(self.cesty("přepiš `tests/*.py`"), ["tests/*.py"])

    def test_holy_nazev_v_backticich_se_dohleda_pri_jedne_shode(self) -> None:
        self.soubor("tools/chip_lint.py")
        self.assertEqual(self.cesty("uprav `chip_lint.py`"), ["tools/chip_lint.py"])

    def test_nejednoznacny_nazev_se_nedohleda(self) -> None:
        """Dva kandidáti = neurčitost, ne informace — nikam se netipuje."""
        self.soubor("a/utils.py")
        self.soubor("b/utils.py")
        cesty, nejasne = chip_slice.cesty_z_textu("uprav `utils.py`", self.dir)
        self.assertEqual(cesty, [])
        self.assertEqual(nejasne, ["utils.py"])

    def test_nazev_mimo_repo_se_nedohleda(self) -> None:
        cesty, nejasne = chip_slice.cesty_z_textu("oprav `cizi_skript.py`", self.dir)
        self.assertEqual(cesty, [])
        self.assertEqual(nejasne, ["cizi_skript.py"])

    def test_holy_nazev_bez_backticku_se_nebere(self) -> None:
        self.soubor("tools/chip_lint.py")
        self.assertEqual(self.cesty("uprav chip_lint.py"), [])

    def test_prepinac_bez_dohledani(self) -> None:
        self.soubor("tools/chip_lint.py")
        self.assertEqual(self.cesty("uprav `chip_lint.py`", dohledat=False), [])

    def test_desetinne_cislo_neni_soubor(self) -> None:
        self.assertEqual(self.cesty("kurz `0.041` je špatně"), [])

    def test_zpetna_lomitka_se_normalizuji(self) -> None:
        self.assertEqual(self.cesty(r"soubor tools\chip_run.py"), ["tools/chip_run.py"])

    def test_tecka_za_vetou_se_do_cesty_nepocita(self) -> None:
        self.assertEqual(self.cesty("uprav src/modul.py."), ["src/modul.py"])


class TestRez(Zaklad):

    def test_dva_ukoly_sdilejici_soubor_jsou_v_jedne_skupine(self) -> None:
        skupiny, nezarazene = chip_slice.rozdel([
            self.ukol("A", "src/a.py"),
            self.ukol("B", "src/a.py", "src/b.py"),
        ])
        self.assertEqual(len(skupiny), 1)
        self.assertEqual(len(skupiny[0].ukoly), 2)
        self.assertEqual(nezarazene, [])

    def test_retez_tri_ukolu_pres_spolecny_soubor(self) -> None:
        # A–B sdílí x.py, B–C sdílí y.py; A a C spolu nesdílí nic, přesto
        # musí skončit v jedné skupině (souvislá komponenta)
        skupiny, _ = chip_slice.rozdel([
            self.ukol("A", "src/x.py"),
            self.ukol("B", "src/x.py", "src/y.py"),
            self.ukol("C", "src/y.py"),
        ])
        self.assertEqual(len(skupiny), 1)
        self.assertEqual(len(skupiny[0].ukoly), 3)

    def test_osamoceny_ukol_ma_vlastni_skupinu(self) -> None:
        skupiny, _ = chip_slice.rozdel([
            self.ukol("A", "src/a.py"),
            self.ukol("B", "src/b.py"),
        ])
        self.assertEqual([len(s.ukoly) for s in skupiny], [1, 1])
        self.assertEqual([s.cislo for s in skupiny], ["01", "02"])

    def test_ukol_bez_souboru_jde_do_nezarazeno(self) -> None:
        skupiny, nezarazene = chip_slice.rozdel([
            self.ukol("A", "src/a.py"),
            self.ukol("bez souborů"),
        ])
        self.assertEqual(len(skupiny), 1)
        self.assertEqual([u.popis for u in nezarazene], ["bez souborů"])
        # a hlavně: nepřilepil se k žádné skupině
        self.assertNotIn("bez souborů", [u.popis for u in skupiny[0].ukoly])

    def test_skupiny_se_navzajem_neprekryvaji_v_souborech(self) -> None:
        """Definition of done: žádná skupina nesdílí soubor s jinou."""
        skupiny, _ = chip_slice.rozdel([
            self.ukol("A", "src/a.py", "src/spolecny.py"),
            self.ukol("B", "src/spolecny.py"),
            self.ukol("C", "src/c.py"),
            self.ukol("D", "docs/d.md", "src/c.py"),
            self.ukol("E", "tests/*.py"),
        ])
        for i, a in enumerate(skupiny):
            for b in skupiny[i + 1:]:
                for x in a.soubory:
                    for y in b.soubory:
                        self.assertFalse(chip_lint.prekryv(x, y),
                                         f"skupiny {a.cislo} a {b.cislo} sdílí {x} × {y}")

    def test_prekryv_pres_vzor_spojuje(self) -> None:
        # `tests/*.py` a `tests/test_a.py` je týž soubor — patří k sobě
        skupiny, _ = chip_slice.rozdel([
            self.ukol("A", "tests/*.py"),
            self.ukol("B", "tests/test_a.py"),
        ])
        self.assertEqual(len(skupiny), 1)

    def test_prekryv_pres_adresar_spojuje(self) -> None:
        skupiny, _ = chip_slice.rozdel([
            self.ukol("A", "tools"),
            self.ukol("B", "tools/chip_run.py"),
        ])
        self.assertEqual(len(skupiny), 1)

    def test_prazdny_vstup_neda_zadnou_skupinu(self) -> None:
        self.assertEqual(chip_slice.rozdel([]), ([], []))


class TestStrop(Zaklad):

    def test_prilis_mnoho_ukolu(self) -> None:
        s = chip_slice.Skupina(ukoly=[self.ukol(f"u{i}", "src/a.py") for i in range(21)])
        self.assertIn("21 úkolů", s.prilis_velka() or "")

    def test_prilis_mnoho_souboru(self) -> None:
        s = chip_slice.Skupina(ukoly=[self.ukol("u", *[f"src/{i}.py" for i in range(16)])])
        self.assertIn("16 souborů", s.prilis_velka() or "")

    def test_pod_stropem_je_ciste(self) -> None:
        s = chip_slice.Skupina(ukoly=[self.ukol("u", "src/a.py")])
        self.assertIsNone(s.prilis_velka())

    def test_strop_se_da_prenastavit(self) -> None:
        s = chip_slice.Skupina(ukoly=[self.ukol("a", "src/a.py"),
                                      self.ukol("b", "src/a.py")])
        self.assertIsNone(s.prilis_velka())
        self.assertIn("2 úkolů", s.prilis_velka(max_ukolu=1) or "")

    def test_znacka_prilis_velka_je_ve_vypisu(self) -> None:
        self.todo("".join(f"- [ ] úkol {i} v `src/spolecny.py`\n" for i in range(21)))
        _, out = self.spust("--todo", str(self.dir / "TODO.md"), "--repo", str(self.dir))
        self.assertIn("PŘÍLIŠ VELKÁ", out)
        self.assertIn("21 úkolů", out)


class TestJsonVstup(Zaklad):

    def json_soubor(self, data) -> str:
        p = self.dir / "fronta.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(p)

    def test_uvedene_soubory_se_berou_jak_jsou(self) -> None:
        cesta = self.json_soubor([{"id": 12, "popis": "oprav parser",
                                   "soubory": ["src/parser.py"]}])
        ukoly = chip_slice.nacti_json(Path(cesta), self.dir)
        self.assertEqual(ukoly[0].id, "#12")
        self.assertEqual(ukoly[0].soubory, ["src/parser.py"])

    def test_bez_klice_soubory_se_cte_text(self) -> None:
        cesta = self.json_soubor([{"id": 1, "popis": "oprav `tools/x.py`"}])
        self.assertEqual(chip_slice.nacti_json(Path(cesta), self.dir)[0].soubory,
                         ["tools/x.py"])

    def test_objekt_s_klicem_issues(self) -> None:
        cesta = self.json_soubor({"issues": [{"id": 1, "popis": "a",
                                              "soubory": ["src/a.py"]}]})
        self.assertEqual(len(chip_slice.nacti_json(Path(cesta), self.dir)), 1)

    def test_json_vstup_projde_cli(self) -> None:
        cesta = self.json_soubor([{"id": 1, "popis": "a", "soubory": ["src/a.py"]},
                                  {"id": 2, "popis": "b", "soubory": ["src/a.py"]}])
        kod, out = self.spust("--json", cesta, "--repo", str(self.dir))
        self.assertEqual(kod, 0)
        self.assertIn("skupina 01", out)
        self.assertIn("1 skupina", out)

    def test_rozbity_json_neshodi_nastroj(self) -> None:
        p = self.dir / "spatny.json"
        p.write_text("{tohle není json", encoding="utf-8")
        kod, out = self.spust("--json", str(p))
        self.assertEqual(kod, 0)
        self.assertIn("nečitelný vstup", out)


class TestZapis(Zaklad):

    def priprav(self, obsah: str | None = None) -> Path:
        self.todo(obsah or "- [ ] A v `src/a.py`\n- [ ] B v `src/b.py`\n")
        return self.dir / "navrh"

    def zapis(self, cil: Path, *argv: str) -> tuple[int, str]:
        return self.spust("--todo", str(self.dir / "TODO.md"),
                          "--repo", str(self.dir), "--zapsat", str(cil), *argv)

    def test_zapise_brief_pro_kazdou_skupinu(self) -> None:
        cil = self.priprav()
        kod, out = self.zapis(cil)
        self.assertEqual(kod, 0)
        self.assertEqual(sorted(p.name for p in cil.glob("*.md")),
                         ["01-navrh-01.md", "02-navrh-02.md"])
        self.assertIn("zapsáno 2", out)

    def test_brief_ma_stav_draft_a_vyplnene_sekce(self) -> None:
        cil = self.priprav()
        self.zapis(cil)
        text = (cil / "01-navrh-01.md").read_text(encoding="utf-8")
        self.assertIn("stav: draft", text)
        self.assertIn("src/a.py", text)
        self.assertNotIn("src/parser.py", text)      # placeholder ze šablony pryč
        chip = chip_common.parse(cil / "01-navrh-01.md")
        self.assertEqual(chip.soubory(), ["src/a.py"])
        self.assertEqual(len(chip.issues()), 1)

    def test_vygenerovane_briefy_projdou_lintem(self) -> None:
        """Draft brief, který neprojde lintem, je k ničemu — člověk ho pak stejně
        přepisuje ručně a nástroj nic neušetřil."""
        cil = self.priprav()
        self.zapis(cil)
        buf = io.StringIO()
        with patch("sys.argv", ["chip_lint.py", "--dir", str(cil)]):
            with contextlib.redirect_stdout(buf):
                kod = chip_lint.main()
        self.assertEqual(kod, 0, buf.getvalue())

    def test_kolize_cisla_neprepise_cizi_soubor(self) -> None:
        cil = self.priprav()
        cil.mkdir(parents=True)
        cizi = cil / "01-cizi-chip.md"
        cizi.write_text("cizí obsah\n", encoding="utf-8")
        self.zapis(cil)
        self.assertEqual(cizi.read_text(encoding="utf-8"), "cizí obsah\n")
        self.assertEqual(sorted(p.name for p in cil.glob("*.md")),
                         ["01-cizi-chip.md", "02-navrh-02.md", "03-navrh-03.md"])

    def test_volne_cislo_preskoci_obsazena(self) -> None:
        (self.dir / "01-a.md").write_text("x", encoding="utf-8")
        (self.dir / "02-b.md").write_text("x", encoding="utf-8")
        self.assertEqual(chip_slice.volne_cislo(self.dir), "03")

    def test_prilis_velka_skupina_ma_varovani_i_v_briefu(self) -> None:
        cil = self.priprav("".join(f"- [ ] úkol {i} v `src/spolecny.py`\n"
                                   for i in range(21)))
        self.zapis(cil)
        self.assertIn("PŘÍLIŠ VELKÁ",
                      (cil / "01-navrh-01.md").read_text(encoding="utf-8"))

    def test_vetev_je_dosazena_a_zadny_placeholder_nezustal(self) -> None:
        """Přesně chyba z code review: `.replace()` se starým tvarem `vetev:`
        tiše selhal a brief odešel s doslovným placeholderem ze šablony."""
        cil = self.priprav()
        self.zapis(cil)
        text = (cil / "01-navrh-01.md").read_text(encoding="utf-8")
        self.assertIn("vetev: ai/chip-01/navrh-01", text)
        frontmatter = text[3:text.find("\n---", 3)]
        for ph in ("NN", "kratky-nazev-s-pomlckami", "C:/cesta/k/repu",
                   "YYYY-MM-DD"):
            with self.subTest(placeholder=ph):
                self.assertNotIn(ph, frontmatter,
                                 f"ve frontmatteru zůstalo '{ph}' — šablona "
                                 f"a dosazování se rozešly")


class TestShodaSeSablonou(Zaklad):
    """Stejný princip jako `test_kazdy_replace_v_chip_new_ma_vzor_v_sablone`
    v `tests/test_chip_new.py`: `.replace()` bez shody nic neudělá a nic
    neohlásí. Tahle třída chyb už jednou prošla (chip 08 → chip_new), oprava
    se ale zastavila u prvního výskytu vzoru — druhý žil tady."""

    def test_kazdy_replace_v_text_briefu_ma_vzor_v_sablone(self) -> None:
        """Bere se zdroják `text_briefu()` — tam žije celé dosazování do
        šablony. Celý modul se scanovat nedá: `cesty_z_textu()` normalizuje
        lomítka přes `.replace("\\\\", "/")` a ten vzor v šabloně být nemá."""
        zdroj = inspect.getsource(chip_slice.text_briefu)
        sablona = (ROOT / "chips" / "TEMPLATE.md").read_text(encoding="utf-8")
        vzory = re.findall(r'\.replace\(\s*"((?:[^"\\]|\\.)*)"', zdroj)
        self.assertTrue(vzory, "v text_briefu() nejsou žádné .replace() — "
                               "změnila se struktura?")
        for vzor in vzory:
            with self.subTest(vzor=vzor):
                self.assertIn(vzor, sablona,
                              f"chip_slice.text_briefu dosazuje za '{vzor}', "
                              f"ale ten řetězec v TEMPLATE.md není — dosazení "
                              f"tiše propadne")


class TestCli(Zaklad):

    def test_navratovy_kod_je_vzdy_nula(self) -> None:
        self.todo("- [ ] A v `src/a.py`\n- [ ] bez souboru\n")
        kod, _ = self.spust("--todo", str(self.dir / "TODO.md"), "--repo", str(self.dir))
        self.assertEqual(kod, 0)

    def test_vypis_ma_sekci_nezarazeno(self) -> None:
        self.todo("- [ ] A v `src/a.py`\n- [ ] jen text bez cesty\n")
        _, out = self.spust("--todo", str(self.dir / "TODO.md"), "--repo", str(self.dir))
        self.assertIn("NEZAŘAZENO", out)
        self.assertIn("jen text bez cesty", out)
        self.assertIn("1 nezařazených", out)

    def test_chybejici_todo_neshodi_nastroj(self) -> None:
        kod, out = self.spust("--todo", str(self.dir / "nic.md"))
        self.assertEqual(kod, 0)
        self.assertIn("neexistuje", out)

    def test_prazdna_fronta_da_hlasku(self) -> None:
        self.todo("# TODO\n\nžádné odrážky\n")
        kod, out = self.spust("--todo", str(self.dir / "TODO.md"))
        self.assertEqual(kod, 0)
        self.assertIn("není co řezat", out)

    def test_radky_vypisu_se_vejdou_do_80_sloupcu(self) -> None:
        self.todo("- [ ] velmi dlouhý popis úkolu, který se nikdy nevejde na jeden "
                  "řádek a musí se zalomit, `src/velmi/dlouha/cesta/k/modulu.py`\n")
        _, out = self.spust("--todo", str(self.dir / "TODO.md"), "--repo", str(self.dir))
        for radek in out.splitlines():
            self.assertLessEqual(len(radek), 80, radek)


if __name__ == "__main__":
    unittest.main()
