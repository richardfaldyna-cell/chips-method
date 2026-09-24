"""Stavová deska běžících chipů — z worktree a z gitu, ne z tvrzení agenta.

Když běží pět chipů naráz, jediný způsob, jak zjistit stav, je zeptat se agentů,
tedy věřit tvrzení modelu o sobě samém. Přesně to je selhání, kvůli kterému
projekt vznikl. `chip_status.py` čte briefy v **hlavním stromě**, kde se za běhu
chipu nehýbe nic: checkboxy i soubory se mění ve **worktree**. Tenhle nástroj
proto bere data odtamtud a z gitu — z tvrdých zdrojů.

Použití:
    python tools/chip_dashboard.py                    # vygeneruje dashboard.html
    python tools/chip_dashboard.py --out /tmp/d.html
    python tools/chip_dashboard.py --watch            # + <meta refresh> v HTML
    python tools/chip_dashboard.py --watch --opakovat --interval 15
    python tools/chip_dashboard.py --dir ../jiny/chips

Nástroj je **jen pro čtení**: jediný soubor, na který sáhne, je výstupní HTML.
Git se pouští výhradně přes `_git()`, které pustí jen příkazy z `POVOLENE_GIT`.

Logika je rozdělená na čisté funkce (`parsuj_status`, `parsuj_commity`,
`ocas_logu`, `sestav_html`) a na `posbirej()`/`main()`, které jediné sahají na
disk a na git — kvůli testovatelnosti (konvence projektu).
"""

from __future__ import annotations

import argparse
import html
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from chip_common import (ROOT, STAVY, nacti_vse, nastav_chips_dir, parse,
                         pridej_arg_dir, utf8_vystup)
from chip_run import cesty
# `_chipu` je skloňování za číslovkou (1 chip / 2 chipy / 5 chipů). Je sice
# privátní, ale mít druhou kopii téhož pravidla ve dvou nástrojích je přesně to,
# co časem začne psát „1 chipů" na jednom místě a ne na druhém.
from chip_status import _chipu, spocitej_vlny

# Git smí být puštěn JEN s těmito podpříkazy. Whitelist, ne blacklist: nový
# zapisující příkaz se sem musí vědomě dopsat, takže „jen pro čtení" (issue #10)
# nezávisí na tom, že si to autor volajícího kódu pamatuje.
POVOLENE_GIT = frozenset({"log", "status", "for-each-ref"})

# `%at` je UNIX timestamp — číslo se řadí i porovnává bez tahanic s časovými
# zónami, na rozdíl od ISO řetězců s různým offsetem. Oddělovač `\x1f` (US)
# se v předmětu commitu reálně nevyskytuje, takže se pole nerozpadnou.
ODDELOVAC = "\x1f"
FORMAT_LOGU = ODDELOVAC.join(["%H", "%h", "%an", "%at", "%s"])

LIMIT_COMMITU = 15      # kolik commitů na větev do časové osy
LIMIT_ZMEN = 12         # kolik rozeditovaných souborů na kartu
LIMIT_LOGU = 3          # kolik posledních řádků sekce Log na kartu
LIMIT_BUNKY = 200       # na kolik znaků se ustřihne buňka Logu na kartě

# Stavy, ve kterých chybějící worktree NENÍ v pořádku: běžící chip bez worktree
# znamená, že se práce buď neděje, nebo se děje jinde, než si brief myslí.
STAVY_SE_ZIVOTEM = ("running", "gated")


class ChybaJenCteni(RuntimeError):
    """Pokus pustit přes `_git()` něco jiného než čtení — chyba programátora."""


@dataclass
class Zmena:
    """Jeden řádek `git status --porcelain`: dvouznakový kód a cesta."""

    kod: str
    cesta: str


@dataclass
class Commit:
    sha: str
    kratky: str
    autor: str
    cas: int
    predmet: str
    chip: str = ""


