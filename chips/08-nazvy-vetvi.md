---
chip: 08
nazev: nazvy-vetvi
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-08/nazvy-vetvi   # nová konvence; FYZICKÁ větev je pořád chip/08-nazvy-vetvi — viz Log
worktree: ../CHIPS-chip-08
---

# CHIP 08 — názvy větví musí nést, že kód psal AI agent

Dnešní `chip/05-oprava-pbip` neříká, kdo kód napsal. Praxe doporučuje prefix
`ai/`, aby to bylo z názvu i z `git log` okamžitě zřejmé — kvůli auditovatelnosti
při review a u firemních repů zvlášť.

**Pozor, tohle je skrytá vazba:** na tvar větve se váže `chip_gate.id_z_vetve`
(`chip/(\d+)`) i `hook_chip_gate.VETEV`. Když změníš konvenci a zapomeneš na ně,
**tvrdá brána tiše přestane blokovat** — hook větev nepozná a mlčky pustí merge.
To je nejhorší možný způsob selhání, jaký tenhle projekt zná.

## Issues

- [x] #1 — nová konvence: `ai/chip-NN/nazev` (např. `ai/chip-08/nazvy-vetvi`)
- [x] #2 — `chip_run.py` zakládá větve v novém tvaru; `vetev:` z frontmatteru
      má dál přednost, když je vyplněná
- [x] #3 — `chip_gate.id_z_vetve` rozpozná **oba** tvary — nový `ai/chip-NN/…`
      i starý `chip/NN-…` (v repu existují staré větve, nesmí přestat fungovat)
- [x] #4 — `hook_chip_gate.VETEV` totéž: oba tvary, jinak hook přestane blokovat
- [x] #5 — `chips/TEMPLATE.md`: `vetev:` v šabloně na nový tvar + komentář proč
- [x] #6 — test, který **dokáže**, že hook zamítne merge větve v novém tvaru
      s červenou bránou (regresní pojistka proti tichému vypnutí brány)
