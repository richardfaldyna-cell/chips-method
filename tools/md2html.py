"""Převod Markdown → čitelné samostatné HTML (offline, jeden soubor).

Použití:
    python tools/md2html.py soubor.md [...]   # vytvoří soubor.html vedle .md
    python tools/md2html.py --all             # převede všechny .md v projektu

Převzato z jiného projektu workspace (konvence: ke každému .md patří .html).
Bez externích závislostí kromě `markdown`.

**Vstup se bere jako text, ne jako HTML.** Nástroj převádí dokumentaci, ne
šablony — `<script>` nebo `<div>` ve zdrojovém `.md` je vždycky buď omyl,
nebo něco, co má být ve výstupu vidět. Ve výchozím nastavení by je
`markdown.markdown()` pustil skrz jako živé tagy, proto je vypíná
`BezSurovehoHTML`. Bloky kódu a text v backtickách se escapují dál stejně
jako předtím (jednou, ne dvakrát) — tam se HTML neřeší, tam se vypisuje.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

import markdown
from markdown.extensions import Extension

ROOT = Path(__file__).resolve().parent.parent

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", system-ui, Arial, sans-serif;
  max-width: 900px; margin: 0 auto; padding: 32px 24px 80px;
  line-height: 1.6; font-size: 16px;
  color: #1a2733; background: #ffffff;
}
h1, h2, h3, h4 { color: #163a4d; line-height: 1.25; margin: 1.6em 0 .5em; }
h1 { font-size: 1.9em; border-bottom: 3px solid #e8734a; padding-bottom: .3em; margin-top: .2em; }
h2 { font-size: 1.4em; border-bottom: 1px solid #d8dee3; padding-bottom: .25em; }
h3 { font-size: 1.15em; }
a { color: #1f6f8b; }
code { background: #eef2f4; padding: .1em .35em; border-radius: 4px; font-size: .88em;
       font-family: Consolas, "Courier New", monospace; }
pre { background: #f4f6f8; padding: 14px 16px; border-radius: 8px; overflow-x: auto;
      border: 1px solid #e2e8ec; }
pre code { background: none; padding: 0; }
blockquote { border-left: 4px solid #e8734a; margin: 1em 0; padding: .4em 1em;
             background: #f7f9fa; color: #33454f; }
table { border-collapse: collapse; width: 100%; margin: 1.2em 0; font-size: .93em;
        display: block; overflow-x: auto; }
th, td { border: 1px solid #cfd8dd; padding: 7px 11px; text-align: left; vertical-align: top; }
th { background: #163a4d; color: #fff; }
tr:nth-child(even) td { background: #f5f8fa; }
ul, ol { padding-left: 1.5em; }
li { margin: .25em 0; }
hr { border: none; border-top: 1px solid #d8dee3; margin: 2em 0; }
strong { color: #10222e; }
.doc-foot { margin-top: 60px; padding-top: 16px; border-top: 1px solid #d8dee3;
            font-size: .8em; color: #8496a0; }
@media (prefers-color-scheme: dark) {
  body { color: #d7e0e6; background: #14202a; }
  h1, h2, h3, h4 { color: #7fc7e8; }
  h2 { border-bottom-color: #2a3b47; }
  a { color: #6cb6d9; }
  code { background: #22323d; }
  pre { background: #1b2933; border-color: #2a3b47; }
  blockquote { background: #1b2933; color: #b9c6ce; }
  th, td { border-color: #2f4450; }
  th { background: #1f4a5f; }
  tr:nth-child(even) td { background: #1a2833; }
  strong { color: #eef4f7; }
  hr { border-top-color: #2a3b47; }
}
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
{body}
<div class="doc-foot">Vygenerováno z <code>{src}</code> &middot; {title}</div>
</body>
</html>
"""

class BezSurovehoHTML(Extension):
    """Surové HTML ze vstupu se neprovádí, projde do výstupu jako text.

    Python-markdown od verze 3 nemá `safe_mode`; místo něj si surové HTML
    odkládá do `md.htmlStash` a postprocesor `raw_html` ho na konci vrací
    zpátky jako živý tag. Odregistrují se proto právě ty dva kroky, které do
    stashe ukládají **vstupní** HTML — blokový preprocesor `html_block`
    a řádkový vzor `html`. Co tam odloží někdo jiný (hlavně `fenced_code`,
    který si tak chrání hotový `<pre><code>`), zůstane nedotčené; tím se
    bloky kódu escapují dál právě jednou a nevzniká `&amp;lt;`.

    Hrubé `html.escape()` nad celým vstupem by tuhle hranici neumělo — sebralo
    by markdownu i to, co si generuje sám.
    """

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")


EXT = ["tables", "fenced_code", "sane_lists", "toc", "attr_list", "nl2br",
       BezSurovehoHTML()]

# Adresáře, do kterých `--all` nemá chodit. Jedno pojmenované místo, ne
# podmínka rozepsaná v `main()` — seznam roste a rozeseté podmínky by se
# časem rozešly.
IGNOROVANE_ADRESARE = frozenset({".git", "__pycache__"})


def preskocit(relativni: Path) -> bool:
    """Leží cesta (relativní ke kořeni) uvnitř ignorovaného adresáře?

    Rozhoduje se podle *relativní* cesty schválně: kdyby se koukalo na
    absolutní, stačilo by mít projekt pod složkou s takovým jménem a `--all`
    by tiše nepřevedlo nic.
    """
    return bool(IGNOROVANE_ADRESARE.intersection(relativni.parts))


def convert(md_path: Path) -> Path:
    text = md_path.read_text(encoding="utf-8")
    title = md_path.stem
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    body = markdown.markdown(text, extensions=EXT)
    out = md_path.with_suffix(".html")
    out.write_text(
        TEMPLATE.format(title=html.escape(title), css=CSS, body=body,
                        src=html.escape(md_path.name)),
        encoding="utf-8")
    return out


def main() -> int:
    """Návratový kód je 1, když některý ze zadaných souborů chyběl.

    Chybějící soubor se jen ohlásí a jede se dál (dávka nesmí spadnout na
    jednom překlepu), ale nesmí projít jako úspěch — jinak by předcommitové
    `--all` tiše přehlédlo, že se nepřevedlo nic.
    """
    args = sys.argv[1:]
    if args == ["--all"]:
        targets = sorted(p for p in ROOT.rglob("*.md")
                         if not preskocit(p.relative_to(ROOT)))
    else:
        targets = [Path(a) for a in args]
    if not targets:
        print(__doc__)
        return 0
    chybi = False
    for md in targets:
        if not md.exists():
            print(f"  ! chybí: {md}")
            chybi = True
            continue
        out = convert(md)
        print(f"  {md.name} -> {out.name}  ({out.stat().st_size // 1024} kB)")
    return 1 if chybi else 0


if __name__ == "__main__":
    sys.exit(main())
