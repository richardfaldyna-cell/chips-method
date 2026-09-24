"""Testy brány `tools/chip_lint.py`.

Každý test si staví vlastní dočasné repo i vlastní adresář s chip briefy
(`tempfile`) a po sobě uklidí — nic nezávisí na stavu disku ani na obsahu
`chips/` v tomhle repu. Pouze standardní knihovna, žádný pytest.

Čísla `#1` … `#12` u tříd a metod odkazují na issues z briefu
`chips/01-testy-lint.md`.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import chip_common  # noqa: E402
import chip_lint  # noqa: E402

PLOT = "```"


class ZakladChipu(unittest.TestCase):
    """Dočasné repo + dočasný adresář s briefy, generátor briefů, spouštěč lintu."""

    def setUp(self) -> None:
        self._puvodni_chips_dir = chip_common.CHIPS_DIR
        self.tmp = Path(tempfile.mkdtemp(prefix="chip_lint_test_")).resolve()
        self.chips_dir = self.tmp / "chips"
        self.chips_dir.mkdir()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.addCleanup(self._uklid)

    def _uklid(self) -> None:
        chip_common.CHIPS_DIR = self._puvodni_chips_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- pomocníci ---------------------------------------------------------

    def vyrob_soubor(self, rel: str) -> Path:
        """Založí prázdný soubor v dočasném repu (včetně adresářů)."""
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
        return p

    def napis_brief(self, jmeno: str, *, chip: str | None = None, stav: str = "ready",
                    soubory: tuple[str, ...] = ("modul.py",),
                    issues: tuple[str, ...] = ("#1 — prvni krok",),
                    zavisi_na: str = "", repo: str | None = None,
                    bez_repo: bool = False, vynech: tuple[str, ...] = (),
                    vetev: str | None = None, proza: str = "Testovaci brief.",
                    log: tuple[str, ...] = (),
                    greenfield: str | None = None) -> Path:
        """Vyrobí syntakticky platný brief; parametry umí každou vadu rozbít cíleně.

        `vetev`, `proza` a `log` existují kvůli placeholderům: tentýž řetězec
        je v identitě briefu vada, kdežto v próze nebo v Logu jen citace.
        `greenfield` se do frontmatteru dopíše jen když se předá — chip 17
        potřebuje porovnat TENTÝŽ brief s příznakem a bez něj.
        """
        chip = chip or jmeno.split("-")[0]
        cesta_repa = self.repo.as_posix() if repo is None else repo
        fm = ["---", f"chip: {chip}", f"nazev: {jmeno}", f"stav: {stav}",
              f"zavisi_na: {zavisi_na}"]
        if greenfield is not None:
            fm.append(f"greenfield: {greenfield}")
        if not bez_repo:
            fm.append(f"repo: {cesta_repa}")
        fm += [f"vetev: {vetev if vetev is not None else 'chip/' + jmeno}",
               f"worktree: ../wt-{chip}", "---", "", ""]

        casti = ["\n".join(fm), f"# CHIP {chip} — {jmeno}\n\n{proza}\n\n"]
        sekce = {
            "issues": ("Issues", "\n".join(f"- [ ] {i}" for i in issues)),
            "soubory": ("Dotčené soubory  ⚠️ NÁROK",
                        PLOT + "\n" + "\n".join(soubory) + "\n" + PLOT),
            "done": ("Definition of done", "- [ ] brána projde"),
            "brana": ("Ověření (brána)", PLOT + "bash\npython tools/chip_lint.py\n" + PLOT),
        }
        for klic, (nadpis, telo) in sekce.items():
            if klic in vynech:
                continue
            casti.append(f"## {nadpis}\n\n{telo}\n\n")
        casti.append("## Log\n\n| Datum | Stav | Poznámka |\n|---|---|---|\n"
                     + "".join(f"| 2026-07-27 | {stav} | {r} |\n" for r in log))

        p = self.chips_dir / f"{jmeno}.md"
        p.write_text("".join(casti), encoding="utf-8")
        return p

    def spust(self, *argv: str) -> tuple[int, str]:
        """Zavolá `chip_lint.main()` nad dočasným adresářem; vrátí (kód, stdout)."""
        proud = io.StringIO()
        cely_argv = ["chip_lint.py", "--dir", str(self.chips_dir), *argv]
        with patch.object(sys, "argv", cely_argv):
            with contextlib.redirect_stdout(proud):
                kod = chip_lint.main()
        return kod, proud.getvalue()

    def radky_s(self, vystup: str, jehla: str) -> list[str]:
        return [r.strip() for r in vystup.splitlines() if jehla in r]

    def nacti(self, path: Path):
        return chip_common.parse(path)


# =========================================================================
# #1, #2, #5 — jádro disjunktnosti na úrovni jednotlivých funkcí
# =========================================================================

class TestPrekryv(unittest.TestCase):
    """#1 + #2 — `prekryv()` rozhoduje o disjunktnosti dvou nároků."""

    def test_prekryv_shodna_cesta(self):
        # #1 — dva chipy si nárokují úplně stejný soubor
        self.assertTrue(chip_lint.prekryv("src/modul.py", "src/modul.py"))

    def test_prekryv_adresar_obsahuje_soubor(self):
        # #1 — nárok na adresář pohltí nárok na soubor uvnitř (v obou pořadích)
        self.assertTrue(chip_lint.prekryv("src", "src/modul.py"))
        self.assertTrue(chip_lint.prekryv("src/modul.py", "src"))

    def test_prekryv_dva_ruzne_soubory_nekoliduji(self):
        # #1 — disjunktní nároky se hlásit nesmí
        self.assertFalse(chip_lint.prekryv("src/a.py", "src/b.py"))
        self.assertFalse(chip_lint.prekryv("src/a.py", "src/ab.py"))
        self.assertFalse(chip_lint.prekryv("src/a.py", "tests/a.py"))

    def test_prekryv_vzor_a_soubor(self):
        # #2 — vzor × konkrétní soubor, v obou pořadích
        self.assertTrue(chip_lint.prekryv("src/*.py", "src/modul.py"))
        self.assertTrue(chip_lint.prekryv("src/modul.py", "src/*.py"))
        # Dřív tu stálo assertFalse pro ("src/*.py", "src/data.json") — od
        # chipu 11 (#1) má literál adresářovou sémantiku a `src/*.py` umí
        # matchnout `src/data.json/x.py` (`*` jde i přes `/`), takže tahle
        # dvojice je záměrně kolize navíc. Prokazatelně disjunktní zůstává
        # literál, pod kterým žádná shoda vzoru ležet nemůže:
        self.assertFalse(chip_lint.prekryv("src/*.py", "tests/data.json"))

    def test_prekryv_dva_vzory(self):
        # #2 — vzor × vzor; shodné vzory a nesouvisející vzory sedí
        self.assertTrue(chip_lint.prekryv("src/*.py", "src/*.py"))
        self.assertTrue(chip_lint.prekryv("src/*.py", "src/*"))
        self.assertFalse(chip_lint.prekryv("src/*.py", "tests/*.js"))

    def test_prekryv_dvou_ruznotvarych_vzoru(self):
        """#2 — bývalý nález N1 (chip 05): vzor × vzor, když se liší tvarem.

        `src/*.py` a `src/mo*` sdílejí `src/modul.py`. Dřív se druhý vzor bral
        doslova (`fnmatch(retezec, vzor)`) a kolize propadla — zachytilo ji až
        rozbalení v `naroky()`, tedy jen když sdílený soubor v repu **už
        existuje**. Ve stavech `running`/`gated` a u cest `# nový` tiše prošla.
        Od chipu 05 se počítá skutečný průnik obou globů.
        """
        self.assertTrue(chip_lint.prekryv("src/*.py", "src/mo*"))
        self.assertTrue(chip_lint.prekryv("src/mo*", "src/*.py"))

    def test_prekryv_prokazatelne_disjunktnich_vzoru_je_false(self):
        # #2 — průnik nesmí být „hlásím všechno": tyhle dvojice sdílet nic nemohou
        for a, b in (("src/a_*.py", "src/b_*.py"),      # jiný prefix za 'src/'
                     ("src/*.py", "tests/*.py"),        # jiný adresář
                     ("src/*.py", "tests/*.js"),
                     ("tools/chip_*.py", "tests/*_lint.py")):
            with self.subTest(a=a, b=b):
                self.assertFalse(chip_lint.prekryv(a, b))
                self.assertFalse(chip_lint.prekryv(b, a), "musí být symetrické")

    def test_prekryv_vzoru_se_spolecnym_souborem_je_true(self):
        # #1 — společný soubor existuje, i když se vzory tvarem neshodují
        for a, b in (("src/*.py", "src/mo*"),           # src/modul.py
                     ("tools/chip_*.py", "tools/*_lint.py"),   # tools/chip_lint.py
                     ("src/a*", "src/*b"),              # src/ab
                     ("src/*", "src/mo*")):
            with self.subTest(a=a, b=b):
                self.assertTrue(chip_lint.prekryv(a, b))
                self.assertTrue(chip_lint.prekryv(b, a), "musí být symetrické")

    def test_prekryv_adresar_a_glob_bez_textoveho_prefixu(self):
        """#1 (chip 11) — literál-adresář × glob, který matchuje cesty uvnitř něj.

        `prekryv('src', '*.py')` bývalo False, přestože `fnmatch('src/foo.py',
        '*.py')` je True a `src/foo.py` leží uvnitř nároku `src`. Literál bez
        zástupných znaků se proto porovnává i jako prefix možných shod globu.
        """
        self.assertTrue(chip_lint.prekryv("src", "*.py"))
        self.assertTrue(chip_lint.prekryv("*.py", "src"), "musí být symetrické")
        self.assertTrue(chip_lint.prekryv("src", "*/modul.py"))
        self.assertTrue(chip_lint.prekryv("docs", "*.md"))

    def test_prekryv_adresar_a_glob_jinam_zustava_disjunktni(self):
        # #1 (chip 11) — adresářová sémantika nesmí udělat kolizi ze VŠEHO:
        #                pod `src` žádná shoda `tests/*.py` neleží
        self.assertFalse(chip_lint.prekryv("src", "tests/*.py"))
        self.assertFalse(chip_lint.prekryv("tests/*.py", "src"), "musí být symetrické")
        self.assertFalse(chip_lint.prekryv("src/a.py", "src/b*"))
        self.assertFalse(chip_lint.prekryv("docs", "src/*.md"))

    def test_prekryv_otaznik_je_prave_jeden_znak(self):
        # #1 — `?` sedne na jeden znak, ne na dva a ne na nic
        self.assertTrue(chip_lint.prekryv("src/?.py", "src/a.py"))
        self.assertTrue(chip_lint.prekryv("src/?.py", "src/*.py"))
        self.assertFalse(chip_lint.prekryv("src/?.py", "src/ab.py"))
        self.assertFalse(chip_lint.prekryv("src/?.py", "src/.py"))

    def test_prekryv_trida_znaku_se_bere_konzervativne(self):
        # #1 — `[…]` = „libovolný znak": raději kolize navíc než přehlédnutá,
        #      ale ani tak se nesmí slepit dvě evidentně cizí cesty
        self.assertTrue(chip_lint.prekryv("src/[ab].py", "src/a.py"))
        self.assertTrue(chip_lint.prekryv("src/[ab].py", "src/c.py"))   # nadhodnoceno záměrně
        self.assertFalse(chip_lint.prekryv("src/[ab].py", "src/cc.py"))
        self.assertFalse(chip_lint.prekryv("src/[ab].py", "tests/a.py"))

    def test_prekryv_dlouhych_vzoru_s_hvezdickami_neexploduje(self):
        # #1 — bez memoizace `(i, j)` je rekurze exponenciální; strop je velkorysý,
        #      jde o rozdíl mezi zlomkem sekundy a „nikdy"
        a = "src/" + "*x" * 40 + ".py"
        b = "src/" + "y*" * 40 + ".py"
        start = time.monotonic()
        chip_lint.prekryv(a, b)
        self.assertLess(time.monotonic() - start, 2.0)

    def test_prekryv_vzoru_je_radeji_prisnejsi_pres_lomitko(self):
        # #2 — `fnmatch` bere `*` i přes `/`; dokumentované záměrné přehánění
        self.assertTrue(chip_lint.prekryv("src/*.py", "src/hluboko/modul.py"))

    def test_vzor_pozna_zastupne_znaky(self):
        # #2 — co je vzor a co konkrétní cesta
        for cesta in ("src/*.py", "src/?.py", "src/[ab].py"):
            with self.subTest(cesta=cesta):
                self.assertTrue(chip_lint.vzor(cesta))
        self.assertFalse(chip_lint.vzor("src/modul.py"))

    def test_absolutni_rozpozna_disk_i_lomitko(self):
        # #5 — `/x`, `\x` i `C:/x` jsou absolutní; relativní cesta ne
        for cesta in ("/src/x.py", "\\src\\x.py", "C:/src/x.py", "D:\\src\\x.py"):
            with self.subTest(cesta=cesta):
                self.assertTrue(chip_lint.absolutni(cesta))
        for cesta in ("src/x.py", "../src/x.py", "x.py"):
            with self.subTest(cesta=cesta):
                self.assertFalse(chip_lint.absolutni(cesta))


