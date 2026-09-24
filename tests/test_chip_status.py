"""Testy pro tools/chip_status.py — vlny, cyklus, souhrn, prázdný vstup.

Každý test si staví vlastní dočasný adresář s briefy (`tempfile`) a po sobě
uklidí — nic nezávisí na skutečném obsahu `chips/`. Jen standardní knihovna.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import chip_common          # noqa: E402
import chip_status          # noqa: E402

BRIEF = """\
---
chip: {id}
nazev: {nazev}
stav: {stav}
zavisi_na: {zavisi}
repo: {repo}
---

# CHIP {id} — {nazev}

## Issues

{issues}

## Dotčené soubory

```
tools/soubor_{id}.py         # nový
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
"""


class Zaklad(unittest.TestCase):
    """Dočasný adresář s briefy + návrat globálního CHIPS_DIR do původního stavu."""

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="chip-status-test-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        puvodni = chip_common.CHIPS_DIR
        self.addCleanup(chip_common.nastav_chips_dir, puvodni)
        chip_common.nastav_chips_dir(self.dir)

    def brief(self, cislo: str, *, nazev: str = "pokus", stav: str = "ready",
              zavisi: str = "", issues: int = 2, hotovo: int = 0) -> None:
        radky = "\n".join(
            f"- [{'x' if i < hotovo else ' '}] #{i + 1} — issue číslo {i + 1}"
            for i in range(issues)) or "- [ ] #1 — nic"
        (self.dir / f"{cislo}-{nazev}.md").write_text(
            BRIEF.format(id=cislo, nazev=nazev, stav=stav, zavisi=zavisi,
                         repo=self.dir.as_posix(), issues=radky),
            encoding="utf-8")

    def vlny(self) -> dict[str, int | None]:
        return chip_status.spocitej_vlny(chip_common.nacti_vse())

    def spust(self, *argv: str) -> tuple[int, str]:
        """Zavolá main() s podvrženým sys.argv a vrátí (kód, stdout)."""
        buf = io.StringIO()
        with patch("sys.argv", ["chip_status.py", "--dir", str(self.dir), *argv]):
            with contextlib.redirect_stdout(buf):
                kod = chip_status.main()
        return kod, buf.getvalue()


class TestVlny(Zaklad):

    def test_chip_bez_zavislosti_je_vlna_nula(self) -> None:
        self.brief("01")
        self.assertEqual(self.vlny(), {"01": 0})

    def test_osamoceny_chip_mezi_ostatnimi_zustava_vlna_nula(self) -> None:
        # 03 na nikom nezávisí a nikdo nezávisí na něm — nesmí ho strhnout řetěz
        self.brief("01")
        self.brief("02", zavisi="01")
        self.brief("03")
        self.assertEqual(self.vlny(), {"01": 0, "02": 1, "03": 0})

    def test_retez_zavislosti_roste_po_jedne(self) -> None:
        self.brief("01")
        self.brief("02", zavisi="01")
        self.brief("03", zavisi="02")
        self.assertEqual(self.vlny(), {"01": 0, "02": 1, "03": 2})

    def test_vlna_je_maximum_z_predku(self) -> None:
        # 04 závisí na 01 (vlna 0) i na 03 (vlna 2) → 3, ne 1
        self.brief("01")
        self.brief("02", zavisi="01")
        self.brief("03", zavisi="02")
        self.brief("04", zavisi="01, 03")
        self.assertEqual(self.vlny()["04"], 3)

    def test_neznamy_predek_neshodi_vypocet(self) -> None:
        # chybějící chip hlásí chip_lint; tady se bere jako by byl hotový
        self.brief("02", zavisi="99")
        self.assertEqual(self.vlny(), {"02": 1})

    def test_zavislost_zapsana_jednou_cislici_se_dopocita(self) -> None:
        self.brief("01")
        self.brief("02", zavisi="1")
        self.assertEqual(self.vlny()["02"], 1)


class TestCyklus(Zaklad):

    def test_vzajemny_cyklus_da_none(self) -> None:
        self.brief("01", zavisi="02")
        self.brief("02", zavisi="01")
        self.assertEqual(self.vlny(), {"01": None, "02": None})

    def test_zavislost_sam_na_sobe_je_cyklus(self) -> None:
        self.brief("01", zavisi="01")
        self.assertIsNone(self.vlny()["01"])

    def test_potomek_cyklu_je_take_none(self) -> None:
        self.brief("01", zavisi="02")
        self.brief("02", zavisi="01")
        self.brief("03", zavisi="02")
        self.assertIsNone(self.vlny()["03"])

    def test_cyklus_neshodi_vypis_a_vypise_se_jako_otaznik(self) -> None:
        self.brief("01", zavisi="02")
        self.brief("02", zavisi="01")
        self.brief("03")
        kod, out = self.spust()
        self.assertEqual(kod, 0)
        self.assertIn("?", out)
        self.assertIn("cyklická závislost", out)
        # zdravý chip se pořád normálně zařadí do vlny
        self.assertIn("vlna 0:", out)


class TestVypis(Zaklad):

    def test_tabulka_ma_hlavicku_a_radek_pro_kazdy_chip(self) -> None:
        self.brief("01", nazev="prvni")
        self.brief("02", nazev="druhy", zavisi="01")
        kod, out = self.spust()
        self.assertEqual(kod, 0)
        for nadpis in ("ID", "vlna", "stav", "název", "issues", "cest", "závisí na"):
            self.assertIn(nadpis, out)
        self.assertIn("prvni", out)
        self.assertIn("druhy", out)

    def test_radky_se_vejdou_do_80_sloupcu(self) -> None:
        self.brief("01", nazev="velmi-dlouhy-nazev-chipu-ktery-se-nevejde",
                   zavisi="02, 03, 04, 05, 06")
        self.brief("02")
        kod, out = self.spust()
        self.assertEqual(kod, 0)
        for radek in out.splitlines():
            self.assertLessEqual(len(radek), 80, radek)

    def test_hlaska_o_cyklu_se_vejde_do_80_sloupcu(self) -> None:
        self.brief("01", nazev="hodne-dlouhy-nazev-chipu-s-kruhem", zavisi="02")
        self.brief("02", nazev="druhy-clen-kruhu", zavisi="01")
        _, out = self.spust()
        self.assertIn("cyklická závislost", out)
        for radek in out.splitlines():
            self.assertLessEqual(len(radek), 80, radek)

    def test_diakritika_neposune_zarovnani(self) -> None:
        self.brief("01", nazev="bez-diakritiky")
        self.brief("02", nazev="příliš-žluťoučký")
        _, out = self.spust()
        radky = [r for r in out.splitlines() if r.startswith("  0")]
        self.assertEqual(len(radky), 2)
        self.assertEqual(radky[0].index("ready"), radky[1].index("ready"))

    def test_prepinac_vlny_vypise_jen_rozpis_vln(self) -> None:
        self.brief("01")
        kod, out = self.spust("--vlny")
        self.assertEqual(kod, 0)
        self.assertIn("vlna 0:", out)
        self.assertNotIn("Souhrn:", out)
        self.assertNotIn("závisí na", out)

    def test_ve_vlne_se_nabizi_jen_ready(self) -> None:
        self.brief("01", nazev="hotovy", stav="merged")
        self.brief("02", nazev="pripraveny", stav="ready")
        _, out = self.spust("--vlny")
        self.assertIn("02 pripraveny", out)
        self.assertNotIn("vlna 0:  01 hotovy", out)
        self.assertIn("mimo pořadí", out)


class TestSouhrn(Zaklad):

    def test_souhrn_scita_stavy_a_issues(self) -> None:
        self.brief("01", stav="ready", issues=4, hotovo=1)
        self.brief("02", stav="merged", issues=3, hotovo=3)
        self.brief("03", stav="ready", issues=0)
        _, out = self.spust()
        self.assertIn("3 chipy", out)
        self.assertIn("ready 2", out)
        self.assertIn("merged 1", out)
        self.assertIn("4/8 hotových", out)

    def test_tabulka_ukazuje_hotove_ku_celkovym(self) -> None:
        """Sloupec `issues` je `hotové/celkem` (počítá sdílený `Chip.hotove_issues`)."""
        self.brief("01", issues=5, hotovo=2)
        _, out = self.spust()
        self.assertIn("2/5", out)
        self.assertIn("2/5 hotových", out)

    def test_souhrn_bez_issues_nedeli_nulou(self) -> None:
        self.brief("01", issues=0)
        kod, out = self.spust()
        self.assertEqual(kod, 0)
        self.assertIn("0/1 hotových", out)


class TestPrazdnyVstup(Zaklad):

    def test_prazdny_adresar_da_hlasku_a_kod_nula(self) -> None:
        kod, out = self.spust()
        self.assertEqual(kod, 0)
        self.assertIn("žádné chipy", out)
        self.assertIn(str(self.dir), out)

    def test_samotna_sablona_se_nepocita(self) -> None:
        (self.dir / "TEMPLATE.md").write_text("# šablona\n", encoding="utf-8")
        kod, out = self.spust()
        self.assertEqual(kod, 0)
        self.assertIn("žádné chipy", out)

    def test_vlny_prazdneho_seznamu(self) -> None:
        self.assertEqual(chip_status.spocitej_vlny([]), {})


class TestNavratovyKod(Zaklad):

    def test_kod_je_nula_i_kdyz_je_neco_spatne(self) -> None:
        # přehled není brána: neplatný stav ani cyklus nesmí shodit návratový kód
        self.brief("01", stav="vymysleny", zavisi="02")
        self.brief("02", zavisi="01")
        for argv in ((), ("--vlny",)):
            with self.subTest(argv=argv):
                self.assertEqual(self.spust(*argv)[0], 0)


if __name__ == "__main__":
    unittest.main()
