# CHIPS

**Metodika paralelního vývoje s AI agenty.** Práci nakrájíš na uzavřené balíčky
(„chipy"), každý dostane vlastní izolované okno, odpracuje se autonomně a smí se
sloučit teprve po projití automatické brány.

> **CHIP** = **C**ontained **H**ands-off **I**ssue **P**acket
> (backronym vymyšlený v tomhle projektu — mimo něj to slovo nikdo nezná, viz
> [docs/konverzace-2026-07-25.md](docs/konverzace-2026-07-25.md))

---

## Problém, který to řeší

Máš 100 issues a jednoho Clauda. Sériově je to týdny. Pustíš deset oken paralelně
a získáš tři nové problémy:

1. **Deset session píše do jednoho working tree** → navzájem si přepisují soubory.
   Není to konflikt v gitu, jsou to tiše ztracené změny.
2. **Autonomní merge bez brány** → „důsledně jsem to zkontroloval" je tvrzení
   modelu o sobě samém, ne ověřený fakt.
3. **Nejasné hranice** → dva balíčky sáhnou na stejný soubor a poslední vyhrává.

CHIPS je sada pravidel, která tyhle tři věci řeší dřív, než pustíš první okno.

---

## Šest pravidel

| # | Pravidlo | Proč |
|---|---|---|
| 1 | **Jeden chip = jeden git worktree = jedna větev** | izolace na úrovni filesystému, ne na úrovni důvěry |
| 2 | **Dva chipy nesmí sahat na stejný soubor** | jediné kritérium, podle kterého se řeže |
| 3 | **Merge jen přes zelenou bránu** (testy + build + smoke) | autonomie se nedává promptem, ale ověřováním |
| 4 | **Definition of done napsaná předem a měřitelná** | „hotovo" musí jít ověřit příkazem, ne názorem |
| 5 | **Eskalace místo hádání** — co je T3, končí jako PR + otázka | model, který si není jistý, nemá mergovat |
| 6 | **Chip má strop** (≤ 20 issues, ≤ ~15 souborů) | větší balíček nedojede v jednom kontextu |

Pravidla 1 a 3 nejsou volitelná. Bez nich to není orchestrace, ale řízený chaos,
jehož výsledek stejně musíš celý přečíst.

---

## Rychlý start

**Požadavky:** Python 3.10+ a git. Nástroje jsou jen stdlib; `md2html.py`
potřebuje navíc `pip install markdown`.

```bash
# 1) založ chip z šablony
python tools/chip_new.py 01 refaktor-parseru

# 2) vyplň chips/01-refaktor-parseru.md
#    → hlavně: Issues, Dotčené soubory, Definition of done, Ověření

# 3) zkontroluj, že si chipy nelezou do souborů
python tools/chip_lint.py

# 4) pusť chip v izolovaném worktree
python tools/chip_run.py 01 --dry-run     # ukáže příkazy
python tools/chip_run.py 01 --stav        # založí worktree + větev, přepne stav na 'running'
python tools/chip_run.py 01 --spustit     # navíc rovnou spustí Claude Code ve worktree
python tools/chip_run.py 02 --od ai/chip-01/zaklad   # navazující chip: větvit z předchůdce
python tools/chip_run.py 01 --zaloz-repo  # greenfield: repo teprve vznikne

# 5) přehled: kdo v jakém stavu, co smí běžet paralelně
python tools/chip_status.py          # z briefů v hlavním stromě
python tools/chip_dashboard.py       # ŽIVĚ z worktree běžících chipů (+ --watch)

# 6) ověř bránu ručně, než mergneš (PreToolUse hook ji spustí ještě jednou)
python tools/chip_gate.py 01         # běží ve worktree chipu, ne v hlavním stromě

# 7) AŽ PO MERGI ukliď worktree — dřív ne, hook by merge zamítl
#    (nezmergovanou větev nástroj uklidit odmítne; opuštěný chip: --uklid --presto)
python tools/chip_run.py 01 --uklid
```

Bez `--spustit` otevřeš vytvořený worktree v novém okně Claude Code sám a předáš
mu vypsané zadání. Podrobně: [docs/metodika.md](docs/metodika.md).

**V cizím repu, kam nemá zůstat stopa**, dej briefy stranou (`--dir <cesta>`
nebo `CHIPS_DIR`) a repo přihlas k bráně jedním netrackovaným souborem:

```bash
echo /cesta/k/briefum > <repo>/.chips
echo .chips >> <repo>/.git/info/exclude
```

Bez toho signálu hook briefy nenajde a **mlčky pustí i červený merge** —
adresář `chips/`, marker `.chips` a `CHIPS_DIR` jsou jediné tři způsoby, jak
mu říct, že repo řídí CHIPS.

Dva nástroje navíc, které se nepoužívají v každém kole:

```bash
# nakrájí hotový seznam issues (TODO.md, JSON) na návrhy chipů
python tools/chip_slice.py --todo TODO.md --zapsat chips/

# podklad pro nezávislého reviewera hotového chipu
python tools/chip_review.py 01
```

---

## Struktura

```
CHIPS/
├── chips/              # briefy jednotlivých balíčků (TEMPLATE.md + 01-*.md …)
├── docs/
│   ├── metodika.md     # celý postup: řezání, izolace, brána, eskalace
│   ├── konverzace-2026-07-25.md   # vznik projektu, původní diskuse
│   └── vlna-4-preruseno.md        # co vydrží přerušení vlny (a jak ji dokončit)
├── tests/              # 693 testů, stdlib unittest
└── tools/
    ├── chip_new.py     # založí chip z šablony
    ├── chip_slice.py   # nakrájí seznam issues na návrhy chipů
    ├── chip_lint.py    # disjunktnost souborů + existence nárokovaných cest
    ├── chip_run.py     # worktree + větev + volitelně spustí okno
    ├── chip_status.py  # přehled chipů, vln a stavů (z hlavního stromu)
    ├── chip_dashboard.py  # živá deska: čte worktree běžících chipů a git
    ├── chip_gate.py    # spustí bránu chipu v jeho worktree
    ├── hook_chip_gate.py  # PreToolUse hook: merge až po zelené bráně
    ├── chip_review.py  # podklad pro nezávislého reviewera
    ├── chip_common.py  # parser briefů (sdílený základ)
    └── md2html.py      # .md → .html (konvence workspace)
```

Testy: `python -m unittest discover -s tests -v`

---

## Stav

Metodika je ověřená **dvěma pilotními běhy a jednou opravnou vlnou**.

| | výsledek |
|---|---|
| chipy celkem | 24/24 merged, 0 `blocked` |
| testy | 0 → **693** |
| zásahy mimo nárokované soubory | 0 |
| konflikty při merge | 0 (jednou zaviněné nástrojem, ne chipem) |
| nálezy poslané nahoru místo tichého opravení | 10 |

**Pilot 1 — na tomhle repu (2026-07-26).** Šest chipů ve dvou vlnách, každý ve
vlastním worktree s vlastním oknem, merge až po zelené bráně.

**Pilot 2 — cizí repo `pilot-repo` (2026-07-26).** Sedm chipů, 0 → 235 testů,
7 oprav v zápisové cestě PBIP nástroje. Že hlavní strom zůstal nedotčený, je
doložené manifestem 6037 souborů před a po.

**Vlna 4 — externí code review (2026-07-27).** 30 agentů s adversariální
verifikací našlo 10 vad ve vlastních nástrojích CHIPS, včetně čtyř způsobů,
jak tiše obejít bránu. Všech 10 opraveno; průběh a poučení v
[docs/vlna-4-preruseno.md](docs/vlna-4-preruseno.md).

**Vlna 5 — subagenti místo oken (2026-07-28).** Tři chipy paralelně, poprvé
odbavené subagenty v jedné session místo tří oken. 3/3 merged, 0 zásahů mimo
nárok, 454 → 523 testů. Součet testů po každém mergi seděl na jedničku
(476 → 496 → 523), takže mezi chipy nevznikla žádná kolize. Dva nálezy šly
nahoru místo tichého opravení.

**Vlna 6 — pět chipů naráz (2026-07-28).** 5/5 merged, 0 zásahů mimo nárok,
523 → 676 testů. Součet po každém mergi opět seděl (548 → 562 → 585 → 590 → 676).
Vlna opravila tři vady vlastních nástrojů, u kterých platilo totéž: **pravidlo
bylo správně napsané a nástroj ho porušoval.** Vznikl `chip_dashboard.py`,
který na sobě rovnou doložil, proč je potřeba — nad pěti běžícími chipy hlásil
177/192 hotových issues tam, kde `chip_status.py` z hlavního stromu viděl 140/192.

Co z toho plyne pro tvoje řezání, je v [docs/metodika.md](docs/metodika.md),
sekce „Co ukázal pilot".

**Další krok:** nasazení na reálný firemní projekt. Viz [TODO.md](TODO.md).

---

## Licence

[MIT](LICENSE) © 2026 Richard Faldyna
