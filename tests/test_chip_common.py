"""Testy mini-parseru chip briefů (`tools/chip_common.py`).

Parser je vlastní implementace bez PyYAML — když tiše přestane rozumět
frontmatteru nebo poznámce za cestou, rozpadne se `chip_lint.py` i `chip_run.py`.
Testy proto sahají na každou veřejnou část `Chip` zvlášť.

Pokrývá issues #1–#12 z briefu `chips/03-testy-common.md` a navíc sdílené
helpery sloučené sem chipem 06 (`Chip.hotove_issues()`, `prepis_stav()`) —
testy tvůrců obou funkcí zůstávají v `test_chip_status.py` / `test_chip_run.py`
jen jako testy chování nástrojů.
Jen standardní knihovna (`unittest`), žádné nové závislosti.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import chip_common  # noqa: E402
from chip_common import Chip, _norm, nacti_vse, nastav_chips_dir, parse  # noqa: E402


class ZakladChipu(unittest.TestCase):
    """Dočasný adresář s briefy + obnova globálního `CHIPS_DIR`.

    `CHIPS_DIR` je modulová globálka — kdyby ji test nechal přepnutou, ovlivnil
    by všechny následující. Vrací se proto v `tearDown` přímým přiřazením
    (`nastav_chips_dir(None)` by ji záměrně nechal být).
    """

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="chip-test-"))
        self._puvodni_chips_dir = chip_common.CHIPS_DIR

    def tearDown(self) -> None:
        chip_common.CHIPS_DIR = self._puvodni_chips_dir
        shutil.rmtree(self.dir, ignore_errors=True)

    def zapis(self, text: str, jmeno: str = "07-pokus.md") -> Path:
        """Uloží brief do dočasného adresáře (UTF-8 kvůli diakritice na Windows)."""
        cesta = self.dir / jmeno
        cesta.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
        return cesta

    def brief(self, text: str, jmeno: str = "07-pokus.md") -> Chip:
        return parse(self.zapis(text, jmeno))

    def brief_doslova(self, text: str, jmeno: str = "07-pokus.md") -> Chip:
        """Jako `brief()`, ale bez dedentu — když na odsazení řádků záleží."""
        cesta = self.dir / jmeno
        cesta.write_text(text, encoding="utf-8")
        return parse(cesta)


# --------------------------------------------------------------------------
# #1 — frontmatter
# --------------------------------------------------------------------------
class TestFrontmatter(ZakladChipu):

    def test_klic_hodnota_se_nacte(self) -> None:
        c = self.brief("""
            ---
            chip: 07
            nazev: pokusny-chip
            stav: ready
            ---

            # CHIP 07
            """)
        self.assertEqual(c.meta["chip"], "07")
        self.assertEqual(c.meta["nazev"], "pokusny-chip")
        self.assertEqual(c.stav, "ready")

    def test_komentar_za_mrizkou_se_odrizne(self) -> None:
        c = self.brief("""
            ---
            stav: ready   # zatím jen návrh
            ---
            """)
        self.assertEqual(c.meta["stav"], "ready")

    def test_zakomentovany_radek_frontmatteru_se_preskoci(self) -> None:
        c = self.brief("""
            ---
            # stav: merged
            stav: ready
            ---
            """)
        self.assertEqual(c.meta["stav"], "ready")
        self.assertNotIn("# stav", c.meta)

    def test_chybejici_frontmatter_neshodi_parser(self) -> None:
        """Brief bez `---` má prázdnou meta, sekce se ale načíst musí."""
        c = self.brief("""
            # CHIP bez frontmatteru

            ## Issues

            - [ ] #1 — něco
            """)
        self.assertEqual(c.meta, {})
        self.assertEqual(c.stav, "draft")
        self.assertIsNotNone(c.najdi("issues"))

    def test_prazdna_hodnota_je_prazdny_retezec(self) -> None:
        c = self.brief("""
            ---
            chip: 07
            zavisi_na:
            ---
            """)
        self.assertEqual(c.meta["zavisi_na"], "")

    def test_hodnota_s_dvojteckou_zustane_cela(self) -> None:
        """Windowsová cesta `C:/...` se dělí jen na první dvojtečce."""
        c = self.brief("""
            ---
            repo: C:/Users/nekdo/repo
            ---
            """)
        self.assertEqual(c.meta["repo"], "C:/Users/nekdo/repo")

    def test_neuzavreny_frontmatter_se_nebere(self) -> None:
        """Bez druhého `---` není co parsovat — text zůstává tělem briefu."""
        c = self.brief("""
            ---
            stav: ready

            # CHIP 07
            """)
        self.assertEqual(c.meta, {})


# --------------------------------------------------------------------------
# #2 — hledání sekcí
# --------------------------------------------------------------------------
class TestSekce(ZakladChipu):

    def test_sekce_s_diakritikou_se_najde(self) -> None:
        c = self.brief("""
            ## Ověření (brána)

            spusť lint
            """)
        self.assertIn("spusť lint", c.najdi("overeni brana"))

    def test_sekce_s_ozdobami_v_nadpisu_se_najde(self) -> None:
        """`## Dotčené soubory ⚠️ NÁROK` musí sedět na prefix `dotcene soubory`."""
        c = self.brief("""
            ## Dotčené soubory  ⚠️ NÁROK

            obsah
            """)
        self.assertIn("obsah", c.najdi("dotcene soubory"))

    def test_vsechny_povinne_sekce_se_najdou(self) -> None:
        c = self.brief("""
            ## Issues

            - [ ] #1 — něco

            ## Dotčené soubory  ⚠️ NÁROK

            ```
            src/a.py
            ```

            ## Definition of done

            - [ ] hotovo

            ## Ověření (brána)

            ```bash
            python tools/chip_lint.py
            ```
            """)
        for klic in ("issues", "dotcene soubory", "definition of done", "overeni brana"):
            with self.subTest(klic=klic):
                self.assertIsNotNone(c.najdi(klic))

    def test_neznama_sekce_vraci_none(self) -> None:
        c = self.brief("""
            ## Issues

            - [ ] #1 — něco
            """)
        self.assertIsNone(c.najdi("eskalace"))

    def test_nadpis_treti_urovne_neni_sekce(self) -> None:
        """Dělí se jen na `## `, aby `### ` zůstalo součástí nadřazené sekce."""
        c = self.brief("""
            ## Issues

            ### Podnadpis

            - [ ] #1 — něco
            """)
        self.assertIsNone(c.najdi("podnadpis"))
        self.assertIn("Podnadpis", c.najdi("issues"))


# --------------------------------------------------------------------------
# #3 + #4 + #5 + #6 — sekce 'Dotčené soubory'
# --------------------------------------------------------------------------
class TestSoubory(ZakladChipu):

    def _s_bloky(self, *radky: str) -> Chip:
        """Brief s jedinou sekcí 'Dotčené soubory' a danými řádky v ``` bloku."""
        text = "## Dotčené soubory  ⚠️ NÁROK\n\n```\n" + "\n".join(radky) + "\n```\n"
        return self.brief_doslova(text)

    # --- #3 -------------------------------------------------------------
    def test_poznamka_za_cestou_se_odrizne(self) -> None:
        c = self._s_bloky("tools/chip_lint.py    # jen doplnit hlášku")
        self.assertEqual(c.soubory_detail(), [("tools/chip_lint.py", False)])

    def test_priznak_novy_nastavi_poznamka_novy(self) -> None:
        for pozn in ("# nový", "# novy", "# nový soubor", "# new", "# NOVÝ", "# new file"):
            with self.subTest(pozn=pozn):
                c = self._s_bloky(f"tests/test_x.py    {pozn}")
                self.assertEqual(c.soubory_detail(), [("tests/test_x.py", True)])

    def test_priznak_novy_nenastavi_jina_poznamka(self) -> None:
        """`NOVY` se kotví na začátek poznámky — `# bude nový` se nepočítá."""
        for pozn in ("# poznámka", "# bude nový", "# přepsat", "# novinka je jinde"):
            with self.subTest(pozn=pozn):
                c = self._s_bloky(f"tests/test_x.py    {pozn}")
                self.assertEqual(c.soubory_detail(), [("tests/test_x.py", False)])

    def test_novinka_neni_novy(self) -> None:
        """`\\b` za `nov[ýy]` brání shodě uvnitř delšího slova."""
        c = self._s_bloky("src/a.py  # novinka")
        self.assertEqual(c.soubory_detail(), [("src/a.py", False)])

    def test_mrizka_bez_mezery_pred_sebou_neni_poznamka(self) -> None:
        """`KOMENTAR` vyžaduje bílé znaky před `#` — jinak by se ořezala cesta."""
        c = self._s_bloky("src/soubor#1.py")
        self.assertEqual(c.soubory(), ["src/soubor#1.py"])

    def test_jedna_mezera_a_mrizka_je_soucast_cesty(self) -> None:
        """Nález #4 (chip 11): `docs/plan #1.md` se tiše usekával na `docs/plan`.

        Poznámka se od cesty odděluje DVĚMA a více bílými znaky — jedna mezera
        + `#` patří ke jménu souboru.
        """
        c = self._s_bloky("docs/plan #1.md")
        self.assertEqual(c.soubory_detail(), [("docs/plan #1.md", False)])

    def test_dva_bile_znaky_pred_mrizkou_jsou_poznamka(self) -> None:
        # #4 (chip 11) — dvě mezery, mezera+tab i dva taby poznámku oddělují
        for radek in ("src/a.py  # nový", "src/a.py \t# nový", "src/a.py\t\t# nový"):
            with self.subTest(radek=radek):
                c = self._s_bloky(radek)
                self.assertEqual(c.soubory_detail(), [("src/a.py", True)])

    def test_cesta_s_mezerou_a_mrizkou_unese_i_poznamku(self) -> None:
        # #4 (chip 11) — poznámka za takovou cestou dál funguje
        c = self._s_bloky("docs/plan #1.md    # nový")
        self.assertEqual(c.soubory_detail(), [("docs/plan #1.md", True)])

    # --- #4 -------------------------------------------------------------
    def test_zakomentovany_radek_se_ignoruje(self) -> None:
        c = self._s_bloky("# tenhle řádek je jen komentář", "src/a.py")
        self.assertEqual(c.soubory(), ["src/a.py"])

    def test_prazdne_radky_se_ignoruji(self) -> None:
        c = self._s_bloky("src/a.py", "", "   \t", "src/b.py")
        self.assertEqual(c.soubory(), ["src/a.py", "src/b.py"])

    def test_koncove_lomitko_se_orizne(self) -> None:
        c = self._s_bloky("docs/", "tests/  # nový")
        self.assertEqual(c.soubory_detail(), [("docs", False), ("tests", True)])

    def test_okolni_mezery_se_orezou(self) -> None:
        c = self._s_bloky("      src/a.py      ")
        self.assertEqual(c.soubory(), ["src/a.py"])

    # --- #5 -------------------------------------------------------------
    def test_soubory_vraci_cesty_bez_poznamek(self) -> None:
        """Kontrola kolizí porovnává řetězce — poznámka by ji rozbila."""
        c = self._s_bloky("tools/chip_lint.py   # jen hlášky",
                          "tests/test_lint.py   # nový")
        self.assertEqual(c.soubory(), ["tools/chip_lint.py", "tests/test_lint.py"])
        self.assertEqual([n for _, n in c.soubory_detail()], [False, True])

    def test_soubory_je_projekce_soubory_detail(self) -> None:
        c = self._s_bloky("a.py   # nový", "b.py")
        self.assertEqual(c.soubory(), [cesta for cesta, _ in c.soubory_detail()])

    # --- #6 -------------------------------------------------------------
    def test_cesty_mimo_blok_se_nepocitaji(self) -> None:
        c = self.brief("""
            ## Dotčené soubory  ⚠️ NÁROK

            Chip sahá na src/mimo_blok.py, ale nárok je až v bloku:

            ```
            src/v_bloku.py
            ```

            A ještě věta o src/uplne_mimo.py na konci.
            """)
        self.assertEqual(c.soubory(), ["src/v_bloku.py"])

    def test_vice_bloku_se_secte(self) -> None:
        c = self.brief("""
            ## Dotčené soubory  ⚠️ NÁROK

            ```
            src/a.py
            ```

            ```text
            src/b.py
            ```
            """)
        self.assertEqual(c.soubory(), ["src/a.py", "src/b.py"])

    def test_chybejici_sekce_dava_prazdny_seznam(self) -> None:
        c = self.brief("""
            ## Issues

            - [ ] #1 — něco
            """)
        self.assertEqual(c.soubory(), [])
        self.assertEqual(c.soubory_detail(), [])

    def test_prazdny_blok_dava_prazdny_seznam(self) -> None:
        c = self.brief("""
            ## Dotčené soubory  ⚠️ NÁROK

            ```
            ```
            """)
        self.assertEqual(c.soubory(), [])


