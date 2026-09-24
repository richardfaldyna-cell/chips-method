---
chip: 17
nazev: lint-navazujici
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-17/lint-navazujici
worktree: ../CHIPS-chip-17
---

# CHIP 17 — lint hlásí jako chybu i to, co je legitimní postup

Dvě hlášení `chip_lint.py` jsou dnes **pravdivá, ale nepoužitelná**: popisují
správně, co vidí, a přitom brání postupu, který metodika povoluje.

1. **Navazující chip.** Chip ve stavu `running`/`gated`, jehož předek je
   `gated` (hotový, čeká na bránu), je hlášený jako **chyba** — a lint je
   brána s exit 1. Jenže přesně tak navazující chip vypadá: předek dojel,
   potomek na něm staví, merguje se to po sobě. Chyba tu má být jen tam, kde
   se stavět **nedá**.
2. **Greenfield.** První chip v projektu, jehož repo teprve vznikne, spadne na
   „repo neexistuje" a na neexistujících nárokovaných cestách. Dnes se musí
   repo založit ručně dřív, než lint vůbec pustíš.

Obojí je jeden soubor a jedna otázka: **kdy je nesplněný předpoklad chyba a kdy
jen varování.** Rozhoduje, jestli s tím jde pokračovat, nebo ne.

## Issues

- [x] #1 — předek ve stavu `gated`: varování místo chyby (potomek smí běžet
      i mergovat, jen ne dřív než předek)
- [x] #2 — předek ve stavu `merged`: beze změny, čisto
- [x] #3 — předek ve stavu `draft`/`ready`/`running`: **zůstává chyba** — na
      nehotové práci se stavět nedá a tichý průchod by kolizi jen odložil
- [x] #4 — předek `blocked`: **zůstává chyba**, a hláška ať řekne proč
      (blocked = někdo musí rozhodnout, ne „skoro hotovo")
- [x] #5 — hláška u varování musí říct pořadí merge („merguj 16 před 17"),
      ne jen konstatovat stav
- [x] #6 — frontmatter `greenfield: ano` znamená „repo teprve vznikne":
      neexistující `repo:` je pak varování, ne chyba
- [x] #7 — s `greenfield: ano` se nekontroluje existence nárokovaných cest
      (repo tam ještě není, takže by padaly všechny)
- [x] #8 — **bez** `greenfield:` zůstává „repo neexistuje" chybou; příznak je
      vědomé prohlášení, ne měkčí default
- [x] #9 — `greenfield: ano` u chipu, jehož repo **už existuje a má commity**,
      je varování „příznak je zastaralý, smaž ho" — jinak by v briefu zůstal
      navždy a tiše vypínal kontrolu cest
- [x] #10 — testy ke všem bodům výš, včetně regrese na dnešní chování
- [x] #11 — docstring modulu (seznam „Kontroluje:") doplnit o nové chování

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_lint.py
tests/test_chip_lint.py
```

`chips/TEMPLATE.md` je **mimo nárok** — příznak `greenfield:` do šablony a do
metodiky dopíše orchestrátor po mergi.

## Definition of done

- [x] `python -m unittest discover -s tests` projde a testů je **víc** než
      dnešních 454
- [x] `python tools/chip_lint.py` nad tímhle repem vrací **0** a nehlásí nic
      nového proti dnešku (regrese: dnes 0 chyb, 0 varování)
- [x] test, který postaví dvojici chipů `předek gated → potomek running` a
      ověří, že lint vrací **0** a text obsahuje varování — dnes vrací 1
- [x] test, který u téže dvojice se stavem předka `blocked` ověří návrat **1**
- [x] test, který nad chipem s `greenfield: ano` a neexistujícím `repo:` ověří
      návrat **0**, a bez příznaku návrat **1** (tentýž brief, jediný rozdíl)

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Zastav se, zapiš do Logu a nech na uživateli:

- **jakékoli zeslabení kontroly disjunktnosti** (sekce „3 — disjunktnost")
  — to je hlavní důvod, proč lint existuje; sem nesaháš
- převedení další dnešní **chyby** na varování nad rámec issues výš
- jakýkoli zásah mimo „Dotčené soubory" — `chip_run.py` a `chip_common.py`
  si nárokuje jiný chip téže vlny
- nová externí závislost

## Kontext pro agenta

- Testy: `python -m unittest discover -s tests -v`, stdlib `unittest`, **žádný
  pytest**. Vlastní `tempfile` fixture, úklid po sobě.
- `chip_common.CHIPS_DIR` je globální stav; v `tearDown` ho vracej.
- Lint vrací **exit 1 při nálezu** — je to brána, ne doporučení. Rozdíl
  chyba/varování je proto celý rozdíl mezi „nespouštěj" a „vím o tom".
- Rozhodovací pravidlo, které se drž: **chyba = nejde s tím pokračovat,
  varování = jde, ale musíš vědět v jakém pořadí.**
- Závislosti se vyhodnocují v sekci „2b" v `main()`; existující řádek pro
  `ready` (varování „čeká na chip NN") je vzor tvaru hlášky.
- `zkontroluj_cesty()` už dnes rozlišuje chyby a varování a vrací dvojici —
  greenfield tam zapadne bez změny struktury.
- Příznak čti přes `c.meta.get(...)`; parser frontmatteru komentáře za `#`
  odřezává sám, takže `greenfield: ano  # …` funguje.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-28 | ready | brief založen orchestrátorem |
| 2026-07-28 | running | #1–#5 hotové: sekce 2b rozlišuje stav předka. `gated` = varování „merguj NN před MM", `blocked` = chyba s důvodem (čeká na rozhodnutí), `draft`/`ready`/`running` beze změny („očekává se 'merged'"). Potomek ve stavu `ready` se nedotčen dál jen „nespouštět dřív". |
| 2026-07-28 | running | #6–#9 hotové: `je_greenfield()` čte `greenfield:` (kladné hodnoty ano/yes/true/1). Neexistující `repo:` je s příznakem varování, bez něj dál chyba; s příznakem se přeskočí ověření existence nárokovaných cest, ale NE kontrola tvaru cesty (relativní, bez `..`) — ta na repu nezávisí a je vstupem do disjunktnosti, takže se neměkčí. |
| 2026-07-28 | running | #9 — zastaralost příznaku poznává `ma_commity()`: čte `refs/heads` a `packed-refs` bez subprocesu (`git init` bez commitu ještě greenfield je). Ověřeno i proti skutečnému gitu včetně stavu po `git gc`. Kontrola cest zůstává i tak vypnutá, jen už ne tiše — varování říká „smaž příznak". |
| 2026-07-28 | running | #10 — přibyly třídy `TestNavazujiciChip` a `TestGreenfield` (22 testů). Sada 454 → 476, celá zeleně. `chip_lint.py` nad tímhle repem: rc 0, 0 chyb, 0 varování — beze změny proti výchozímu stavu. |
| 2026-07-28 | running | #11 — docstring modulu doplněn o bod 5 (stavy předka), o greenfield a o dělící pravidlo chyba/varování. |
| 2026-07-28 | running | Mimo nárok, na orchestrátora: (a) `greenfield:` dopsat do `chips/TEMPLATE.md` a do `docs/metodika.md`, (b) přegenerovat `chips/17-lint-navazujici.html` (`md2html.py` si nárokuje jiný chip vlny, HTML jsem proto nesahal). Nic k eskalaci T3 — disjunktnost ani žádná další chyba se nezeslabovala. |