@dataclass
class Karta:
    """Jeden chip tak, jak se vykreslí — už posbíraný, bez dalších dotazů."""

    id: str
    nazev: str
    stav: str
    vlna: int | None = None
    hotovo: int = 0
    celkem: int = 0
    zavislosti: list[str] = field(default_factory=list)
    vetev: str = ""
    worktree: str = ""
    # Prázdná poznámka = data jsou z worktree. Neprázdná říká PROČ nejsou —
    # karta nikdy nevydává „nevím" za „nula" (issue #6).
    poznamka: str = ""
    varovani: bool = False
    # Odkud jsou čísla issues a ocas Logu. `False` = z hlavního stromu, kde se
    # za běhu chipu nehýbe nic — na kartě to musí být vidět, jinak dashboard
    # tvrdí „nula hotových" tam, kde ve skutečnosti neví (issue #2, #6).
    brief_z_worktree: bool = False
    vetev_existuje: bool = False
    # Je poslední commit na větvi prací chipu, nebo jen společný základ, ze
    # kterého se větvilo? Čerstvý worktree zdědí historii hlavní větve, takže
    # „poslední commit" sám o sobě neříká, že agent už něco odevzdal.
    posledni_je_chipu: bool = False
    zmeny: list[Zmena] = field(default_factory=list)
    zmen_celkem: int = 0
    posledni: Commit | None = None
    log: list[list[str]] = field(default_factory=list)

    @property
    def zivo(self) -> bool:
        return not self.poznamka

    @property
    def procenta(self) -> int:
        return round(100 * self.hotovo / self.celkem) if self.celkem else 0


@dataclass
class Deska:
    """Kompletní vstup pro `sestav_html` — čistá data, žádné I/O."""

    karty: list[Karta] = field(default_factory=list)
    commity: list[Commit] = field(default_factory=list)
    ted: int = 0
    chips_dir: str = ""
    interval: int | None = None      # None = bez <meta refresh>


def parsuj_status(vystup: str) -> list[Zmena]:
    """`git status --porcelain` → seznam změn. Prázdný vstup = čistý strom.

    Formát v1 je `XY <cesta>`, u přejmenování `XY <puvodni> -> <nova>`; bere se
    nová cesta, protože zajímá „kde agent je", ne odkud soubor přišel. Cesty se
    zvláštními znaky git obalí uvozovkami — ty se sundají, ať se v kartě
    neukazuje uvozovka jako součást jména.
    """
    zmeny: list[Zmena] = []
    for radek in vystup.splitlines():
        if radek.startswith("##"):
            continue                       # hlavička větve z `--porcelain -b`
        if len(radek) < 4 or not radek[2:3].isspace():
            continue                       # smetí a useknuté řádky
        kod = radek[:2]
        cesta = radek[3:].strip()
        if " -> " in cesta:
            cesta = cesta.split(" -> ")[-1].strip()
        if len(cesta) > 1 and cesta.startswith('"') and cesta.endswith('"'):
            cesta = cesta[1:-1]
        if cesta:
            zmeny.append(Zmena(kod=kod, cesta=cesta))
    return zmeny


def parsuj_commity(vystup: str, chip: str = "") -> list[Commit]:
    """Výstup `git log --pretty=FORMAT_LOGU` → commity; nečitelný řádek se zahodí.

    `maxsplit` je 4, aby předmět commitu zůstal celý i kdyby v něm oddělovač
    náhodou byl. Nečíselný timestamp znamená rozbitý řádek — takový commit do
    časové osy nepatří, seřadit by se stejně nedal.
    """
    out: list[Commit] = []
    for radek in vystup.splitlines():
        if not radek.strip():
            continue
        casti = radek.split(ODDELOVAC, 4)
        if len(casti) < 5 or not casti[3].strip().lstrip("-").isdigit():
            continue
        out.append(Commit(sha=casti[0].strip(), kratky=casti[1].strip(),
                          autor=casti[2].strip(), cas=int(casti[3].strip()),
                          predmet=casti[4].strip(), chip=chip))
    return out


def ocas_logu(text: str, kolik: int = LIMIT_LOGU) -> list[list[str]]:
    """Poslední řádky markdown tabulky v sekci Log → seznam buněk.

    Hlavička ani oddělovací řádek `|---|---|` se nevrací: na kartě je místo
    na obsah, ne na popisky. Když sekce tabulku nemá (nebo je prázdná), vrací
    se prázdný seznam a karta Log prostě neukáže — to je poctivější než
    vymyšlený řádek.
    """
    radky: list[list[str]] = []
    for radek in (text or "").splitlines():
        radek = radek.strip()
        if not radek.startswith("|"):
            continue
        bunky = [b.strip() for b in radek.strip("|").split("|")]
        if all(set(b) <= set("-: ") for b in bunky):
            continue                       # oddělovač hlavičky
        radky.append(bunky)
    return radky[1:][-kolik:] if len(radky) > 1 else []


