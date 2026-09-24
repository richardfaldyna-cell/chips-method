---
chip: 02
nazev: chip-status
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-02/chip-status
worktree: ../CHIPS-chip-02
---

# CHIP 02 — `chip_status.py`: přehled chipů a vln

Dnes nejde zjistit stav sady chipů jinak než čtením briefů. Tenhle chip přidá
nástroj, který to vypíše v jedné tabulce a spočítá vlny.

## Issues

- [x] #1 — `python tools/chip_status.py` vypíše tabulku: ID, název, stav, počet issues, počet nároků, závislosti
- [x] #2 — spočítat **vlnu** každého chipu = hloubka v grafu závislostí (bez závislostí → vlna 0)
- [x] #3 — přehled po vlnách: které chipy smí běžet paralelně (jen stav `ready`)
- [x] #4 — souhrn na konci: kolik chipů v jakém stavu, kolik issues celkem, kolik hotových
- [x] #5 — `--vlny` vypíše jen rozpis vln, `--dir` přepne adresář s briefy (stejně jako ostatní nástroje)
- [x] #6 — cyklická závislost nesmí nástroj zacyklit — detekuj a vypiš jako `?`
- [x] #7 — prázdný adresář s chipy = smysluplná hláška, návratový kód 0
- [x] #8 — návratový kód vždy 0 (je to přehled, ne brána)
- [x] #9 — testy pro výpočet vln, souhrn, cyklus a prázdný vstup

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_status.py         # nový
tests/test_chip_status.py    # nový
```

Nesmíš měnit `chip_common.py`, `chip_lint.py` ani `chip_run.py` — když ti něco
chybí, dopočítej si to u sebe a zapiš do Logu, že by to patřilo do společného modulu.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] `python tools/chip_status.py --dir <tmp>` vypíše tabulku a skončí s kódem 0
- [x] výpočet vln pokrytý testem včetně cyklu a osamoceného chipu
- [x] pouze standardní knihovna (žádné nové závislosti)
- [x] výstup čitelný na 80 sloupcích, diakritika neláme zarovnání

## Ověření (brána)

Bez zelené brány se **nemerguje**. Když selže → stav `blocked`, popiš proč v Logu.

```bash
python -m unittest discover -s tests -v
python tools/chip_status.py --dir chips
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Při zásahu do čehokoli z tohoto seznamu: **zastav, zapiš do Logu, nehádej.**

- změna `chip_common.py` (sdílený parser — nárokuje si ho jiný chip)
- nová závislost mimo stdlib (tabulky, barvy, rich, tabulate)
- změna formátu frontmatteru nebo šablony briefu
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- Briefy načteš přes `chip_common`: `nacti_vse()`, `nastav_chips_dir()`,
  `pridej_arg_dir(ap)`, `utf8_vystup()`. Import stejně jako ostatní nástroje:
  `from chip_common import ...` a v `__main__` bloku `sys.path.insert(0, str(ROOT / "tools"))`.
- `Chip` má: `.id`, `.stav`, `.nazev`, `.issues()`, `.soubory()`, `.zavislosti()`,
  `.repo_path()`. Hotové issues poznáš podle `- [x]` v sekci Issues —
  `issues()` vrací text bez značky, takže na počítání hotových si přečti sekci
  `najdi("issues")` sám.
- Vlna = 0 pro chip bez závislostí, jinak `1 + max(vlna předků)`. Cyklus ošetři
  množinou navštívených ID (vzor je v `chip_lint.predci`).
- `utf8_vystup()` volej hned v `__main__`, jinak Windows konzole rozbije diakritiku.
- Vzhled výpisu drž v duchu ostatních nástrojů: dva mezery odsazení, `X` pro
  chybu, `!` pro varování, žádné barvy.
- Stavy jsou v `chip_common.STAVY`: draft, ready, running, gated, merged, blocked.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-26 | ready | založeno orchestrátorem |
| 2026-07-26 | running | `tools/chip_status.py` + `tests/test_chip_status.py` hotové; 23 testů, brána zelená (unittest OK, chip_status --dir chips exit 0, chip_lint exit 0) |
| 2026-07-26 | running | `chip_common` nemá počítání odškrtnutých issues — `hotove_issues()` je proto lokálně v `chip_status.py`; patřilo by do sdíleného modulu (nárokuje si ho jiný chip, neměnil jsem ho) |
| 2026-07-26 | running | neznámý předek (`zavisi_na` na chip, který neexistuje) se ve výpočtu vln bere jako hotový, tj. potomek má vlnu 1 — nález hlásí `chip_lint`, nedublovat |
| 2026-07-26 | running | stav ve frontmatteru nechávám `ready`: přepnutí na `gated`/`merged` je rozhodnutí uživatele, brief smím upravovat jen v Logu a checkboxech |
| 2026-07-26 | merged | brána ověřena orchestrátorem nezávisle (testy + lint), sloučeno do master, worktree uklizen |
| 2026-07-27 | merged | Sjednocení složky: `vetev:` převedena na konvenci `ai/chip-NN/<nazev>` (zavedl chip 08 — tenhle chip běžel ještě pod starým tvarem `chip/NN-<nazev>`), doplněn slovník stavů do komentáře u `stav:`. Obsah chipu nedotčen. |
