"""Testy pro tools/md2html.py.

Tenhle nástroj jako jediný v projektu **zapisuje do repa** — `--all` přepíše
desítky `.html`. Proto tady platí tvrdší pravidlo než u ostatních sad: každý
test píše výhradně do `tempfile` a `md2html.ROOT` je po dobu testu přesměrovaný
mimo projekt (globální stav, v `tearDown` se vrací — stejně jako
`chip_common.CHIPS_DIR` jinde). `TestNesahaNaRepo` to hlídá otiskem skutečného
stromu, aby se případný únik poznal hned, ne až z `git status`.

Názvy testů nesou číslo bodu z briefu chipu 18, ať jde zadání spárovat s tím,
co ho doopravdy pokrývá.
"""

from __future__ import annotations

import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import md2html  # noqa: E402

# Kořen projektu odchycený **před** jakýmkoli patchováním `md2html.ROOT` —
# proti němu se v `TestNesahaNaRepo` porovnává, že sada nic nepřepsala.
PROJEKT = md2html.ROOT

DIAKRITIKA = "ěščřžýáíé ĚŠČŘŽÝÁÍÉ"

DOKUMENT = """\
# Nadpis s diakritikou {diakritika}

Odstavec, ve kterém je `kód` a text mimo markdown: a < b & c.

| Sloupec | Hodnota |
|---|---|
| ěščřžýáíé | 42 |

```python
print("ahoj")
```
"""


def otisk(koren: Path) -> dict[str, tuple[int, int]]:
    """Otisk `.md` a `.html` ve stromu — velikost a čas změny, obsah netřeba.

    Zúženo právě na tyhle dvě přípony: to je celá plocha, na kterou umí
    `md2html.py` sáhnout. Čtení celého repa by bylo pomalé a `__pycache__`
    by ho rozkolísal.
    """
    otisky = {}
    for vzor in ("*.md", "*.html"):
        for p in koren.rglob(vzor):
            if ".git" in p.relative_to(koren).parts:
                continue
            st = p.stat()
            otisky[str(p.relative_to(koren))] = (st.st_size, st.st_mtime_ns)
    return otisky


class ZakladPrevodu(unittest.TestCase):
    """Dočasný strom + `md2html.ROOT` přesměrovaný do něj."""

    def setUp(self) -> None:
        self._puvodni_root = md2html.ROOT
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        md2html.ROOT = self.base

    def tearDown(self) -> None:
        md2html.ROOT = self._puvodni_root
        self._tmp.cleanup()

    def napis(self, jmeno: str, text: str = DOKUMENT) -> Path:
        cesta = self.base / jmeno
        cesta.parent.mkdir(parents=True, exist_ok=True)
        cesta.write_text(text.format(diakritika=DIAKRITIKA)
                         if "{diakritika}" in text else text,
                         encoding="utf-8")
        return cesta

    def spust(self, *argv: str) -> tuple[int, str]:
        """`main()` s podstrčeným argv a odchyceným stdout."""
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["md2html.py", *argv]), \
                redirect_stdout(buf):
            rc = md2html.main()
        return rc, buf.getvalue()


