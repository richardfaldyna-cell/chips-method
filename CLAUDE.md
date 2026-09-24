# CLAUDE.md — CHIPS

Metodika + nástroje pro paralelní vývoj s AI agenty. Práce se krájí na uzavřené
balíčky („chipy"), každý běží v izolovaném git worktree a merguje se až po
projití automatické brány. Vznik a odůvodnění: `docs/konverzace-2026-07-25.md`.

## Co tady platí

- **Metodika je v `docs/metodika.md`** — když se mění pravidlo, mění se tam,
  ne v README ani v šabloně. README je jen rozcestník.
- **`chips/TEMPLATE.md` je zdroj pravdy pro strukturu briefu.** Když se do něj
  přidá sekce, přidej ji i do `POVINNE` v `tools/chip_lint.py` — jinak se
  nekontroluje a časem vyhnije.
- **Nástroje bez externích závislostí** kromě `markdown` (jen `md2html.py`).
  Chip briefy parsuje vlastní mini-parser v `chip_common.py`, ne PyYAML.
- **Ke každému `.md` patří `.html`** (konvence workspace):
  `python tools/md2html.py --all`. Před commitem přegeneruj.
- `chip_lint.py` vrací **exit 1 při nálezu** — je to brána, ne doporučení.
  Nezaváděj do něj nic, co by se dalo „jen tak" ignorovat.
- **Testy: `python -m unittest discover -s tests -v`**, stdlib `unittest`, žádný
  pytest. Každý test si staví vlastní `tempfile` fixture a uklidí po sobě;
  `chip_common.CHIPS_DIR` je globální stav, v `tearDown` ho vracej.
  Nová funkce bez testu se sem nedostane — sada je jediné, co drží bránu poctivou.

## Když tenhle projekt řídíš jako orchestrátor

- **Commitni před `chip_run.py`** — worktree se větví z HEAD, ne z working tree.
- **Nesahej na brief běžícího chipu.** Je to soubor, který zároveň edituje agent
  (Log, checkboxy) — přepis stavu dělej před spuštěním nebo až po merge
  (`chip_common.prepis_stav`).
- **Bránu ověř sám** (`chip_gate.py NN`), nezávisle na tom, co agent napsal
  do souhrnu. PreToolUse hook ji spustí ještě jednou při merge — když ho
  budeš chtít obejít, zastav se a zeptej se uživatele. Po každém
  merge pusť celou sadu na hlavní větvi — zelená v izolaci není zelená dohromady.
- Stav chipu přepínáš ty, ne agent. Mandát chipu je Log a checkboxy.

## Čeho se držet obsahově

Projekt existuje kvůli třem konkrétním selháním paralelního vývoje. Když se
přidává funkce, musí sloužit aspoň jednomu z nich:

1. N session nad jedním working tree → tiše ztracené změny (→ worktree)
2. autonomní merge bez ověření → „zkontroloval jsem to" jako tvrzení modelu (→ brána)
3. nejasné hranice mezi balíčky → kolize (→ disjunktnost + `chip_lint.py`)

Naopak sem **nepatří**: hlasování více modelů jako náhrada rozhodnutí,
automatický merge bez brány, měkká formulace pravidel typu „buď opatrný".

## Git / bezpečnost

- **Push jen na vlastní větev a přes PR**, nikdy rovnou do `master`.
- **Repo je veřejné.** Do briefů, logů, dokumentace ani commitů nepatří
  absolutní lokální cesty (`repo:` piš relativně k adresáři s briefy, typicky
  `..`), názvy firemních repů ani secrets. Cizí projekt popiš obecně
  („firemní ERP projekt"), ne jménem.