def zkrat(text: str, limit: int = LIMIT_BUNKY) -> str:
    """Ustřihne dlouhou buňku Logu. Karta je přehled, ne archiv.

    Agenti do Logu píšou celé odstavce s důkazy; nezkrácené by jedna karta
    zabrala celou obrazovku a deska by přestala plnit smysl. Výpustka `…` je
    signál, že text pokračuje — celý je v briefu.
    """
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def format_casu(ts: int) -> str:
    """UNIX timestamp → `2026-07-28 11:21` v místním čase; 0 = neznámo."""
    if ts <= 0:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def stari(kdy: int, ted: int) -> str:
    """„před 12 min" — z toho je vidět tempo a prodleva, ne jen razítko.

    Jednotky jsou zkratky (`s`, `min`, `h`, `d`), aby odpadlo skloňování za
    číslovkou; hranice jsou posunuté (90 s, 90 min, 48 h), ať se neukazuje
    „před 60 min" místo „před 1 h".
    """
    if kdy <= 0:
        return "—"
    d = max(0, ted - kdy)
    if d < 90:
        return f"před {d} s"
    if d < 5400:
        return f"před {round(d / 60)} min"
    if d < 172800:
        return f"před {round(d / 3600)} h"
    return f"před {round(d / 86400)} d"


# Paleta i typografie je schválně stejná jako v `md2html.py` — dashboard má
# vypadat jako součást projektu, ne jako cizí nástroj. Barvy stavů jsou v
# proměnných, aby je šlo v tmavém režimu přesvítit jedním blokem.
CSS = """
:root {
  color-scheme: light dark;
  --draft: #7a8b95; --ready: #1f6f8b; --running: #b8621f;
  --gated: #6f57a0; --merged: #2c7a54; --blocked: #b3402f;
  --ram: #dbe3e8; --tise: #6e808c; --karta: #fbfcfd;
}
* { box-sizing: border-box; }
body {
  font-family: "Segoe UI", system-ui, Arial, sans-serif;
  max-width: 1200px; margin: 0 auto; padding: 28px 22px 70px;
  line-height: 1.55; font-size: 15px; color: #1a2733; background: #ffffff;
}
h1 { font-size: 1.6em; color: #163a4d; margin: 0 0 .15em;
     border-bottom: 3px solid #e8734a; padding-bottom: .25em; }
h2 { font-size: 1.05em; color: #163a4d; margin: 1.8em 0 .6em;
     border-bottom: 1px solid var(--ram); padding-bottom: .25em; }
code { font-family: Consolas, "Courier New", monospace; font-size: .88em; }
.hlava { color: var(--tise); font-size: .85em; margin: .2em 0; }
.souhrn { margin: .6em 0 0; font-size: .95em; }
.souhrn strong { color: #10222e; }
.karty { display: grid; gap: 12px;
         grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); }
.karta { border: 1px solid var(--ram); border-left: 5px solid var(--barva);
         border-radius: 8px; padding: 10px 13px 12px; background: var(--karta); }
.karta.varovani { border-color: var(--blocked); }
.stav-draft   { --barva: var(--draft); }
.stav-ready   { --barva: var(--ready); }
.stav-running { --barva: var(--running); }
.stav-gated   { --barva: var(--gated); }
.stav-merged  { --barva: var(--merged); }
.stav-blocked { --barva: var(--blocked); }
.karta.stav-jiny { --barva: var(--tise); }
.titulek { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.cislo { font-weight: 700; color: var(--barva); font-size: 1.05em; }
.nazev { font-weight: 600; }
.znak { margin-left: auto; font-size: .75em; letter-spacing: .04em;
        text-transform: uppercase; color: var(--barva);
        border: 1px solid var(--barva); border-radius: 10px; padding: 0 7px; }
.pas { height: 7px; border-radius: 4px; background: var(--ram); margin: 8px 0 5px;
       overflow: hidden; }
.pas > i { display: block; height: 100%; background: var(--barva); }
.cisla { font-size: .84em; color: var(--tise); margin: 0 0 6px; }
.zdroj { font-size: .82em; margin: 0 0 6px; color: var(--merged); }
.zdroj.chybi { color: var(--tise); font-style: italic; }
.zdroj.spatne { color: var(--blocked); font-style: normal; font-weight: 600; }
.radek { font-size: .85em; margin: 0 0 5px; }
.tise { color: var(--tise); }
ul.zmeny { list-style: none; padding: 0; margin: 4px 0 6px; font-size: .82em; }
ul.zmeny li { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
ul.zmeny b { display: inline-block; min-width: 2.1em; color: var(--running);
             font-family: Consolas, monospace; }
table { border-collapse: collapse; width: 100%; font-size: .84em; }
th, td { border: 1px solid var(--ram); padding: 4px 8px; text-align: left;
         vertical-align: top; }
th { background: #163a4d; color: #fff; font-weight: 600; }
tr:nth-child(even) td { background: #f2f6f8; }
table.log { margin-top: 4px; font-size: .78em; }
table.log td { border-color: var(--ram); }
.osa td.kdy { white-space: nowrap; color: var(--tise); }
.osa td.kdo { white-space: nowrap; font-weight: 600; }
.pata { margin-top: 42px; padding-top: 12px; border-top: 1px solid var(--ram);
        font-size: .78em; color: var(--tise); }
@media (prefers-color-scheme: dark) {
  :root {
    --draft: #93a4ae; --ready: #6cb6d9; --running: #e8a05a;
    --gated: #a894d8; --merged: #63c295; --blocked: #e0705c;
    --ram: #2a3b47; --tise: #8ba0ad; --karta: #1b2933;
  }
  body { color: #d7e0e6; background: #14202a; }
  h1, h2 { color: #7fc7e8; }
  .souhrn strong { color: #eef4f7; }
  th { background: #1f4a5f; }
  tr:nth-child(even) td { background: #1a2833; }
}
"""

