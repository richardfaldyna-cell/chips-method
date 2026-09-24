# Vlna 4 — přerušeno a dokončeno

**Datum:** 2026-07-27 · **Stav:** ✅ **dokončeno** — 10/10 nálezů opraveno,
4 chipy zmergovány, 366 → 413 testů. Průběh dokončení je na konci dokumentu;
zbytek je záznam přerušení, ponechaný kvůli poučení z něj.

Vlna 4 opravovala 10 nálezů z externího code review (workflow, 30 agentů,
adversariální verifikace). Všichni tři agenti skončili předčasně — **ne kvůli
kódu**, ale na limitech účtu.

## Co se stalo

| Chip | Příčina pádu | Uloženo |
|---|---|---|
| 10 hook-diry | překročen limit **16 000 výstupních tokenů** na jednu odpověď | nic — 0 změn |
| 11 lint-common | **session limit** účtu | commit `beb6a5f` na `ai/chip-11/lint-common` |
| 12 slice-run | **session limit** účtu | commit `7810e9d` na `ai/chip-12/slice-run` |

Hlavní strom `CHIPS` zůstal čistý a nedotčený — izolace zafungovala i při
trojnásobném pádu uprostřed práce.

## Stav jednotlivých chipů

### CHIP 10 — hook-diry (nezačato)

Worktree `../CHIPS-chip-10` je čistý, žádná práce se neztratila, protože
žádná nevznikla. Agent narazil na strop **jedné odpovědi**, ne na limit účtu —
zadání bylo příliš husté: čtyři nezávislé opravy plus regresní důkaz ke každé.

**Doporučení: rozříznout na dva chipy.** Nálezy se dělí přirozeně:

- **10a — extrakce z příkazu**: nález #1 (větev se bere z prvního tokenu
  místo z argumentu `merge`) a #2 (`cilove_repo` bere první `git -C`/`cd`).
  Obojí je práce s parsováním příkazové řádky.
- **10b — kdy zamítnout**: nález #3 (fallback brány na hlavní strom při
  chybějícím worktree) a #4 (brána běží nad working tree, merge bere
  committed tip). Obojí je rozhodnutí „raději zamítnout než ověřit něco jiného".

Oba dědí sekci „Dotčené soubory" z původního briefu (`tools/hook_chip_gate.py`,
`tests/test_chip_gate.py`), takže **nesmí běžet paralelně** — buď sériově,
nebo 10b jako navazující chip větvený z 10a.

### CHIP 11 — lint-common (rozpracováno, commit `beb6a5f`)

Hotovo podle diffu (**neověřeno reviewem ani celou bránou**):

- #1 `prekryv()` — kolize adresář × glob
- #2 `strom_ke_kontrole()` — ověřování proti správnému repu

Zbývá: #3 absolutní glob shodí lint tracebackem, #4 cesta s ` #` ve jméně,
#5 regresní důkazy ke všem opravám, #6 kontrola stávající sady.

Sada v tom stromě prochází (**373 testů OK**), ale brána nebyla spuštěna celá
a Definition of done není ověřená.

### CHIP 12 — slice-run (rozpracováno, commit `7810e9d`)

Rozeditovaných 5 souborů, +131 řádků v `chip_slice.py`, `chip_run.py`
a jejich testech. Sada prochází (**366 testů OK**), brána nespuštěna,
DoD neověřena. Které z issues #1–#6 jsou hotové, se musí zjistit z diffu —
agent to nestihl zapsat do Logu.

## Jak pokračovat

1. **Nepouštět znovu od nuly.** Práce chipů 11 a 12 je v gitu; agent musí
   dostat brief **plus informaci, co už je hotové**, ať to nepřepisuje.
2. Ověřit rozdělaný stav: `git -C ../CHIPS-chip-NN diff a827840..HEAD`
   a projít, které issues jsou splněné.
3. **Chip 10 nejdřív rozřezat** podle návrhu výše — pouštět ho v původní
   podobě znamená narazit na týž strop.
