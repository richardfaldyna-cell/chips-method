---
chip: NN
nazev: kratky-nazev-s-pomlckami
stav: draft
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
repo: C:/cesta/k/repu
greenfield: ne       # 'ano' = repo teprve vznikne; lint pak neexistenci repa a cest jen varuje
vetev: ai/chip-NN/kratky-nazev-s-pomlckami   # prefix ai/ = kód psal AI agent (audit v git logu); prázdné = odvodí chip_run.py
worktree: ../repo-chip-NN
---

# CHIP NN — <název>

Jednou větou, co tenhle balíček řeší.

## Issues

- [ ] #12 — stručný popis
- [ ] #13 — stručný popis
- [ ] #14 — stručný popis

> Strop: 10–20 issues. Víc → rozřež na dva chipy.

## Dotčené soubory  ⚠️ NÁROK

Seznam souborů/adresářů, které tenhle chip smí měnit. **Žádný jiný chip je nesmí
mít v seznamu** — kontroluje `tools/chip_lint.py`.

```
src/parser.py
src/parser_utils.py
src/parser_cache.py      # nový — chip ho teprve vytvoří
tests/*.py
```

Cesty jsou **relativní k `repo:`** (bez `..`, bez disku). Ve stavu `ready` lint
ověří, že v repu opravdu existují — soubor, který teprve vznikne, označ `# nový`,
jinak je nárok hlášený jako překlep. Vzory (`src/*.py`) fungují a pro kontrolu
kolizí se rozbalují na konkrétní soubory.

Poznámka za cestou se odděluje **dvěma a více mezerami** před `#`. Jedna mezera
se bere jako součást jména, aby se cesta `docs/plan #1.md` neusekla na `docs/plan`.

Soubory mimo tento seznam se **nemění**. Když je to nutné → eskalace (viz níže).

## Definition of done

Musí jít ověřit příkazem, ne názorem.

- [ ] `pytest tests/test_parser.py` projde beze změny počtu testů
- [ ] `ruff check src/parser.py` bez nálezů
- [ ] `parser.py` má < 300 řádků

## Ověření (brána)

Bez zelené brány se **nemerguje**. Když selže → stav `blocked`, otevři PR.

```bash
pytest -q
python -m build
python smoke_test.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Při zásahu do čehokoli z tohoto seznamu: **zastav, otevři PR s otázkou, nehádej.**

- změna veřejného API nebo formátu dat
- migrace schématu / nevratná operace nad daty
- nová závislost nebo změna licence
- bezpečnostní rozhodnutí, cokoli se secrets
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

Co potřebuje vědět, aby nemusel hádat: konvence projektu, kde jsou testy,
známé gotchas, odkazy na dokumentaci.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| YYYY-MM-DD | draft | založeno |