# --------------------------------------------------------------------------
# #7 — repo_path()
# --------------------------------------------------------------------------
class TestRepoPath(ZakladChipu):

    def test_absolutni_cesta_zustane(self) -> None:
        c = self.brief(f"""
            ---
            repo: {self.dir.as_posix()}
            ---
            """)
        self.assertEqual(c.repo_path(), self.dir.resolve())

    def test_relativni_se_bere_od_adresare_s_briefy(self) -> None:
        c = self.brief("""
            ---
            repo: ../sousedni-repo
            ---
            """)
        self.assertEqual(c.repo_path(), (self.dir / ".." / "sousedni-repo").resolve())

    def test_relativni_bez_teckoteckou(self) -> None:
        c = self.brief("""
            ---
            repo: podrepo
            ---
            """)
        self.assertEqual(c.repo_path(), (self.dir / "podrepo").resolve())

    def test_vlnovka_se_rozvine_na_domovsky_adresar(self) -> None:
        c = self.brief("""
            ---
            repo: ~/chips-test-neexistujici
            ---
            """)
        ocekavano = (Path.home() / "chips-test-neexistujici").resolve()
        self.assertEqual(c.repo_path(), ocekavano)
        self.assertTrue(c.repo_path().is_absolute())

    def test_chybejici_klic_vraci_none(self) -> None:
        c = self.brief("""
            ---
            chip: 07
            ---
            """)
        self.assertIsNone(c.repo_path())

    def test_prazdna_hodnota_vraci_none(self) -> None:
        c = self.brief("""
            ---
            repo:
            ---
            """)
        self.assertIsNone(c.repo_path())