class TestConvert(ZakladPrevodu):
    def test_01_vytvori_html_vedle_zdroje_a_vrati_jeho_cestu(self) -> None:
        md = self.napis("dokument.md")
        out = md2html.convert(md)
        self.assertEqual(out, md.with_suffix(".html"))
        self.assertEqual(out.parent, md.parent)
        self.assertTrue(out.is_file())
        self.assertTrue(out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>"))

    def test_01_prevod_nesmaze_ani_neprepise_zdroj(self) -> None:
        md = self.napis("dokument.md")
        pred = md.read_bytes()
        md2html.convert(md)
        self.assertEqual(md.read_bytes(), pred)

    def test_02_vystup_je_samostatny_soubor_s_vlozenym_css(self) -> None:
        """Offline je celý smysl nástroje — CSS musí být uvnitř `<style>`."""
        text = md2html.convert(self.napis("dokument.md")).read_text(encoding="utf-8")
        self.assertIn("<style>", text)
        self.assertIn("font-family", text)
        self.assertIn("prefers-color-scheme", text)

    def test_02_vystup_neodkazuje_na_zadny_externi_zdroj(self) -> None:
        text = md2html.convert(self.napis("dokument.md")).read_text(encoding="utf-8")
        for zakazano in ("http://", "https://", "@import", "url(", "<link", "<script"):
            self.assertNotIn(zakazano, text, f"externí zdroj ve výstupu: {zakazano}")
        self.assertIsNone(re.search(r"\bsrc\s*=", text))

    def test_03_diakritika_prezije_prevod_v_utf8(self) -> None:
        out = md2html.convert(self.napis("dokument.md"))
        self.assertIn(DIAKRITIKA.encode("utf-8"), out.read_bytes())
        text = out.read_text(encoding="utf-8")
        self.assertIn(DIAKRITIKA, text)
        self.assertIn("ěščřžýáíé", text)                     # i uvnitř tabulky
        self.assertIn('charset="utf-8"', text)

    def test_03_diakritika_v_nazvu_souboru_projde_do_titulku(self) -> None:
        """Bez nadpisu se titulek bere ze jména souboru — i to bývá s háčky."""
        out = md2html.convert(self.napis("žluťoučký.md", "Jen odstavec.\n"))
        text = out.read_text(encoding="utf-8")
        self.assertIn("<title>žluťoučký</title>", text)

    def test_04_text_mimo_markdown_se_escapuje(self) -> None:
        text = md2html.convert(self.napis("dokument.md")).read_text(encoding="utf-8")
        self.assertIn("a &lt; b &amp; c", text)

    def test_04_znaky_v_titulku_a_v_paticce_se_escapuji(self) -> None:
        """`html.escape` na titulku i na jménu zdroje — jinak by `<` rozbil hlavičku."""
        out = md2html.convert(self.napis("a&b.md", "# Nadpis <s> & spol.\n"))
        text = out.read_text(encoding="utf-8")
        self.assertIn("<title>Nadpis &lt;s&gt; &amp; spol.</title>", text)
        self.assertIn("<code>a&amp;b.md</code>", text)

    def test_04_script_v_markdownu_se_nedostane_jako_zivy_tag(self) -> None:
        """Nález chipu 18, opravený chipem 20 (`BezSurovehoHTML`).

        Nástroj převádí dokumentaci, ne šablony — surové HTML ve vstupu je
        omyl, nebo se má ukázat jako text. Živý `<script>` by navíc rozbil
        `test_02_vystup_neodkazuje_na_zadny_externi_zdroj`.
        """
        out = md2html.convert(self.napis("zla.md", "# Zlá\n\n<script>alert(1)</script>\n"))
        self.assertNotIn("<script>", out.read_text(encoding="utf-8"))

    def test_04_surove_html_je_ve_vystupu_videt_jako_text(self) -> None:
        """Nestačí, že tag nežije — obsah se nesmí ztratit, má být čitelný."""
        out = md2html.convert(self.napis("zla.md", "# Zlá\n\n<script>alert(1)</script>\n"))
        text = out.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)

    def test_04_radkovy_tag_uprostred_odstavce_je_taky_jen_text(self) -> None:
        """Blokový a řádkový vzor jsou v markdownu dva různé kroky."""
        out = md2html.convert(self.napis("radek.md", "Text s <b>tučným</b> kusem.\n"))
        text = out.read_text(encoding="utf-8")
        self.assertNotIn("<b>", text)
        self.assertIn("&lt;b&gt;tučným&lt;/b&gt;", text)

    def test_04_blokovy_div_je_taky_jen_text(self) -> None:
        out = md2html.convert(self.napis("blok.md", "<div>\nobsah\n</div>\n"))
        text = out.read_text(encoding="utf-8")
        self.assertNotIn("<div>", text)
        self.assertIn("&lt;div&gt;", text)
        self.assertIn("obsah", text)

    def test_04_placeholder_v_nadpisu_je_videt_a_nezmizi(self) -> None:
        """Nejčastější „surové HTML" v tomhle repu je zástupný text `<název>`.

        Před opravou ho markdown bral jako neznámý tag a odložil do stashe —
        v HTML pak zůstal prázdný element, tedy v prohlížeči nebylo vidět nic.
        """
        out = md2html.convert(self.napis("sablona.md", "# CHIP NN — <název>\n"))
        text = out.read_text(encoding="utf-8")
        self.assertIn("CHIP NN — &lt;název&gt;", text)
        self.assertNotIn("<název>", text)

    def test_04_html_komentar_se_nedostane_do_vystupu_jako_komentar(self) -> None:
        """Komentář jde přes stejný preprocesor jako blokový tag."""
        text = md2html.convert(
            self.napis("kom.md", "<!-- skryto -->\n")).read_text(encoding="utf-8")
        self.assertNotIn("<!-- skryto -->", text)
        self.assertIn("skryto", text)

    def test_05_titulek_je_prvni_nadpis_urovne_1(self) -> None:
        out = md2html.convert(self.napis("jmeno-souboru.md", "# Skutečný titulek\n"))
        text = out.read_text(encoding="utf-8")
        self.assertIn("<title>Skutečný titulek</title>", text)
        self.assertNotIn("<title>jmeno-souboru</title>", text)

    def test_05_bez_nadpisu_je_titulkem_nazev_souboru(self) -> None:
        out = md2html.convert(self.napis("18-md2html-testy.md", "Jen text.\n"))
        self.assertIn("<title>18-md2html-testy</title>",
                      out.read_text(encoding="utf-8"))

    def test_05_bere_se_prvni_nadpis_ne_pozdejsi(self) -> None:
        out = md2html.convert(self.napis("x.md", "# První\n\n# Druhý\n"))
        self.assertIn("<title>První</title>", out.read_text(encoding="utf-8"))

    def test_06_tabulka_se_prevede_na_html_tabulku(self) -> None:
        text = md2html.convert(self.napis("dokument.md")).read_text(encoding="utf-8")
        self.assertIn("<table>", text)
        self.assertIn("<th>Sloupec</th>", text)
        self.assertIn("<td>42</td>", text)

    def test_06_blok_kodu_se_prevede_na_pre_code(self) -> None:
        text = md2html.convert(self.napis("dokument.md")).read_text(encoding="utf-8")
        self.assertIn("<pre>", text)
        self.assertIn('<code class="language-python">', text)
        # Uvnitř `<pre>` jsou uvozovky escapované — proto `&quot;`, ne `"`.
        self.assertIn("print(&quot;ahoj&quot;)", text)
        self.assertNotIn("```", text, "fence zůstal ve výstupu — extension vypadla")

    def test_06_tag_v_bloku_kodu_je_videt_a_neescapuje_se_dvakrat(self) -> None:
        """Hlavní riziko vypnutí surového HTML: dvojité escapování `&amp;lt;`.

        `fenced_code` si hotový `<pre><code>` odkládá do stejného stashe jako
        surové HTML — kdyby oprava sáhla na celý stash, projevilo by se to
        právě tady.
        """
        text = md2html.convert(self.napis(
            "kod.md", "```html\n<div>obsah</div>\n```\n")).read_text(encoding="utf-8")
        self.assertIn("<pre>", text)
        self.assertIn("&lt;div&gt;obsah&lt;/div&gt;", text)
        self.assertNotIn("&amp;lt;", text)

    def test_06_tag_v_backtickach_je_videt_a_neescapuje_se_dvakrat(self) -> None:
        text = md2html.convert(self.napis(
            "backtick.md", "Element `<div>` uvnitř textu.\n")).read_text(encoding="utf-8")
        self.assertIn("<code>&lt;div&gt;</code>", text)
        self.assertNotIn("&amp;lt;", text)

    def test_06_odsazeny_blok_kodu_se_taky_escapuje_jen_jednou(self) -> None:
        """Odsazený blok jde jinou cestou než fence — kontroluje se zvlášť."""
        text = md2html.convert(self.napis(
            "odsazeny.md", "Ukázka:\n\n    <span>x</span>\n")).read_text(encoding="utf-8")
        self.assertIn("&lt;span&gt;x&lt;/span&gt;", text)
        self.assertNotIn("&amp;lt;", text)

    def test_06_markdown_konstrukce_prevodem_neutrpely(self) -> None:
        """Vypnout surové HTML nesmí znamenat vypnout půl markdownu."""
        text = md2html.convert(self.napis("ostatni.md", (
            "# Nadpis\n\n"
            "Text s **tučným** a *kurzívou* a [odkazem](https://example.com).\n\n"
            "- položka\n\n"
            "> citace\n\n"
            "<https://example.com>\n"
        ))).read_text(encoding="utf-8")
        self.assertIn("<strong>tučným</strong>", text)
        self.assertIn("<em>kurzívou</em>", text)
        self.assertIn('<a href="https://example.com">odkazem</a>', text)
        self.assertIn("<li>položka</li>", text)
        self.assertIn("<blockquote>", text)
        # Autolink `<url>` má v markdownu přednost před řádkovým HTML —
        # vypnutí surového HTML ho tedy nesmí srazit na text.
        self.assertIn('<a href="https://example.com">https://example.com</a>', text)

    def test_06_html_entita_ve_zdroji_zustava_entitou(self) -> None:
        """`&amp;` je zápis znaku, ne tag — dvojité escapování by ho rozbilo."""
        text = md2html.convert(self.napis(
            "entita.md", "AT&amp;T a &middot; tečka.\n")).read_text(encoding="utf-8")
        self.assertIn("AT&amp;T", text)
        self.assertIn("&middot;", text)
        self.assertNotIn("&amp;amp;", text)


