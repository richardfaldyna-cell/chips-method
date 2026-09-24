---
chip: 06
nazev: sdilene-helpery
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-06/sdilene-helpery
worktree: ../CHIPS-chip-06
---

# CHIP 06 — sloučit duplicitní helpery do `chip_common.py`

Dva chipy z vlny 1 si musely lokálně napsat funkci, která patří do sdíleného
modulu — nesměly na něj sáhnout, protože si ho nárokoval někdo jiný. Obojí
eskalovaly do Logu místo hádání. Tenhle chip ten dluh splácí.

## Issues

- [x] #1 — přesunout počítání odškrtnutých issues z `chip_status.py` do `chip_common.Chip` (metoda vracející hotové issues, aby šlo psát `hotové/celkem`)
- [x] #2 — přesunout `prepis_stav()` z `chip_run.py` do `chip_common.py` (textový přepis `stav:` v prvním frontmatteru, bajtově bezpečný)
- [x] #3 — `chip_status.py` i `chip_run.py` volají nově sdílenou verzi; lokální kopie zmizí beze zbytku
- [x] #4 — chování zůstává **beze změny**: stejné výstupy, stejné návratové kódy, stejné hlášky
- [x] #5 — testy sdílených funkcí patří do `tests/test_chip_common.py`; v `test_chip_status.py` a `test_chip_run.py` nech jen testy chování nástrojů
- [x] #6 — `prepis_stav()` musí umět i cílový stav jiný než `running` (orchestrátor přepíná na `merged`) a nesmí sáhnout na soubor, když není co měnit
- [x] #7 — celá stávající sada testů musí projít beze změny počtu selhání

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_common.py
tools/chip_status.py
tools/chip_run.py
tests/test_chip_common.py
tests/test_chip_status.py
tests/test_chip_run.py
```

Nesmíš měnit `tools/chip_lint.py` ani `tests/test_chip_lint.py` — nárokuje si je
paralelně běžící chip 05. Pokud tvoje změna v `chip_common.py` rozbije lint,
je to chyba tohoto chipu: `chip_common` je sdílený základ, ne prostor pro
přejmenovávání. **Nic ze stávajícího veřejného API neodstraňuj ani nepřejmenovávej.**

## Definition of done

- [ ] `python -m unittest discover -s tests -v` projde, počet selhání se oproti dnešku nezhorší
- [ ] `grep` neukáže žádnou duplicitní implementaci obou funkcí mimo `chip_common.py`
- [ ] `python tools/chip_status.py --dir chips` vypíše stejnou tabulku jako před zásahem (porovnej s baseline pořízenou PŘED úpravou)
- [ ] `python tools/chip_run.py 06 --dry-run` funguje jako dnes
- [ ] `python tools/chip_lint.py` vrací 0
- [ ] pouze standardní knihovna

## Ověření (brána)

Bez zelené brány se **nemerguje**. Když selže → stav `blocked`, popiš proč v Logu.

```bash
python -m unittest discover -s tests -v
python tools/chip_status.py --dir chips
python tools/chip_run.py 06 --dry-run
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Při zásahu do čehokoli z tohoto seznamu: **zastav, zapiš do Logu, nehádej.**

- změna `chip_lint.py` nebo `tests/test_chip_lint.py` (nárokuje si je chip 05)
- odstranění nebo přejmenování stávající funkce/metody v `chip_common.py`
- změna formátu briefu, frontmatteru nebo šablony
- nová závislost mimo stdlib
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- Původ obou dluhů je zapsaný v Logu briefů `chips/02-chip-status.md` a
  `chips/04-run-spusteni.md` — přečti si je, ať víš, proč to tak vzniklo.
- `chip_common.py` je záměrně bez závislostí (vlastní mini-parser místo PyYAML).
  Drž ten styl: stdlib, krátké funkce, české docstringy vysvětlující *proč*.
- `prepis_stav()` v `chip_run.py` pracuje přes `read_bytes`/`write_bytes` a regex
  omezený na první frontmatter — zachovej to, je to kvůli CRLF a diakritice.
- Odškrtnuté issues se poznají podle `- [x]`; `Chip.issues()` dnes vrací text
  bez značky, takže se z něj hotové poznat nedají — proto ta lokální kopie.
- **Nejdřív si pořiď baseline**: spusť `python tools/chip_status.py --dir chips`
  a `python tools/chip_run.py 06 --dry-run` PŘED zásahem a výstupy si ulož do
  scratchpadu; DoD po tobě chce porovnání.
- Import v testu: `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))`.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-26 | ready | založeno orchestrátorem ze dvou eskalací vlny 1 |
| 2026-07-26 | running | baseline výstupů (`chip_status --dir chips`, `chip_run 06 --dry-run`, `chip_lint`) pořízen PŘED zásahem do scratchpadu; po refaktoru jsou všechny tři **bajt v bajt shodné** (`cmp`) |
| 2026-07-26 | running | `hotove_issues()` je nově metoda `Chip` a vrací **seznam textů** (ne počet) — `len(c.hotove_issues())/len(c.issues())`; regex má stejný tvar jako `ISSUE`, takže hotové jsou vždy podmnožinou celkových |
| 2026-07-26 | running | jediný rozdíl proti staré verzi je degenerovaný řádek `- [x]` úplně bez textu: dřív se počítal do čitatele (ale ne do jmenovatele, `issues()` vyžaduje text), nově se nepočítá ani do jednoho. V žádném briefu ani testu se nevyskytuje, výstupy jsou shodné; sjednocení je smyslem issue #1 |
| 2026-07-26 | running | `prepis_stav()` přesunut do `chip_common.py` beze změny těla (`read_bytes`/`write_bytes` + regex na první frontmatter kvůli CRLF a diakritice); `chip_run` ho jen importuje, test `test_pouziva_sdilenou_funkci` hlídá, že se kopie nevrátí |
| 2026-07-26 | running | z veřejného API `chip_common` nic neubylo ani se nepřejmenovalo — jen přibylo (`ISSUE`, `HOTOVA_ISSUE`, `STAV_RADEK`, `Chip.hotove_issues`, `prepis_stav`); `chip_lint.py` ani `tests/test_chip_lint.py` jsem nesahal (nárok chipu 05) |
| 2026-07-26 | gated | brána zelená: 183 testů OK (1 očekávané selhání, stejně jako v baseline 169/1), `chip_status --dir chips` i `chip_run 06 --dry-run` beze změny chování, `chip_lint.py` exit 0. Merge nechávám na uživateli. |
| 2026-07-26 | merged | brána ověřena orchestrátorem (183 testů, bajtová shoda výstupů), sloučeno |
| 2026-07-27 | merged | Sjednocení složky: `vetev:` převedena na konvenci `ai/chip-NN/<nazev>` (zavedl chip 08 — tenhle chip běžel ještě pod starým tvarem `chip/NN-<nazev>`), doplněn slovník stavů do komentáře u `stav:`. Obsah chipu nedotčen. |