# --------------------------------------------------------------------------
# #8 — zavislosti()
# --------------------------------------------------------------------------
class TestZavislosti(ZakladChipu):

    def _s_zavislosti(self, hodnota: str) -> Chip:
        return self.brief(f"""
            ---
            chip: 07
            zavisi_na: {hodnota}
            ---
            """)

    def test_prazdna_hodnota_nema_zavislosti(self) -> None:
        self.assertEqual(self._s_zavislosti("").zavislosti(), [])

    def test_chybejici_klic_nema_zavislosti(self) -> None:
        c = self.brief("""
            ---
            chip: 07
            ---
            """)
        self.assertEqual(c.zavislosti(), [])

    def test_zastupne_hodnoty_znamenaji_nic(self) -> None:
        for hodnota in ("-", "nic", "[]"):
            with self.subTest(hodnota=hodnota):
                self.assertEqual(self._s_zavislosti(hodnota).zavislosti(), [])

    def test_jedno_id(self) -> None:
        self.assertEqual(self._s_zavislosti("01").zavislosti(), ["01"])

    def test_seznam_doplni_nulu_na_dve_mista(self) -> None:
        self.assertEqual(self._s_zavislosti("01, 2").zavislosti(), ["01", "02"])

    def test_hranate_zavorky_se_orezou(self) -> None:
        self.assertEqual(self._s_zavislosti("[01, 03]").zavislosti(), ["01", "03"])

    def test_prazdne_polozky_se_zahodi(self) -> None:
        self.assertEqual(self._s_zavislosti("01, , 02,").zavislosti(), ["01", "02"])


