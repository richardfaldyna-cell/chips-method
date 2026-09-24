---
chip: 13
nazev: hook-extrakce
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-13/hook-extrakce
worktree: ../CHIPS-chip-13
---

# CHIP 13 — hook čte větev a repo ze špatného místa příkazu

První polovina rozřezaného chipu 10 (čtyři díry v hooku z externího code
review). Tenhle chip řeší **čtení vstupu**: z jakého místa složeného příkazu
hook bere název větve a cílový repozitář. Druhá polovina (kdy zamítnout) je
chip 14, který na tenhle navazuje.

Obě díry jsou v prostoru složených příkazů (`&&`, `;`), který testy nepokrývaly.

## Issues

- [x] #1 — **Hook bere PRVNÍ chip token v příkazu, ne argument merge**
      (`VETEV.search(prikaz)`, ř. ~106). `git branch -d ai/chip-04/x && git
      merge ai/chip-05/y` ověří bránu chipu 04 a pustí merge chipu 05.
      Oprav: větev se musí extrahovat z argumentu **za `merge`** — regex
      kotvený na `\bmerge\b` s přeskočením přepínačů (`--no-ff`, `--squash`,
      `-m "…"` a spol.), ne `search` přes celý řetězec.
- [x] #2 — **`cilove_repo()` bere první `git -C`/`cd` kdekoli v příkazu**
      (ř. ~51), i když patří jinému git volání než samotnému merge; relativní
      cesty navíc resolvuje proti cwd hook procesu místo session cwd z payloadu.
      Oprav obojí: `git -C` hledat jen v té části příkazu, která obsahuje
      merge; relativní cesty resolvovat proti `data["cwd"]`.
- [x] #3 — regresní testy na oba scénáře; každý musí na PŮVODNÍ verzi hooku
      selhat (ověř podstrčením staré verze, hlášky zapiš do Logu)
- [x] #4 — stávající testy (`TestHook`, parity test) musí dál procházet;
      co se změnou rozbije právem, uprav s komentářem proč

## Dotčené soubory  ⚠️ NÁROK

```
tools/hook_chip_gate.py
tests/test_chip_gate.py
```

Nesahej na `chip_gate.py` (parity test s ním musí dál platit — když potřebuješ
změnit sdílené jádro vzoru, zapiš do Logu a vyřeš to jen na straně hooku),
ani na `chip_lint.py`, `chip_common.py`, `chip_slice.py`, `chip_run.py`.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] scénář z #1 (`branch -d` chipu A + `merge` chipu B v jednom příkazu)
      ověřuje bránu chipu B — pokryto testem
- [x] `git -C` patřící jinému volání než merge se ignoruje — test
- [x] relativní cesta se resolvuje proti `cwd` z payloadu, ne proti cwd
      procesu — test
- [x] oba nové testy na původní verzi hooku selžou (doloženo v Logu)
- [x] pouze standardní knihovna

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

- změna `chip_gate.py`, `chip_lint.py`, `chip_common.py`
- **oslabení hooku**: kdyby oprava vyžadovala, aby hook v jiném případě mlčel
  tam, kde dnes blokuje — zastav se a zapiš do Logu
- nová závislost mimo stdlib
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- Hook čte JSON na stdin (`tool_input.command`, `cwd`), výstup je buď nic
  (povoleno) nebo JSON s `permissionDecision: deny`. Vzor volání s podstrčeným
  stdin je v `tests/test_chip_gate.py`, třída `TestHook`.
- Bias projektu: **raději zamítnout navíc než pustit červený merge.** Falešný
  poplach stojí uživatele vysvětlení; propuštěný červený merge stojí důvěru
  v celou bránu.
- Pozor na parity test `test_hook_a_brana_poznaji_stejne_vetve` — hlídá shodu
  vzoru s `chip_gate.VETEV_CHIP`. Když změníš způsob extrakce (kotvení na
  merge), parity test se možná musí přeformulovat: porovnávej rozpoznání
  *názvu větve*, ne celé komandliny. Zapiš do Logu, jak jsi to vyřešil.
- Rozsah čísla chipu ve vzoru je `(\d+)` — **neměň ho na `\w+`**, jinak by
  `ai/chip-10a/…` matchovalo jako chip 10. Číslo je číslo.
- Regresní důkaz: původní verzi vytáhni `git show HEAD:tools/hook_chip_gate.py`
  do dočasného souboru a **zaregistruj do `sys.modules` před importem testů**
  (`sys.path.insert` nestačí — načte se opravená verze a důkaz je bezcenný).
