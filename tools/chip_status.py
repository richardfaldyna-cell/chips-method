"""Přehled chipů: tabulka stavů, rozpis vln a souhrn.

Vlna = hloubka chipu v grafu závislostí. Chip bez závislostí je vlna 0, jinak
`1 + max(vlna předků)`. Chipy stejné vlny ve stavu `ready` smí běžet paralelně
(že si navzájem nesahají do souborů, hlídá `chip_lint.py`).

Použití:
    python tools/chip_status.py                   # tabulka + vlny + souhrn
    python tools/chip_status.py --vlny            # jen rozpis vln
    python tools/chip_status.py --dir ../jiny/chips

Návratový kód je vždy 0 — tohle je přehled, ne brána (tou je `chip_lint.py`).
"""

from __future__ import annotations

import argparse
import sys
import textwrap
import unicodedata
from collections import Counter

from chip_common import (ROOT, STAVY, nacti_vse, nastav_chips_dir,
                         pridej_arg_dir, utf8_vystup)

# (nadpis, šířka) — součet + odsazení drží řádek pod 80 sloupci
SLOUPCE = (("ID", 2), ("vlna", 4), ("stav", 7), ("název", 22),
           ("issues", 6), ("cest", 4), ("závisí na", 12))
VPRAVO = {"vlna", "issues", "cest"}

SIRKA = 78          # na kolik sloupců se zalamují seznamy chipů


def spocitej_vlny(chipy) -> dict[str, int | None]:
    """ID chipu → vlna; `None` znamená, že chip visí na cyklu závislostí.

    Cyklus se pozná množinou ID na aktuální větvi rekurze (stejný vzor jako
    `chip_lint.predci`). Nákaza se šíří dál: kdo závisí na cyklickém chipu,
    má vlnu taky nespočitatelnou.
    """
    znam = {c.id: c for c in chipy}
    cache: dict[str, int | None] = {}

    def vlna(cid: str, vetev: frozenset[str]) -> int | None:
        if cid in cache:
            return cache[cid]
        if cid in vetev:                    # kruh — hloubka nedává smysl
            return None
        chip = znam.get(cid)
        if chip is None:
            return 0                        # neznámý předek; hlásí ho chip_lint
        hloubky = [vlna(d, vetev | {cid}) for d in chip.zavislosti()]
        if any(h is None for h in hloubky):
            cache[cid] = None
        else:
            cache[cid] = 1 + max(hloubky) if hloubky else 0
        return cache[cid]

    return {c.id: vlna(c.id, frozenset()) for c in chipy}


def _zkrat(text: str, sirka: int) -> str:
    """Delší hodnotu ustřihne, ať se nerozjede zarovnání tabulky."""
    return text if len(text) <= sirka else text[:sirka - 1] + "…"


def _radek(hodnoty) -> str:
    """Jeden řádek tabulky; diakritika se normalizuje na NFC kvůli zarovnání."""
    kusy = []
    for (nadpis, sirka), hodnota in zip(SLOUPCE, hodnoty):
        h = _zkrat(unicodedata.normalize("NFC", str(hodnota)), sirka)
        kusy.append(h.rjust(sirka) if nadpis in VPRAVO else h.ljust(sirka))
    return ("  " + "  ".join(kusy)).rstrip()


def vypis_tabulku(chipy, vlny) -> None:
    print(_radek([n for n, _ in SLOUPCE]))
    print(_radek(["-" * s for _, s in SLOUPCE]))
    for c in chipy:
        v = vlny.get(c.id)
        print(_radek([c.id,
                      "?" if v is None else v,
                      c.stav,
                      c.nazev,
                      f"{len(c.hotove_issues())}/{len(c.issues())}",
                      len(c.soubory()),
                      ", ".join(c.zavislosti()) or "—"]))


def vypis_vlny(chipy, vlny) -> None:
    """Rozpis po vlnách — co smí běžet naráz, a co ve vlně čeká na jiný stav."""
    podle_vlny: dict[int, list] = {}
    cyklicke = []
    for c in chipy:
        v = vlny.get(c.id)
        if v is None:
            cyklicke.append(c)
        else:
            podle_vlny.setdefault(v, []).append(c)

    print("  Vlny (paralelně smí běžet jen chipy stejné vlny ve stavu 'ready'):")
    for v in sorted(podle_vlny):
        ready = [c for c in podle_vlny[v] if c.stav == "ready"]
        ostatni = [c for c in podle_vlny[v] if c.stav != "ready"]
        odsazeni = f"    vlna {v}:  "
        popis = ", ".join(f"{c.id} {c.nazev}" for c in ready) or "— (nic ve stavu ready)"
        print(textwrap.fill(popis, width=SIRKA, initial_indent=odsazeni,
                            subsequent_indent=" " * len(odsazeni)))
        if ostatni:
            zbytek = ", ".join(f"{c.id} {c.stav}" for c in ostatni)
            print(textwrap.fill(f"mimo pořadí: {zbytek}", width=SIRKA,
                                initial_indent=" " * len(odsazeni),
                                subsequent_indent=" " * (len(odsazeni) + 2)))
    for c in cyklicke:
        print(textwrap.fill(f"{c.path.name}: cyklická závislost — vlnu nelze "
                            f"spočítat (oprav 'zavisi_na' ve frontmatteru)",
                            width=SIRKA, initial_indent="  ! ",
                            subsequent_indent="      "))


def _chipu(n: int) -> str:
    """České skloňování za číslovkou: 1 chip / 2 chipy / 5 chipů."""
    return "chip" if n == 1 else ("chipy" if 2 <= n <= 4 else "chipů")


def vypis_souhrn(chipy) -> None:
    pocty = Counter(c.stav for c in chipy)
    poradi = STAVY + sorted(set(pocty) - set(STAVY))     # neznámý stav hlásí lint
    rozpis = ", ".join(f"{s} {pocty[s]}" for s in poradi if pocty.get(s))
    celkem = sum(len(c.issues()) for c in chipy)
    hotovo = sum(len(c.hotove_issues()) for c in chipy)
    procenta = f" ({round(100 * hotovo / celkem)} %)" if celkem else ""
    print(f"  Souhrn: {len(chipy)} {_chipu(len(chipy))} — {rozpis}")
    print(f"          issues: {hotovo}/{celkem} hotových{procenta}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Přehled chipů, vln a stavů.")
    ap.add_argument("--vlny", action="store_true", help="vypsat jen rozpis vln")
    pridej_arg_dir(ap)
    args = ap.parse_args()
    cesta = nastav_chips_dir(args.dir)

    chipy = nacti_vse()
    if not chipy:
        print(f"  žádné chipy v {cesta} (kromě šablony) — není co ukázat")
        return 0

    vlny = spocitej_vlny(chipy)
    if not args.vlny:
        vypis_tabulku(chipy, vlny)
        print()
    vypis_vlny(chipy, vlny)
    if not args.vlny:
        print()
        vypis_souhrn(chipy)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    utf8_vystup()
    sys.exit(main())