- [x] #7 — test pro oba tvary v `id_z_vetve` včetně jednociferného čísla
- [x] #8 — `docs/metodika.md` ani `README.md` neměň — udělá to orchestrátor po merge

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_run.py
tools/chip_gate.py
tools/hook_chip_gate.py
chips/TEMPLATE.md
tests/test_chip_run.py
tests/test_chip_gate.py
```

Nesahej na `chip_common.py`, `chip_lint.py`, `chip_status.py` ani na nový
`chip_review.py` — poslední si nárokuje souběžný chip 07.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] `python tools/chip_run.py 08 --dry-run` ukáže větev v novém tvaru
- [x] `python tools/chip_gate.py --vetev ai/chip-08/nazvy-vetvi` najde brief chipu 08
- [x] `python tools/chip_gate.py --vetev chip/08-nazvy-vetvi` (starý tvar) taky
- [x] test z issue #6 na původní verzi `hook_chip_gate.py` **selže** — ověř to
      a napiš do Logu, jak přesně padal
- [x] pouze standardní knihovna

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_run.py 08 --dry-run
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

- přejmenování **existujících** větví v repu (historie je uživatelova věc)
- změna `chip_common.py`, `chip_lint.py`, `chip_status.py`, `chip_review.py`
- oslabení hooku: kdyby nová konvence šla podchytit jen za cenu, že hook
  přestane rozpoznávat některý případ — **zastav se a zeptej**
- nová závislost mimo stdlib
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- `chip_run.cesty(chip)` skládá větev z `chip.meta["vetev"]` s fallbackem
  `f"chip/{cislo}"` — fallback je to, co se mění.
- `chip_gate.VETEV_CHIP = re.compile(r"chip/(\d+)")` a
  `hook_chip_gate.VETEV = re.compile(r"chip/(\d+)[\w.-]*")`. Nový regex musí
  chytit `ai/chip-08/nazvy-vetvi` i `chip/08-nazvy-vetvi`; pozor, aby
  `ai/chip-08/...` nespadlo do skupiny s číslem `08` omylem přes starý vzor.
- Hook má tři podmínky (merge + chip větev + adresář `chips/`); měníš jen
  rozpoznání větve, ostatní nech být.
- Testy hooku jsou v `tests/test_chip_gate.py`, třída `TestHook` — rozšiřuj je,
  neber je jinam. Vzor volání hooku s podstrčeným stdin je tam připravený.
- Konvence: komentáře a hlášky česky, docstringy vysvětlují *proč*.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-26 | ready | založeno z poznatků NotebookLM (konvence `ai/...` pro větve psané agentem) |
| 2026-07-26 | running | Konvence: `ai/chip-NN/nazev`. Jedno jádro vzoru `(?:\bai/chip-\|\bchip/)(\d+)` ve `chip_gate.VETEV_CHIP` i `hook_chip_gate.VETEV` — jedna zachytávající skupina pro oba tvary, nová alternativa první. |
| 2026-07-26 | running | `chip_run.cesty()`: fallback `f"chip/{id}"` → `vychozi_vetev()` = `ai/chip-NN/nazev`. `vetev:` z frontmatteru má dál přednost, ale **jen když je vyplněná** — prázdná hodnota už neznamená „větev jménem prázdno", nýbrž „odvoď to". |
| 2026-07-26 | running | **Důkaz k issue #6.** Původní `tools/hook_chip_gate.py` (`git show HEAD:`) předložen testům přes `sys.modules`, spuštěna třída `TestHook`: **6 selhání ze 14** (`VETEV = chip/(\d+)[\w.-]*`). Klíčové: `FAIL test_nova_konvence_cervena_brana_zamita` → `AssertionError: '' is not true : hook na větev 'ai/chip-01/pokus' MLČEL — nepoznal ji jako chip větev a merge s červenou bránou by prošel`. Stejně padly `test_nova_konvence_ve_slozenem_prikazu_zamita` a `test_nova_konvence_chybejici_brief_zamita` (prázdný stdout = tiché povolení) a 3 subtesty `test_hook_a_brana_poznaji_stejne_vetve` (`AssertionError: None != '08'` pro `ai/chip-08/nazvy-vetvi`, `ai/chip-8/x`, `origin/ai/chip-08/nazvy-vetvi`). Testy starého tvaru přitom prošly — přesně ten tichý polovičatý stav, který brief popisuje. |
| 2026-07-26 | running | Sada: 237 → 251 testů (+14), 0 selhání. Jen stdlib. |
| 2026-07-26 | running | **T3 / ESKALACE — `tools/chip_new.py` je mimo můj nárok, ale je na TEMPLATE.md navázaný.** Řádek 53 dělá `.replace("vetev: chip/NN-kratky-nazev-s-pomlckami", f"vetev: chip/{cislo}-{nazev}")`. Po změně šablony (issue #5) se ten řetězec nenajde → nový brief si odnese `vetev: ai/chip-NN/kratky-nazev-s-pomlckami` s nedosazeným `NN`. `chip_lint.py` to zachytí jen jako **varování** (`kratky-nazev-s-pomlckami` je v `PLACEHOLDERY`) a až mimo stav `draft`. Nesahal jsem na to. Oprava je jednořádková: `.replace("vetev: ai/chip-NN/kratky-nazev-s-pomlckami", f"vetev: ai/chip-{cislo}/{nazev}")` — nebo řádek z `chip_new.py` vypustit úplně a nechat `vetev:` v šabloně prázdné, `cesty()` už si tvar odvodí sám. |
| 2026-07-26 | running | `vetev:` ve frontmatteru tohoto briefu přepsán na `ai/chip-08/nazvy-vetvi` kvůli DoD („dry-run ukáže větev v novém tvaru"). **Fyzická větev se ale nepřejmenovala** — pořád je to `chip/08-nazvy-vetvi` (přejmenování existující větve = T3). **Merguj `chip/08-nazvy-vetvi`.** Hook i brána oba tvary poznají, takže vynucení funguje v obou případech. |
