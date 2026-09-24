---
chip: 22
nazev: slovnik-stavu
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
greenfield: ne       # 'ano' = repo teprve vznikne
vetev: ai/chip-22/slovnik-stavu
worktree: ../CHIPS-chip-22
---

# CHIP 22 — agenti si vymýšlejí stavy, protože slovník mají jinde

Tři agenti během pilotů napsali do briefu `stav: done`. Takový stav neexistuje —
`chip_lint.py` ho odmítne a chip se zasekne. Není to nepozornost: **slovník
stavů je v `docs/metodika.md`, ale agent čte brief.** Kdo má v ruce jen brief,
vidí na řádku `stav:` komentář `# draft | ready | running | gated | merged |
blocked` — tedy jména bez významů, ze kterých nepozná, který stav mu přísluší.

Chip má dostat slovník tam, kde se rozhoduje: **do generovaného briefu.**

Druhá polovina je jazyková: stavy nepřepíná agent, ale orchestrátor. To musí
z briefu být vidět, jinak si i správný slovník vyloží jako pozvánku.

## Issues

- [x] #1 — generovaný brief obsahuje slovník stavů s **významy**, ne jen jmény
- [x] #2 — u slovníku je věta, že `stav:` přepíná **orchestrátor**, ne agent;
      mandát agenta je Log a checkboxy
- [x] #3 — slovník je **v šabloně**, aby ho měl každý nový brief i ten
      založený ručně kopií
- [x] #4 — **NEZAKLÁDAT novou `## sekci`** — povinné sekce hlídá `POVINNE`
      v `chip_lint.py`, který je mimo tvůj nárok. Slovník patří jako komentář
      u frontmatteru nebo jako blok pod nadpis chipu, ne jako `## Slovník`.
- [x] #5 — jména stavů ve slovníku se musí shodovat s `chip_common.STAVY`;
      test, který to porovná, aby se to nikdy nerozešlo
- [x] #6 — `chip_new.py` dál generuje brief, který projde `chip_lint.py` čistě
      (žádné nové placeholdery, žádný klíč bez hodnoty)
- [x] #7 — pořadí stavů ve slovníku odpovídá životnímu cyklu
      (`draft → ready → running → gated → merged`, `blocked` stranou), ne abecedě
- [x] #8 — testy: generovaný brief obsahuje všech šest stavů i větu o tom,
      kdo je přepíná
- [x] #9 — existující testy `chip_new.py` musí dál platit (hlavně invariant
      „každý klíč frontmatteru má hodnotu" — dnes na něm padá každý překlep
      v šabloně, viz `test_kazdy_klic_frontmatteru_ma_hodnotu`)

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_new.py
tests/test_chip_new.py
chips/TEMPLATE.md
```

`chips/TEMPLATE.html` přegeneruje **orchestrátor po mergi** (`md2html.py` si
nárokuje jiný chip téže vlny). `chip_lint.py`, `chip_common.py` a `docs/` jsou
mimo nárok.

## Definition of done

- [x] `python -m unittest discover -s tests` projde a testů je **víc** než
      dnešních 523
- [x] `python tools/chip_new.py 99 pokus --repo .` vygeneruje brief, ve kterém
      jsou všechna jména z `chip_common.STAVY` i s významem (ověř očima i testem)
- [x] `python tools/chip_lint.py` nad repem s tím briefem vrací **0**
      (po zkoušce brief smaž — nesmí zůstat v `chips/`)
- [x] test, který porovná jména stavů v šabloně s `chip_common.STAVY` a selže
      při rozejití
- [x] v šabloně nepřibyla žádná `## sekce`

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Zastav se, zapiš do Logu a nech na uživateli:

- **potřeba přidat sekci do `POVINNE`** v `chip_lint.py` — ten soubor je mimo
  nárok a je to brána; když se ukáže, že slovník potřebuje vlastní sekci,
  zastav se a napiš to
- změna významu kteréhokoli stavu (to je změna metodiky, ne šablony)
- jakýkoli zásah mimo „Dotčené soubory"
- nová externí závislost

## Kontext pro agenta

- Testy: `python -m unittest discover -s tests -v`, stdlib `unittest`, **žádný
  pytest**. Vlastní `tempfile` fixture, úklid po sobě.
- **Významy stavů opiš z `docs/metodika.md`, sekce „Životní cyklus chipu"** —
  je to zdroj pravdy, ten soubor jen čti, needituj.
- `tests/test_chip_new.py` má třídu `TestZadnyZbytek` s obecnými pojistkami
  (placeholder ve frontmatteru, klíč bez hodnoty, `.replace()` bez vzoru).
  Nové testy pověs vedle nich a **ani jednu pojistku neobcházej** —
  orchestrátor na jedné z nich dnes padl a bylo to správně.
- `chip_new.py` dosazuje do šablony přes `.replace()`; test
  `test_kazdy_replace_v_chip_new_ma_vzor_v_sablone` hlídá, že se generátor
  a šablona nerozejdou. Když přidáš dosazování, drž se toho vzoru.
- Šablona je zdroj pravdy pro strukturu briefu (viz `CLAUDE.md`).

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-28 | ready | brief založen orchestrátorem |
| 2026-07-28 | running | Slovník je ve **frontmatteru šablony** hned pod `stav:` — jako komentářové řádky, které `chip_common.parse` ignoruje (žádný nový klíč, žádná nová `## sekce`, `POVINNE` v `chip_lint.py` se nesahalo → nic k eskalaci T3). Pořadí = životní cyklus, tedy `chip_common.STAVY`; nad ním věta, že `stav:` přepíná orchestrátor a mandát agenta je Log a checkboxy. |
| 2026-07-28 | running | Inline komentář `# draft \| ready \| …` na řádku `stav:` jsem **zrušil** — dvě místa se stejným seznamem se rozejdou. `stav: draft` jako řetězec zůstal, takže `test_chip_lint.TestPlaceholdery` (dělá `replace("stav: draft", "stav: ready")`) i `prepis_stav` fungují dál. |
| 2026-07-28 | running | Významy opsané z `docs/metodika.md` §7 doslova, s jednou úpravou: u `blocked` „čeká na tebe" → „čeká na rozhodnutí člověka". V metodice mluví orchestrátor, v briefu čte agent, a „tebe" by tam znamenalo jeho. Význam stavu se tím nemění; kdyby to orchestrátor viděl jinak, je to jednořádková oprava. |
| 2026-07-28 | running | `tools/chip_new.py` **nezměněn** — slovník patří do šablony (má ho mít i brief založený ručně kopií), generátor za něj nic nedosazuje, takže by nová `.replace()` jen přidala místo, kde se to může rozejít. Nárok na soubor zůstal, změna nebyla potřeba. |
| 2026-07-28 | running | Regresní důkaz: čtyři mutace šablony (abecední pořadí, stav bez významu, `merged`→`done`, smazaná věta o orchestrátorovi) i pátá (slovník jako `## sekce`) sadu shodí; po každé zpět obnoveno. Brána: **528 testů** (523 → +5, 2 expected failures patří chipu 20), `chip_lint.py` rc 0. DoD ověřeno i ručně: `chip_new.py 99 pokus --repo .` → brief se slovníkem, lint 0, brief smazán. |
| 2026-07-28 | running | Mimo nárok, na orchestrátora: `chips/TEMPLATE.html` je proti `.md` zastaralé (`md2html.py` si nárokuje chip 20) — přegenerovat po mergi. |