SABLONA = """<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{refresh}<title>{titulek}</title>
<style>{css}</style>
</head>
<body>
{telo}
</body>
</html>
"""

TITULEK = "CHIPS — stavová deska"


def _e(hodnota) -> str:
    """Zkratka za `html.escape` — v sestavování HTML je na každé druhé řádce."""
    return html.escape(str(hodnota), quote=True)


def _trida_stavu(stav: str) -> str:
    """CSS třída podle stavu; neznámý stav dostane neutrální (hlásí ho lint)."""
    return f"stav-{stav}" if stav in STAVY else "stav-jiny"


def _karta_html(k: Karta, ted: int) -> str:
    """Jedna karta chipu. Nic nedopočítává — všechno už je v `Karta`."""
    tridy = ["karta", _trida_stavu(k.stav)] + (["varovani"] if k.varovani else [])
    kusy = [f'<article class="{" ".join(tridy)}">',
            '<div class="titulek">',
            f'<span class="cislo">{_e(k.id)}</span>',
            f'<span class="nazev">{_e(k.nazev)}</span>',
            f'<span class="znak">{_e(k.stav)}</span>',
            '</div>',
            f'<div class="pas"><i style="width:{k.procenta}%"></i></div>']

    popis = [f"issues {k.hotovo}/{k.celkem} ({k.procenta} %)" if k.celkem
             else "issues: žádné"]
    if k.vlna is not None:
        popis.append(f"vlna {k.vlna}")
    if k.zavislosti:
        popis.append("závisí na " + ", ".join(k.zavislosti))
    kusy.append(f'<p class="cisla">{_e(" · ".join(popis))}</p>')

    if k.zivo:
        odkud = ("" if k.brief_z_worktree
                 else " · pozor: brief jen z hlavního stromu, "
                      "kopie ve worktree není")
        kusy.append(f'<p class="zdroj">živá data z worktree '
                    f'<code>{_e(k.worktree)}</code>{_e(odkud)}</p>')
    else:
        trida = "zdroj spatne" if k.varovani else "zdroj chybi"
        kusy.append(f'<p class="{trida}">bez živých dat — {_e(k.poznamka)}</p>')

    if k.posledni is not None:
        c = k.posledni
        cizi = "" if k.posledni_je_chipu else " · společný základ, chip zatím " \
                                              "nic neodevzdal"
        kusy.append(f'<p class="radek">poslední commit <code>{_e(c.kratky)}</code> '
                    f'{_e(zkrat(c.predmet, 90))}<br><span class="tise">'
                    f'{_e(format_casu(c.cas))} · {_e(stari(c.cas, ted))} · '
                    f'{_e(k.vetev)}{_e(cizi)}</span></p>')
    elif k.vetev_existuje:
        kusy.append(f'<p class="radek tise">na větvi <code>{_e(k.vetev)}</code> '
                    f'zatím žádný commit</p>')
    elif k.vetev:
        # Zmergovaný chip má větev typicky smazanou — „žádný commit" by bylo
        # zavádějící, práce je v hlavní větvi.
        kusy.append(f'<p class="radek tise">větev <code>{_e(k.vetev)}</code> '
                    f'v repu není</p>')

    if k.zmeny:
        kusy.append(f'<p class="radek">rozeditováno ({k.zmen_celkem}):</p>'
                    '<ul class="zmeny">')
        kusy += [f'<li><b>{_e(z.kod.replace(" ", "·"))}</b>{_e(z.cesta)}</li>'
                 for z in k.zmeny]
        if k.zmen_celkem > len(k.zmeny):
            kusy.append(f'<li class="tise">… a další '
                        f'{k.zmen_celkem - len(k.zmeny)}</li>')
        kusy.append("</ul>")
    elif k.zivo:
        kusy.append('<p class="radek tise">pracovní strom je čistý</p>')

    if k.log:
        kusy.append('<table class="log">')
        kusy += ["<tr>" + "".join(f"<td>{_e(zkrat(b))}</td>" for b in r) + "</tr>"
                 for r in k.log]
        kusy.append("</table>")

    kusy.append("</article>")
    return "\n".join(kusy)