class TestMain(ZakladPrevodu):
    def test_07_prevede_zadany_soubor_a_konci_nulou(self) -> None:
        md = self.napis("dokument.md")
        rc, out = self.spust(str(md))
        self.assertEqual(rc, 0)
        self.assertTrue(md.with_suffix(".html").is_file())
        self.assertIn("dokument.md -> dokument.html", out)

    def test_07_prevede_i_vic_souboru_najednou(self) -> None:
        prvni, druhy = self.napis("a.md"), self.napis("b.md")
        rc, _ = self.spust(str(prvni), str(druhy))
        self.assertEqual(rc, 0)
        self.assertTrue(prvni.with_suffix(".html").is_file())
        self.assertTrue(druhy.with_suffix(".html").is_file())

    def test_07_bez_argumentu_vypise_napovedu_a_konci_nulou(self) -> None:
        rc, out = self.spust()
        self.assertEqual(rc, 0)
        self.assertIn("--all", out)
        self.assertEqual(list(self.base.rglob("*.html")), [])

    def test_08_neexistujici_soubor_nespadne_tracebackem(self) -> None:
        rc, out = self.spust(str(self.base / "neni.md"))
        self.assertNotIn("Traceback", out)
        self.assertIn("chybí", out)
        self.assertIsInstance(rc, int)

    def test_08_neexistujici_soubor_konci_nenulovym_kodem(self) -> None:
        """Tichá nula by znamenala, že se dávka „povedla" a nepřevedla nic."""
        rc, _ = self.spust(str(self.base / "neni.md"))
        self.assertNotEqual(rc, 0)

    def test_08_chybejici_soubor_nezastavi_zbytek_davky(self) -> None:
        md = self.napis("dokument.md")
        rc, out = self.spust(str(self.base / "neni.md"), str(md))
        self.assertEqual(rc, 1)
        self.assertTrue(md.with_suffix(".html").is_file())
        self.assertIn("chybí", out)
        self.assertIn("dokument.html", out)

    def test_09_all_prevede_md_v_celem_stromu(self) -> None:
        self.napis("nahore.md")
        self.napis("docs/vnorene.md")
        rc, out = self.spust("--all")
        self.assertEqual(rc, 0)
        self.assertTrue((self.base / "nahore.html").is_file())
        self.assertTrue((self.base / "docs" / "vnorene.html").is_file())
        self.assertIn("nahore.md -> nahore.html", out)
        self.assertIn("vnorene.md -> vnorene.html", out)

    def test_09_all_preskakuje_git(self) -> None:
        self.napis("nahore.md")
        self.napis(".git/objekt.md")
        rc, out = self.spust("--all")
        self.assertEqual(rc, 0)
        self.assertFalse((self.base / ".git" / "objekt.html").exists())
        self.assertNotIn("objekt.md", out)

    def test_09_all_preskakuje_pycache(self) -> None:
        """Nález chipu 18, opravený chipem 20 (`IGNOROVANE_ADRESARE`)."""
        self.napis("__pycache__/zbytek.md")
        self.spust("--all")
        self.assertFalse((self.base / "__pycache__" / "zbytek.html").exists())

    def test_09_all_preskakuje_ignorovany_adresar_i_hloubeji(self) -> None:
        """Filtr se ptá na celou cestu, ne jen na první úroveň."""
        self.napis("nahore.md")
        self.napis("tools/__pycache__/hloubeji.md")
        self.napis("docs/.git/uvnitr.md")
        rc, out = self.spust("--all")
        self.assertEqual(rc, 0)
        self.assertFalse((self.base / "tools" / "__pycache__" / "hloubeji.html").exists())
        self.assertFalse((self.base / "docs" / ".git" / "uvnitr.html").exists())
        self.assertNotIn("hloubeji.md", out)
        self.assertNotIn("uvnitr.md", out)
        self.assertTrue((self.base / "nahore.html").is_file())

    def test_09_all_bez_md_souboru_vypise_napovedu(self) -> None:
        """Prázdný strom není chyba — jen není co převádět."""
        rc, out = self.spust("--all")
        self.assertEqual(rc, 0)
        self.assertIn("--all", out)


