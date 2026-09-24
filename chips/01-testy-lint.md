---
chip: 01
nazev: testy-lint
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-01/testy-lint
worktree: ../CHIPS-chip-01
---

# CHIP 01 — testy pro `chip_lint.py`

Brána projektu nemá dnes jediný automatický test. Tenhle chip ji pokryje, aby
šla měnit bez toho, že se tiše rozbije disjunktnost.

## Issues

- [x] #1 — disjunktnost: shodná cesta, adresář ⊃ soubor, dva různé soubory (bez kolize)
- [x] #2 — disjunktnost s vzory: vzor × soubor, vzor × vzor, vzor × soubor, který teprve vznikne
- [x] #3 — hlášení kolize je jeden řádek na dvojici nároků z briefu, s důkazem `(např. …)`
- [x] #4 — existence cest: chybějící soubor = chyba, `# nový` = projde, existující + `# nový` = varování
- [x] #5 — absolutní cesta (`/x`, `C:/x`) i `..` = chyba
- [x] #6 — vzor, který v repu nic nenajde = chyba
- [x] #7 — chybějící `repo:` i neexistující adresář repa = chyba
- [x] #8 — stav `draft` kontrolu cest přeskočí; `merged`/`blocked` se nekontrolují na kolize
- [x] #9 — povinné sekce, neplatný stav, zbylé placeholdery ze šablony
- [x] #10 — závislosti: neexistující, cyklická, `running` s předkem jiným než `merged` = chyba; `ready` s nehotovým předkem = varování
- [x] #11 — chipy ve vztahu předek–potomek se na kolizi nekontrolují
- [x] #12 — návratové kódy: 0 když je čisto, 1 při jakékoli chybě (varování nesmí shodit)

## Dotčené soubory  ⚠️ NÁROK

```
tests/test_chip_lint.py      # nový
```

Nesmíš měnit `tools/` ani nic mimo tento seznam. Když test odhalí chybu v
`chip_lint.py`, **neopravuj ji** — zapiš ji do sekce Log a označ test
`@unittest.expectedFailure` s komentářem proč. Oprava je rozhodnutí mimo tenhle chip.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] alespoň 20 testovacích metod, každá issue výše pokrytá aspoň jednou
- [x] testy si staví vlastní dočasné repo (`tempfile`) a po sobě uklidí — žádná závislost na stavu disku
- [x] pouze standardní knihovna (žádný pytest, žádné nové závislosti)
- [x] `python tools/chip_lint.py` v repu dál vrací 0

## Ověření (brána)

Bez zelené brány se **nemerguje**. Když selže → stav `blocked`, popiš proč v Logu.

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Při zásahu do čehokoli z tohoto seznamu: **zastav, zapiš do Logu, nehádej.**

- změna chování `tools/chip_lint.py` nebo `chip_common.py` (jsou mimo tvůj nárok)
- nová závislost (pytest, hypothesis, cokoli mimo stdlib)
- soubor mimo sekci „Dotčené soubory"
- cokoli se secrets nebo firemními cestami v testovacích datech

## Kontext pro agenta

- Testovaný kód: `tools/chip_lint.py`, pomocný parser `tools/chip_common.py`.
  Import: `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))`.
- `chip_lint.main()` čte globální `CHIPS_DIR` — přepíná se přes
  `chip_common.nastav_chips_dir(cesta)`. V testu tedy: vyrob tmp adresář s
  briefy, zavolej `nastav_chips_dir`, pak `chip_lint.main()` a odchyť návratový
  kód. `main()` parsuje `sys.argv` → použij `unittest.mock.patch("sys.argv", [...])`
  nebo volej vnitřní funkce (`prekryv`, `naroky`, `zkontroluj_cesty`) přímo.
- Výstup se tiskne na stdout → `contextlib.redirect_stdout(io.StringIO())`.
- Brief musí mít sekce `## Issues`, `## Dotčené soubory`, `## Definition of done`,
  `## Ověření (brána)` a frontmatter mezi `---`, jinak lint hlásí chybějící sekce.
- Placeholdery, které lint hlásí jako varování, jsou v `chip_lint.PLACEHOLDERY` —
  v testovacích briefech je nepoužívej, ať si nevyrobíš falešná varování.
- Konvence workspace: ke každému `.md` patří `.html` — testy jsou `.py`, netýká se jich.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-26 | ready | založeno orchestrátorem |
| 2026-07-26 | gated | `tests/test_chip_lint.py` — 49 testovacích metod (48 zelených + 1 `expectedFailure`), všech 12 issues pokryto. Brána zelená: `python -m unittest discover -s tests -v` → `OK (expected failures=1)`, `python tools/chip_lint.py` → exit 0. |

### Nálezy v testovaném kódu (NEOPRAVENO — mimo nárok chipu, viz Eskalace T3)

**N1 — `prekryv()` neumí vzor × vzor, když se vzory liší tvarem.**
`prekryv("src/*.py", "src/mo*")` vrací `False`, přestože oba nároky sdílejí
`src/modul.py`. Důvod: `fnmatch` se v `prekryv()` volá vždy jako
vzor × *řetězec*, takže se porovnává druhý vzor jako doslovný text
(`"src/mo*"` nevyhoví vzoru `src/*.py`, protože nekončí `.py` — a obráceně
totéž). Skutečný průnik dvou vzorů se netestuje.

*Dopad:* v praxi kolizi obvykle zachytí až rozbalení vzorů v `naroky()` —
ale jen pokud společný soubor v repu **už existuje**. Tiše projde tam, kde
sdílený soubor teprve vznikne: u chipů ve stavu `running`/`gated`
(tam se existence cest nekontroluje) a u cest označených `# nový`.
Ve stavu `ready` je to zčásti zamaskované tím, že vzor bez shody je sám
o sobě chyba (issue #6).

*Stav:* test `TestPrekryv.test_prekryv_dvou_ruznotvarych_vzoru` je označen
`@unittest.expectedFailure` — až se chování opraví, unittest ohlásí
`unexpected success` a nález se sám připomene. Oprava = změna chování
`tools/chip_lint.py`, tedy rozhodnutí mimo tenhle chip (T3).

**Poznámka k `tests/`:** adresář v repu neexistoval, chip ho zakládá spolu
s nárokovaným souborem. Žádný jiný soubor mimo sekci „Dotčené soubory"
(a tento brief) změněn nebyl.
| 2026-07-26 | merged | brána ověřena orchestrátorem (49 testů, 1 expected failure = nález N1), sloučeno; oprava N1 jde do chipu 05 |
| 2026-07-27 | merged | Sjednocení složky: `vetev:` převedena na konvenci `ai/chip-NN/<nazev>` (zavedl chip 08 — tenhle chip běžel ještě pod starým tvarem `chip/NN-<nazev>`), doplněn slovník stavů do komentáře u `stav:`. Obsah chipu nedotčen. |