def _vlny_html(karty: list[Karta], ted: int) -> str:
    """Karty seskupené po vlnách, uvnitř vlny podle ID (issue #5)."""
    podle: dict[tuple[int, int], list[Karta]] = {}
    for k in karty:
        # Chipy s nespočitatelnou vlnou (cyklus) jdou úplně nakonec, ne na
        # začátek — jsou to výjimky, ne výchozí stav.
        podle.setdefault((1, 0) if k.vlna is None else (0, k.vlna), []).append(k)

    kusy = []
    for klic in sorted(podle):
        skupina = sorted(podle[klic], key=lambda k: k.id)
        nadpis = ("vlna neurčená (cyklická závislost)" if klic[0]
                  else f"vlna {klic[1]}")
        zive = sum(1 for k in skupina if k.zivo)
        kusy.append(f"<h2>{_e(nadpis)} — {len(skupina)} {_chipu(len(skupina))}, "
                    f"{zive} se živými daty</h2>")
        kusy.append('<div class="karty">')
        kusy += [_karta_html(k, ted) for k in skupina]
        kusy.append("</div>")
    return "\n".join(kusy)


def _osa_html(commity: list[Commit], ted: int) -> str:
    """Časová osa: commity chip větví, které ještě nejsou v HEAD hlavní větve.

    Právě ty ukazují tempo běžících chipů; commity už obsažené v HEAD jsou
    společný základ a v ose by jen dělaly šum (a hlásily by se u každé větve).
    """
    if not commity:
        return ("<h2>Časová osa</h2><p class=\"radek tise\">žádné commity na "
                "chip větvích mimo HEAD — buď se ještě necommitovalo, nebo je "
                "všechno zmergované.</p>")
    kusy = ["<h2>Časová osa — commity chip větví mimo HEAD</h2>",
            '<table class="osa"><tr><th>kdy</th><th>chip</th><th>commit</th>'
            "<th>autor</th></tr>"]
    for c in commity:
        kusy.append(f'<tr><td class="kdy">{_e(format_casu(c.cas))}<br>'
                    f'<span class="tise">{_e(stari(c.cas, ted))}</span></td>'
                    f'<td class="kdo">{_e(c.chip or "—")}</td>'
                    f'<td><code>{_e(c.kratky)}</code> {_e(c.predmet)}</td>'
                    f'<td>{_e(c.autor)}</td></tr>')
    kusy.append("</table>")
    return "\n".join(kusy)


