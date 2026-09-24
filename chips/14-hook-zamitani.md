---
chip: 14
nazev: hook-zamitani
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na: 13
repo: ..
vetev: ai/chip-14/hook-zamitani
worktree: ../CHIPS-chip-14
---

# CHIP 14 — hook radši ověří něco jiného, než by zamítl

Druhá polovina rozřezaného chipu 10. Zatímco chip 13 řeší, **odkud** hook bere
vstup, tenhle řeší, **kdy má říct ne**. Obě zbylé díry mají stejný tvar: hook
narazí na stav, ve kterém nemůže ověřit to, co se merguje — a místo zamítnutí
ověří něco jiného a vrátí zelenou.

**Závisí na chipu 13** (týž soubor). Větev se zakládá z jeho výsledku, ne
z masteru — před založením worktree ověř, že chip 13 je `merged`.

## Issues

- [x] #1 — **Fallback brány na hlavní strom** (`kde_overit`, ř. ~179): když
      worktree chipu neexistuje, brána se spustí v hlavním stromě — který
      změny chipu z definice nemá — a vrátí zelenou nad starým kódem.
      Docstring to dnes hájí jako „lepší ověřit něco než nic"; to je přesně
      obráceně. Oprav: bez worktree **zamítnout** s vysvětlením („worktree
      chipu neexistuje — bránu není kde ověřit; obnov worktree, nebo merguj
      vědomě a vysvětli to uživateli"), ne tiše ověřit jiný strom.
- [x] #2 — **Brána běží nad working tree, merge bere committed tip**
      (`main()`, ř. ~245). Necommitnuté změny ve worktree znamenají verdikt o jiném
      stavu, než jaký se merguje — a to v obou směrech: zelená nad
      rozdělanou opravou, která není v commitu, i červená nad rozbitým
      experimentem, který se nemerguje. Oprav: před spuštěním brány
      zkontroluj `git -C <worktree> status --porcelain`; když je strom
      špinavý, zamítni s hláškou „ve worktree jsou necommitnuté změny —
      brána by ověřovala jiný stav, než jaký se merguje".
- [x] #3 — regresní testy na oba scénáře; každý musí na verzi PŘED tímhle
      chipem selhat (podstrč starou verzi, hlášky do Logu)
- [x] #4 — stávající testy (`TestHook`, parity test, testy z chipu 13) musí
      dál procházet; co se změnou rozbije právem, uprav s komentářem proč

## Dotčené soubory  ⚠️ NÁROK

```
tools/hook_chip_gate.py
tests/test_chip_gate.py
```

Nesahej na `chip_gate.py` (parity test s ním musí dál platit), ani na
`chip_lint.py`, `chip_common.py`, `chip_slice.py`, `chip_run.py`.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] chybějící worktree končí zamítnutím, ne zelenou — test
- [x] špinavý worktree končí zamítnutím — test
- [x] hláška zamítnutí uživateli říká, **co má udělat**, ne jen co je špatně
- [x] oba nové testy na předchozí verzi hooku selžou (doloženo v Logu)
- [x] pouze standardní knihovna

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

- změna `chip_gate.py`, `chip_lint.py`, `chip_common.py`
- kdyby zamítnutí u #1 nebo #2 blokovalo i legitimní běžný merge (falešný
  poplach v denním provozu) — zastav se a zapiš, neřeš to změkčením
- nová závislost mimo stdlib
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- Hook čte JSON na stdin (`tool_input.command`, `cwd`), výstup je buď nic
  (povoleno) nebo JSON s `permissionDecision: deny`. Vzor volání s podstrčeným
  stdin je v `tests/test_chip_gate.py`, třída `TestHook`.
- Bias projektu: **raději zamítnout navíc než pustit červený merge.** U obou
  nálezů je zamítnutí správná odpověď, ne heuristika — nesnaž se uhodnout,
  jestli to „asi bude v pořádku".
- `kde_overit()` má dnes návratový typ `Path` a nikdy neselže. Po opravě musí
  umět říct „nemám kde" — zvol tvar, který volající nemůže omylem ignorovat
  (výjimka nebo `None` s povinným ošetřením), ne prázdnou cestu.
