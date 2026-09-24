---
chip: 09
nazev: rezani-z-issues
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-09/rezani-z-issues
worktree: ../CHIPS-chip-09
---

# CHIP 09 — `chip_slice.py`: návrh řezu z fronty úkolů

Řezání dnes dělá člověk ručně. U stovky issues je to úzké hrdlo — a přitom
kritérium je mechanické: **disjunktnost souborů**. Tenhle nástroj z fronty úkolů
navrhne rozdělení na chipy a řekne, co je sporné.

Nástroj **nerozhoduje** — připraví návrh, který člověk opraví. Automatický řez
bez kontroly by porušoval pravidlo 5 (eskalace místo hádání).

## Issues

- [x] #1 — načíst úkoly z `TODO.md` ve formátu `- [ ]` (výchozí zdroj)
- [x] #2 — `--json <soubor>` jako alternativní vstup: seznam
      `{"id", "popis", "soubory": [...]}` (odtud půjde napojit GitHub issues)
- [x] #3 — u úkolu bez uvedených souborů zkusit odhad: cesty zmíněné přímo
      v textu úkolu (tvar `adresar/soubor.pripona`) — nic víc, **nehádat**
- [x] #4 — seskupit úkoly do skupin tak, aby se skupiny **nepřekrývaly** v souborech
      (souvislé komponenty grafu „úkol–soubor"); vzájemně se dotýkající úkoly
      musí skončit v jedné skupině
- [x] #5 — respektovat strop: skupina nad 20 úkolů nebo nad 15 souborů se označí
      `PŘÍLIŠ VELKÁ` s návrhem rozřezat
- [x] #6 — úkoly **bez jediného známého souboru** vypsat zvlášť jako
      `NEZAŘAZENO — doplň soubory ručně`, nikdy je nikam netipovat
- [x] #7 — výstup: přehled navržených skupin + `--zapsat <adresář>` vygeneruje
      draft briefy ze šablony (`stav: draft`, vyplněné Issues a Dotčené soubory)
- [x] #8 — vygenerované briefy musí projít `chip_lint.py` ve stavu `draft`
- [x] #9 — návratový kód 0 (je to návrh, ne brána)
- [x] #10 — testy: překryv dvou úkolů, řetěz tří úkolů přes společný soubor,
      osamocený úkol, úkol bez souborů, překročení stropu, prázdný vstup

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_slice.py         # nový
tests/test_chip_slice.py    # nový
```

Nesahej na žádný jiný nástroj — `chip_run.py`, `chip_gate.py`,
`hook_chip_gate.py` a `TEMPLATE.md` si nárokuje chip 08, `chip_review.py` chip 07.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] `python tools/chip_slice.py --todo TODO.md` na tomhle repu vypíše smysluplný
      návrh (ověř ručně, výstup dej do Logu)
- [x] `--zapsat` vygeneruje briefy, které projdou `chip_lint.py`
- [x] žádná skupina ve výstupu nesdílí soubor s jinou skupinou (pokryto testem)
- [x] pouze standardní knihovna
- [x] alespoň 15 testovacích metod

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_slice.py --todo TODO.md
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

- **nehádej soubory** k úkolu, který je neuvádí — takový úkol patří do
  `NEZAŘAZENO`. Odhad by vypadal jako informace a přitom by nebyl.
- změna formátu briefu nebo šablony (šablonu vlastní chip 08)
- automatické spouštění chipů z návrhu (`chip_run`) — nástroj jen navrhuje
- nová závislost mimo stdlib
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- Šablonu čti z `chips/TEMPLATE.md` (vlastní ji chip 08, ty ji jen **čteš**),
  ne z natvrdo zapsaného řetězce — jinak vyhnije.
- Skupiny jsou souvislé komponenty bipartitního grafu úkol–soubor. Union-find
  nebo prostý BFS; obojí stdlib.
- `chip_common` umí `nacti_vse`, `pridej_arg_dir`, `utf8_vystup`; `chip_lint.prekryv`
  a `vzor` můžeš **importovat** na porovnání cest (číst cizí modul je v pořádku).
- Formát TODO odrážky viz `chip_common.ISSUE` — použij ho, ať se to nerozejde.
- Vzor CLI a stylu výstupu: `chip_status.py`.
- Pojmenování skupin: `01`, `02`, … podle pořadí; číslo musí jít přepsat, protože
  v cílovém adresáři už nějaké chipy být můžou — ošetři kolizi (nepřepisuj cizí soubor).

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-26 | ready | založeno z poznatků NotebookLM (orchestrátor čte frontu issues) |
| 2026-07-26 | running | `chip_slice.py` + 45 testů; brána zelená (282 testů, lint 0 chyb) |
| 2026-07-27 | merged | Sjednocení složky: `vetev:` převedena na konvenci `ai/chip-NN/<nazev>` (zavedl chip 08 — tenhle chip běžel ještě pod starým tvarem `chip/NN-<nazev>`), doplněn slovník stavů do komentáře u `stav:`. Obsah chipu nedotčen. |

### Nálezy

**N1 — „nehádat" muselo dostat tvrdé pravidlo, jinak se rozteče.** Issue #3 říká
„cesty zmíněné přímo v textu (tvar `adresar/soubor.pripona`)". Nad skutečným
`TODO.md` tohohle repa to samo o sobě zařadí **jeden** úkol z deseti — většina
odrážek mluví o `chip_lint.py`, `chip_common.py` bez adresáře. Řešení, které
není hádání: **holé jméno se bere jen v backticích a jen když se v repu dohledá
právě jeden takový soubor** (0 shod = soubor tu není, 2+ = neví se který →
obojí jde do NEZAŘAZENO a jméno se vypíše jako „nedohledáno"). Je to ověření
proti stromu, ne odhad. Vypíná se `--bez-dohledani`.

**N2 — odrážky se v `TODO.md` lámou přes víc řádků a cesta bývá až na druhém.**
Kdyby se braly jen řádky, na které sedne `chip_common.ISSUE`, zmizel by nárok
u poloviny úkolů (např. `_pilot-repo/VYSLEDEK.md`). Parser proto přilepuje
odsazené pokračovací řádky. Odškrtnuté (`- [x]`) se přeskakují — hotová práce
se neřeže.

**N3 — šablona nese příklady, které by se ve vygenerovaném briefu četly jako
tvrzení.** `TEMPLATE.md` má v Definition of done `pytest tests/test_parser.py`
a v bráně `python -m build`. Kopie do draftu by vypadala jako vyplněná brána,
která ale nikdy neběžela. Generátor obě sekce **vyprázdní** na výzvu „doplň
ručně" — nástroj podmínky brány nevymýšlí. (Vedlejší efekt: mizí i placeholder
`src/parser.py`, který by `chip_lint` hlásil při přepnutí na `ready`.)

**N4 — číslování skupin musí počítat s cizími chipy v cílovém adresáři.**
`volne_cislo()` přeskočí obsazená dvojčíslí a existující soubor se nikdy
nepřepíše (ověřeno testem `test_kolize_cisla_neprepise_cizi_soubor`).

### Skutečný výstup nad `TODO.md` tohohle repa

```
  Návrh řezu: 2 skupiny, 2 zařazených, 8 nezařazených úkolů

  skupina 01  (1 úkol, 1 soubor)
    - #1 **Rozhodnout o merge výsledků pilotu na `pilot-repo`** …
    soubory: _pilot-repo/VYSLEDEK.md

  skupina 02  (1 úkol, 2 soubory)
    - #7 `git_koren()` / `strom_ke_kontrole()` z `chip_lint.py` přesunout do
      `chip_common.py` …
    soubory: tools/chip_common.py, tools/chip_lint.py

  NEZAŘAZENO — doplň soubory ručně (nástroj je nehádá): #2 #3 #4 #5 #6 #8 #9 #10
```

Osm z deseti nezařazených **je ten správný výsledek**, ne selhání: ty úkoly
opravdu neříkají, čeho se dotknou. `#2` navíc ukazuje odmítnutí odhadu s důvodem
— `pbip_fix_visual_titles.py` v tomhle repu není, takže se nedohledal.
