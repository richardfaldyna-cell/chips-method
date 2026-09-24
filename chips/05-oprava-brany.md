---
chip: 05
nazev: oprava-brany
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-05/oprava-brany
worktree: ../CHIPS-chip-05
---

# CHIP 05 — oprava dvou děr v bráně

Pilot vlny 1 odhalil dvě místa, kde `chip_lint.py` tvrdí „čisto", i když čisto
není. Obojí jsou přesně ty tiché chyby, kvůli kterým projekt vznikl.

## Issues

- [x] #1 — **N1: `prekryv()` neumí vzor × vzor.** `prekryv("src/*.py", "src/mo*")` vrací `False`, přestože oba nároky sdílejí `src/modul.py`. Implementuj skutečný test průniku dvou glob vzorů (rekurzivně, podpora `*`, `?`, literálů; `[…]` ber konzervativně jako kolizi).
- [x] #2 — `src/*.py` × `tests/*.py` musí zůstat `False`; `src/a_*.py` × `src/b_*.py` musí být `False` (jsou opravdu disjunktní); `src/*.py` × `src/mo*` musí být `True`
- [x] #3 — v `tests/test_chip_lint.py` zruš `@unittest.expectedFailure` u `TestPrekryv.test_prekryv_dvou_ruznotvarych_vzoru` (jinak sada spadne na `unexpected success`)
- [x] #4 — **N2: kontrola existence cest se ptá špatného stromu.** Když brief leží uvnitř git worktree, `repo:` z frontmatteru ukazuje na hlavní strom → lint ověřuje nároky proti cizímu checkoutu. Řeš to tak, že se strom pro kontrolu existence odvodí od umístění briefu, když je uvnitř gitu.
- [x] #5 — když brief leží mimo jakýkoli git strom (režim `--dir`), použije se dál `repo:` z frontmatteru — chování zůstává jako dnes
- [x] #6 — `chip_run.py` musí dál zakládat worktree podle `repo:` z frontmatteru, ne podle stromu briefu — proto změnu **nedělej** v `chip_common.repo_path()`, ale lokálně v `chip_lint.py`
- [x] #7 — testy pro #1–#5, včetně případu „soubor je v hlavním stromě, ale ve worktree chybí → chyba"
- [x] #8 — po opravě musí celá sada projít bez jediného `expected failure`

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_lint.py
tests/test_chip_lint.py
```

Nesmíš měnit `chip_common.py`, `chip_status.py` ani `chip_run.py` — nárokuje si je
paralelně běžící chip 06. Když potřebuješ pomocnou funkci, měj si ji lokálně
v `chip_lint.py` a zapiš do Logu, že by patřila do sdíleného modulu.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, **0 selhání a 0 expected failures**
- [x] `prekryv()` splňuje všechny případy z issues #1 a #2
- [x] `python tools/chip_lint.py` v repu vrací 0
- [x] pouze standardní knihovna (žádné nové závislosti)
- [x] hlášky a exit kódy lintu zůstávají jinak beze změny

## Ověření (brána)

Bez zelené brány se **nemerguje**. Když selže → stav `blocked`, popiš proč v Logu.

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Při zásahu do čehokoli z tohoto seznamu: **zastav, zapiš do Logu, nehádej.**

- změna `chip_common.py`, `chip_status.py`, `chip_run.py` (nárokuje si je chip 06)
- změna formátu briefu, frontmatteru nebo šablony
- nová závislost mimo stdlib
- oslabení brány: cokoli, co by chybu měnilo na varování
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- Nález N1 je detailně popsaný v `chips/01-testy-lint.md`, sekce Log — přečti si ho.
- Dnešní `prekryv()` volá `fnmatch(retezec, vzor)`, tedy druhý vzor bere doslova.
  Průnik dvou globů se dá rozhodnout rekurzivně: porovnávej znak po znaku, na `*`
  zkoušej „spotřebuj nic" i „spotřebuj jeden znak z druhé strany", výsledky
  memoizuj (`functools.lru_cache` nebo slovník) — bez memoizace to u dlouhých
  cest exploduje.
- Rozbalení vzorů v `naroky()` řeší jen soubory, které **už existují** — proto
  N1 tiše projde u cest značených `# nový` a u stavů `running`/`gated`.
