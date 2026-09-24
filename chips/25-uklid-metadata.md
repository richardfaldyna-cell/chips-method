---
chip: 25
nazev: uklid-metadata
stav: merged
# `stav:` přepíná ORCHESTRÁTOR, ne agent — mandát agenta je Log a checkboxy.
# Jiná hodnota než tahle šestice je pro `chip_lint.py` chyba (slovník je tady,
# protože agent drží v ruce brief, ne metodiku):
#   draft   — brief se píše, hranice ještě nejsou jisté
#   ready   — vyplněný brief, `chip_lint.py` čistý → smí se pustit
#   running — běží ve worktree
#   gated   — práce hotová, čeká na bránu
#   merged  — brána zelená, sloučeno, worktree uklizen
#   blocked — narazil na T3 nebo brána selhala → čeká na rozhodnutí člověka
zavisi_na:           # ID chipů, které musí být 'merged' dřív, např. 00, 01
repo: ..
greenfield: ne       # 'ano' = repo teprve vznikne; lint pak neexistenci repa a cest jen varuje
vetev: ai/chip-25/uklid-metadata   # prefix ai/ = kód psal AI agent (audit v git logu); prázdné = odvodí chip_run.py
worktree: ../CHIPS-chip-25
---

# CHIP 25 — `--uklid` ručí i za metadata, ne jen za pracovní adresář

`chip_run.uklid()` po smazání pracovního stromu spouští `git worktree prune`,
ale jeho výsledek nečte a úspěch měří jen přes `worktree.exists()` — když
prune nechá v `.git/worktrees/` mrtvý adresář (na Windows běžně: zbylý
`ORIG_HEAD` a spol., `Permission denied`, a přesto rc 0), nástroj ohlásí
úspěch. Chip doplní ověření a doklizení metadat.

## Issues

