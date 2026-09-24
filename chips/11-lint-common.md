---
chip: 11
nazev: lint-common
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-11/lint-common
worktree: ../CHIPS-chip-11
---

# CHIP 11 — čtyři nálezy v lintu a parseru

Externí code review potvrdil tři vady v `chip_lint.py` a jednu v
`chip_common.py`. Dvě z nich přímo zasahují reálný firemní projekt (ERP-CHIPS).

## Issues

- [x] #1 — **`prekryv()` mine kolizi adresář × glob bez textového prefixu**
      (ř. ~233): `prekryv('src', '*.py')` vrací False, přestože
      `fnmatch('src/foo.py', '*.py')` je True. Literál bez zástupných znaků,
      který je *adresářem nároku*, musí kolidovat s globem, jenž může
      matchovat cestu uvnitř něj. Oprav v `_prunik`/`prekryv`: literální
      cesta bez vzoru se má porovnávat i jako prefix možných shod globů
      (glob `*.py` ↔ adresář `src` = kolize, protože `src/x.py` vyhoví oběma).
      Bias: raději kolize navíc než přehlédnutá.
- [x] #2 — **Existence se ověřuje proti repu, kde leží briefy, ne proti
      `repo:`** (`strom_ke_kontrole`, ř. ~93). Layout ERP-CHIPS: briefy
      v repu ERP-CHIPS, cíl `erp` — lint hledá nároky ve špatném
      repozitáři. Oprav: `strom_ke_kontrole` má přednostně vracet strom
      briefu JEN tehdy, když je to **týž repozitář** jako `repo:` (worktree
      pozná přes `git rev-parse --git-common-dir`, nebo jednodušeji: strom
      briefu použij jen když `repo:` je předkem/potomkem cesty briefu);
      jinak platí `repo:` z frontmatteru.
- [x] #3 — **Absolutní glob shodí lint tracebackem** (`naroky()`, ř. ~252):
      `repo.glob('C:/data/*.xlsx')` vyhodí NotImplementedError dřív, než
      lint cokoli vypíše. Oprav: cesty, které jsou absolutní nebo obsahují
      `..`, do `repo.glob()` vůbec neposílat (validace v `zkontroluj_cesty`
      je hlásí, ale `naroky()` běží i mimo ni).
- [x] #4 — **Cesta s ' #' ve jméně se tiše usekne** (`chip_common.
      soubory_detail`, ř. ~105): `docs/plan #1.md` se zkrátí na `docs/plan`.
      Rozhodnutí: poznámka se odděluje **dvěma a více mezerami + #** (dnes
      stačí jedna mezera). Uprav regex `KOMENTAR` na `\s{2,}#\s*(.*)$`,
      zdokumentuj v šabloně... POZOR: šablonu nevlastníš — jen zapiš do Logu,
      že komentář v TEMPLATE.md („`src/nove.py    # nový`" už používá 4 mezery,
      takže je kompatibilní) a případnou úpravu textu nech orchestrátorovi.
- [x] #5 — testy na všechny čtyři opravy; každý musí na PŮVODNÍ verzi selhat
      (doloženo v Logu s hláškami)
- [x] #6 — celá stávající sada projde; testy, které fixovaly staré chování,
      uprav s komentářem proč

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_lint.py
tools/chip_common.py
tests/test_chip_lint.py
tests/test_chip_common.py
```

Nesahej na `hook_chip_gate.py`, `chip_gate.py` (chip 10), `chip_slice.py`,
`chip_run.py` (chip 12), ani na `chip_status.py`, `chip_review.py`,
`chip_new.py` a jejich testy — importují `chip_common`, takže **z veřejného
API nic neodstraňuj ani nepřejmenovávej**, jen oprav chování.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] `prekryv('src', '*.py')` je True — pokryto testem
- [x] lint nad briefy ERP-CHIPS (`--dir <workspace>/ERP-CHIPS/chips`)
      dál vrací 0 chyb — spusť to doopravdy, výstup do Logu
- [x] absolutní glob v nároku = hláška, ne traceback — test
- [x] `docs/plan #1.md` se už neusekne; `# nový` (2+ mezery) dál funguje — testy
- [x] pouze standardní knihovna

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

