---
chip: 15
nazev: lint-placeholdery
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-15/lint-placeholdery
worktree: ../CHIPS-chip-15
---

# CHIP 15 — lint hlásí placeholder i tam, kde je jen citovaný

Kontrola nedovyplněné šablony hledá vzorové řetězce **v celém textu briefu**,
takže varuje i u chipů, které o tom placeholderu jen píšou. Je to jako by
kontrola pravopisu podtrhla slovo „překlep" ve větě „tady je překlep".

Dnes to dělá tři trvalá falešná varování (briefy 08, 09, 12). Nic to neblokuje —
jsou to varování, ne chyby. Vadí to jinak: **na trvalý šum si člověk zvykne
a přestane ho číst**, takže mu unikne čtvrté varování, které bude pravé.

## Kde přesně to je

`tools/chip_lint.py`, ř. ~359:

```python
text = c.path.read_text(encoding="utf-8")
for ph in PLACEHOLDERY:
    if ph in text:
        varovani.append(...)
```

## Issues

- [x] #1 — **Každý placeholder kontroluj jen tam, kde skutečně škodí.**
      Nahraď plošné `ph in text` mapováním placeholder → místo:

      | Placeholder | Kde vadí | Kde je neškodný |
      |---|---|---|
      | `C:/cesta/k/repu` | frontmatter `repo:` | próza, Log |
      | `kratky-nazev-s-pomlckami` | frontmatter `nazev:`, `vetev:` | próza, Log, text issue |
      | `src/parser.py` | cesty v sekci „Dotčené soubory" (`c.soubory()`) | próza, Log |
      | `#12 — stručný popis` | texty issues (`c.issues()`) | próza, Log |

      **Past, na kterou nesmíš naletět:** „stačí vynechat Log" NEFUNGUJE.
      Brief 12 má `kratky-nazev-s-pomlckami` i v textu issue #1, protože ten
      chip právě tenhle placeholder opravoval. Proto se u něj musí kontrolovat
      **jen frontmatter**, ne issues.
- [x] #2 — **Nesmí to oslabit kontrolu.** Brief vyrobený přímo z `TEMPLATE.md`
      a přepnutý na `ready` musí dál nahlásit **všechny čtyři** placeholdery.
      To je hlavní důkaz, že oprava neudělala z kontroly atrapu.
- [x] #3 — testy: (a) test z #2 nad kopií skutečné `TEMPLATE.md`, ne nad
      vymyšleným textem; (b) po jednom testu na každé ze tří dnešních falešných
      varování (citace v Logu, citace v prózi, citace v textu issue)
- [x] #4 — **doloženo na skutečných briefech**: `python tools/chip_lint.py`
      musí skončit na **0 chyb, 0 varování o placeholderech**. Varování jiného
      druhu (např. závislost na nezmergovaném chipu) tím dotčená nejsou —
      výstup před i po zapiš do Logu.
