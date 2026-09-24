"""Založí nový chip brief z šablony.

Použití:
    python tools/chip_new.py 01 refaktor-parseru
    python tools/chip_new.py 02 oprava-exportu --repo C:/projekty/muj-repo
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys

import chip_common
from chip_common import ROOT, nastav_chips_dir, pridej_arg_dir, utf8_vystup


def main() -> int:
    p = argparse.ArgumentParser(description="Založí chip brief z šablony.")
    p.add_argument("cislo", help="dvojmístné číslo chipu, např. 01")
    p.add_argument("nazev", help="krátký název s pomlčkami, např. refaktor-parseru")
    p.add_argument("--repo", default="C:/cesta/k/repu", help="cesta k cílovému repu")
    p.add_argument("--datum", default=None, help="YYYY-MM-DD (default: dnes)")
    pridej_arg_dir(p)
    args = p.parse_args()
    CHIPS_DIR = nastav_chips_dir(args.dir)

    cislo = args.cislo.zfill(2)
    nazev = re.sub(r"[^a-z0-9-]+", "-", args.nazev.lower()).strip("-")
    if not nazev:
        print("! název musí obsahovat aspoň jeden znak a-z/0-9")
        return 1

    sablona = CHIPS_DIR / "TEMPLATE.md"
    if not sablona.exists():
        sablona = ROOT / "chips" / "TEMPLATE.md"   # sdilena sablona
    if not sablona.exists():
        print(f"! chybí šablona: {sablona}")
        return 1

    cil = CHIPS_DIR / f"{cislo}-{nazev}.md"
    if cil.exists():
        print(f"! už existuje: {cil}  (nepřepisuji)")
        return 1

    datum = args.datum or dt.date.today().isoformat()
    text = sablona.read_text(encoding="utf-8")
    text = (text
            .replace("chip: NN", f"chip: {cislo}")
            .replace("nazev: kratky-nazev-s-pomlckami", f"nazev: {nazev}")
            .replace("repo: C:/cesta/k/repu", f"repo: {args.repo}")
            # Dosazení hlídá test — dřív se tenhle řádek vázal na starý tvar
            # větve a po změně konvence tiše propadl, takže brief odešel
            # s nedosazeným `NN` v názvu větve.
            .replace("vetev: ai/chip-NN/kratky-nazev-s-pomlckami",
                     f"vetev: ai/chip-{cislo}/{nazev}")
            .replace("worktree: ../repo-chip-NN", f"worktree: ../repo-chip-{cislo}")
            .replace("# CHIP NN — <název>", f"# CHIP {cislo} — {nazev.replace('-', ' ')}")
            .replace("| YYYY-MM-DD | draft | založeno |", f"| {datum} | draft | založeno |"))

    cil.write_text(text, encoding="utf-8")
    print(f"  vytvořeno: {cil}")
    print("  dál: vyplň Issues, Dotčené soubory, Definition of done a Ověření,")
    print("       pak přepni stav na 'ready' a spusť: python tools/chip_lint.py")
    return 0


if __name__ == "__main__":
    utf8_vystup()
    sys.exit(main())