class TestNaroky(ZakladChipu):
    """#2 — rozbalení vzorů podle obsahu repa."""

    def test_naroky_rozbali_vzor_a_ponecha_ho(self):
        self.vyrob_soubor("src/a.py")
        self.vyrob_soubor("src/b.py")
        self.vyrob_soubor("src/data.json")
        p = self.napis_brief("01-vzor", soubory=("src/*.py",))
        dvojice = chip_lint.naroky(self.nacti(p))
        self.assertIn(("src/*.py", "src/*.py"), dvojice, "vzor musí v seznamu zůstat")
        self.assertIn(("src/a.py", "src/*.py"), dvojice)
        self.assertIn(("src/b.py", "src/*.py"), dvojice)
        self.assertNotIn(("src/data.json", "src/*.py"), dvojice)

    def test_naroky_konkretni_cestu_nerozbaluji(self):
        self.vyrob_soubor("modul.py")
        p = self.napis_brief("01-presny", soubory=("modul.py",))
        self.assertEqual(chip_lint.naroky(self.nacti(p)), [("modul.py", "modul.py")])

    def test_naroky_absolutni_vzor_nerozbaluji_a_nespadnou(self):
        """#3 (chip 11) — `repo.glob('C:/data/*.xlsx')` házel NotImplementedError.

        Nevalidní tvar cesty hlásí `zkontroluj_cesty`; `naroky()` běží i mimo
        ni (kolizní smyčka) a nesmí na absolutním vzoru spadnout tracebackem.
        """
        for cesta in ("C:/data/*.xlsx", "/abs/*.py", "../jinde/*.py"):
            with self.subTest(cesta=cesta):
                p = self.napis_brief("01-abs", soubory=(cesta,))
                self.assertEqual(chip_lint.naroky(self.nacti(p)), [(cesta, cesta)])