def souhrn(karty: list[Karta]) -> str:
    """Věta nad deskou: kolik chipů, v jakých stavech, kolik má živá data."""
    pocty: dict[str, int] = {}
    for k in karty:
        pocty[k.stav] = pocty.get(k.stav, 0) + 1
    poradi = STAVY + sorted(set(pocty) - set(STAVY))
    rozpis = ", ".join(f"{s} {pocty[s]}" for s in poradi if pocty.get(s))
    hotovo = sum(k.hotovo for k in karty)
    celkem = sum(k.celkem for k in karty)
    zive = sum(1 for k in karty if k.zivo)
    return (f"{len(karty)} {_chipu(len(karty))} — {rozpis or '—'} · "
            f"issues {hotovo}/{celkem} · živá data z {zive} worktree")


def sestav_html(deska: Deska) -> str:
    """Celé HTML jako řetězec — čistá funkce, žádné I/O ani git.

    Soubor musí fungovat offline (issue #1): styl je inline v `<style>`,
    nikde není odkaz na cizí zdroj a nejsou tu ani skripty — všechno, co má
    dashboard ukázat, se spočítá při generování.
    """
    refresh = ""
    if deska.interval:
        refresh = (f'<meta http-equiv="refresh" '
                   f'content="{int(deska.interval)}">\n')
    varovani = [k for k in deska.karty if k.varovani]
    telo = [f"<h1>{_e(TITULEK)}</h1>",
            f'<p class="hlava">vygenerováno {_e(format_casu(deska.ted))}'
            + (f" · obnova každých {int(deska.interval)} s" if deska.interval else "")
            + f" · briefy: <code>{_e(deska.chips_dir)}</code></p>",
            f'<p class="souhrn"><strong>{_e(souhrn(deska.karty))}</strong></p>']
    if varovani:
        telo.append('<p class="zdroj spatne">pozor: '
                    + _e(", ".join(f"chip {k.id} ({k.stav}) — {k.poznamka}"
                                   for k in varovani)) + "</p>")
    telo.append(_vlny_html(deska.karty, deska.ted))
    telo.append(_osa_html(deska.commity, deska.ted))
    telo.append('<p class="pata">Vygenerováno nástrojem '
                "<code>tools/chip_dashboard.py</code> — data z worktree "
                "jednotlivých chipů a z gitu, ne z hlášení agentů.</p>")
    return SABLONA.format(refresh=refresh, titulek=_e(TITULEK), css=CSS,
                          telo="\n".join(telo))


def _git(cwd: Path, *args: str) -> tuple[int, str]:
    """Git jen ke čtení; vrací `(kód, stdout)`. Selhání není výjimka.

    `args[0]` musí být v `POVOLENE_GIT` — jinak `ChybaJenCteni`. Whitelist je
    záměrně tvrdý: dashboard smí zapsat jedině do výstupního HTML (issue #10)
    a tuhle vlastnost má hlídat kód, ne dobrá vůle volajícího.

    Nepovedený git (chybějící repo, rozbitý worktree, git není na PATH) se
    vrací jako nenulový kód — nesmí shodit celou desku, jen svoji kartu
    (issue #11).
    """
    if not args or args[0] not in POVOLENE_GIT:
        raise ChybaJenCteni(f"chip_dashboard smí jen číst; '{args and args[0]}' "
                            f"není v POVOLENE_GIT")
    try:
        p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    return p.returncode, p.stdout or ""


def _vetve(repo: Path, cache: dict[str, set[str]]) -> set[str]:
    """Názvy lokálních větví repa; cache, protože chipy sdílejí jedno repo."""
    klic = str(repo)
    if klic not in cache:
        kod, out = _git(repo, "for-each-ref", "--format=%(refname:short)",
                        "refs/heads")
        cache[klic] = {r.strip() for r in out.splitlines() if r.strip()} \
            if kod == 0 else set()
    return cache[klic]