4. Po dokončení: brána v každém worktree, kontrola rozsahu proti nároku,
   celá sada na hlavní větvi po každém merge.
5. Nálezy z review pak nahlásit s `outcome` (fixed / skipped / no_change_needed).

## Poznámka k odhadům

Chip 10 je první případ, kdy zadání narazilo na **limit jedné odpovědi**, ne
na spotřebu celkem. Do odhadů z metodiky (~100 tis. tokenů na chip) tedy patří
druhá mez: **hustota zadání**. Čtyři nezávislé opravy s regresním důkazem ke
každé se do jedné odpovědi nevejdou — a projeví se to až pádem, ne varováním.

---

## Jak to dopadlo

Vlna byla dokončena týž den po resetu limitů. Výsledek: **10/10 nálezů
opraveno**, čtyři chipy zmergovány, sada **366 → 413 testů**, lint 0 chyb.

| Chip | Výsledek | Testy |
|---|---|---|
| 12 slice-run | byl **hotový celý** — stačilo ověřit bránu a mergnout | 366 |
| 11 lint-common | kód a testy hotové z WIP, doplněn regresní důkaz a Log | 373 → 379 na masteru |
| 13 hook-extrakce | odkud hook bere větev a repo (z chipu 10) | 396 |
| 14 hook-zamitani | kdy má hook zamítnout (z chipu 10) | 413 |

### Rozříznutí chipu 10 → chipy 13 a 14

**Ne 10a/10b, jak zněl původní návrh.** Hook i brána matchují číslo chipu jako
`(\d+)`, takže větev `ai/chip-10a/…` by se rozpoznala jako **chip 10** a brána
by ověřovala cizí brief. Pojmenování se přizpůsobilo nástroji, protože nástroj
je vynucovací bod.

Dělicí čára vedla **podle povahy práce, ne podle počtu nálezů**: chip 13 =
parsování příkazové řádky, chip 14 = rozhodovací pravidla. Mechanické dělení
„dva a dva" by agenta nutilo přepínat mezi dvěma způsoby uvažování — přesně ta
hustota, na které původní chip 10 umřel.

### Co se ukázalo navíc

- **Záchranný zápis podceňoval hotovou práci.** Chip 12 byl hotový celý včetně
  Logu a odškrtané DoD; chip 11 měl všechny čtyři opravy nakódované a pokryté
  13 testy. Poučení: **než pustíš agenta na „rozdělaný" chip, přečti diff** —
  ne poznámku o něm.
- **Agent chipu 13 našel třetí nález, který code review minul**: octopus merge
  (`git merge A B`) ověřoval bránu jen první větve a druhou pustil bez kontroly.
  Vyplynulo to z opravy #1 — když se větve berou z argumentů za `merge`,
  je vidět, že argumentů může být víc.
- **Agent chipu 11 našel díru ve vlastní Definition of done.** DoD zněla „lint
  nad ERP-CHIPS vrátí 0 chyb"; to vracela i rozbitá verze, protože všech 11
  briefů je `draft` a kontrola cest se na ně nespustí. Doložil to tedy přímým
  měřením návratové hodnoty `strom_ke_kontrole()`. **DoD ve tvaru „nástroj
  vrátí 0 chyb" je slabá**, pokud nedokazuje, že kontrola vůbec proběhla.
- **`--uklid` patří až po mergi.** Nový hook zamítne merge, když worktree chipu
  chybí — po úklidu tedy chip nejde mergnout. Navíc: po `--uklid` zůstávají
  adresáře bez `.git`, takže `is_dir()` na ně sedne a chybějící worktree
  odhalí až `git status`.
- **`git worktree remove` v tomhle prostředí padá** na `Permission denied`
  u mazání, i když commit a merge projdou. Obejití: `git branch -d` + smazání
  adresáře přes PowerShell `Remove-Item -Recurse -Force`.
