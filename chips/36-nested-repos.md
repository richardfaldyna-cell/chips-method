---
chip: 36
nazev: nested-repos
stav: merged
# `stav:` přepíná ORCHESTRÁTOR, ne agent — mandát agenta je Log a checkboxy.
zavisi_na: 35
repo: ..
greenfield: ne
vetev: ai/chip-36/nested-repos
worktree: ../CHIPS-chip-36
---

# CHIP 36 — nested repos: nástroje nad briefy pro VÍC repozitářů a nad Windows shellem

První nasazení na projekt, kde jeden adresář s briefy (`--dir`) řídí 18 chipů přes
13 různých (vnořených) repozitářů, odhalilo pět vad nástrojů (2026-10-25, session
nad domácím infrastrukturním projektem). Společný jmenovatel: nástroje mlčky
předpokládají jedno repo, jeden shell a čistý pracovní strom. Žádná z vad není
metodická — pravidla jsou napsaná správně, nástroj je porušoval (týž tvar jako
ve vlně 6).

## Issues

- [x] #1 — `chip_lint.py` porovnává nároky **ukotvené k `repo:`** (absolutní cesta
      repa + nárok), ne holé relativní cesty: `README.md` chipu v repu A a
      `README.md` chipu v repu B nekolidují; `sub/README.md` v rodičovském repu ×
      `README.md` ve vnořeném repu `sub/` kolidují dál (týž soubor). Hlášení
      zůstává v nárocích z briefu, u dvou různých rep s poznámkou
- [x] #2 — `chip_gate.py`: **tag ``` bloku určuje shell**. `bash`/`sh`/`shell` →
      bash (na Windows Git Bash vedle `git.exe`, přepsatelné `CHIPS_BASH`; WSL
      `System32\bash.exe` se nebere), `cmd`/`bat`/`batch` → `cmd.exe` (jen
      Windows), bez tagu nebo jiný tag → systémový shell jako dosud. Bash
      nenalezen → příkaz skončí 127 s hláškou, co nainstalovat nebo jak blok
      otagovat — žádný tichý fallback na cmd. `prikazy()` zůstává (chip_review ho
      počítá), přibývá `prikazy_se_shellem()`
- [x] #3 — `chip_review.py` bez `--commit` hodnotí **celou práci chipu**, ne jen
      poslední commit: rozsah `<merge-base>..HEAD`, kde základ je první z: HEAD
      hlavního stromu z `repo:` (když se liší od kontrolovaného stromu), `master`,
      `main`, `origin/HEAD`. Když HEAD hlavní větev je nebo základ nejde určit →
      `HEAD` jako dosud. Hlavička vypíše použitý rozsah a proč
- [x] #4 — `chip_lint.py` ověřuje existenci nároků **proti HEAD** (`git ls-tree -r
      HEAD`), ne proti pracovnímu stromu: `# nový` na souboru, který leží na disku
      jen netrackovaný, nevaruje; nárok bez `# nový` na soubor jen v pracovním
      stromu je chyba („worktree větví z HEAD, chip ho neuvidí — commitni, nebo
      označ `# nový`"). Mimo git nebo bez commitu platí dosavadní kontrola disku;
      vzory se dál rozbalují z disku
- [x] #5 — `chip_run.py` odmítne založit worktree, který by ležel **uvnitř jiného
      git stromu** (vnořené repo: `../X-chip-NN` padne do rodičovského repa jako
      netrackovaný adresář) i uvnitř vlastního repa; hláška říká, co napsat do
      `worktree:`. Kontrola až za `--uklid`, ten se nemění; `--dry-run` ji hlásí
      taky
- [x] #6 — testy ke každému bodu, každý tak, aby na dosavadním kódu padal (kolize
      dvou rep, cmd blok na Windows, dva commity na větvi chipu, netrackovaný
      `# nový`, worktree do rodičovského repa)
- [x] #7 — `docs/metodika.md` i `docs/methodology.md` (nárok relativní k `repo:`
      a týž soubor přes dvě repa; existence = HEAD; shell podle tagu; umístění
      worktree u vnořeného repa; review celé větve), poznámka u bloku brány
      v `chips/TEMPLATE.md`, README (CS i EN); `.html` přegenerovat

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_lint.py
tools/chip_gate.py
tools/chip_review.py
tools/chip_run.py
tests/test_chip_lint.py
tests/test_chip_gate.py
tests/test_chip_review.py
tests/test_chip_run.py
docs/metodika.md
docs/methodology.md
chips/TEMPLATE.md
README.md
README.cs.md
TODO.md
.github/workflows/tests.yml    # nový
```

## Definition of done

- [x] `python -m unittest discover -s tests` zelené, počet = výchozí stav + nové testy
- [x] lint nad fixture se dvěma repy a stejnojmenným `README.md` v obou nárocích
      hlásí 0 kolizí; `sub/README.md` v rodiči × `README.md` ve vnořeném `sub/`
      hlásí 1 kolizi
- [x] brána s blokem ```cmd a příkazem s `%CD%` na Windows projde; blok ```bash
      s `&&`/`$VAR` projde přes bash; bash nenalezen → exit 127, ne průchod
- [x] `chip_review.py NN` bez `--commit` nad větví chipu se dvěma commity vypíše
      soubory obou
- [x] lint: `# nový` na netrackovaném souboru → 0 varování; nárok bez `# nový` jen
      na disku → 1 chyba