# --------------------------------------------------------------------------
# #9 — issues()
# --------------------------------------------------------------------------
class TestIssues(ZakladChipu):

    def test_nezaskrtnute_i_zaskrtnute_se_pocitaji(self) -> None:
        c = self.brief("""
            ## Issues

            - [ ] #1 — otevřené
            - [x] #2 — hotové
            - [X] #3 — hotové velkým X
            """)
        self.assertEqual(c.issues(), ["#1 — otevřené", "#2 — hotové", "#3 — hotové velkým X"])

    def test_odsazene_issue_se_pocita(self) -> None:
        c = self.brief("""
            ## Issues

              - [ ] #1 — odsazené dvěma mezerami
            """)
        self.assertEqual(c.issues(), ["#1 — odsazené dvěma mezerami"])

    def test_radky_mimo_sekci_se_nepocitaji(self) -> None:
        c = self.brief("""
            ## Issues

            - [ ] #1 — patří sem

            ## Definition of done

            - [ ] tohle je DoD, ne issue
            """)
        self.assertEqual(c.issues(), ["#1 — patří sem"])

    def test_obycejna_odrazka_neni_issue(self) -> None:
        c = self.brief("""
            ## Issues

            - jen poznámka bez zaškrtávátka
            - [ ] #1 — skutečné issue
            """)
        self.assertEqual(c.issues(), ["#1 — skutečné issue"])

    def test_chybejici_sekce_dava_prazdny_seznam(self) -> None:
        c = self.brief("""
            ## Definition of done

            - [ ] něco
            """)
        self.assertEqual(c.issues(), [])


