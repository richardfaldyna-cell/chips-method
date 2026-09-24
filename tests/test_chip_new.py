"""Testy zakládání chipu ze šablony (`chip_new.py`).

Existují kvůli konkrétnímu selhání: chip 08 změnil tvar `vetev:` v
`chips/TEMPLATE.md`, ale `chip_new.py` dosazoval podle starého řetězce.
`.replace()`, kterému se nenajde vzor, **nic neudělá a nic neohlásí** —
brief tedy odešel s nedosazeným `NN` v názvu větve a přišlo se na to až
náhodou. Proto se tu netestuje jen správný výsledek, ale hlavně to, že
ve vygenerovaném briefu nezůstal ŽÁDNÝ placeholder ze šablony.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import chip_common                                                    # noqa: E402
import chip_new                                                       # noqa: E402

# Zbytky ze šablony, které v hotovém briefu nesmí zůstat.
PLACEHOLDERY = ("NN", "kratky-nazev-s-pomlckami", "C:/cesta/k/repu", "YYYY-MM-DD")

# Slovník stavů ve frontmatteru: odsazený komentářový řádek `#   stav — význam`.
# Hlavička bloku má za `#` jednu mezeru, položky nejmíň dvě — tím se od sebe
# poznají, aniž by text hlavičky musel být přesně daný.
SLOVNIK_RADEK = re.compile(r"^#\s{2,}([a-z]+)\s+—\s*(.*)$", re.M)

# Sekce, které šablona má mít — v pořadí, jak jdou v dokumentu (klíče podle
# `chip_common._norm`). Nová `## sekce` se musí přidat i do `POVINNE`
# v `chip_lint.py`, jinak se nekontroluje; proto je jejich seznam zafixovaný.
SEKCE_SABLONY = ("issues", "dotcene soubory narok", "definition of done",
                 "overeni brana", "eskalace co nerozhodovat sam t3",
                 "kontext pro agenta", "log")


def slovnik(frontmatter: str) -> list[tuple[str, str]]:
    """(stav, význam) v pořadí, v jakém stojí v briefu — pořadí je část sdělení."""
    return [(stav, vyznam.strip()) for stav, vyznam in SLOVNIK_RADEK.findall(frontmatter)]


class Zaklad(unittest.TestCase):
    def setUp(self) -> None:
        self.puvodni = chip_common.CHIPS_DIR
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.addCleanup(self._vrat)

    def _vrat(self) -> None:
        chip_common.CHIPS_DIR = self.puvodni

    def spust(self, argv: list[str]) -> int:
        """`chip_new.main()` čte `sys.argv` — nebere parametr."""
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        # Výstup nástroje by jinak zaplevelil běh celé sady.
        with patch.object(sys, "argv", ["chip_new.py", *argv]),              redirect_stdout(io.StringIO()):
            return chip_new.main()

    def zaloz(self, cislo: str = "42", nazev: str = "zkouska",
              repo: str = "C:/projekt/moje-repo") -> Path:
        kod = self.spust(["--dir", str(self.tmp), "--repo", repo,
                          "--datum", "2026-01-02", cislo, nazev])
        self.assertEqual(kod, 0, "chip_new skončil chybou")
        return self.tmp / f"{cislo.zfill(2)}-{nazev}.md"   # soubor je vždy dvojmístný

    def frontmatter(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        return text[3:text.find("\n---", 3)]


class TestDosazeni(Zaklad):
    def test_soubor_vznikne(self) -> None:
        self.assertTrue(self.zaloz().exists())

    def test_cislo_a_nazev(self) -> None:
        fm = self.frontmatter(self.zaloz())
        self.assertIn("chip: 42", fm)
        self.assertIn("nazev: zkouska", fm)

    def test_jednociferne_cislo_se_doplni_nulou(self) -> None:
        p = self.zaloz("7", "sedmicka")
        self.assertIn("chip: 07", self.frontmatter(p))

    def test_repo(self) -> None:
        self.assertIn("repo: C:/projekt/moje-repo", self.frontmatter(self.zaloz()))

    def test_vetev_ma_novy_tvar_a_dosazene_hodnoty(self) -> None:
        """Přesně to, co se dřív rozešlo se šablonou."""
        self.assertIn("vetev: ai/chip-42/zkouska", self.frontmatter(self.zaloz()))

    def test_worktree(self) -> None:
        self.assertIn("worktree: ../repo-chip-42", self.frontmatter(self.zaloz()))

    def test_nadpis(self) -> None:
        self.assertIn("# CHIP 42 — zkouska",
                      self.zaloz().read_text(encoding="utf-8"))

    def test_datum_v_logu(self) -> None:
        self.assertIn("| 2026-01-02 | draft | založeno |",
                      self.zaloz().read_text(encoding="utf-8"))


class TestZadnyZbytek(Zaklad):
    """Obecná pojistka — chytí i placeholder, na který nikdo nemyslel."""

    def test_ve_frontmatteru_nezustal_placeholder(self) -> None:
        fm = self.frontmatter(self.zaloz())
        for ph in PLACEHOLDERY:
            with self.subTest(placeholder=ph):
                self.assertNotIn(ph, fm, f"ve frontmatteru zůstalo '{ph}' — "
                                         f"šablona a dosazování se rozešly")

    def test_kazdy_klic_frontmatteru_ma_hodnotu(self) -> None:
        for radek in self.frontmatter(self.zaloz()).splitlines():
            if ":" not in radek or radek.strip().startswith("#"):
                continue
            klic, _, hodnota = radek.partition(":")
            if klic.strip() in ("zavisi_na",):        # smí být prázdné
                continue
            with self.subTest(klic=klic.strip()):
                self.assertTrue(hodnota.split("#")[0].strip(),
                                f"klíč '{klic.strip()}' zůstal bez hodnoty")

    def test_kazdy_replace_v_chip_new_ma_vzor_v_sablone(self) -> None:
        """`.replace()` bez shody selže tiše — tohle je ta tichá díra.

        Projde zdroják `chip_new.py`, vytáhne první argument každého
        `.replace("…", …)` a ověří, že se ten řetězec v šabloně opravdu
        vyskytuje. Jinak by změna šablony zase prošla bez povšimnutí.
        """
        zdroj = Path(chip_new.__file__).read_text(encoding="utf-8")
        sablona = (Path(chip_new.__file__).resolve().parent.parent
                   / "chips" / "TEMPLATE.md").read_text(encoding="utf-8")
        vzory = re.findall(r'\.replace\(\s*"((?:[^"\\]|\\.)*)"', zdroj)
        self.assertTrue(vzory, "v chip_new.py nejsou žádné .replace() — změnila se struktura?")
        for vzor in vzory:
            with self.subTest(vzor=vzor):
                self.assertIn(vzor, sablona,
                              f"chip_new.py dosazuje za '{vzor}', ale ten řetězec "
                              f"v TEMPLATE.md není — dosazení tiše propadne")


class TestSlovnikStavu(Zaklad):
    """Slovník stavů musí být v briefu, ne jen v `docs/metodika.md`.

    Tři agenti během pilotů napsali do briefu `stav: done` — stav, který
    neexistuje a na kterém se chip zasekne na lintu. Nebyla to nepozornost:
    na řádku `stav:` stála jen jména bez významů, takže z briefu nešlo poznat,
    který stav komu přísluší ani že ho vůbec přepíná někdo jiný. Slovník proto
    patří tam, kde se o stavu rozhoduje: do frontmatteru generovaného briefu.
    """

    def frontmatter_sablony(self) -> str:
        """Šablona sama — brief založený ručně kopií musí mít slovník taky."""
        return self.frontmatter(Path(chip_new.__file__).resolve().parent.parent
                                / "chips" / "TEMPLATE.md")

    def test_slovnik_zna_prave_stavy_z_chip_common(self) -> None:
        """Jména i POŘADÍ proti `chip_common.STAVY` — jediný zdroj pravdy.

        `assertEqual` na seznamu hlídá obojí najednou: chybějící/vymyšlený stav
        i rozejití s životním cyklem (`draft → ready → running → gated → merged`,
        `blocked` stranou), kdyby někdo slovník srovnal třeba podle abecedy.
        """
        for kde, fm in (("brief", self.frontmatter(self.zaloz())),
                        ("šablona", self.frontmatter_sablony())):
            with self.subTest(kde=kde):
                self.assertEqual([s for s, _ in slovnik(fm)], chip_common.STAVY,
                                 "slovník stavů v briefu se rozešel s "
                                 "chip_common.STAVY — lint by odmítl stav, "
                                 "který brief sám nabízí")

    def test_kazdy_stav_ma_vyznam_ne_jen_jmeno(self) -> None:
        """Jména bez významů jsou přesně to, co selhalo — šest slov nestačí."""
        for stav, vyznam in slovnik(self.frontmatter(self.zaloz())):
            with self.subTest(stav=stav):
                self.assertGreater(len(vyznam.split()), 2,
                                   f"stav '{stav}' je ve slovníku bez významu")

    def test_slovnik_rika_ze_stav_prepina_orchestrator(self) -> None:
        """Bez téhle věty si agent i správný slovník vyloží jako pozvánku."""
        fm = self.frontmatter(self.zaloz()).lower()
        for slovo in ("orchestrátor", "log", "checkbox"):
            with self.subTest(slovo=slovo):
                self.assertIn(slovo, fm,
                              "u slovníku chybí, kdo stav přepíná a co je "
                              "mandát agenta (Log a checkboxy)")

    def test_slovnik_zustal_komentarem_a_nerozbil_frontmatter(self) -> None:
        """Parser bere `#` řádky jako komentář — slovník nesmí přidat klíč.

        Kdyby se z něj staly klíče, `stav:` by zůstal správně, ale `chip_lint.py`
        i dashboard by v meta viděly šest smyšlených položek.
        """
        chip = chip_common.parse(self.zaloz())
        self.assertEqual(list(chip.meta), ["chip", "nazev", "stav", "zavisi_na",
                                           "repo", "greenfield", "vetev", "worktree"])
        self.assertEqual(chip.stav, "draft")

    def test_slovnik_nezalozil_novou_sekci(self) -> None:
        """`## sekce` navíc by se musela přidat do `POVINNE` v `chip_lint.py`.

        Ten soubor je brána; sekce, kterou nekontroluje, časem vyhnije. Slovník
        proto žije ve frontmatteru, ne pod vlastním nadpisem.
        """
        self.assertEqual(tuple(chip_common.parse(self.zaloz()).sekce), SEKCE_SABLONY,
                         "změnily se sekce briefu — nová patří i do POVINNE "
                         "v chip_lint.py (rozhodnutí orchestrátora, ne chipu)")


class TestOchrany(Zaklad):
    def test_nepřepise_existujici(self) -> None:
        p = self.zaloz()
        puvodni = p.read_text(encoding="utf-8")
        kod = self.spust(["--dir", str(self.tmp), "--repo", "C:/jine",
                          "42", "zkouska"])
        self.assertEqual(kod, 1)
        self.assertEqual(p.read_text(encoding="utf-8"), puvodni)

    def test_vysledek_projde_lintem_jako_draft(self) -> None:
        import chip_lint
        self.zaloz()
        chip_common.nastav_chips_dir(self.tmp)
        import io
        from contextlib import redirect_stdout
        from unittest.mock import patch
        with redirect_stdout(io.StringIO()),              patch.object(sys, "argv", ["chip_lint.py", "--dir", str(self.tmp)]):
            self.assertEqual(chip_lint.main(), 0)


if __name__ == "__main__":
    unittest.main()
