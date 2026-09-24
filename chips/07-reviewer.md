---
chip: 07
nazev: reviewer
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-07/reviewer
worktree: ../CHIPS-chip-07
---

# CHIP 07 — `chip_review.py`: nezávislá kontrola chipu

Brána je dnes jen tak přísná, jak přísné jsou testy — a ty píše **týž model**,
který psal kód. Zdroje o multiagentním vývoji na to shodně nasazují oddělenou
QA/reviewer roli. Tenhle chip pro ni staví nástroj: co jde ověřit strojově,
ověří sám; zbytek předá druhému agentovi jako zadání.

## Issues

- [x] #1 — `python tools/chip_review.py NN` sesbírá fakta o hotovém chipu:
      soubory v commitu, diff stat, seznam nárokovaných cest, stav briefu
- [x] #2 — **kontrola rozsahu**: soubor změněný mimo sekci „Dotčené soubory"
      je nález (kromě vlastního briefu chipu a jeho `.html`)
- [x] #3 — **podezřelé testy**: testovací metoda bez jediného `assert*`/`with self.assertRaises`,
      metoda označená `@unittest.skip`, `expectedFailure` — vypiš je jmenovitě
- [x] #4 — **DoD vs. realita**: odškrtnuté body Definition of done vypiš vedle
      sebe s příkazy brány, ať jde porovnat, co je ověřené a co jen odškrtnuté
- [x] #5 — spočítej poměr přidaných řádků testů k přidaným řádkům kódu
      (hrubý ukazatel, ne verdikt — vypiš, nekomentuj)
- [x] #6 — `--zadani` vypíše **zadání pro reviewer agenta**: co má přečíst,
      na co se ptát a co NESMÍ (opravovat kód, mergovat, měnit brief)
- [x] #7 — návratový kód: 1 při nálezu v #2 (rozsah je tvrdé pravidlo),
      0 při ostatních (jsou to podklady pro člověka/agenta, ne verdikt)
- [x] #8 — `--repo` pro kontrolu chipu v cizím repu (pilot na `pilot-repo`)
- [x] #9 — testy pro #1–#8 nad dočasným repem s připraveným commitem

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_review.py         # nový
tests/test_chip_review.py    # nový
```

Nesahej na `chip_run.py`, `chip_gate.py`, `hook_chip_gate.py` ani `chip_common.py`
— první tři si nárokuje souběžný chip 08. Co potřebuješ, měj lokálně a zapiš
do Logu jako kandidáta na sloučení.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] `python tools/chip_review.py 07 --repo <vlastní worktree>` doběhne a vypíše
      přehled; ověř to na sobě samém
- [x] kontrola rozsahu odhalí uměle podstrčený soubor mimo nárok (pokryto testem)
- [x] detekce testu bez assertu funguje na syntetickém příkladu
- [x] pouze standardní knihovna
- [x] alespoň 15 testovacích metod

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

- změna `chip_run.py`, `chip_gate.py`, `hook_chip_gate.py`, `chip_common.py` (chip 08)
- nová závislost mimo stdlib
- **nedělej z reviewu bránu, která blokuje merge** — o tom rozhoduje uživatel;
  tenhle nástroj podklady sbírá, nerozhoduje
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- Vzor stylu: `chip_status.py` (tabulka) a `chip_gate.py` (spouštění + hlášení).
  Import `from chip_common import ...`, `pridej_arg_dir(ap)`, `utf8_vystup()`,
  dvě mezery odsazení, `X` chyba / `!` varování, hlášky česky.
- Chip má `.soubory()` (nárokované cesty), `.issues()`, `.hotove_issues()`,
  `.najdi("definition of done")`, `.meta["vetev"]`, `.repo_path()`.
- Soubory v commitu zjistíš `git -C <repo> show --name-only --format= HEAD`
  (přes `subprocess`, vzor v `chip_gate.spust`).
- Na porovnání cesty s nárokem použij stejnou logiku jako `chip_lint.prekryv`
  — ale **nekopíruj ji**, importuj: `from chip_lint import prekryv, vzor`.
  (Čtení cizího modulu je v pořádku, jeho změna ne.)
- Detekci assertů dělej přes `ast`, ne regexem: hledej `unittest.TestCase`
  třídy, v nich metody `test_*`, a v jejich těle volání `self.assert*`,
  `self.fail`, `with self.assertRaises`. `ast` je stdlib.
- Zadání pro reviewera (#6) piš jako text v modulu, stejně jako `ZADANI`
  v `chip_run.py`. Musí obsahovat: přečti brief celý, ověř že testy opravdu
  testují (ne že jen procházejí), ověř DoD proti skutečnosti, hlásit — neopravovat.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-26 | ready | založeno z poznatků NotebookLM (QA/reviewer role v multiagentním flow) |
| 2026-07-26 | hotovo | `chip_review.py` + 51 testů; sada 288 testů zelená, `chip_lint.py` OK (2 varování „# nový", cesty teď existují) |
| 2026-07-27 | merged | Sjednocení složky: `vetev:` převedena na konvenci `ai/chip-NN/<nazev>` (zavedl chip 08 — tenhle chip běžel ještě pod starým tvarem `chip/NN-<nazev>`), doplněn slovník stavů do komentáře u `stav:`. Obsah chipu nedotčen. |

**Nálezy a rozhodnutí (k posouzení uživatelem, neřešeno v tomhle chipu):**

1. **Nástroj nerozhoduje.** Exit 1 vrací výhradně kontrola rozsahu (#2); podezřelé
   testy, DoD ani poměr řádků návratový kód nezvedají — je na to test
   (`test_podezrely_test_nezvedne_navratovy_kod`). Kdyby se to mělo změnit,
   je to změna metodiky, ne nástroje.
2. **Kandidát na sloučení do `chip_common.py`** (nechal jsem lokálně, `chip_common`
   si nárokuje jiný chip):
   - `_git(repo, *args)` — git bez shellu; `chip_gate.spust` umí jen `shell=True`
     a vrací spojený stdout+stderr, což se na `git show --numstat` nehodí.
   - `DOD_RADEK` — čtení checkboxů se značkou. `chip_common.ISSUE` /
     `HOTOVA_ISSUE` vrací jen texty, takže „odškrtnuté vedle neodškrtnutých"
     z nich složit nejde.
3. **Závislost na cizích modulech je jen ke čtení**: `from chip_lint import prekryv,
   vzor` a `from chip_gate import prikazy`. Chip 08 (`chip_gate.py`) prosím
   zachovej funkci `prikazy(chip) -> list[str]`, jinak se rozbije sekce DoD.
4. `--commit` je default `HEAD`. Když se pustí nad commitem, který chip nedělal
   (např. orchestrátorův commit se třemi briefy), vyjdou cizí briefy jako
   „mimo nárok" — je to správně, ale volající si musí rozsah hlídat
   (`--commit main..HEAD` u víc commitů).
5. Detekce assertů je záměrně **konzervativní**: volání pomocné metody, která
   assertuje uvnitř, se nepozná a test se nahlásí jako podezřelý. Falešný nález
   stojí jedno přečtení testu, přehlédnutý nález stojí bránu.
6. Kontrola rozsahu pouští vlastní brief chipu a jeho `.html` (mandát agenta),
   cizí brief hlásí — pokryto testy `test_vlastni_brief_je_povoleny` /
   `test_cizi_brief_je_nalez`.