# --------------------------------------------------------------------------
# #10 — id / nazev / stav fallback
# --------------------------------------------------------------------------
class TestIdentita(ZakladChipu):

    def test_id_fallback_z_nazvu_souboru(self) -> None:
        c = self.brief("""
            ---
            stav: ready
            ---
            """, jmeno="07-nejaky-chip.md")
        self.assertEqual(c.id, "07")

    def test_nazev_fallback_z_nazvu_souboru(self) -> None:
        c = self.brief("""
            ---
            stav: ready
            ---
            """, jmeno="07-nejaky-chip.md")
        self.assertEqual(c.nazev, "07-nejaky-chip")

    def test_frontmatter_ma_prednost_pred_nazvem_souboru(self) -> None:
        c = self.brief("""
            ---
            chip: 42
            nazev: uplne-jiny-nazev
            ---
            """, jmeno="07-nejaky-chip.md")
        self.assertEqual(c.id, "42")
        self.assertEqual(c.nazev, "uplne-jiny-nazev")

    def test_prazdna_hodnota_fallback_nespousti(self) -> None:
        """Dokumentuje současné chování: `nazev:` bez hodnoty NENÍ totéž co chybějící klíč.

        `meta.get(klic, default)` vrátí uložený prázdný řetězec, ne default —
        fallback na název souboru se tedy neuplatní. Není to v nároku tohoto
        chipu (viz Log v `chips/03-testy-common.md`), test to jen zafixuje.
        """
        c = self.brief("""
            ---
            chip:
            nazev:
            stav:
            ---
            """, jmeno="07-nejaky-chip.md")
        self.assertEqual(c.id, "")
        self.assertEqual(c.nazev, "")
        self.assertEqual(c.stav, "")

    def test_stav_bez_frontmatteru_je_draft(self) -> None:
        c = self.brief("# jen nadpis\n", jmeno="07-nejaky-chip.md")
        self.assertEqual(c.stav, "draft")