class TestFiltrAdresaru(unittest.TestCase):
    """Filtr `--all` sám o sobě — bez zápisu na disk."""

    def test_09_ignorovane_adresare_obsahuji_git_i_pycache(self) -> None:
        self.assertIn(".git", md2html.IGNOROVANE_ADRESARE)
        self.assertIn("__pycache__", md2html.IGNOROVANE_ADRESARE)

    def test_09_preskoci_se_jen_cely_nazev_slozky(self) -> None:
        """`.github` ani `gitignore.md` nejsou `.git` — jinak by mizely doklady."""
        for cesta in ("docs/prehled.md", ".github/workflow.md", "git/README.md",
                      "docs/__pycache__.md"):
            with self.subTest(cesta=cesta):
                self.assertFalse(md2html.preskocit(Path(cesta)))

    def test_09_preskoci_se_na_kterekoli_urovni(self) -> None:
        for cesta in (".git/objekt.md", "docs/.git/objekt.md",
                      "__pycache__/zbytek.md", "tools/__pycache__/zbytek.md"):
            with self.subTest(cesta=cesta):
                self.assertTrue(md2html.preskocit(Path(cesta)))


class TestNesahaNaRepo(ZakladPrevodu):
    """Pojistka proti hlavnímu riziku chipu: přepsané `.html` ve skutečném repu."""

    def test_10_fixture_odklani_root_mimo_projekt(self) -> None:
        """Kdyby `setUp` přestal patchovat, `--all` by šlo na skutečný repo."""
        self.assertEqual(md2html.ROOT, self.base)
        self.assertNotEqual(md2html.ROOT, PROJEKT)
        self.assertNotIn(PROJEKT, md2html.ROOT.parents)

    def test_10_prevod_ani_all_nesahnou_na_skutecny_repo(self) -> None:
        pred = otisk(PROJEKT)
        self.napis("nahore.md")
        self.napis("docs/vnorene.md")
        md2html.convert(self.napis("rucne.md"))
        rc, _ = self.spust("--all")
        self.assertEqual(rc, 0)
        self.assertEqual(otisk(PROJEKT), pred,
                         "test sáhl na .md/.html ve skutečném repu")

    def test_10_puvodni_root_se_vraci_v_teardownu(self) -> None:
        """Bez návratu by globální stav prosákl do sousedních sad."""
        self.assertEqual(self._puvodni_root, PROJEKT)


if __name__ == "__main__":
    unittest.main()