- [x] #5 — testy z #3 musí na PŮVODNÍ verzi selhat (doloženo hláškami v Logu)
- [x] #6 — celá stávající sada projde beze změny počtu selhání

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_lint.py
tests/test_chip_lint.py
```

Nesahej na `chips/TEMPLATE.md` (test si z ní jen čte), na žádný brief kromě
vlastního, ani na `chip_common.py` a ostatní nástroje.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] `python tools/chip_lint.py` nad skutečnou složkou `chips/` nehlásí
      **žádné** varování o placeholderu — spusť doopravdy, výstup do Logu
- [x] brief vyrobený z `TEMPLATE.md` ve stavu `ready` hlásí **všechny čtyři**
      placeholdery — pokryto testem nad skutečnou šablonou
- [x] `kratky-nazev-s-pomlckami` v textu issue se **nehlásí**, v `nazev:`
      nebo `vetev:` **hlásí** — dva testy
- [x] pouze standardní knihovna

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

- **oslabení lintu**: nic, co je dnes chyba, se nesmí stát varováním, a žádná
  kontrola nesmí zmlknout úplně. Kdyby jediné čisté řešení znamenalo některý
  placeholder přestat hlídat, zastav se a zapiš
- změna `chips/TEMPLATE.md` nebo textu cizích briefů (falešná varování se řeší
  v lintu, **ne přepsáním briefů, aby lint mlčel**)
- odstranění/přejmenování čehokoli z veřejného API `chip_lint`
- nová závislost mimo stdlib
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- Kontrola běží jen pro `c.stav != "draft"` — to nech být.
- `c.soubory()` vrací nárokované cesty bez poznámek, `c.issues()` texty issues,
  `c.meta` frontmatter. Všechno je v `tools/chip_common.py` (jen čti).
- Tvar `PLACEHOLDERY` si zvol sám (dnes je to `tuple` řetězců) — dává smysl
  udělat z toho mapování nebo malou datovou strukturu. Ať je z kódu vidět
  **proč** se který placeholder hledá jinde, ne jen že se hledá.
- Zvaž, jestli u frontmatteru kontrolovat celý řádek, nebo jen hodnotu za
  dvojtečkou. Brief 08 má za hodnotou komentář — nesmí ho to rozhodit.
- Regresní důkaz: původní verzi vytáhni `git show HEAD:tools/chip_lint.py`
  do dočasného souboru a **zaregistruj do `sys.modules` před importem testů**
  (`sys.path.insert` nestačí, testy si `tools/` samy vkládají na `sys.path[0]`).
  Ověř assertem, že testovaný modul je opravdu ta podstrčená kopie. Hotové
  vzory jsou v Logu briefů 13 a 14 (jen čti).
- Konvence: hlášky česky, `X` chyba / `!` varování, odsazení kódu 4 mezery
  (PEP 8) podle zbytku `tools/`.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-27 | ready | založeno — tři trvalá falešná varování po sjednocení složky chips/ |
| 2026-07-27 | ready | #1: `PLACEHOLDERY` je nově n-tice `Placeholder(text, kde, hodnoty, cela_hodnota)` — ke každému vzorovému řetězci patří **funkce, která vrátí hodnoty k prohledání**, ne celý text briefu. Mapování: `C:/cesta/k/repu` → `meta['repo']`; `kratky-nazev-s-pomlckami` → `meta['nazev']` + `meta['vetev']`; `src/parser.py` → `c.soubory()`; `#12 — stručný popis` → `c.issues()`. Kontroluje se **hodnota za dvojtečkou, ne celý řádek** — `chip_common.parse` komentář za hodnotou odřízne, takže `stav: ready  # draft \| ready \| …` v briefu 08 nic nerozhodí (test `test_komentar_za_hodnotou_frontmatteru_kontrolu_nerozhodi`). U cest se porovnává **celá hodnota** (`cela_hodnota=True`): podřetězec by hlásil i legitimní `balik/src/parser.py`, kdežto nevyplněná šablona má nárok přesně `src/parser.py`. Nová `zbyle_placeholdery(c)` vrací hlášky (jedna na placeholder) a nese i místo: „zůstal placeholder ze šablony: 'src/parser.py' (nárokovaná cesta v 'Dotčené soubory')". Kontrola dál běží jen mimo `draft` — nedotčeno. |
| 2026-07-27 | ready | **Past ověřena, ne uvěřena.** „Stačí vynechat Log" opravdu NEFUNGUJE: brief 12 má `kratky-nazev-s-pomlckami` na ř. 20–21 uvnitř textu issue #1 (a až pak v Logu na ř. 107). Navíc `c.issues()` vrací jen PRVNÍ řádek odrážky, takže ani kontrola nad texty issues by ten výskyt nechytla — vyšlo by falešné „čisto" ze špatného důvodu. Proto je u tohohle placeholderu jediné poctivé místo frontmatter (`nazev:`/`vetev:`), kam nedosazený název briefu skutečně škodí (chip_run z něj zakládá větev). Ověřeno: `c.issues()[0]` chipu 12 placeholder neobsahuje, celý text ano. |
| 2026-07-27 | ready | #3 testy: nová třída `TestPlaceholdery` (9 testů). #2 = `test_brief_ze_skutecne_sablony_hlasi_vsechny_ctyri` nad KOPIÍ skutečné `chips/TEMPLATE.md` (jen `stav: draft`→`ready`), ověřuje všechny čtyři přes `zbyle_placeholdery()` (subTesty) i end-to-end přes výstup lintu (přesně 4 řádky). Tři falešná varování: `test_citace_v_logu_nevaruje` (08), `test_citace_v_proze_nevaruje` (09), `test_citace_v_textu_issue_nevaruje` (12). Protipól: `test_placeholder_v_nazvu_varuje`, `test_placeholder_ve_vetvi_varuje`, `test_placeholder_v_naroku_varuje`, `test_komentar_za_hodnotou_frontmatteru_kontrolu_nerozhodi`, `test_draft_se_na_placeholdery_nekontroluje`. Fixture `napis_brief()` dostal tři NEPOVINNÉ parametry (`vetev`, `proza`, `log`) — bez nich se chová bajt v bajt jako dřív, žádný stávající test se neupravoval. |
| 2026-07-27 | ready | #5 regresní důkaz (`git show HEAD~1:tools/chip_lint.py` → dočasný soubor, registrace do `sys.modules['chip_lint']` PŘED importem testů; ověřeno assertem `t.chip_lint is mod` + `isinstance(mod.PLACEHOLDERY[0], str)`, že jde opravdu o původní verzi): **3 FAIL + 1 ERROR z 9**. Hlášky tří klíčových testů — všechny „Lists differ: [...] != []": „! 01-alfa.md: zůstal placeholder ze šablony: 'kratky-nazev-s-pomlckami'" (citace v Logu), „…: 'src/parser.py'" (citace v próze), „…: 'kratky-nazev-s-pomlckami'" (citace v textu issue). ERROR: „AttributeError: module 'chip_lint' has no attribute 'zbyle_placeholdery'" u testu ze šablony. **Poctivě: test ze šablony (#2) na původní verzi selhat NEMŮŽE obsahem** — původní plošné hledání všechny čtyři placeholdery hlásí taky; je to pojistka proti oslabení, ne regresní důkaz, a musí být zelený na obou verzích (jeho end-to-end část na původní verzi projde). Ostatních 5 testů na původní verzi právem prošlo — hlídají, že se varovat MUSÍ. Na opravené verzi 9/9 OK. |
| 2026-07-27 | ready | Brána: `python -m unittest discover -s tests -v` → **422 testů, 0 selhání** (před chipem 413 → +9, žádný stávající test neupraven). `python tools/chip_lint.py` **PŘED**: „zkontrolováno 14 chipů (1 aktivních) / ! 08-nazvy-vetvi.md: zůstal placeholder ze šablony: 'kratky-nazev-s-pomlckami' / ! 09-rezani-z-issues.md: … 'src/parser.py' / ! 12-slice-run.md: … 'kratky-nazev-s-pomlckami' / ! 15-lint-placeholdery.md: … 'src/parser.py' / … '#12 — stručný popis' / … 'C:/cesta/k/repu' / … 'kratky-nazev-s-pomlckami' / OK — 0 chyb, 7 varování" (chip 15 spouštěl všechna čtyři, protože placeholdery vyjmenovává v tabulce). **PO**: „zkontrolováno 14 chipů (1 aktivních) / OK — 0 chyb, 0 varování", rc 0 — 0 varování o placeholderech i 0 varování celkem (jiný druh dnes žádný není). Jen stdlib (`typing.NamedTuple`, `Callable`). Žádný T3: nic z lintu nezmlklo, co bylo chyba zůstalo chybou, cizí briefy ani `TEMPLATE.md` jsem nesáhl. `.html` k briefu nepřegenerováno (`md2html.py --all` sahá mimo NÁROK) — dělá orchestrátor po merge. |