# =========================================================================
# #1, #2, #3, #8, #11 — kolize mezi chipy z pohledu celé brány
# =========================================================================

class TestKolizeMeziChipy(ZakladChipu):

    def test_kolize_shodna_cesta_je_chyba(self):
        # #1
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", soubory=("modul.py",))
        self.napis_brief("02-beta", soubory=("modul.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertEqual(len(self.radky_s(vystup, "KOLIZE")), 1, vystup)
        self.assertIn("modul.py", vystup)

    def test_kolize_adresar_versus_soubor(self):
        # #1 — adresář ⊃ soubor
        self.vyrob_soubor("src/modul.py")
        self.napis_brief("01-alfa", soubory=("src",))
        self.napis_brief("02-beta", soubory=("src/modul.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        radky = self.radky_s(vystup, "KOLIZE")
        self.assertEqual(len(radky), 1, vystup)
        self.assertIn("src", radky[0])

    def test_dva_ruzne_soubory_nekoliduji(self):
        # #1 — kontrolní vzorek: čistý stav nesmí nic hlásit
        self.vyrob_soubor("a.py")
        self.vyrob_soubor("b.py")
        self.napis_brief("01-alfa", soubory=("a.py",))
        self.napis_brief("02-beta", soubory=("b.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertEqual(self.radky_s(vystup, "KOLIZE"), [])

    def test_kolize_vzor_versus_soubor(self):
        # #2
        self.vyrob_soubor("src/a.py")
        self.vyrob_soubor("src/b.py")
        self.napis_brief("01-alfa", soubory=("src/*.py",))
        self.napis_brief("02-beta", soubory=("src/a.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertEqual(len(self.radky_s(vystup, "KOLIZE")), 1, vystup)

    def test_kolize_vzor_versus_vzor(self):
        # #2
        self.vyrob_soubor("src/a.py")
        self.napis_brief("01-alfa", soubory=("src/*.py",))
        self.napis_brief("02-beta", soubory=("src/a*",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertTrue(self.radky_s(vystup, "KOLIZE"), vystup)

    def test_kolize_adresar_versus_glob_bez_textoveho_prefixu(self):
        # #1 (chip 11) — nárok na adresář × glob bez textového prefixu:
        #                `src` a `*.py` sdílejí `src/modul.py`
        self.vyrob_soubor("src/modul.py")
        self.vyrob_soubor("top.py")               # ať vzor `*.py` v repu něco najde
        self.napis_brief("01-alfa", soubory=("src",))
        self.napis_brief("02-beta", soubory=("*.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        radky = self.radky_s(vystup, "KOLIZE")
        self.assertEqual(len(radky), 1, vystup)
        self.assertIn("src", radky[0])
        self.assertIn("*.py", radky[0])

    def test_kolize_ruznotvarych_vzoru_bez_spolecneho_souboru_v_repu(self):
        # N1 (chip 05) — vzory se v repu nemají do čeho společného rozbalit,
        #                kolizi na `src/modul.py` musí najít sám `prekryv()`
        self.vyrob_soubor("src/alfa.py")     # sedne jen na `src/*.py`
        self.vyrob_soubor("src/most.txt")    # sedne jen na `src/mo*`
        self.napis_brief("01-alfa", soubory=("src/*.py",))
        self.napis_brief("02-beta", soubory=("src/mo*",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        radky = self.radky_s(vystup, "KOLIZE")
        self.assertEqual(len(radky), 1, vystup)
        self.assertIn("src/*.py", radky[0])
        self.assertIn("src/mo*", radky[0])

    def test_disjunktni_vzory_branu_neshodi(self):
        # N1 (chip 05) — kontrolní vzorek: přísnější průnik nesmí hlásit nesmysly
        self.vyrob_soubor("src/a_prvni.py")
        self.vyrob_soubor("src/b_druhy.py")
        self.napis_brief("01-alfa", soubory=("src/a_*.py",))
        self.napis_brief("02-beta", soubory=("src/b_*.py",))
        kod, vystup = self.spust()
        self.assertEqual(self.radky_s(vystup, "KOLIZE"), [], vystup)
        self.assertEqual(kod, 0, vystup)

    def test_kolize_vzoru_se_souborem_ktery_teprve_vznikne(self):
        # #2 — `# nový` soubor v repu ještě není, rozbalení ho nenajde;
        #      chytit ho musí vzor ponechaný v seznamu nároků
        self.vyrob_soubor("src/a.py")
        self.napis_brief("01-alfa", soubory=("src/*.py",))
        self.napis_brief("02-beta", soubory=("src/novy.py    # nový",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        radky = self.radky_s(vystup, "KOLIZE")
        self.assertEqual(len(radky), 1, vystup)
        self.assertIn("src/novy.py", radky[0])

    def test_kolize_je_jeden_radek_na_dvojici_naroku_s_dukazem(self):
        # #3 — rozbalený vzor nesmí vygenerovat tři skoro stejné řádky
        for n in ("a.py", "b.py", "c.py"):
            self.vyrob_soubor(f"src/{n}")
        self.napis_brief("01-alfa", soubory=("src/*.py",))
        self.napis_brief("02-beta", soubory=("src/*.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        radky = self.radky_s(vystup, "KOLIZE")
        self.assertEqual(len(radky), 1, vystup)
        self.assertIn("src/*.py", radky[0])
        self.assertIn("(např.", radky[0])

    def test_kolize_presnych_cest_dukaz_nepridava(self):
        # #3 — když je nárok sám důkazem, `(např. …)` je zbytečné
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", soubory=("modul.py",))
        self.napis_brief("02-beta", soubory=("modul.py",))
        _, vystup = self.spust()
        radky = self.radky_s(vystup, "KOLIZE")
        self.assertEqual(len(radky), 1, vystup)
        self.assertNotIn("(např.", radky[0])

    def test_predek_a_potomek_se_na_kolizi_nekontroluji(self):
        # #11 — chipy ve vztahu závislosti nikdy neběží současně
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", soubory=("modul.py",))
        self.napis_brief("02-beta", soubory=("modul.py",), zavisi_na="01")
        kod, vystup = self.spust()
        self.assertEqual(self.radky_s(vystup, "KOLIZE"), [], vystup)
        self.assertEqual(kod, 0, vystup)
        self.assertIn("čeká na chip 01", vystup)

    def test_merged_a_blocked_chipy_nekoliduji(self):
        # #8 — historie už o nároky nesoupeří
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", soubory=("modul.py",), stav="ready")
        self.napis_brief("02-beta", soubory=("modul.py",), stav="merged")
        self.napis_brief("03-gama", soubory=("modul.py",), stav="blocked")
        kod, vystup = self.spust()
        self.assertEqual(self.radky_s(vystup, "KOLIZE"), [], vystup)
        self.assertEqual(kod, 0, vystup)


# =========================================================================
# #4, #5, #6, #7, #8 — existence a tvar nárokovaných cest
# =========================================================================

class TestExistenceCest(ZakladChipu):

    def test_chybejici_soubor_je_chyba(self):
        # #4
        p = self.napis_brief("01-alfa", soubory=("neexistuje.py",))
        chyby, varovani = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual(len(chyby), 1, chyby)
        self.assertIn("neexistuje.py", chyby[0])
        self.assertEqual(varovani, [])
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)

    def test_novy_soubor_projde(self):
        # #4
        p = self.napis_brief("01-alfa", soubory=("jeste_neni.py    # nový",))
        chyby, varovani = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual((chyby, varovani), ([], []))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)

    def test_existujici_oznaceny_jako_novy_je_varovani(self):
        # #4 — brief je zastaralý, ale bránu to neshodí
        self.vyrob_soubor("uz_existuje.py")
        p = self.napis_brief("01-alfa", soubory=("uz_existuje.py    # nový",))
        chyby, varovani = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual(chyby, [])
        self.assertEqual(len(varovani), 1, varovani)
        self.assertIn("zastaralý", varovani[0])
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)

    def test_absolutni_cesta_je_chyba(self):
        # #5
        for cesta in ("/abs/soubor.py", "C:/abs/soubor.py"):
            with self.subTest(cesta=cesta):
                p = self.napis_brief("01-alfa", soubory=(cesta,))
                chyby, _ = chip_lint.zkontroluj_cesty(self.nacti(p))
                self.assertEqual(len(chyby), 1, chyby)
                self.assertIn("musí být relativní", chyby[0])

    def test_cesta_s_dvema_teckami_je_chyba(self):
        # #5
        p = self.napis_brief("01-alfa", soubory=("../mimo/soubor.py",))
        chyby, _ = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual(len(chyby), 1, chyby)
        self.assertIn("bez '..'", chyby[0])
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)

    def test_absolutni_vzor_je_hlaska_ne_traceback(self):
        # #3 (chip 11) — celá brána: dřív spadla NotImplementedError z `naroky()`
        #                dřív, než lint cokoli vypsal
        self.napis_brief("01-alfa", soubory=("C:/data/*.xlsx",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("musí být relativní", vystup)

    def test_vzor_s_dvema_teckami_je_hlaska_ne_traceback(self):
        # #3 (chip 11) — `..` se do `repo.glob()` nesmí dostat ani u vzoru
        self.napis_brief("01-alfa", soubory=("../jinde/*.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("bez '..'", vystup)

    def test_vzor_ktery_nic_nenajde_je_chyba(self):
        # #6
        self.vyrob_soubor("src/data.json")
        p = self.napis_brief("01-alfa", soubory=("src/*.py",))
        chyby, _ = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual(len(chyby), 1, chyby)
        self.assertIn("nic nenajde", chyby[0])
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)

    def test_vzor_se_shodou_projde(self):
        # #6 — kontrolní vzorek
        self.vyrob_soubor("src/a.py")
        p = self.napis_brief("01-alfa", soubory=("src/*.py",))
        self.assertEqual(chip_lint.zkontroluj_cesty(self.nacti(p)), ([], []))

    def test_chybejici_repo_je_chyba(self):
        # #7
        p = self.napis_brief("01-alfa", bez_repo=True)
        chyby, _ = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual(len(chyby), 1, chyby)
        self.assertIn("nemá 'repo:'", chyby[0])
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)

    def test_neexistujici_adresar_repa_je_chyba(self):
        # #7
        p = self.napis_brief("01-alfa", repo=(self.tmp / "neni-tu").as_posix())
        chyby, _ = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual(len(chyby), 1, chyby)
        self.assertIn("neexistuje", chyby[0])
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)

    def test_draft_kontrolu_cest_preskoci(self):
        # #8 — brief se teprve píše, nároky ještě nemusí sedět
        p = self.napis_brief("01-alfa", stav="draft", soubory=("neexistuje.py",))
        self.assertEqual(chip_lint.zkontroluj_cesty(self.nacti(p)), ([], []))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)

    def test_running_kontrolu_cest_preskoci(self):
        # #8 — za běhu je strom rozpracovaný, kontrola by hlásila falešné nálezy
        p = self.napis_brief("01-alfa", stav="running", soubory=("neexistuje.py",))
        self.assertEqual(chip_lint.zkontroluj_cesty(self.nacti(p)), ([], []))


# =========================================================================
# N2 (chip 05) — proti kterému stromu se existence cest vůbec ověřuje
# =========================================================================

class TestStromKeKontrole(ZakladChipu):
    """Brief ve worktree se musí kontrolovat proti worktree, ne proti hlavnímu stromu.

    `repo:` ve frontmatteru ukazuje na hlavní strom (podle něj `chip_run.py`
    worktree zakládá), takže dokud lint bral `repo:` i na kontrolu existence,
    ověřoval nároky proti cizímu checkoutu — soubor smazaný ve worktree tiše prošel.
    """

    def setUp(self) -> None:
        super().setUp()
        if chip_lint.git_koren(self.tmp) is not None:      # pragma: no cover
            self.skipTest("dočasný adresář sám leží v git stromu — test by měřil něco jiného")
        self.hlavni = self.tmp / "hlavni"
        (self.hlavni / "chips").mkdir(parents=True)
        (self.hlavni / ".git").mkdir()                     # hlavní checkout: `.git` je adresář
        self.wt = self.tmp / "wt-01"
        (self.wt / "chips").mkdir(parents=True)
        (self.wt / ".git").write_text(                     # worktree: `.git` je SOUBOR
            f"gitdir: {(self.hlavni / '.git' / 'worktrees' / 'wt-01').as_posix()}\n",
            encoding="utf-8")

    def vyrob_v(self, koren: Path, rel: str) -> Path:
        p = koren / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
        return p

    def brief_ve_worktree(self, **kw) -> Path:
        """Brief uložený do `wt-01/chips/`, s `repo:` mířícím na hlavní strom."""
        self.chips_dir = self.wt / "chips"
        return self.napis_brief("01-alfa", repo=self.hlavni.as_posix(), **kw)

    # --- detekce stromu ----------------------------------------------------

    def test_git_koren_pozna_adresar_i_soubor(self):
        # #4 — ve worktree je `.git` soubor, v hlavním stromu adresář
        self.assertEqual(chip_lint.git_koren(self.hlavni / "chips"), self.hlavni)
        self.assertEqual(chip_lint.git_koren(self.wt / "chips"), self.wt)
        self.assertEqual(chip_lint.git_koren(self.wt / "chips" / "01-alfa.md"), self.wt)

    def test_git_koren_mimo_git_vraci_none(self):
        # #5
        self.assertIsNone(chip_lint.git_koren(self.chips_dir))

    def test_strom_briefu_ve_worktree_prebije_repo_z_frontmatteru(self):
        # #4
        p = self.brief_ve_worktree(soubory=("modul.py    # nový",))
        c = self.nacti(p)
        self.assertEqual(c.repo_path(), self.hlavni, "repo: se nemění — bere ho chip_run")
        self.assertEqual(chip_lint.strom_ke_kontrole(c), self.wt)

    def test_brief_v_hlavnim_stromu_pouzije_hlavni_strom(self):
        # #4 — chip ještě neběží ve worktree; strom vyjde stejně jako `repo:`
        self.chips_dir = self.hlavni / "chips"
        p = self.napis_brief("01-alfa", repo=self.hlavni.as_posix(),
                             soubory=("modul.py    # nový",))
        self.assertEqual(chip_lint.strom_ke_kontrole(self.nacti(p)), self.hlavni)

    def test_brief_mimo_git_pouziva_repo_z_frontmatteru(self):
        # #5 — režim `--dir` nad samostatným adresářem: chování jako dřív
        p = self.napis_brief("01-alfa", soubory=("modul.py    # nový",))
        self.assertEqual(chip_lint.strom_ke_kontrole(self.nacti(p)), self.repo)

    # --- dopad na bránu ----------------------------------------------------

    def test_soubor_jen_v_hlavnim_stromu_je_ve_worktree_chyba(self):
        # #7 — jádro nálezu N2: tohle dřív tiše prošlo
        self.vyrob_v(self.hlavni, "tools/modul.py")
        p = self.brief_ve_worktree(soubory=("tools/modul.py",))
        chyby, _ = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual(len(chyby), 1, chyby)
        self.assertIn("tools/modul.py", chyby[0])
        self.assertIn("neexistuje", chyby[0])
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)

    def test_soubor_ve_worktree_projde_i_kdyz_v_hlavnim_neni(self):
        # #4 — opačný směr: co chip ve svém stromě má, je platný nárok
        self.vyrob_v(self.wt, "tools/modul.py")
        p = self.brief_ve_worktree(soubory=("tools/modul.py",))
        self.assertEqual(chip_lint.zkontroluj_cesty(self.nacti(p)), ([], []))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)

    def test_vzor_se_rozbaluje_podle_stromu_briefu(self):
        # #4 — `naroky()` musí sahat do téhož stromu, jinak by kolize dokládal
        #      souborem, který ve worktree vůbec není
        self.vyrob_v(self.hlavni, "src/z_hlavniho.py")
        self.vyrob_v(self.wt, "src/z_worktree.py")
        p = self.brief_ve_worktree(soubory=("src/*.py",))
        dvojice = chip_lint.naroky(self.nacti(p))
        self.assertIn(("src/z_worktree.py", "src/*.py"), dvojice)
        self.assertNotIn(("src/z_hlavniho.py", "src/*.py"), dvojice)

    def test_vzor_bez_shody_ve_worktree_je_chyba(self):
        # #4 — vzor se hodnotí proti worktree, i když v hlavním stromu by sedl
        self.vyrob_v(self.hlavni, "src/a.py")
        p = self.brief_ve_worktree(soubory=("src/*.py",))
        chyby, _ = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual(len(chyby), 1, chyby)
        self.assertIn("nic nenajde", chyby[0])

    def test_chybejici_repo_zustava_chybou_i_uvnitr_gitu(self):
        # #6 — strom briefu `repo:` nenahrazuje, jen doplňuje: brána se nesmí zeslabit
        self.vyrob_v(self.wt, "modul.py")
        p = self.brief_ve_worktree(bez_repo=True, soubory=("modul.py",))
        chyby, _ = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual(len(chyby), 1, chyby)
        self.assertIn("nemá 'repo:'", chyby[0])
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)

    def test_neexistujici_repo_zustava_chybou_i_uvnitr_gitu(self):
        # #6 — `repo:` musí platit dál, podle něj se zakládá worktree
        self.vyrob_v(self.wt, "modul.py")
        self.chips_dir = self.wt / "chips"
        p = self.napis_brief("01-alfa", repo=(self.tmp / "neni-tu").as_posix(),
                             soubory=("modul.py",))
        chyby, _ = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual(len(chyby), 1, chyby)
        self.assertIn("neexistuje", chyby[0])
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)


# =========================================================================
# #2 (chip 11) — briefy v jiném repozitáři než cílový projekt
# =========================================================================

class TestStromKeKontroleCiziRepo(ZakladChipu):
    """Brief v CIZÍM repu se musí kontrolovat proti `repo:` z frontmatteru.

    Layout ERP-CHIPS: briefy leží v repu ERP-CHIPS, cílový projekt
    `erp` je vnořený repozitář s vlastním `.git`. `strom_ke_kontrole`
    dřív vracel strom briefu VŽDY, takže existence nároků se ověřovala proti
    repu s briefy — špatnému repozitáři. Strom briefu smí `repo:` přebít jen
    u TÉHOŽ repozitáře (worktree × hlavní strom sdílejí společný `.git`
    adresář); worktree chování hlídá `TestStromKeKontrole`.
    """

    def setUp(self) -> None:
        super().setUp()
        if chip_lint.git_koren(self.tmp) is not None:      # pragma: no cover
            self.skipTest("dočasný adresář sám leží v git stromu — test by měřil něco jiného")
        self.briefy = self.tmp / "briefy"                  # repo s briefy
        (self.briefy / "chips").mkdir(parents=True)
        (self.briefy / ".git").mkdir()
        self.cil = self.briefy / "projekt"                 # vnořený cílový repozitář
        self.cil.mkdir()
        (self.cil / ".git").mkdir()
        self.chips_dir = self.briefy / "chips"

    def vyrob_v(self, koren: Path, rel: str) -> Path:
        p = koren / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
        return p

    def brief_v_cizim_repu(self, **kw) -> Path:
        """Brief v `briefy/chips/`, s `repo:` mířícím na vnořený cílový repozitář."""
        return self.napis_brief("01-alfa", repo=self.cil.as_posix(), **kw)

    def test_strom_ke_kontrole_je_repo_z_frontmatteru(self):
        p = self.brief_v_cizim_repu(soubory=("modul.py    # nový",))
        c = self.nacti(p)
        self.assertEqual(c.repo_path(), self.cil)
        self.assertEqual(chip_lint.strom_ke_kontrole(c), self.cil)

    def test_soubor_v_cilovem_repu_projde(self):
        # jádro nálezu #2: tohle dřív padalo, protože se hledalo v repu briefů
        self.vyrob_v(self.cil, "app/models.py")
        p = self.brief_v_cizim_repu(soubory=("app/models.py",))
        self.assertEqual(chip_lint.zkontroluj_cesty(self.nacti(p)), ([], []))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)

    def test_soubor_jen_v_repu_briefu_je_chyba(self):
        # opačný směr: nárok existující jen vedle briefů je v cílovém repu fikce
        self.vyrob_v(self.briefy, "app/models.py")
        p = self.brief_v_cizim_repu(soubory=("app/models.py",))
        chyby, _ = chip_lint.zkontroluj_cesty(self.nacti(p))
        self.assertEqual(len(chyby), 1, chyby)
        self.assertIn("app/models.py", chyby[0])
        self.assertIn("neexistuje", chyby[0])
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)

    def test_vzor_se_rozbaluje_proti_cilovemu_repu(self):
        self.vyrob_v(self.cil, "src/z_cile.py")
        self.vyrob_v(self.briefy, "src/z_briefu.py")
        p = self.brief_v_cizim_repu(soubory=("src/*.py",))
        dvojice = chip_lint.naroky(self.nacti(p))
        self.assertIn(("src/z_cile.py", "src/*.py"), dvojice)
        self.assertNotIn(("src/z_briefu.py", "src/*.py"), dvojice)


# =========================================================================
# #9 — struktura briefu: povinné sekce, stav, placeholdery
# =========================================================================

class TestStrukturaBriefu(ZakladChipu):

    def test_chybejici_povinna_sekce_je_chyba(self):
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", vynech=("done",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("chybí sekce '## Definition of done'", vystup)

    def test_kazda_povinna_sekce_se_kontroluje(self):
        self.vyrob_soubor("modul.py")
        ocekavane = {"issues": "Issues", "soubory": "Dotčené soubory",
                     "done": "Definition of done", "brana": "Ověření (brána)"}
        for klic, popis in ocekavane.items():
            with self.subTest(sekce=klic):
                self.napis_brief("01-alfa", vynech=(klic,))
                kod, vystup = self.spust()
                self.assertEqual(kod, 1, vystup)
                self.assertIn(f"chybí sekce '## {popis}'", vystup)

    def test_neplatny_stav_je_chyba(self):
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", stav="hotovo")
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("neplatný stav 'hotovo'", vystup)

    def test_zbyly_placeholder_je_varovani(self):
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", issues=("#12 — stručný popis",))
        kod, vystup = self.spust()
        self.assertIn("zůstal placeholder ze šablony", vystup)
        self.assertEqual(kod, 0, vystup)

    def test_prazdna_sekce_dotcenych_souboru_je_chyba(self):
        self.napis_brief("01-alfa", soubory=())
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("nemá žádnou cestu", vystup)

    def test_chip_bez_issues_je_chyba(self):
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", issues=())
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("žádné issues", vystup)


# =========================================================================
# CHIP 15 — placeholder se hlásí jen tam, kde nevyplněný škodí
# =========================================================================

class TestPlaceholdery(ZakladChipu):
    """Dva protichůdné požadavky: nevyplněná šablona se MUSÍ ozvat (#2),
    citace placeholderu v próze / Logu / textu issue NESMÍ (#1)."""

    SABLONA = chip_common.ROOT / "chips" / "TEMPLATE.md"

    def placeholdery(self, vystup: str) -> list[str]:
        return self.radky_s(vystup, "zůstal placeholder")

    # --- #2: kontrola se nesmí stát atrapou --------------------------------

    def test_brief_ze_skutecne_sablony_hlasi_vsechny_ctyri(self):
        """Nad KOPIÍ skutečné `chips/TEMPLATE.md`, ne nad vymyšleným textem —
        šablona se může změnit a test to musí poznat."""
        self.assertTrue(self.SABLONA.is_file(), f"chybí šablona {self.SABLONA}")
        text = self.SABLONA.read_text(encoding="utf-8")
        p = self.chips_dir / "01-ze-sablony.md"
        p.write_text(text.replace("stav: draft", "stav: ready", 1), encoding="utf-8")

        hlasky = chip_lint.zbyle_placeholdery(self.nacti(p))
        for ph in ("src/parser.py", "#12 — stručný popis", "C:/cesta/k/repu",
                   "kratky-nazev-s-pomlckami"):
            with self.subTest(placeholder=ph):
                self.assertTrue(any(f"'{ph}'" in h for h in hlasky),
                                f"nevyplněná šablona neohlásila {ph!r}: {hlasky}")
        _, vystup = self.spust()                    # a projde to i celým lintem
        self.assertEqual(len(self.placeholdery(vystup)), 4, vystup)

    def test_placeholder_v_nazvu_varuje(self):
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-kratky-nazev-s-pomlckami", vetev="ai/chip-01/alfa")
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertIn("'kratky-nazev-s-pomlckami'", vystup)

    def test_placeholder_ve_vetvi_varuje(self):
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", vetev="ai/chip-NN/kratky-nazev-s-pomlckami")
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertIn("'kratky-nazev-s-pomlckami'", vystup)

    def test_placeholder_v_naroku_varuje(self):
        self.vyrob_soubor("src/parser.py")
        self.napis_brief("01-alfa", soubory=("src/parser.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertIn("'src/parser.py'", vystup)

    def test_komentar_za_hodnotou_frontmatteru_kontrolu_nerozhodi(self):
        """Brief 08 má za hodnotou komentář — hledá se hodnota, ne celý řádek."""
        self.napis_brief("01-alfa", repo="C:/cesta/k/repu    # doplnit před spuštěním")
        _, vystup = self.spust()
        self.assertIn("'C:/cesta/k/repu'", vystup)

    # --- #1: citace placeholderu není nedodělek ----------------------------

    def test_citace_v_logu_nevaruje(self):
        # brief 08: `kratky-nazev-s-pomlckami` je citovaný v poznámce Logu
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", log=(
            "T3: `chip_new.py` dosazuje `vetev: ai/chip-NN/kratky-nazev-s-pomlckami`",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertEqual(self.placeholdery(vystup), [], vystup)

    def test_citace_v_proze_nevaruje(self):
        # brief 09: `src/parser.py` je jen ukázka v textu, ne nárok
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", proza="Ukázková cesta ze šablony je `src/parser.py`.")
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertEqual(self.placeholdery(vystup), [], vystup)

    def test_citace_v_textu_issue_nevaruje(self):
        # brief 12: chip, který opravoval právě tenhle placeholder, ho má
        # v textu issue — proto se `kratky-nazev-s-pomlckami` hlídá jen
        # ve frontmatteru („vynechat Log" by tenhle případ nechytlo)
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", issues=(
            "#1 — `chip_slice.py` nahrazuje `vetev: chip/NN-kratky-nazev-s-pomlckami`",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertEqual(self.placeholdery(vystup), [], vystup)

    def test_draft_se_na_placeholdery_nekontroluje(self):
        """Rozdělaný brief placeholdery mít smí — to se nezměnilo."""
        self.napis_brief("01-alfa", stav="draft", soubory=("src/parser.py",),
                         issues=("#12 — stručný popis",), repo="C:/cesta/k/repu")
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertEqual(self.placeholdery(vystup), [], vystup)


# =========================================================================
# #10 — závislosti mezi chipy
# =========================================================================

class TestZavislosti(ZakladChipu):

    def test_neexistujici_zavislost_je_chyba(self):
        self.vyrob_soubor("a.py")
        self.napis_brief("01-alfa", soubory=("a.py",), zavisi_na="09")
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("závisí na chipu 09, který neexistuje", vystup)

    def test_zavislost_sam_na_sobe_je_chyba(self):
        self.vyrob_soubor("a.py")
        self.napis_brief("01-alfa", soubory=("a.py",), zavisi_na="01")
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("závisí sám na sobě", vystup)

    def test_cyklicka_zavislost_je_chyba(self):
        self.vyrob_soubor("a.py")
        self.vyrob_soubor("b.py")
        self.napis_brief("01-alfa", soubory=("a.py",), zavisi_na="02")
        self.napis_brief("02-beta", soubory=("b.py",), zavisi_na="01")
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("cyklická závislost", vystup)

    def test_running_s_nehotovym_predkem_je_chyba(self):
        self.vyrob_soubor("a.py")
        self.vyrob_soubor("b.py")
        self.napis_brief("01-alfa", soubory=("a.py",), stav="ready")
        self.napis_brief("02-beta", soubory=("b.py",), stav="running", zavisi_na="01")
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("očekává se 'merged'", vystup)

    def test_running_s_mergnutym_predkem_projde(self):
        self.vyrob_soubor("a.py")
        self.vyrob_soubor("b.py")
        self.napis_brief("01-alfa", soubory=("a.py",), stav="merged")
        self.napis_brief("02-beta", soubory=("b.py",), stav="running", zavisi_na="01")
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)

    def test_ready_s_nehotovym_predkem_je_jen_varovani(self):
        self.vyrob_soubor("a.py")
        self.vyrob_soubor("b.py")
        self.napis_brief("01-alfa", soubory=("a.py",), stav="ready")
        self.napis_brief("02-beta", soubory=("b.py",), stav="ready", zavisi_na="01")
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertIn("nespouštět dřív", vystup)


# =========================================================================
# CHIP 17 — navazující chip: kdy je nehotový předek chyba a kdy jen pořadí
# =========================================================================

class TestNavazujiciChip(ZakladChipu):
    """Předek `gated` je hotová práce čekající na bránu — potomek na ní smí stavět.

    Dřív byl každý nemergnutý předek u běžícího chipu chyba, a protože lint je
    brána s exit 1, nešlo navazující chip vůbec spustit. Chyba tu má zůstat jen
    tam, kde se stavět NEDÁ: na rozdělané práci (`draft`/`ready`/`running`)
    a na `blocked`, který čeká na rozhodnutí člověka.
    """

    def dvojice(self, *, predek: str, potomek: str) -> tuple[int, str]:
        """Předek 01 a potomek 02 se zadanými stavy, disjunktní nároky."""
        self.vyrob_soubor("a.py")
        self.vyrob_soubor("b.py")
        self.napis_brief("01-alfa", soubory=("a.py",), stav=predek)
        self.napis_brief("02-beta", soubory=("b.py",), stav=potomek, zavisi_na="01")
        return self.spust()

    def test_gated_predek_pusti_beziciho_potomka(self):
        # #1 — jádro chipu: tohle dnes vracelo 1 a chip nešlo spustit
        kod, vystup = self.dvojice(predek="gated", potomek="running")
        self.assertEqual(kod, 0, vystup)
        self.assertEqual(self.radky_s(vystup, " X "), [], vystup)

    def test_gated_predek_rekne_poradi_merge(self):
        # #5 — varování musí říct, co s tím, ne jen konstatovat stav
        _, vystup = self.dvojice(predek="gated", potomek="running")
        radky = self.radky_s(vystup, "merguj")
        self.assertEqual(len(radky), 1, vystup)
        self.assertIn("merguj 01 před 02", radky[0])
        self.assertIn("gated", radky[0])

    def test_gated_predek_plati_i_pro_gated_potomka(self):
        # #1 — potomek už sám čeká na bránu; pořád jde jen o pořadí merge
        kod, vystup = self.dvojice(predek="gated", potomek="gated")
        self.assertEqual(kod, 0, vystup)
        self.assertIn("merguj 01 před 02", vystup)

    def test_merged_predek_nehlasi_nic(self):
        # #2 — hotový předek zůstává úplně čistý, ani varování
        kod, vystup = self.dvojice(predek="merged", potomek="running")
        self.assertEqual(kod, 0, vystup)
        self.assertIn("OK — 0 chyb, 0 varování", vystup)

    def test_blocked_predek_zustava_chybou(self):
        # #4 — blokovaný chip čeká na rozhodnutí, ne na dokončení
        kod, vystup = self.dvojice(predek="blocked", potomek="running")
        self.assertEqual(kod, 1, vystup)
        radky = self.radky_s(vystup, "blocked")
        self.assertEqual(len(radky), 1, vystup)
        self.assertIn("rozhodnutí", radky[0])
        self.assertNotIn("merguj", vystup)

    def test_nehotovy_predek_zustava_chybou(self):
        # #3 — na rozdělané práci se stavět nedá; tichý průchod by kolizi jen odložil
        for predek in ("draft", "ready", "running"):
            with self.subTest(predek=predek):
                kod, vystup = self.dvojice(predek=predek, potomek="running")
                self.assertEqual(kod, 1, vystup)
                self.assertIn("očekává se 'merged'", vystup)
                self.assertNotIn("merguj", vystup)

    def test_ready_potomek_dal_jen_ceka(self):
        # #5 — chip, který ještě neběží, se nespouští ani za `gated` předkem;
        #      hláška zůstává beze změny („nespouštět dřív")
        kod, vystup = self.dvojice(predek="gated", potomek="ready")
        self.assertEqual(kod, 0, vystup)
        self.assertIn("čeká na chip 01", vystup)
        self.assertIn("nespouštět dřív", vystup)


# =========================================================================
# CHIP 17 — `greenfield: ano`: repo, které teprve vznikne
# =========================================================================

class TestGreenfield(ZakladChipu):
    """První chip projektu nemá kam ukázat `repo:` — dnes musí repo vzniknout dřív.

    Příznak je vědomé prohlášení autora briefu: bez něj zůstává neexistující
    repo chybou, protože překlep v cestě je mnohem častější než greenfield.
    """

    def nevzniklo(self) -> str:
        return (self.tmp / "jeste-nevzniklo").as_posix()

    def vyrob_git(self, koren: Path, *, commity: bool = True) -> None:
        """Kostra `.git` bez volání gitu — `ma_commity` čte jen refs."""
        heads = koren / ".git" / "refs" / "heads"
        heads.mkdir(parents=True, exist_ok=True)
        if commity:
            (heads / "master").write_text("0" * 40 + "\n", encoding="utf-8")

    # --- #6, #8: tentýž brief s příznakem a bez něj ------------------------

    def test_neexistujici_repo_je_s_priznakem_varovani(self):
        # #6
        self.napis_brief("01-alfa", repo=self.nevzniklo(), greenfield="ano",
                         soubory=("app/models.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        radky = self.radky_s(vystup, "zatím neexistuje")
        self.assertEqual(len(radky), 1, vystup)
        self.assertIn("greenfield", radky[0])

    def test_bez_priznaku_zustava_tentyz_brief_chybou(self):
        # #8 — jediný rozdíl mezi průchodem a pádem je příznak
        kw = dict(repo=self.nevzniklo(), soubory=("app/models.py",))
        self.napis_brief("01-alfa", **kw)
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("neexistuje (nebo to není adresář)", vystup)

        self.napis_brief("01-alfa", greenfield="ano", **kw)
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)

    def test_priznak_musi_byt_kladny(self):
        # #8 — `greenfield: ne` není příznak, je to poznámka, že se nejedná o něj
        self.napis_brief("01-alfa", repo=self.nevzniklo(), greenfield="ne",
                         soubory=("app/models.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)

    # --- #7: nároky se proti neexistujícímu repu neověřují ------------------

    def test_greenfield_neoveruje_existenci_narokovanych_cest(self):
        # #7 — proti neexistujícímu repu by padly úplně všechny nároky
        self.napis_brief("01-alfa", repo=self.nevzniklo(), greenfield="ano",
                         soubory=("app/models.py", "src/*.py", "docs/plan.md"))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertNotIn("v repu neexistuje", vystup)
        self.assertNotIn("nic nenajde", vystup)

    def test_greenfield_plati_i_kdyz_adresar_repa_uz_existuje(self):
        # #7 — prázdný adresář (nebo `git init` bez commitu) je pořád greenfield
        self.napis_brief("01-alfa", greenfield="ano", soubory=("app/models.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertEqual(self.radky_s(vystup, "zastaralý"), [], vystup)

    def test_greenfield_nevypina_kontrolu_tvaru_cesty(self):
        # #7 — tvar cesty na existenci repa nezávisí a rozhoduje o porovnání
        #      s ostatními chipy; měkčit ho by znamenalo měkčit disjunktnost
        for cesta in ("C:/abs/soubor.py", "../mimo/soubor.py"):
            with self.subTest(cesta=cesta):
                self.napis_brief("01-alfa", repo=self.nevzniklo(),
                                 greenfield="ano", soubory=(cesta,))
                kod, vystup = self.spust()
                self.assertEqual(kod, 1, vystup)
                self.assertIn("musí být relativní", vystup)

    def test_greenfield_bez_repa_zustava_chybou(self):
        # #6 — příznak říká „repo teprve vznikne", ne „nevím kde";
        #      podle `repo:` zakládá chip_run worktree
        self.napis_brief("01-alfa", bez_repo=True, greenfield="ano")
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("nemá 'repo:'", vystup)

    # --- #9: příznak, který přežil svůj účel -------------------------------

    def test_zastaraly_priznak_v_repu_s_commity_varuje(self):
        # #9 — jinak by v briefu zůstal navždy a tiše vypínal kontrolu cest
        self.vyrob_git(self.repo)
        self.napis_brief("01-alfa", greenfield="ano", soubory=("app/models.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        radky = self.radky_s(vystup, "zastaralý")
        self.assertEqual(len(radky), 1, vystup)
        self.assertIn("smaž ho", radky[0])

    def test_repo_bez_commitu_zastaraly_neni(self):
        # #9 — `git init` sám o sobě neznamená, že se dá na čem stavět
        self.vyrob_git(self.repo, commity=False)
        self.napis_brief("01-alfa", greenfield="ano", soubory=("app/models.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertEqual(self.radky_s(vystup, "zastaralý"), [], vystup)

    def test_bez_priznaku_se_o_zastaralosti_nemluvi(self):
        # #9 — kontrolní vzorek: hlásí se příznak, ne repo
        self.vyrob_git(self.repo)
        self.vyrob_soubor("app/models.py")
        self.napis_brief("01-alfa", soubory=("app/models.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertEqual(self.radky_s(vystup, "zastaralý"), [], vystup)

    # --- pomocné funkce -----------------------------------------------------

    def test_je_greenfield_bere_jen_kladne_hodnoty(self):
        for hodnota, cekano in (("ano", True), ("ANO", True), ("yes", True),
                                ("true", True), ("1", True), ("ne", False),
                                ("", False), ("později", False)):
            with self.subTest(hodnota=hodnota):
                p = self.napis_brief("01-alfa", greenfield=hodnota)
                self.assertIs(chip_lint.je_greenfield(self.nacti(p)), cekano)

    def test_je_greenfield_bez_klice_je_false(self):
        p = self.napis_brief("01-alfa")
        self.assertFalse(chip_lint.je_greenfield(self.nacti(p)))

    def test_je_greenfield_snese_komentar_za_hodnotou(self):
        # parser frontmatteru komentář odřezává — ať to nikdo nerozbije
        p = self.napis_brief("01-alfa", greenfield="ano  # repo vznikne až tímhle chipem")
        self.assertTrue(chip_lint.je_greenfield(self.nacti(p)))

    def test_ma_commity_cte_refs_i_packed_refs(self):
        prazdny = self.tmp / "bez-gitu"
        prazdny.mkdir()
        self.assertFalse(chip_lint.ma_commity(prazdny), "adresář bez .git")

        cerstvy = self.tmp / "git-init"
        cerstvy.mkdir()
        self.vyrob_git(cerstvy, commity=False)
        self.assertFalse(chip_lint.ma_commity(cerstvy), "git init bez commitu")

        (cerstvy / ".git" / "packed-refs").write_text(
            "# pack-refs with: peeled fully-peeled sorted\n", encoding="utf-8")
        self.assertFalse(chip_lint.ma_commity(cerstvy), "packed-refs jen s hlavičkou")

        (cerstvy / ".git" / "packed-refs").write_text(
            "# pack-refs with: peeled\n" + "0" * 40 + " refs/heads/master\n",
            encoding="utf-8")
        self.assertTrue(chip_lint.ma_commity(cerstvy), "ref v packed-refs")

        s_commitem = self.tmp / "git-plny"
        s_commitem.mkdir()
        self.vyrob_git(s_commitem)
        self.assertTrue(chip_lint.ma_commity(s_commitem))

    def test_ma_commity_najde_ref_i_ve_vetvi_s_lomitkem(self):
        # `refs/heads/ai/chip-17/x` je soubor o dvě patra níž — proto rglob
        koren = self.tmp / "git-vnoreny"
        koren.mkdir()
        self.vyrob_git(koren, commity=False)
        vetev = koren / ".git" / "refs" / "heads" / "ai" / "chip-17"
        vetev.mkdir(parents=True)
        (vetev / "greenfield").write_text("0" * 40 + "\n", encoding="utf-8")
        self.assertTrue(chip_lint.ma_commity(koren))


# =========================================================================
# #12 — návratové kódy brány
# =========================================================================

class TestNavratoveKody(ZakladChipu):

    def test_ciste_repo_vraci_nulu(self):
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa")
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertIn("OK — 0 chyb", vystup)

    def test_jakakoli_chyba_vraci_jednicku(self):
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", soubory=("modul.py",))
        self.napis_brief("02-beta", soubory=("modul.py",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 1, vystup)
        self.assertIn("NEPROŠLO", vystup)

    def test_samotna_varovani_branu_neshodi(self):
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa", soubory=("modul.py    # nový",),
                         issues=("#12 — stručný popis",))
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertIn("varování nebrání spuštění", vystup)

    def test_prazdny_adresar_vraci_nulu(self):
        kod, vystup = self.spust()
        self.assertEqual(kod, 0, vystup)
        self.assertIn("žádné chipy", vystup)

    def test_prepinac_ready_vynecha_neaktivni_chipy(self):
        self.vyrob_soubor("modul.py")
        self.napis_brief("01-alfa")
        self.napis_brief("02-beta", stav="draft", vynech=("done",))
        kod_vse, vystup_vse = self.spust()
        self.assertEqual(kod_vse, 1, vystup_vse)
        kod_ready, vystup_ready = self.spust("--ready")
        self.assertEqual(kod_ready, 0, vystup_ready)


if __name__ == "__main__":
    unittest.main()