def _z_briefu(chip, k: Karta, limit_logu: int) -> None:
    """Naplní kartu z daného briefu: stav, issues, ocas Logu.

    I `stav:` patří mezi živá data — `chip_run.py --stav` ho přepisuje do
    **kopie ve worktree**, takže hlavní strom u běžícího chipu pořád tvrdí
    `ready`. Karta má ukazovat, co platí teď.
    """
    k.stav = chip.stav
    k.hotovo = len(chip.hotove_issues())
    k.celkem = len(chip.issues())
    k.log = ocas_logu(chip.najdi("log") or "", limit_logu)


def koren_stromu(cesta: Path) -> Path | None:
    """Kořen pracovního stromu nad `cesta` — první rodič s `.git`; jinak `None`.

    `.git` je v worktree soubor, ne adresář, proto `exists()` a ne `is_dir()`.
    """
    for kandidat in [cesta.resolve(), *cesta.resolve().parents]:
        if (kandidat / ".git").exists():
            return kandidat
    return None


def brief_ve_worktree(brief: Path, worktree: Path) -> Path | None:
    """Kopie briefu ve worktree chipu, nebo `None`, když tam žádná není.

    Mapuje se přes kořen stromu, ve kterém dashboard právě čte briefy — ne
    přes `repo:` z frontmatteru jako `chip_run.brief_ke_stavu()`. Ten totiž
    odpovídá na jinou otázku („kam smí `--stav` zapsat") a spoléhá, že se čte
    z hlavního stromu; dashboard se ale běžně pouští z worktree některého
    chipu, kde by `relative_to(repo)` selhalo a všechny karty by tiše spadly
    zpátky na briefy toho jednoho worktree — tedy přesně na data, která se
    nehýbou (issue #2).
    """
    koren = koren_stromu(brief)
    if koren is None:
        return None
    try:
        rel = brief.resolve().relative_to(koren)
    except ValueError:                       # pragma: no cover — koren je předek
        return None
    kopie = worktree / rel
    return kopie if kopie.exists() else None


def karta_chipu(chip, vlna: int | None, cache: dict[str, set[str]], *,
                limit_zmen: int = LIMIT_ZMEN, limit_commitu: int = LIMIT_COMMITU,
                limit_logu: int = LIMIT_LOGU) -> tuple[Karta, list[Commit]]:
    """Karta jednoho chipu + jeho commity do časové osy.

    Pořadí je dané tím, co se smí nevyvést: nejdřív se karta naplní z hlavního
    stromu (to jde vždycky), pak se přepíše živými daty z worktree. Když
    worktree chybí nebo je rozbitý, zůstane karta s poznámkou PROČ — nikdy
    prázdná čísla vydávaná za nulu.
    """
    repo, vetev, worktree = cesty(chip)
    k = Karta(id=chip.id, nazev=chip.nazev, stav=chip.stav, vlna=vlna,
              zavislosti=chip.zavislosti(), vetev=vetev, worktree=worktree.name)
    _z_briefu(chip, k, limit_logu)

    if repo is None:
        k.poznamka = "brief nemá ve frontmatteru 'repo:'"
    elif not worktree.exists():
        k.poznamka = f"worktree {worktree.name} na disku není"
    elif not (worktree / ".git").exists():
        # Bez `.git` by se git zeptal nadřazeného adresáře a odpověděl by za
        # úplně jiné repo — to je horší než přiznat, že data nejsou.
        k.poznamka = f"{worktree.name} není worktree (chybí .git)"
    else:
        kod, vystup = _git(worktree, "status", "--porcelain")
        if kod != 0:
            k.poznamka = f"git ve worktree {worktree.name} selhal"
        else:
            zmeny = parsuj_status(vystup)
            k.zmen_celkem = len(zmeny)
            k.zmeny = zmeny[:limit_zmen]
            # Tohle je jádro chipu: stav i checkboxy se hýbou v kopii briefu
            # ve worktree, ne v originále. Když kopie není, řekne se to na
            # kartě nahlas — čísla z hlavního stromu nejsou živá data.
            kopie = brief_ve_worktree(chip.path, worktree)
            if kopie is not None:
                try:
                    _z_briefu(parse(kopie), k, limit_logu)
                    k.brief_z_worktree = True
                except (OSError, ValueError, UnicodeError):
                    # Agent do briefu právě píše / je rozeditovaný — karta si
                    # nechá čísla z hlavního stromu a nespadne (nástroj běží
                    # i ve chvíli, kdy se zapisuje).
                    k.brief_z_worktree = False

    k.varovani = bool(k.poznamka) and k.stav in STAVY_SE_ZIVOTEM

    commity: list[Commit] = []
    k.vetev_existuje = repo is not None and vetev in _vetve(repo, cache)
    if k.vetev_existuje:
        pretty = f"--pretty=format:{FORMAT_LOGU}"
        kod, out = _git(repo, "log", "-n", "1", pretty, vetev, "--")
        posledni = parsuj_commity(out, chip.id) if kod == 0 else []
        k.posledni = posledni[0] if posledni else None
        kod, out = _git(repo, "log", "-n", str(limit_commitu), pretty, vetev,
                        "--not", "HEAD", "--")
        if kod == 0:
            commity = parsuj_commity(out, chip.id)
        k.posledni_je_chipu = bool(k.posledni) and any(
            c.sha == k.posledni.sha for c in commity)
    return k, commity