- Rozlišuj **worktree hlavního stromu**: když je `repo:` chipu totožné
  s worktree, kontrola špinavosti by zamítala běžný stav vývoje. Ověř si na
  reálném rozložení, co se stane, a případ zapiš do Logu.
- Regresní důkaz: předchozí verzi vytáhni `git show HEAD:tools/hook_chip_gate.py`
  do dočasného souboru a **zaregistruj do `sys.modules` před importem testů**
  (`sys.path.insert` nestačí — načte se opravená verze a důkaz je bezcenný).
  Ověř assertem, že testovaný modul je opravdu ta podstrčená kopie.
- **Chip 13 hook právě přepsal**: přibyly `segmenty()`, `tokeny()`,
  `merge_tokeny()`, `pozicni()`, `cisla_chipu()`, `slozit()`; `main()` teď
  prochází VÍCE chip větví (octopus merge) v cyklu. Tvoje zamítnutí se musí
  chovat správně i uvnitř toho cyklu — zamítni na první větvi, která nejde
  ověřit, ne až po projití všech.
- Konvence: hlášky česky, docstringy vysvětlují proč. Odsazení kódu podle
  souboru (`tools/` je 4 mezery, PEP 8); dvě mezery se týkají odsazení
  vypisovaných hlášek, ne Pythonu.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-27 | ready | druhá polovina rozřezaného chipu 10 (nálezy #3 a #4) |
| 2026-07-27 | ready | #1: `kde_overit()` už nemá fallback na hlavní strom — vyhazuje novou `NeniKdeOverit`. Zvolena VÝJIMKA, ne `None`: `None` by šlo přehlédnout stejně snadno jako dosavadní tichý fallback (chyba by praskla až hluboko v bráně), výjimka projde skrz a merge zamítne. Zamítá se ve třech případech: worktree neexistuje, `worktree:` v briefu je prázdné, a `worktree:` ukazuje na strom, do kterého se merguje (táž falešná zelená, jen zapsaná v briefu — brána by tam ověřila stav PŘED mergem). Hláška vždy říká, co dělat: obnov worktree `python tools/chip_run.py NN` a merguj až po zelené, nebo merguj vědomě mimo hook a vysvětli uživateli, co tím obcházíš. Provozní důsledek: **úklid worktree (`--uklid`) patří AŽ po mergi** — je to v hlášce. |
| 2026-07-27 | ready | #2: nová `necommitnute(strom)` = `git status --porcelain` ve stromě CHIPU; neprázdný výstup → zamítnutí s výpisem prvních 10 položek a pokynem „commitni (nebo zahoď) a merguj znovu — merge bere commitnutý tip větve, ne working tree". Netrackované soubory se počítají (co není v commitu, to se nemerguje), ignorované ne — `__pycache__/` a `*.pyc` jsou v `.gitignore`, takže běh brány sám strom nešpiní (test `test_ignorovany_soubor_strom_nespini`). Když stav zjistit nejde (adresář není git strom, `git` chybí), zamítá se taky — nevědět, co ve stromě je, se pro potřeby brány rovná nemít ho. `import subprocess` je až uvnitř funkce, hook běží před každým příkazem shellu. Zamítá se HNED na první neověřitelné větvi octopus merge; testy `test_octopus_zamita_hned_na_prvni_neoveritelne_vetvi` a `test_brana_se_nad_spinavym_stromem_vubec_nespusti` to dokazují stopou (brána druhé/té větve se vůbec nespustí). |
| 2026-07-27 | ready | **Past „hlavní strom je sám worktree a bývá špinavý" — ověřeno na reálném rozložení.** `git worktree list` ve workspace: hlavní strom `CHIPS` (master) + `CHIPS-chip-14`; žádný z 13 briefů nemá `worktree:` mířící na hlavní strom (všechny `../CHIPS-chip-NN`), takže žádný legitimní merge se neblokuje. Kontrola špinavosti se pouští **na strom chipu (`strom`), nikdy na cíl merge (`koren`)** — rozeditované soubory v `CHIPS` při běžné práci merge neblokují; hlídá test `test_spinavy_hlavni_strom_merge_neblokuje` (repo úmyslně špinavé, worktree čisté → hook mlčí). Kdyby `worktree:` přesto na hlavní strom ukazoval, rozhodne se to DŘÍV v `kde_overit()` (viz #1) a uživatel dostane hlášku o špatném `worktree:`, ne matoucí „ve worktree jsou necommitnuté změny". Žádný T3: falešný poplach v denním provozu nevzniká. |
| 2026-07-27 | ready | Ověřeno na živém rozložení (`echo … \| python tools/hook_chip_gate.py`): ve workspace po chipech 01–09 zůstaly ADRESÁŘE `CHIPS-chip-01..09` bez `.git` — `git worktree remove` smaže `.git`, ale adresář se zbytky ne. `is_dir()` na ně tedy sedne a chybějící worktree by se nepoznal; odhalí to až `git status` (exit 128). Zamítnutí je i tady správně (bránu není kde ověřit) a hláška to říká přímo: „Není to git strom chipu — typicky zbytek adresáře po úklidu worktree." Společný závěr hlášek „NEJDE OVĚŘIT" je jedna věta v `main()`: `python tools/chip_run.py NN` + „úklid `--uklid` patří AŽ po mergi". |
| 2026-07-27 | ready | #3 regresní důkaz (`git show HEAD~1:tools/hook_chip_gate.py` → dočasný soubor, registrace do `sys.modules["hook_chip_gate"]` PŘED importem testů, ověřeno assertem `t.hook is mod` + `not hasattr(mod, "necommitnute")`): **16 z 18 nových testů na PŮVODNÍ verzi selhalo** (8 FAIL + 8 ERROR). Hlášky: 5× „hook MLČEL — merge by prošel bez ověření" (chybějící worktree, hláška co dělat, `worktree:` na cílový strom, octopus, špinavý worktree); „brána běžela nad stromem, který se nemerguje"; „'necommitnuté změny' not found in 'CHIPS brána chipu 01 (pokus) NEPROŠLA…'" (červená brána nad nemergovaným experimentem — verdikt o cizím stavu); 5× „AttributeError: module 'hook_chip_gate' has no attribute 'necommitnute'" a 3× „…has no attribute 'NeniKdeOverit'". Zelené zůstaly právem jen dva kontrolní testy, které ověřují, že se zamítat NESMÍ: `test_cisty_worktree_se_zelenou_branou_projde` a `test_spinavy_hlavni_strom_merge_neblokuje`. Na opravené verzi 18/18 OK. |
| 2026-07-27 | ready | #4 stávající testy: rozbil se právem jediný — `test_bez_worktree_spadne_na_repo` („lepší ověřit něco než nic") je přepsaný na `test_bez_worktree_selze` s komentářem, proč se obrátil. Fixture `Zaklad` nově zakládá **skutečné git stromy** (`git init`, vzor převzatý z `test_chip_review.py` včetně skipu, když `git` není na PATH) — hook stav worktree zjišťuje přes `git`, nad pouhým adresářem by zamítal; `TestHook.setUp` proto chipům 01 a 02 chystá čistý worktree. `zavolej_hook()` vytažen na úroveň modulu, aby ho mohla použít i nová třída. `chip_gate.py` nedotčen, parity test beze změny. |
| 2026-07-27 | ready | Brána: `python -m unittest discover -s tests -v` → **413 testů, 0 selhání** (před chipem 396 → +17). `python tools/chip_lint.py` → rc 0, 0 chyb, 3 varování (placeholdery v briefech 08/09/12, existovaly už před chipem). Jen stdlib (`json`, `os`, `re`, `sys`, `pathlib`, `subprocess`). Žádný T3. `.html` k briefu nepřegenerováno (`md2html.py --all` sahá mimo NÁROK) — dělá orchestrátor po merge. |