- [x] #1 — `uklid()` po každém `git worktree prune` ověří, že adresář metadat
      chipu (`.git/worktrees/<jméno worktree>`) opravdu zmizel — obě volání,
      ř. ~250 (větev „worktree na disku není") i ř. ~263 (po ručním mazání)
- [x] #2 — když adresář metadat po prune zůstal, smazat ho rekurzivně
      (`smaz_strom` nebo ekvivalent) — git ho už nevlastní (prune na něm hlásí
      „gitdir file does not exist"), zbývá v něm jen `ORIG_HEAD`/`logs`/`refs`
- [x] #3 — když se metadata nepodaří doklidit ani ručně: nenulový rc a hláška
      se jménem adresáře, ne tiché `return 0` — stejný vzor, jaký už `uklid()`
      má pro pracovní strom (`worktree.exists()` po `smaz_strom`)
- [x] #4 — test: fixture s reálným repem + worktree, pracovní strom smazaný
      ručně a v `.git/worktrees/<jméno>` nastražený soubor (simulace husku) →
      `uklid()` metadata dorazí a vrátí 0
- [x] #5 — regresní test na úspěšnou cestu: `worktree remove` projde, metadata
      zmizí sama, `uklid()` vrací 0 a nic nedomazává
- [x] #6 — docstring `uklid()` doplnit: úspěch = pracovní strom PRYČ **a**
      metadata PRYČ; rc prune se nečte proto, že git vrací 0 i při
      „Permission denied" — proto se výsledek měří stavem na disku

> Strop: 10–20 issues. Víc → rozřež na dva chipy.

## Dotčené soubory  ⚠️ NÁROK

Seznam souborů/adresářů, které tenhle chip smí měnit. **Žádný jiný chip je nesmí
mít v seznamu** — kontroluje `tools/chip_lint.py`.

```
tools/chip_run.py
tests/test_chip_run.py
```

Cesty jsou **relativní k `repo:`** (bez `..`, bez disku). Ve stavu `ready` lint
ověří, že v repu opravdu existují — soubor, který teprve vznikne, označ `# nový`,
jinak je nárok hlášený jako překlep.

Soubory mimo tento seznam se **nemění**. Když je to nutné → eskalace (viz níže).

## Definition of done

Musí jít ověřit příkazem, ne názorem.

- [x] `python -m unittest discover -s tests -v` projde. Výchozí stav před
      chipem: **681 testů, čisté `OK`** (ověřeno 2026-07-31). Po chipu počet
      stoupne (testy k #4 a #5) a výsledek zůstane čisté `OK`.
      → **692 testů, čisté `OK`** (+11).
- [x] `python tools/chip_lint.py` → rc 0, bez chyb
- [x] Test z #4 při vráceném starém chování (`git stash` změn v
      `tools/chip_run.py`) **selže** — jinak neměří opravu, ale počasí
      → ověřeno dvakrát, viz Log.
- [x] `python tools/chip_run.py 25 --dry-run` funguje jako dnes (úklid se
      `--dry-run` nepotkává, ale spouštěcí cesta nesmí být dotčená) → rc 0,
      výpis beze změny.

## Ověření (brána)

Bez zelené brány se **nemerguje**. Když selže → stav `blocked`, otevři PR.

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
python tools/chip_run.py 25 --dry-run
```

## Eskalace — co NEROZHODOVAT sám (T3)

Při zásahu do čehokoli z tohoto seznamu: **zastav, otevři PR s otázkou, nehádej.**

- změna veřejného API nebo formátu dat
- migrace schématu / nevratná operace nad daty
- nová závislost nebo změna licence
- bezpečnostní rozhodnutí, cokoli se secrets
- soubor mimo sekci „Dotčené soubory"
- **mazání čehokoli v `.git/` nad rámec `.git/worktrees/<jméno worktree
  TOHOTO chipu>`** — doklizení je chirurgické, žádné plošné `rm -rf
  .git/worktrees`; jednorázový úklid nakupené historie už udělal orchestrátor
  ručně 2026-07-31, chip řeší jen budoucí běhy

## Kontext pro agenta

**Diagnóza je hotová, neopakuj ji.** Ověřeno 2026-07-31 na tomto repu
(Windows 11, 24 nakupených adresářů z chipů 01–24):

- `git worktree prune -v` na mrtvém adresáři vypíše `Removing …: gitdir file
  does not exist`, pak `error: failed to delete …: Permission denied` — a
  přesto skončí **rc 0**. Chyba mazání je pro git jen poznámka, ne selhání.
  Proto nestačí začít číst rc prune; úspěch se musí měřit stavem na disku,
  stejně jako to `uklid()` už dělá u pracovního stromu.
- Adresář nejde smazat, protože v něm zbývá `ORIG_HEAD`, `logs/`, `refs/`.
  Rekurzivní smazání (`rm -rf` ekvivalent) projde na první pokus — není to
  zámek antiviru ani OneDrive.
- Vzor je o pár řádků výš: u `worktree remove` už `uklid()` komentuje „git
  skončil nulou, ale adresář zůstal" a dokládá kontrolou `worktree.exists()`.
  Tutéž nedůvěru aplikuj na `prune`.

**Kde to je.** `tools/chip_run.py` → `uklid()` (~ř. 210): dvě volání
`git(repo, "worktree", "prune")` — ř. ~250 (větev „worktree na disku není —
jen uklidím metadata", vrací 0 bez jakékoli kontroly) a ř. ~263 (po ručním
`smaz_strom`). Jméno adresáře metadat = `Path(worktree).name`; kořen
`.git` ber přes git (`git rev-parse --git-dir` nebo `--git-path worktrees`),
ne skládáním `repo / ".git"` — repo může být samo worktree.

**Konvence projektu** (`CLAUDE.md`): stdlib `unittest`, žádný pytest; každý
test vlastní `tempfile` fixture s reálným `git init` repem a uklidí po sobě;
`chip_common.CHIPS_DIR` je globální stav — v `tearDown` ho vracej. Fixture
s worktree už v `tests/test_chip_run.py` existují — vyjdi z nich. Simulace
husku v testu: založ worktree, smaž jeho pracovní strom ručně a do
`.git/worktrees/<jméno>` polož soubor navíc; je to přenositelné, na Windows
se nespoléhej (`Permission denied` tam vyrábí git, ne filesystem).

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-31 | draft | založeno |
| 2026-07-31 | ready | Variantu vybral uživatel: oprava přes chip + jednorázové smetení 23 husků udělal orchestrátor ručně hned (záloha ve scratchpadu, `git fsck` rc 0, `prune` po úklidu mlčí). Výchozí stav sady: 681 testů, čisté `OK`; lint rc 0. |
| 2026-07-31 | running | **Oprava #1–#3, #6.** Přibyly `git_vystup()`, `cesta_metadat()`, `metadata_patri_worktree()` a `dokliz_metadata()`; `uklid()` teď vede přes `dokliz_metadata()` **každou** cestu, která končí úspěchem — obě po `prune` i tu po úspěšném `worktree remove`, aby „0 = uklizeno" znamenalo totéž všude. Cesta k metadatům se bere `rev-parse --git-path worktrees/<jméno>`: ověřeno, že míří do *společného* adresáře, takže odpoví správně i když je `repo` samo linkované worktree (`.git` je v něm soubor). |
| 2026-07-31 | running | **Odchylka od zadání #4, s doložením.** Brief navrhoval simulovat husk nastraženým souborem v `.git/worktrees/<jméno>`. Ověřeno na git 2.53: `prune` ten soubor **smete** (`remove_dir_recursively`), takže by se testoval prázdný stav. Deterministickou a plně reálnou páku dělá `git worktree lock` — `prune` adresář mlčky nechá být a skončí rc 0, což je přesně pozorovaný stav z Windows (`gitdir file does not exist` + `Permission denied`, rc 0). Test to má vysvětlené v docstringu. Nastražený soubor v adresáři zůstal — dokládá, že se maže rekurzivně. |
| 2026-07-31 | running | **Nad rámec zadání, uvnitř #2:** před smazáním se kontroluje `gitdir` v adresáři metadat. Chybí-li, git adresář už nevlastní (to je ten husk); ukazuje-li jinam, sedí na jméně cizí worktree (git při kolizi jmen připojuje příponu) a nesahá se na něj. Je to čtení T3 pravidla „mazání je chirurgické" — bez té kontroly by šlo smazat metadata živého cizího worktree. |
| 2026-07-31 | running | **Brána zelená, čeká na přepnutí stavu orchestrátorem.** `unittest discover`: **692 testů, `OK`** (681 → +11). `chip_lint.py` rc 0, 0 chyb / 0 varování. `chip_run.py 25 --dry-run` rc 0, výpis beze změny. Ověření, že testy měří opravu a ne počasí, proběhlo dvakrát: (a) chirurgicky — dočasný návrat `return 0` v jediné větvi → `test_prune_nechal_metadata_uklid_je_dorazi`, `test_nesmazatelna_metadata_konci_jednickou` i `test_cizi_metadata_stejneho_jmena_zustanou` padají na věcných assertech; (b) `git stash push -- tools/chip_run.py` dle DoD → test padá už na fixture (`chip_run` nemá `cesta_metadat`). Průkaznější je (a). Do hlavní větve nemergováno. |
| 2026-07-31 | merged | Brána ověřena orchestrátorem nezávisle: `chip_gate.py 25` ZELENÁ, sada 692 testů čisté `OK` (681 → +11), rozsah jen 2 nárokované soubory + brief. Tvrzení „testy měří opravu" ověřeno vlastní sabotáží (návrat `return 0` v jediné větvi → padají 3 testy na věcných assertech), pak `git checkout` zpět. Po mergi na masteru: 692 testů `OK`, lint rc 0. **Ostrá zkouška opravy:** `--uklid` nad reálným worktree — `worktree remove` selhal dvakrát na „Permission denied", ruční smazání prošlo, `prune` nechal metadata a nový kód je odchytil (`prune nechal metadata … — mažu ručně`), rc 0, `.git/worktrees` prázdný. Přesně scénář, který dřív skončil mlčky. |