def posbirej(chipy, *, ted: int | None = None, interval: int | None = None,
             chips_dir: str = "", limit_zmen: int = LIMIT_ZMEN,
             limit_commitu: int = LIMIT_COMMITU,
             limit_logu: int = LIMIT_LOGU) -> Deska:
    """Sesbírá desku ze všech chipů — jediné místo, které sahá na disk a git.

    Commit může ležet na víc chip větvích naráz (chip větvený z předchůdce
    přes `chip_run.py --od`); v ose se drží u chipu s nejnižším ID, ať se
    tentýž řádek neopakuje.
    """
    vlny = spocitej_vlny(chipy)
    cache: dict[str, set[str]] = {}
    karty: list[Karta] = []
    commity: list[Commit] = []
    videne: set[str] = set()
    for chip in sorted(chipy, key=lambda c: c.id):
        k, nove = karta_chipu(chip, vlny.get(chip.id), cache,
                              limit_zmen=limit_zmen, limit_commitu=limit_commitu,
                              limit_logu=limit_logu)
        karty.append(k)
        for c in nove:
            if c.sha not in videne:
                videne.add(c.sha)
                commity.append(c)
    commity.sort(key=lambda c: (-c.cas, c.chip))
    return Deska(karty=karty, commity=commity,
                 ted=int(time.time()) if ted is None else ted,
                 chips_dir=chips_dir, interval=interval)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Stavová deska chipů — z worktree a z gitu.")
    ap.add_argument("--out", metavar="SOUBOR",
                    help="kam zapsat HTML (default: dashboard.html v kořeni repa)")
    ap.add_argument("--watch", action="store_true",
                    help="vložit do HTML <meta refresh>, ať se stránka obnovuje")
    ap.add_argument("--interval", type=int, default=30, metavar="S",
                    help="perioda obnovy a opakovaného generování (default 30 s)")
    ap.add_argument("--opakovat", action="store_true",
                    help="generovat pořád dokola po --interval sekundách (Ctrl+C)")
    pridej_arg_dir(ap)
    args = ap.parse_args(argv)
    cesta_chipu = nastav_chips_dir(args.dir)

    if args.interval < 1:
        print("! --interval musí být aspoň 1 s")
        return 1
    out = Path(args.out).expanduser() if args.out else ROOT / "dashboard.html"
    if not out.parent.exists():
        # Adresář se schválně nezakládá: jediný zápis, který si tenhle nástroj
        # dovolí, je samotné výstupní HTML (issue #10).
        print(f"! adresář {out.parent} neexistuje — dashboard tam nic nezakládá")
        return 1

    while True:
        chipy = nacti_vse()
        if not chipy:
            print(f"  žádné chipy v {cesta_chipu} (kromě šablony)")
        deska = posbirej(chipy, interval=args.interval if args.watch else None,
                         chips_dir=str(cesta_chipu))
        try:
            out.write_text(sestav_html(deska), encoding="utf-8")
        except OSError as e:
            print(f"! {out} se nepodařilo zapsat: {e}")
            return 1
        print(f"  {out}  —  {souhrn(deska.karty)}")

        if not args.opakovat:
            return 0
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n  konec (Ctrl+C)")
            return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    utf8_vystup()
    sys.exit(main())