# --------------------------------------------------------------------------
# #11 — nacti_vse() a nastav_chips_dir()
# --------------------------------------------------------------------------
class TestNactiVse(ZakladChipu):

    def _naplnit(self) -> None:
        for jmeno in ("02-druhy.md", "01-prvni.md", "TEMPLATE.md"):
            self.zapis("""
                ---
                stav: draft
                ---
                """, jmeno=jmeno)
        nastav_chips_dir(self.dir)

    def test_sablona_se_vynecha(self) -> None:
        self._naplnit()
        self.assertNotIn("TEMPLATE", [c.path.stem for c in nacti_vse()])

    def test_sablona_na_vyzadani(self) -> None:
        self._naplnit()
        self.assertIn("TEMPLATE", [c.path.stem for c in nacti_vse(vcetne_sablony=True)])

    def test_radi_se_podle_jmena_souboru(self) -> None:
        self._naplnit()
        self.assertEqual([c.path.stem for c in nacti_vse()], ["01-prvni", "02-druhy"])

    def test_neexistujici_adresar_dava_prazdny_seznam(self) -> None:
        nastav_chips_dir(self.dir / "tenhle-adresar-neni")
        self.assertEqual(nacti_vse(), [])

    def test_prazdny_adresar_dava_prazdny_seznam(self) -> None:
        nastav_chips_dir(self.dir)
        self.assertEqual(nacti_vse(), [])

    def test_jine_pripony_se_ignoruji(self) -> None:
        (self.dir / "01-prvni.html").write_text("<p>x</p>", encoding="utf-8")
        self.zapis("---\nstav: draft\n---\n", jmeno="01-prvni.md")
        nastav_chips_dir(self.dir)
        self.assertEqual([c.path.name for c in nacti_vse()], ["01-prvni.md"])

    def test_nastav_chips_dir_vraci_absolutni_cestu(self) -> None:
        self.assertEqual(nastav_chips_dir(self.dir), self.dir.resolve())
        self.assertEqual(chip_common.CHIPS_DIR, self.dir.resolve())

    def test_nastav_chips_dir_bez_hodnoty_nemeni_stav(self) -> None:
        """`--dir` / `CHIPS_DIR` bývá prázdné — pak musí zůstat default."""
        nastav_chips_dir(self.dir)
        self.assertEqual(nastav_chips_dir(None), self.dir.resolve())
        self.assertEqual(nastav_chips_dir(""), self.dir.resolve())


# --------------------------------------------------------------------------
# #12 — _norm()
# --------------------------------------------------------------------------
class TestNorm(unittest.TestCase):

    def test_diakritika_se_odstrani(self) -> None:
        self.assertEqual(_norm("Dotčené soubory"), "dotcene soubory")
        self.assertEqual(_norm("Ověření"), "overeni")

    def test_velka_pismena_s_diakritikou(self) -> None:
        self.assertEqual(_norm("NÁROK ŽŽ ŠŤ"), "narok zz st")

    def test_interpunkce_se_nahradi_mezerou(self) -> None:
        self.assertEqual(_norm("Ověření (brána)"), "overeni brana")
        self.assertEqual(_norm("Definition of done!"), "definition of done")

    def test_emoji_a_ozdoby_zmizi(self) -> None:
        self.assertEqual(_norm("Dotčené soubory  ⚠️ NÁROK"), "dotcene soubory narok")

    def test_vicenasobne_mezery_se_slouci(self) -> None:
        self.assertEqual(_norm("  Issues   a    dalsi  "), "issues a dalsi")

    def test_cislice_zustanou(self) -> None:
        self.assertEqual(_norm("Krok 2 — příprava"), "krok 2 priprava")

    def test_je_idempotentni(self) -> None:
        for s in ("Dotčené soubory  ⚠️ NÁROK", "Ověření (brána)", "Issues"):
            with self.subTest(s=s):
                self.assertEqual(_norm(_norm(s)), _norm(s))


