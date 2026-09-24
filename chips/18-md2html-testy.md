---
chip: 18
nazev: md2html-testy
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-18/md2html-testy
worktree: ../CHIPS-chip-18
---

# CHIP 18 — md2html.py je jediný nástroj bez jediného testu

Sada 454 testů je to, co v tomhle projektu drží bránu poctivou. `md2html.py`
z ní vypadl: nemá **žádný** vlastní test, přitom se pouští před každým commitem
(`--all`) a přepisuje desítky souborů v repu. Tichý regres v něm se pozná až
tím, že je HTML rozbité — tedy nejspíš vůbec.

Chip je záměrně jen o testech a o tom, co se při jejich psaní ukáže. **Není to
chip na přepsání md2html.py.**

## Issues

- [x] #1 — `convert()` nad dočasným `.md` vytvoří `.html` **vedle něj** a vrátí
      jeho cestu
- [x] #2 — výstup je samostatný soubor: obsahuje vložené CSS a **žádný odkaz
      na externí zdroj** (offline je celý smysl nástroje)
- [x] #3 — diakritika (`ěščřžýáíé`) přežije převod v UTF-8
- [x] #4 — text mimo markdown se escapuje; `<script>` v `.md` se do HTML
      nedostane jako živý tag
- [x] #5 — `<title>` odpovídá zdroji (název souboru / první nadpis), ať jde
      výstup poznat v záložce prohlížeče
- [x] #6 — tabulka a blok kódu se převedou (obojí je v každém dokumentu
      projektu, takže regres by byl vidět všude)
- [x] #7 — `main()` s cestou k souboru: převede ho a skončí kódem 0
- [x] #8 — `main()` s neexistujícím souborem: **nespadne tracebackem**, ale
      hlásí a končí nenulovým kódem (dnešní chování ověř a zafixuj testem;
      pokud padá, oprav — tohle je jediná povolená změna chování)
- [x] #9 — `--all` převádí `.md` v projektu a **přeskakuje** `.git`
      a `__pycache__`; ověř na dočasném stromu, ne na skutečném repu
- [x] #10 — žádný test nesmí zapsat do skutečného repa ani spustit `--all` nad
      `ROOT` — všechno v `tempfile`

## Dotčené soubory  ⚠️ NÁROK

```
tools/md2html.py
tests/test_md2html.py      # nový
```

## Definition of done

- [x] `tests/test_md2html.py` existuje a `python -m unittest discover -s tests`
      projde; testů je **víc** než dnešních 454
- [x] `git status --porcelain` po celém běhu sady je **prázdný** — testy
      nesmějí přepsat žádný `.html` v repu (to je hlavní riziko tohohle chipu)
- [x] každý bod z Issues má svůj test (název testu ať jde spárovat s číslem)
- [x] `python tools/md2html.py --all` dál funguje a vypíše převedené soubory
- [x] pokud se `md2html.py` měnil, změna je **jen** oprava pádu z #8 —
      formátování ani CSS se nepřepisuje

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Zastav se, zapiš do Logu a nech na uživateli:

- **jakákoli změna CSS nebo tvaru výstupu** — přegenerovalo by to všechny
  `.html` v repu a diff by se nedal přečíst
- přechod na jiný markdown engine nebo nová závislost
- jakýkoli zásah mimo „Dotčené soubory"
- nález, že `--all` sahá i jinam, než by měl (zapiš, neopravuj — je to změna
  chování nástroje, který právě běží nad celým repem)

## Kontext pro agenta

- Testy: `python -m unittest discover -s tests -v`, stdlib `unittest`, **žádný
  pytest**. Vlastní `tempfile` fixture, úklid po sobě.
- `md2html.py` je jediný nástroj se **závislostí** (`markdown`) — je
  nainstalovaná, importuj normálně.
- `ROOT` v modulu ukazuje na kořen projektu. Testy `--all` pouštěj tak, aby na
  `ROOT` nesáhly (monkeypatch `md2html.ROOT` na `tempfile` adresář).
- Nález v cizím kódu se **neopravuje**, zapisuje se do Logu. U testu, který
  dokumentuje vadu, použij `@unittest.expectedFailure` s komentářem — výjimkou
  je bod #8, kde je oprava součástí zadání.
- Konvence: ke každému `.md` v repu patří `.html`; generuje se právě tímhle
  nástrojem. Přegenerování před commitem dělá orchestrátor, ne ty.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-28 | ready | brief založen orchestrátorem |
| 2026-07-28 | running | `tests/test_md2html.py` založen — 27 nových testů, sada 454 → 481, lint rc 0. `git status --porcelain` po celém běhu sady hlásí jen soubory, které jsem vědomě měnil (žádný `.html` v repu se nesáhl). |
| 2026-07-28 | running | Jediná změna `md2html.py` je bod #8: `main()` vrací `int` (1 při chybějícím souboru), `__main__` volá `sys.exit(main())`. Text výstupu, CSS ani `TEMPLATE` se nesáhly — `--all` na repu vyprodukoval bajtově shodné `.html`. Původní chování: chybějící soubor tracebackem nepadal, ale končil nulou; to bylo to, co bylo potřeba zafixovat. |
| 2026-07-28 | running | **NÁLEZ #4 (neopraveno, eskalace):** `markdown.markdown()` pouští surové HTML skrz — `<script>alert(1)</script>` ve zdrojovém `.md` skončí ve výstupu jako živý tag. Zbytek #4 platí (text mimo markdown i titulek/patička se escapují). Test `test_04_script_v_markdownu_se_nedostane_jako_zivy_tag` je `@unittest.expectedFailure`. Oprava (např. rozšíření `EXT`, sanitizace) mění tvar výstupu → přegenerovala by všechny `.html` v repu, tedy T3. Bod #4 nechávám nezaškrtnutý. |
| 2026-07-28 | running | **NÁLEZ #9 (neopraveno, eskalace):** filtr v `--all` zná jen `.git` (`if ".git" not in p.parts`), `__pycache__` nepřeskakuje. Praktická škoda je nulová (`.md` se v `__pycache__` nevyskytne), ale neodpovídá to zadání. Test `test_09_all_preskakuje_pycache` je `@unittest.expectedFailure`; přeskakování `.git` ověřeno a funguje. Rozšíření filtru je změna chování nástroje běžícího nad celým repem → T3. Bod #9 nechávám nezaškrtnutý. |
| 2026-07-28 | running | Poznámka pro orchestrátora: `chips/18-md2html-testy.html` je po zápisu Logu neaktuální — přegenerování (`md2html.py --all`) je podle briefu na orchestrátorovi, do commitu chipu jsem ho nedal. Commitnuty jsou jen `tools/md2html.py` a `tests/test_md2html.py` (+ tenhle brief). |
| 2026-09-24 | merged | Orchestrátor: #4 a #9 dotáhl chip 20 (escape surového HTML, `IGNOROVANE_ADRESARE` s `__pycache__`), `expectedFailure` u obou testů je pryč a testy jsou zelené — odškrtnuto dodatečně, ať přehled neukazuje 8/10 u hotového chipu. |