- Konvence: hlášky česky, docstringy vysvětlují proč, dvě mezery odsazení.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-27 | ready | první polovina rozřezaného chipu 10 (nálezy #1 a #2) |
| 2026-07-27 | ready | #1: příkaz se dělí na segmenty (`&&`, `||`, `;`, `|`, newline) a v segmentu se hledá `merge` jako CELÝ token po tokenu s `git` — ne podřetězcem, jinak by `git -C /x/merge/y status` vypadalo jako merge. Nová `cisla_chipu()` bere jen POZIČNÍ argumenty za `merge`: `pozicni()` přeskakuje přepínače, u hodnotových (`-m/--message`, `-F/--file`, `-s/--strategy`, `-X/--strategy-option`, `--into-name`) i jejich token; `-S`/`--gpg-sign`/`--log` berou hodnotu jen připojenou, takže jsou v seznamu schválně NEjsou. Neznámý `-x` = přepínač bez hodnoty (radši token navíc k prozkoumání než přeskočená větev). `tokeny()` drží uvozovaný celek pohromadě kvůli `-m "merge ai/chip-01/x"`. Octopus merge (`git merge A B`) ověřuje bránu KAŽDÉ chip větve, zamítá na první červené — dřív prošla druhá. Vzor `VETEV` zůstal beze změny včetně `(\d+)`. |
| 2026-07-27 | ready | #2: `cilove_repo()` bere `git -C` jen ze segmentu, který merge doopravdy spouští; `cd` ze segmentů PŘED merge (platí i pro následující příkazy) a skládá se postupně, takže `cd a && cd b` sedí. Relativní cesty jdou přes `slozit()` proti `data["cwd"]` z payloadu, ne proti cwd hook procesu; když výsledek není adresář, drží se dosavadní základ (špatný odhad repa je horší než žádný). |
| 2026-07-27 | ready | #4 parity test: přeformulovávat se NEMUSEL a `chip_gate.py` zůstal nedotčený — vzor `VETEV` se neměnil, změnilo se jen MÍSTO, na které se pouští. Test jsem naopak rozšířil o druhý průchod přes `hook.cisla_chipu(f"git merge {v}")`, aby hlídal i novou cestu, ne jen shodu regexů. Odsazení: brief mluví o dvou mezerách, ale celý `tools/` je 4 mezery (PEP 8) — držel jsem se souboru, míchání by bylo horší. Žádný stávající test se změnou nerozbil (0 úprav existujících testů). |
| 2026-07-27 | ready | #3 regresní důkaz (`git show HEAD~1:tools/hook_chip_gate.py` + registrace do `sys.modules` před importem testů, ověřeno assertem `t.hook is mod`): 18/18 nových testů na PŮVODNÍ verzi selhalo (10 FAIL + 16 ERROR, subTesty). Hlášky hooku: „hook mlčel — ověřil bránu chipu 01 místo mergovaného 02 a pustil merge s červenou bránou"; „hook vzal chip ze zprávy `-m` a pustil červený merge"; „hook ověřil jen první větev octopus merge"; „hook hledal repo podle cizího `git -C` a mlčel"; „hook resolvoval relativní `git -C repo` proti cwd procesu, repo nenašel a červený merge pustil". `cilove_repo`: „WindowsPath('…/jine') != WindowsPath('…/repo')" (cizí `-C`) a „WindowsPath('…/tmpXXXX') != WindowsPath('…/tmpXXXX/repo')" (relativní cesta). `TestCislaChipu` + parity: „AttributeError: module 'hook_chip_gate' has no attribute 'cisla_chipu'". Na opravené verzi 18/18 OK. |
| 2026-07-27 | ready | Brána: `python -m unittest discover -s tests -v` → **383 testů, 0 selhání** (před chipem 366 → +17 testů, parity test rozšířen o subTesty). `python tools/chip_lint.py` → rc 0, 0 chyb, 4 varování (3 placeholdery v briefech 08/09/12 existovaly už před chipem + informace, že chip 14 čeká na 13). Jen stdlib (`re`, `json`, `os`, `sys`, `pathlib`). Žádný T3: `chip_gate.py` ani ostatní cizí soubory jsem nesáhl, hook nikde nezmlkl tam, kde dřív blokoval — jen naopak. `.html` k briefu nepřegenerováno (soubor mimo NÁROK, `md2html.py --all` sahá na celé repo) — dělá orchestrátor po merge. |