# --------------------------------------------------------------------------
# chip 06 #1 — hotove_issues()
# --------------------------------------------------------------------------
class TestHotoveIssues(ZakladChipu):
    """Sdílené počítání odškrtnutých issues (dřív lokálně v `chip_status.py`)."""

    def test_pocita_jen_odskrtnute(self) -> None:
        c = self.brief("""
            ## Issues

            - [ ] #1 — otevřené
            - [x] #2 — hotové
            - [X] #3 — hotové velkým X
            """)
        self.assertEqual(c.hotove_issues(), ["#2 — hotové", "#3 — hotové velkým X"])
        self.assertEqual(len(c.issues()), 3)

    def test_je_podmnozinou_issues(self) -> None:
        """Hotových nesmí nikdy vyjít víc než celkových — zlomek `hotové/celkem`."""
        c = self.brief("""
            ## Issues

              - [x] #1 — odsazené
            - [ ] #2 — otevřené
            - jen poznámka bez zaškrtávátka
            """)
        self.assertEqual(c.hotove_issues(), ["#1 — odsazené"])
        self.assertTrue(set(c.hotove_issues()) <= set(c.issues()))

    def test_radky_mimo_sekci_se_nepocitaji(self) -> None:
        c = self.brief("""
            ## Issues

            - [x] #1 — patří sem

            ## Definition of done

            - [x] tohle je DoD, ne issue
            """)
        self.assertEqual(c.hotove_issues(), ["#1 — patří sem"])

    def test_chybejici_sekce_dava_prazdny_seznam(self) -> None:
        c = self.brief("""
            ## Definition of done

            - [x] něco
            """)
        self.assertEqual(c.hotove_issues(), [])

    def test_nic_odskrtnuteho_dava_prazdny_seznam(self) -> None:
        c = self.brief("""
            ## Issues

            - [ ] #1 — otevřené
            """)
        self.assertEqual(c.hotove_issues(), [])


# --------------------------------------------------------------------------
# chip 06 #2 + #6 — prepis_stav()
# --------------------------------------------------------------------------
class TestPrepisStav(ZakladChipu):
    """Textový přepis `stav:` (dřív lokálně v `chip_run.py`).

    Briefy se zapisují s CRLF a diakritikou — smysl funkce je právě v tom, že
    se souboru mimo hodnotu `stav:` nesmí dotknout ani bajt.
    """

    ZDROJ = ("---\n"
             "chip: 07\n"
             "nazev: pokusny\n"
             "stav: {stav}\n"
             "---\n"
             "\n"
             "# CHIP 07 — diakritika (ěščřžýáíé)\n"
             "\n"
             "## Issues\n"
             "\n"
             "- [ ] #1 — první\n")

    def zapis_brief(self, stav: str = "ready") -> Path:
        cesta = self.dir / "07-pokusny.md"
        cesta.write_bytes(self.ZDROJ.format(stav=stav).replace("\n", "\r\n").encode("utf-8"))
        return cesta

    def test_ready_na_running_a_zbytek_bajt_v_bajt(self) -> None:
        cesta = self.zapis_brief()
        pred = cesta.read_bytes()
        self.assertTrue(chip_common.prepis_stav(cesta))
        po = cesta.read_bytes()
        self.assertEqual(po, pred.replace(b"stav: ready", b"stav: running", 1))
        self.assertEqual(po.count(b"\r\n"), pred.count(b"\r\n"))
        self.assertIn("ěščřžýáíé".encode("utf-8"), po)
        self.assertEqual(parse(cesta).stav, "running")

    def test_cilovy_stav_muze_byt_jiny_nez_running(self) -> None:
        """Orchestrátor přepíná i na `merged` — `novy` proto není napevno."""
        cesta = self.zapis_brief(stav="gated")
        self.assertTrue(chip_common.prepis_stav(cesta, "merged", ocekavany="gated"))
        self.assertEqual(parse(cesta).stav, "merged")

    def test_cilovy_stav_bez_ocekavaneho(self) -> None:
        cesta = self.zapis_brief(stav="running")
        self.assertTrue(chip_common.prepis_stav(cesta, "blocked", ocekavany=None))
        self.assertEqual(parse(cesta).stav, "blocked")

    def test_jina_nez_ocekavana_hodnota_se_nemeni(self) -> None:
        cesta = self.zapis_brief(stav="draft")
        pred = cesta.read_bytes()
        self.assertFalse(chip_common.prepis_stav(cesta))
        self.assertEqual(cesta.read_bytes(), pred)

    def test_uz_prepsany_stav_se_nezapisuje(self) -> None:
        cesta = self.zapis_brief(stav="running")
        pred = cesta.read_bytes()
        self.assertFalse(chip_common.prepis_stav(cesta, ocekavany=None))
        self.assertEqual(cesta.read_bytes(), pred)

    def test_kdyz_neni_co_menit_soubor_se_vubec_neotevre_na_zapis(self) -> None:
        """Nesmí sáhnout na soubor — jinak by se měnil čas změny bez důvodu."""
        cesta = self.zapis_brief(stav="draft")
        with mock.patch.object(Path, "write_bytes") as zapis:
            self.assertFalse(chip_common.prepis_stav(cesta))
        zapis.assert_not_called()

    def test_bez_frontmatteru(self) -> None:
        cesta = self.dir / "bez-hlavicky.txt"
        cesta.write_bytes(b"# nadpis\r\nstav: ready\r\n")
        self.assertFalse(chip_common.prepis_stav(cesta))
        self.assertEqual(cesta.read_bytes(), b"# nadpis\r\nstav: ready\r\n")

    def test_neuzavreny_frontmatter_se_neprepise(self) -> None:
        cesta = self.dir / "07-pokusny.md"
        cesta.write_bytes(b"---\r\nstav: ready\r\n\r\n# CHIP 07\r\n")
        pred = cesta.read_bytes()
        self.assertFalse(chip_common.prepis_stav(cesta))
        self.assertEqual(cesta.read_bytes(), pred)

    def test_chybejici_klic_stav(self) -> None:
        cesta = self.dir / "07-pokusny.md"
        cesta.write_bytes(b"---\r\nchip: 07\r\n---\r\n\r\n# CHIP 07\r\n")
        pred = cesta.read_bytes()
        self.assertFalse(chip_common.prepis_stav(cesta))
        self.assertEqual(cesta.read_bytes(), pred)

    def test_stav_mimo_frontmatter_se_neprepise(self) -> None:
        """`stav:` v těle dokumentu není frontmatter — nesmí se přepsat."""
        cesta = self.zapis_brief(stav="draft")
        text = cesta.read_bytes() + b"\r\nstav: ready\r\n"
        cesta.write_bytes(text)
        self.assertFalse(chip_common.prepis_stav(cesta))
        self.assertEqual(cesta.read_bytes(), text)

    def test_poznamka_za_hodnotou_prezije(self) -> None:
        """Přepisuje se jen hodnota, ne celý řádek."""
        cesta = self.dir / "07-pokusny.md"
        cesta.write_bytes(b"---\r\nstav: ready   # cekame na lint\r\n---\r\n")
        self.assertTrue(chip_common.prepis_stav(cesta))
        self.assertEqual(cesta.read_bytes(),
                         b"---\r\nstav: running   # cekame na lint\r\n---\r\n")