- K N2: v git worktree je `.git` **soubor** (obsahuje `gitdir: …`), ne adresář —
  detekce musí projít oběma případy. Hledej nahoru od `chip.path`.
- Bias projektu je jasný: raději nahlásit kolizi navíc než ji přehlédnout.
  Ale ne za cenu, že se nahlásí i prokazatelně disjunktní vzory (issue #2).
- Konvence: komentáře a hlášky česky, dvě mezery odsazení, `X` chyba / `!` varování.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-26 | ready | založeno orchestrátorem z nálezů vlny 1 (N1 z chipu 01, N2 z ověřování chipu 04) |
| 2026-07-26 | gated | obojí opraveno v `tools/chip_lint.py`, testy rozšířeny na 67 metod (z 49). Brána zelená: `python -m unittest discover -s tests -v` → `Ran 187 tests … OK` (0 selhání, **0 expected failures**), `python tools/chip_lint.py` → `OK — 0 chyb, 0 varování`, exit 0. |

### Jak je to vyřešené

**N1 — průnik dvou vzorů.** `prekryv()` už neporovnává vzor s druhým vzorem jako
s doslovným řetězcem. Vzor se tokenizuje (`_tokeny`) na `HVEZDA` / `JEDEN` /
literál a `_prunik()` rekurzivně (s memoizací `(i, j)`, jinak exponenciální)
rozhodne, jestli existuje řetězec vyhovující oběma. `*` platí dál i přes `/`
(zachováno z původního chování), třída `[…]` se bere konzervativně jako
„libovolný znak" — jazyk vzoru se tím jen rozšíří, takže kolize může vyjít
navíc, ale žádná nezmizí. `src/*.py` × `src/mo*` → kolize, `src/a_*.py` ×
`src/b_*.py` → čisto.

**N2 — strom pro kontrolu existence.** Nové lokální funkce `git_koren()`
(hledá nahoru od briefu, `.git` bere jako adresář i jako soubor `gitdir: …`)
a `strom_ke_kontrole()`. Když brief leží uvnitř git stromu, kontroluje se ten;
mimo git se dál použije `repo:` z frontmatteru. `repo:` se **validuje beze
změny** (chybí / neexistuje = chyba), jen se podle něj už neověřuje existence
nároků — `chip_run.py` tak zakládá worktree pořád podle frontmatteru.
Stejný strom používá i `naroky()` při rozbalování vzorů, aby kolize nedokládal
souborem, který ve worktree není. Ověřeno i na tomhle repu: `repo:` =
`…/CHIPS`, strom kontroly = `…/CHIPS-chip-05`.

### Poznámky / nároky na jiné chipy

- `git_koren()` a `strom_ke_kontrole()` jsou schválně jen v `chip_lint.py`
  (issue #6). Kdyby je potřeboval i jiný nástroj, patřily by do `chip_common.py`
  — to si ale nárokuje chip 06, takže **návrh pro pozdější chip**, ne teď.
- Hranice řešení N2: rozhoduje samotná přítomnost `.git` nad briefem, neověřuje
  se, že jde o tentýž repozitář jako `repo:`. Pro layout „chipy leží v repu,
  kterého se týkají" to sedí; kdyby někdo držel briefy v repu A a nárokoval
  soubory v repu B, kontrola by mířila do A. Rozhodnutí ponecháno tak, jak ho
  zadával brief (issue #4) — případné zpřísnění je nová věc, ne oprava.
- Brána nikde nezměkčena: žádná dosavadní chyba se nestala varováním, hlášky
  ani exit kódy se nezměnily (kontrolováno testy `TestExistenceCest`,
  `TestNavratoveKody` a novými `test_*_zustava_chybou_i_uvnitr_gitu`).
| 2026-07-26 | merged | brána ověřena orchestrátorem (201 testů po integraci s chipem 06), sloučeno |
| 2026-07-27 | merged | Sjednocení složky: `vetev:` převedena na konvenci `ai/chip-NN/<nazev>` (zavedl chip 08 — tenhle chip běžel ještě pod starým tvarem `chip/NN-<nazev>`), doplněn slovník stavů do komentáře u `stav:`. Obsah chipu nedotčen. |
