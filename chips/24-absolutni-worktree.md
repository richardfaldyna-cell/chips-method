---
chip: 24
nazev: absolutni-worktree
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
vetev: ai/chip-24/absolutni-worktree   # prefix ai/ = kód psal AI agent (audit v git logu); prázdné = odvodí chip_run.py
worktree: ../CHIPS-chip-24
---

# CHIP 24 — absolutní `worktree:` čte `chip_run` jinak než brána

`chip_run.cesty()` z absolutní hodnoty `worktree:` vezme jen jméno adresáře a
položí ho vedle repa, kdežto `chip_gate.kde_spustit()` i `hook.kde_overit()` ji
respektují — worktree pak vznikne jinde, než kam se dívá brána. Chip srovnává
`chip_run` na chování brány.

## Issues

- [x] #1 — `chip_run.cesty()`: absolutní `worktree:` platí, jak je zapsaný
      (žádné `.name`, žádné skládání pod `repo.parent`)
- [x] #2 — relativní `worktree:` se chová **přesně jako dnes**: bere se jen
      jméno adresáře a klade se vedle repa, aby výsledek nezávisel na `cwd`
- [x] #3 — bez `repo:` v briefu: absolutní cesta platí dál, relativní spadne
      na dnešní `Path(jmeno)` (volající chybějící `repo:` hlásí sám)
- [x] #4 — regresní test na relativní větev, aby ji oprava #1 nerozbila
      potichu; test musí selhat, kdyby se `.name` u relativní cesty ztratilo
- [x] #5 — test, že `chip_run.cesty()`, `chip_gate.kde_spustit()` a
      `hook.kde_overit()` dají nad TÝMŽ briefem tutéž cestu — pro absolutní
      i relativní zápis. Tohle je vlastní obsah chipu: shoda tří míst, ne
      chování jednoho.
- [x] #6 — v `tests/test_chip_gate.py` zrušit `@unittest.expectedFailure` u
      `test_absolutni_cesta_se_s_chip_run_rozchazi`, přejmenovat na tvrzení o
      shodě a docstring přepsat z „nález, neopravuje se zde" na „srovnáno
      chipem 24". Dekorátor **musí** zmizet — jinak sada spadne na
      *unexpected success*, což je návrh chipu 19, ne chyba.
- [x] #7 — docstring `chip_run.cesty()`: dnešní věta „z `worktree:` se bere jen
      jméno adresáře" je po opravě nepravdivá pro absolutní zápis
- [x] #8 — docstring `chip_gate.kde_spustit()` tvrdí „cesta se řeší jako v
      `chip_run.cesty()`" — dnes je to **lež** a opravou #1 se stane pravdou;
      větu ponech, ale ověř, že po změně sedí, a doplň, co znamená absolutní
- [x] #9 — `python tools/chip_run.py 24 --dry-run` vypíše u absolutního
      `worktree:` tutéž cestu, jakou pak bránu spustí `chip_gate.py`

> Strop: 10–20 issues. Víc → rozřež na dva chipy.

## Dotčené soubory  ⚠️ NÁROK

Seznam souborů/adresářů, které tenhle chip smí měnit. **Žádný jiný chip je nesmí
mít v seznamu** — kontroluje `tools/chip_lint.py`.

```
tools/chip_run.py
tools/chip_gate.py       # POUZE docstring kde_spustit() — chování se nemění
tests/test_chip_run.py
tests/test_chip_gate.py
```

`tools/hook_chip_gate.py` v nároku **není a měnit se nesmí** — absolutní cestu
už dnes respektuje správně, je to strana, na kterou se `chip_run` srovnává.
Test z #5 si ho smí naimportovat a číst; kdyby vyšlo, že se musí změnit i on,
je to eskalace (viz T3), ne tichý zásah.

Cesty jsou **relativní k `repo:`** (bez `..`, bez disku). Ve stavu `ready` lint
ověří, že v repu opravdu existují — soubor, který teprve vznikne, označ `# nový`,
jinak je nárok hlášený jako překlep. Vzory (`src/*.py`) fungují a pro kontrolu
kolizí se rozbalují na konkrétní soubory.

Soubory mimo tento seznam se **nemění**. Když je to nutné → eskalace (viz níže).

## Definition of done

Musí jít ověřit příkazem, ne názorem.