# --------------------------------------------------------------------------
# Integrace — skutečné briefy v repu
# --------------------------------------------------------------------------
class TestSkutecneBriefy(unittest.TestCase):
    """Parser musí zvládnout briefy, které v repu opravdu leží."""

    def setUp(self) -> None:
        self._puvodni_chips_dir = chip_common.CHIPS_DIR
        chip_common.CHIPS_DIR = chip_common.ROOT / "chips"

    def tearDown(self) -> None:
        chip_common.CHIPS_DIR = self._puvodni_chips_dir

    def test_kazdy_brief_ma_id_a_stav(self) -> None:
        chipy = nacti_vse()
        self.assertTrue(chipy, "v chips/ nejsou žádné briefy")
        for c in chipy:
            with self.subTest(brief=c.path.name):
                self.assertRegex(c.id, r"^\d+$")
                self.assertIn(c.stav, chip_common.STAVY)

    def test_kazdy_brief_ma_povinne_sekce(self) -> None:
        for c in nacti_vse():
            for klic in ("issues", "dotcene soubory", "definition of done", "overeni brana"):
                with self.subTest(brief=c.path.name, sekce=klic):
                    self.assertIsNotNone(c.najdi(klic))

    def test_kazdy_brief_narokuje_aspon_jednu_cestu(self) -> None:
        for c in nacti_vse():
            with self.subTest(brief=c.path.name):
                self.assertTrue(c.soubory())


if __name__ == "__main__":
    unittest.main()