- odstranění/přejmenování čehokoli z veřejného API `chip_common` (má 6 konzumentů)
- změna `TEMPLATE.md` (text komentáře o `# nový` — jen zapiš do Logu)
- oslabení lintu: nic, co je dnes chyba, se nesmí stát varováním
- nová závislost mimo stdlib
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- `prekryv`/`_prunik`/`_tokeny` jsou z chipu 05 — memoizovaná rekurze nad
  tokeny HVEZDA/JEDEN/literál. `*` záměrně matchuje i přes `/` (fnmatch styl).
  U #1 dej pozor, ať neuděláš kolizi ze VŠEHO: `src` × `tests/*.py` musí
  zůstat False. Adresářová sémantika platí jen směrem „glob může vyhovět
  cestě UVNITŘ literálu".
- U #2 pozor na testy chipu 05 (`TestStromKeKontrole`) — chování „brief ve
  worktree téhož repa → kontroluj worktree" musí zůstat; mění se jen případ
  „brief v CIZÍM repu".
- Regresní důkaz: `git show HEAD:tools/<soubor>` + `sys.modules` před importem
  testů; vzor v Logu chipů 05–07 v `_pilot-repo/chips/`.
- Konvence: hlášky česky, `X` chyba / `!` varování.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-27 | ready | založeno z code review (nálezy 5–7 + 9) |
| 2026-07-27 | running | **#1** `prekryv()`: literál bez zástupných znaků se proti vzoru porovnává i jako prefix jeho možných shod (`_prunik(_tokeny(lit + "/*"), vzor)`, v obou pořadích) — `src` × `*.py` je kolize, protože `src/x.py` vyhoví oběma. Adresářová sémantika platí JEN směrem „vzor umí matchnout cestu uvnitř literálu": `src` × `tests/*.py`, `docs` × `src/*.md` i `src/a.py` × `src/b*` zůstávají False (test `test_prekryv_adresar_a_glob_jinam_zustava_disjunktni`). |
| 2026-07-27 | running | **#2** `strom_ke_kontrole()`: strom briefu přebíjí `repo:` jen u TÉHOŽ repozitáře. Nová privátní `_git_spolecny_adresar()` čte `.git` (adresář = hlavní strom, soubor `gitdir: …/.git/worktrees/<jméno>` = worktree) a odřízne `worktrees/<jméno>` — ekvivalent `git rev-parse --git-common-dir` bez subprocesu. Navíc se vyžaduje, aby `repo:` byl kořenem svého stromu. Chování chipu 05 (worktree × hlavní strom) beze změny, hlídá `TestStromKeKontrole`. |
| 2026-07-27 | running | **#3** `naroky()`: cesta, která je absolutní nebo obsahuje `..`, se do `repo.glob()` neposílá vůbec (kontrola přes `absolutni()` + `PurePosixPath(...).parts`). Nárok se dál vrací jako sám sebe, takže se pořád účastní kolizní matice; tvar hlásí `zkontroluj_cesty` jako chybu — brána nikde nezměkčena. |
| 2026-07-27 | running | **#4** `chip_common.KOMENTAR` = `\s{2,}#\s*(.*)$` (dřív `\s+#`). **TEMPLATE.md nesahám (T3):** řádek `src/nove.py    # nový` v šabloně používá 4 mezery, takže je s novým pravidlem kompatibilní a šablona nepotřebuje žádnou úpravu chování. Doporučení pro orchestrátora: do textu šablony (a do `docs/metodika.md`) dopsat větu „poznámku odděl od cesty aspoň dvěma mezerami" — jedna mezera je nově součást jména souboru. |
| 2026-07-27 | running | **#5 — regresní důkaz.** Původní `tools/chip_lint.py` a `tools/chip_common.py` z `a827840` (`git show`) PŘEDregistrovány do `sys.modules` před importem testů (`sys.path.insert` nestačí — testy si `tools/` vkládají na `sys.path[0]` samy; skript navíc `assert`uje `chip_lint.__file__` na původní kopii). Výsledky: **#1** `FAIL test_prekryv_adresar_a_glob_bez_textoveho_prefixu` → `AssertionError: False is not true` (`prekryv('src','*.py')`) a `FAIL test_kolize_adresar_versus_glob_bez_textoveho_prefixu` → `AssertionError: 0 != 1 : zkontrolováno 2 chipů (2 aktivních) / OK — 0 chyb` (brána kolizi mlčky pustila). **#2** celá `TestStromKeKontroleCiziRepo` = **4 selhání ze 4**, klíčové `AssertionError: …/briefy != …/briefy/projekt` a `('src/z_cile.py','src/*.py') not found in [('src/*.py','src/*.py'), ('src/z_briefu.py','src/*.py')]` — nároky se ověřovaly proti repu s briefy. **#3** 3 testy = **3 ERROR**, všechny `NotImplementedError: Non-relative patterns are unsupported` z `pathlib/__init__.py:312` přes `naroky()` ř. 253, u `test_absolutni_vzor_je_hlaska_ne_traceback` až z `main()` ř. 337 — traceback dřív, než lint cokoli vypsal. **#4** 2 selhání, `AssertionError: [('docs/plan', False)] != [('docs/plan #1.md', False)]` — cesta se tiše usekla. Testy `test_prekryv_adresar_a_glob_jinam_zustava_disjunktni` a `test_dva_bile_znaky_pred_mrizkou_jsou_poznamka` na původní verzi schválně PROŠLY: to jsou pojistky proti přestřelení opravy, ne důkazy nálezu. |
| 2026-07-27 | running | **#6** Celá sada: `python -m unittest discover -s tests -v` → `Ran 373 tests … OK`, 0 selhání, 0 expected failures (z 360 před chipem, +13 metod). Upraven jediný existující test: v `test_prekryv_vzor_a_konkretni_cesta` nahrazeno `assertFalse(prekryv('src/*.py','src/data.json'))` za `assertFalse(prekryv('src/*.py','tests/data.json'))` — s adresářovou sémantikou z #1 (a `*` matchujícím i přes `/`) je `src/data.json` × `src/*.py` záměrná kolize navíc; důvod je zapsaný komentářem přímo v testu. Nic z veřejného API `chip_common` neodstraněno ani nepřejmenováno. Jen stdlib. |
| 2026-07-27 | running | **DoD — lint nad ERP-CHIPS** spuštěn doopravdy (jen čtení): `python tools/chip_lint.py --dir <workspace>/ERP-CHIPS/chips` → `zkontrolováno 11 chipů (0 aktivních)` / `OK — 0 chyb, 0 varování`, exit 0. Poctivá poznámka: všech 11 briefů je `draft`, takže kontrola existence cest se na ně zatím vůbec nepouští — samotné „0 chyb" tedy #2 nedokazuje. Přímé měření na reálném layoutu ano: `strom_ke_kontrole()` nad `00-kostra-repa.md` vrací po opravě `…/ERP-CHIPS/erp` (cílový repo z `repo:`), zatímco původní verze vracela `…/ERP-CHIPS` (repo s briefy). Jakmile první chip přejde na `ready`, opravená verze hledá nároky ve správném repozitáři. |
| 2026-07-27 | gated | **Brána zelená.** `python -m unittest discover -s tests -v` → `Ran 373 tests … OK`. `python tools/chip_lint.py` → `OK — 0 chyb, 3 varování`, exit 0; všechna tři varování jsou zděděné placeholdery v cizích briefech (`08`, `09`, `12`), na které nemám nárok. NEMERGOVÁNO — merge dělá orchestrátor. |
