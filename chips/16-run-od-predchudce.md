---
chip: 16
nazev: run-od-predchudce
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-16/run-od-predchudce
worktree: ../CHIPS-chip-16
---

# CHIP 16 — chip se musí umět větvit z předchůdce a rozjet prázdné repo

`chip_run.py` zakládá worktree vždycky z `HEAD`. To láme dva reálné případy:

1. **Navazující chip.** Chip B staví na práci chipu A, který ještě není
   zmergovaný. Dnes se jeho worktree musí zakládat ručně `git worktree add`,
   protože nástroj neumí říct „větvi z `ai/chip-A/…`". Metodika to přiznává
   jako díru (`docs/metodika.md`, „Navazující chipy metodika neřeší").
2. **Greenfield.** Když cílové repo teprve vznikne, `git worktree add` selže
   na chybějícím `HEAD` — prázdné repo žádný commit nemá. Dnes se to řeší
   ručním `git init` + prázdným commitem, což si musí každý pamatovat.

Obojí je práce v jednom souboru a v jedné funkci (`main()`), proto jeden chip.

## Issues

- [x] #1 — `--od <ref>`: worktree se založí z daného ref, ne z `HEAD`
      (`git worktree add <cesta> -b <vetev> <ref>`)
- [x] #2 — `--od` s neexistujícím ref: hláška a exit 1 **dřív, než vznikne
      worktree** — poloviční stav blokuje další spuštění (stejný důvod, proč se
      dnes `claude` hledá před `worktree add`)
- [x] #3 — ověření ref přes `git rev-parse --verify`, ne přes odhad z názvu
- [x] #4 — `--od` se propíše do `--dry-run` výpisu, aby šlo zkontrolovat,
      z čeho se bude větvit, ještě před založením
- [x] #5 — zadání pro agenta (`ZADANI`) řekne, z které větve chip vychází;
      dnes agent netuší, že pod ním je cizí rozpracovaná práce
- [x] #6 — `--zaloz-repo`: když `repo:` neexistuje nebo není git, založí
      `git init` + prázdný commit (`--allow-empty`), aby `worktree add` prošel
- [x] #7 — `--zaloz-repo` nad existujícím repem s commity **nesmí nic udělat**
      a musí to říct; založení nad cizí historií je nevratná záměna
- [x] #8 — bez `--zaloz-repo` zůstává dnešní chování (chybějící repo = exit 1)
- [x] #9 — testy ke všem bodům výš; `subprocess` zůstává mockovaný, žádný test
      nesmí spustit skutečný `git` ani `claude`
- [x] #10 — docstring modulu doplnit o oba přepínače (je to jediná nápověda,
      kterou orchestrátor čte)

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_run.py
tests/test_chip_run.py
```

Cokoli jiného (`chip_lint.py`, `chip_common.py`, `docs/`, `README.md`) je mimo
nárok — dokumentaci a šablonu dopisuje orchestrátor po mergi.

## Definition of done

- [x] `python -m unittest discover -s tests` projde a testů je **víc** než
      dnešních 454 (nová funkce bez testu se sem nedostane)
- [x] `python tools/chip_run.py 16 --dry-run --od master` vypíše `worktree add`
      s `master` na konci a **nezaloží** nic
- [x] `python tools/chip_run.py 99 --od neexistuje` skončí kódem 1 a v adresáři
      vedle repa nevznikne žádný nový worktree
- [x] volání bez `--od` vytvoří přesně tentýž příkaz jako dnes (regresní test,
      který porovná argv)
- [x] `tools/chip_run.py` nemá žádný nový import mimo stdlib

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Zastav se, zapiš do Logu a nech na uživateli:

- **změna tvaru názvu větve** (`ai/chip-NN/nazev`) — hook i `chip_gate` ji
  parsují vlastní kopií regexu; tichá změna vypne bránu
- jakýkoli zásah mimo „Dotčené soubory" — `chip_lint.py` a `chip_common.py`
  si nárokuje jiný chip téže vlny
- nová externí závislost (projekt jede na stdlib + `markdown`)
- cokoli, co by `--zaloz-repo` nechalo sáhnout na existující historii

## Kontext pro agenta

- Testy: `python -m unittest discover -s tests -v`, stdlib `unittest`, **žádný
  pytest**. Každý test si staví vlastní `tempfile` fixture a uklízí po sobě.
- `tests/test_chip_run.py` má základ `ZakladChipu` s přepínačem `CHIPS_V_REPU`
  (briefy vedle repa vs. uvnitř repa) — nové testy stav pověs na něj.
- `chip_common.CHIPS_DIR` je globální stav; v `tearDown` ho vracej.
- V `main()` platí pořadí: **všechny kontroly, které můžou selhat, běží před
  `git worktree add`.** Drž se ho i u `--od` a `--zaloz-repo`.
- `git()` vypisuje příkaz a vrací návratový kód, `git_tise()` jen kód bez
  výpisu (pro dotazy). `--dry-run` nesmí spustit vůbec nic.
- Čisté funkce (`cesty`, `zadani`, `brief_ke_stavu`) zůstávají bez vedlejších
  efektů — testy to hlídají.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-28 | ready | brief založen orchestrátorem |
| 2026-07-28 | running | `--od` + `--zaloz-repo` hotové, testů 454 → 474, lint rc 0 |
| 2026-07-28 | running | `chips/16-*.html` NEpřegenerováno — `md2html.py` si nárokuje chip 18, HTML nechávám na orchestrátorovi po mergi |