- [x] `chip_run.py NN` s worktree uvnitř rodičovského git stromu → exit 1 a
      `git worktree add` se nespustí
- [x] strength test: každá oprava zvlášť vrácená zpět shodí aspoň jeden nový test
- [x] `python tools/chip_lint.py` exit 0 (i nad 36)

## Ověření (brána)

```bash
python -m unittest discover -s tests
python tools/chip_lint.py
python tools/chip_review.py --help
```

## Eskalace — co NEROZHODOVAT sám (T3)

- změna rozhodovací logiky hooku (co je merge, co je chip větev, kde se ověřuje)
- jakákoli cesta, kdy nenalezený shell nebo neurčitelný rozsah vede na průchod
  brány / vypuštění kontroly
- změna sémantiky `prekryv()` pro cesty v témže repu
- nová závislost
- soubor mimo „Dotčené soubory"

## Kontext pro agenta

- `chip_lint.git_koren()` a `_git_spolecny_adresar()` už umí poznat strom a jeho
  repo bez subprocesu — `chip_run` si je může půjčit (chip_review už z `chip_lint`
  importuje).
- `chip_review.zmeny()` bere `a..b` i `a...b` (obojí obsahuje `..`); `ref_konce()`
  vrací `HEAD`.
- Na stroji s Git for Windows leží bash v `<Git>/bin/bash.exe`;
  `shutil.which("bash")` může vrátit WSL launcher ze `System32`, který není
  použitelný.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-10-25 | ready | z pěti nálezů session nad projektem s 18 chipy ve 13 vnořených repech (Windows): falešné kolize mezi repy (176 chyb), bash syntaxe v bloku brány běžela pod cmd.exe, review hodnotil jen HEAD, `# nový` varoval u netrackovaného souboru, relativní worktree vnořeného repa spadl do rodiče |
| 2026-10-25 | gated | #1 `kotva()`/`ukotvi()`: kolize nad `<repo>/<nárok>`, přes dvě repa s poznámkou „týž soubor přes dvě repa"; #2 `shell_bloku()`, `bloky()`, `prikazy_se_shellem()`, `najdi_bash()` (CHIPS_BASH → `<Git>/bin/bash.exe` → PATH bez System32), `argv_shellu()`, `spust(..., shell=)`; bash nenalezen → 127 „bash nenalezen", cmd mimo Windows → 127; #3 `vychozi_rozsah()`: hlavní strom z `repo:` → master → main → origin/HEAD, hlavička `rozsah: … (merge-base s …)`, `--commit HEAD` = jen poslední commit; #4 `soubory_v_head()` (`git ls-tree -r -z`, jen kořen stromu, None = disk jako dřív) + `v_head()`, cache na běh lintu; nárok jen na disku → „ne v HEAD"; #5 `strom_nad()` v chip_run (půjčený `chip_lint.git_koren`), odmítá i vlastní repo a `--dry-run`, hláška navrhne `worktree:`. **Testy +58** (lint 21, gate 21, review 7, run 9). **Důkaz síly** ve vývojovém repu: nástroje odstashované → 52 z 58 nových testů červených, žádný starý. **Živě:** kopie 18 briefů nasazení přepnutá na ready: starý lint 176 kolizí, nový 0 falešných (10 skutečných překryvů stejnorepových dvojic); `chip_run --dry-run` nad vnořeným repem odmítne worktree do rodiče. |
| 2026-10-25 | merged | Ve vývojovém repu brána zelená (927 testů, lint 0), merge `--no-ff`, worktree uklizen. Review (nový výchozí rozsah merge-base..HEAD): 16 souborů, všechny v nároku. |
| 2026-10-25 | merged | **Port do veřejného repa `chips-method`.** Hlášky nástrojů i nové testy české (`KOLIZE`, `rozsah:`, „bash nenalezen", `# nový`, `--uklid`), metodika doplněna v obou jazycích. Navíc proti vývojové verzi: CI workflow `.github/workflows/tests.yml` (unittest + lint na ubuntu i windows), na který už mířil odznak vývojového README. 757 → 815 testů. |