- [x] `python -m unittest discover -s tests -v` projde. Výchozí stav před
      chipem: **676 testů, `OK (expected failures=1)`** (ověřeno 2026-07-31).
      Po chipu musí počet testů stoupnout (nové testy k #4 a #5) a výsledek
      být čisté **`OK`** bez expected failures — ta jediná je právě tenhle
      nesoulad. Pozn.: `@unittest.expectedFailure` v `test_chip_review.py`
      je uvnitř řetězcové fixtury, ne skutečný test; nepočítá se.
- [x] `python tools/chip_lint.py` → rc 0, bez chyb
- [x] `grep -n "expectedFailure" tests/test_chip_gate.py` nevrací nic
- [x] `python tools/chip_run.py 24 --dry-run` projde a cesta ve výpisu se
      shoduje s tím, co hlásí `python tools/chip_gate.py 24` (issue #9)

## Ověření (brána)

Bez zelené brány se **nemerguje**. Když selže → stav `blocked`, otevři PR.

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
python tools/chip_run.py 24 --dry-run
```

## Eskalace — co NEROZHODOVAT sám (T3)

Při zásahu do čehokoli z tohoto seznamu: **zastav, otevři PR s otázkou, nehádej.**

- změna veřejného API nebo formátu dat
- migrace schématu / nevratná operace nad daty
- nová závislost nebo změna licence
- bezpečnostní rozhodnutí, cokoli se secrets
- soubor mimo sekci „Dotčené soubory" — jmenovitě `tools/hook_chip_gate.py`
- **změna chování brány.** Směr srovnání je rozhodnutý: `chip_run` se
  přizpůsobuje bráně, ne naopak. Kdyby se ukázalo, že to nejde bez zásahu do
  `kde_spustit()`/`kde_overit()`, zastav se a zeptej — jsi na jiné variantě,
  než která byla schválena.
- **zúžení vstupu místo srovnání** (odmítnout absolutní `worktree:` jako chybu
  briefu) je zvažovaná a **zamítnutá** varianta, ne zkratka k zelené

## Kontext pro agenta

**Proč zrovna tímhle směrem.** Důvod pro `.name` v `chip_run.cesty()` je
nezávislost na `cwd` — aby relativní zápis v briefu neznamenal něco jiného
podle toho, odkud se skript pustí. Absolutní cesta na `cwd` nezávisí, takže
u ní `.name` nic nekupuje: jen zahodí to, co brief říká. Proto se srovnává
`chip_run`, ne brána.

**Kde to je.**

- `tools/chip_run.py` → `cesty()` (~ř. 283), tři návratové hodnoty
  `(repo, vetev, worktree)`, bez vedlejších efektů — dobře testovatelné
- `tools/chip_gate.py` → `kde_spustit()` (~ř. 127), docstring odkazuje na
  `chip_run.cesty()`
- `tools/hook_chip_gate.py` → `kde_overit()` (~ř. 304) — jen ke čtení
- `tests/test_chip_gate.py` → `test_absolutni_cesta_se_s_chip_run_rozchazi`
  (~ř. 1052) je `@unittest.expectedFailure` a jeho docstring popisuje přesně
  tuhle past; přečti si ho první, je to zadání napsané chipem 19

**Konvence projektu** (`CLAUDE.md`): stdlib `unittest`, žádný pytest; každý test
si staví vlastní `tempfile` fixturu a uklidí po sobě; `chip_common.CHIPS_DIR` je
globální stav — v `tearDown` ho vracej. Ke každému `.md` patří `.html`
(`python tools/md2html.py --all`) — briefu se to netýká, ten generuje
orchestrátor po mergi.

**Pozor na Windows.** `Path("/x").is_absolute()` je na Windows `False` (chybí
disk) — testy piš tak, aby platily i tam, kde se pouštějí (`C:/…`), ne jen na
POSIXu. `test_brana_a_hook_resi_worktree_stejne` je vzor, jak to už řeší jinde.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-31 | draft | založeno |
| 2026-07-31 | ready | Směr srovnání rozhodl uživatel: `chip_run` se přizpůsobuje bráně (varianty „gate+hook berou jen jméno" a „absolutní cestu odmítnout jako chybu briefu" zamítnuty). Výchozí stav sady ověřen: 676 testů, `OK (expected failures=1)`; `chip_lint.py` rc 0. |
| 2026-07-31 | merged | Brána ověřena orchestrátorem nezávisle na hlášení agenta: `chip_gate.py 24` ZELENÁ nad worktree, sada 681 testů čisté `OK` (676 → +5, `expected failures` 1 → 0), `expectedFailure` v `test_chip_gate.py` 0 výskytů, diff jen ve 4 nárokovaných souborech + brief, `hook_chip_gate.py` nedotčen. Po mergi celá sada na masteru: 681 testů `OK`, lint rc 0. Sloučeno `--no-ff`, worktree uklizen. |
| 2026-07-31 | running | Hotovo #1–#9. `cesty()` větví na `is_absolute()`: absolutní zápis platí, jak je; relativní beze změny (`.name` vedle repa). Docstringy `cesty()` i `kde_spustit()` srovnány s realitou. +5 testů (4 v `test_chip_run.py`: absolutní s/bez repa, regrese `.name`, relativní bez repa; 1 v `test_chip_gate.py`: shoda tří míst pro relativní/hlubokou/absolutní). Dřívější očekávané selhání přejmenováno na `test_absolutni_cesta_sedne_s_chip_run`. Brána: 681 testů čisté `OK`, lint rc 0, `chip_gate.py 24` ZELENÁ a hlásí týž strom jako `chip_run.py 24 --dry-run`. `hook_chip_gate.py` nedotčen. |
