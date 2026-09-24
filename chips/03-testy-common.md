---
chip: 03
nazev: testy-common
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-03/testy-common
worktree: ../CHIPS-chip-03
---

# CHIP 03 — testy pro `chip_common.py`

Parser briefů je vlastní mini-implementace bez PyYAML. Když tiše přestane
rozumět frontmatteru nebo poznámkám za cestou, rozpadne se všechno ostatní.

## Issues

- [x] #1 — frontmatter: klíč/hodnota, komentář za `#`, chybějící frontmatter, prázdná hodnota
- [x] #2 — sekce: `## Nadpis` s diakritikou i s ozdobami (`## Dotčené soubory ⚠️ NÁROK`) se najde přes `najdi()`
- [x] #3 — `soubory_detail()`: poznámka za `#` se odřízne, `# nový` nastaví příznak, `# poznámka` ne
- [x] #4 — `soubory_detail()`: řádek začínající `#` se ignoruje, prázdné řádky taky, koncové `/` se ořízne
- [x] #5 — `soubory()` vrací cesty bez poznámek (jinak by se rozbila kontrola kolizí)
- [x] #6 — cesty jen z ``` bloků; text mimo blok se nepočítá
- [x] #7 — `repo_path()`: absolutní cesta, relativní (od adresáře s briefy), `~`, chybějící klíč → `None`
- [x] #8 — `zavislosti()`: prázdné, `-`, `nic`, `[]`, `01, 2` (doplnění nuly na dvě místa)
- [x] #9 — `issues()`: `- [ ]` i `- [x]`, odsazené, řádky mimo sekci se nepočítají
- [x] #10 — `id` a `nazev` fallback z názvu souboru, když chybí ve frontmatteru
- [x] #11 — `nacti_vse()` vynechá `TEMPLATE.md`, ale s `vcetne_sablony=True` ho vrátí; neexistující adresář → prázdný seznam
- [x] #12 — `_norm()`: diakritika, interpunkce, vícenásobné mezery

## Dotčené soubory  ⚠️ NÁROK

```
tests/test_chip_common.py    # nový
```

Nesmíš měnit `tools/` ani nic mimo tento seznam. Když test odhalí chybu v
`chip_common.py`, **neopravuj ji** — zapiš ji do sekce Log a označ test
`@unittest.expectedFailure` s komentářem proč.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] alespoň 20 testovacích metod, každá issue výše pokrytá aspoň jednou
- [x] testy si staví vlastní dočasné soubory (`tempfile`) a po sobě uklidí
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

- změna chování `tools/chip_common.py` (je mimo tvůj nárok, nárokuje si ho orchestrátor)
- nová závislost mimo stdlib
- změna formátu frontmatteru nebo šablony briefu
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- Testovaný modul: `tools/chip_common.py`. Import:
  `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))`.
- `CHIPS_DIR` je **globální stav** modulu — přepíná se `nastav_chips_dir(cesta)`.
  V `tearDown` ho vrať na původní hodnotu, jinak si testy ovlivní navzájem.
- `parse(path)` vrací `Chip`; `nacti_vse()` čte celý adresář a řadí podle jména.
- Poznámka za cestou se pozná regexem `KOMENTAR` (`\s+#\s*(.*)$`) a příznak
  „nový" regexem `NOVY` (`^(nov[ýy]|new)\b`, case-insensitive) — tedy `# nový`,
  `# novy soubor`, `# new` ano; `# bude nový` ne (nezačíná tím slovem).
- Soubory piš v UTF-8 (`Path.write_text(..., encoding="utf-8")`) — bez toho
  Windows rozbije diakritiku a testy budou padat z jiného důvodu, než myslíš.
- Konvence: názvy testů a komentáře česky, jako zbytek projektu.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-26 | ready | založeno orchestrátorem |
| 2026-07-26 | hotovo | `tests/test_chip_common.py`: 68 testovacích metod v 10 třídách, issues #1–#12 pokryté. Brána zelená: `python -m unittest discover -s tests -v` → `Ran 68 tests … OK`, `python tools/chip_lint.py` → `OK — 0 chyb, 0 varování`, exit 0. |
| 2026-07-26 | nález | **Prázdná hodnota ve frontmatteru není totéž co chybějící klíč.** `chip:` / `nazev:` / `stav:` bez hodnoty uloží `""`, takže `meta.get(klic, default)` vrátí prázdný řetězec a fallback (`path.stem`, `"draft"`) se neuplatní. Důsledek: `chip_lint.py` takový brief nahlásí jako „neplatný stav ''“, ne jako chybějící údaj. Nejde o rozpor se zadáním (issue #10 mluví o *chybějícím* klíči), takže bez `@unittest.expectedFailure` — chování je zafixované charakterizačním testem `TestIdentita.test_prazdna_hodnota_fallback_nespousti`. Případná změna je zásah do `tools/chip_common.py` = mimo nárok tohoto chipu, rozhodne orchestrátor. |
| 2026-07-26 | nález | Ostatní chování odpovídá briefu — žádná chyba v `chip_common.py` nenalezena, žádný test není `expectedFailure`. Ověřené hraniční případy nad rámec issues: neuzavřený frontmatter (bez druhého `---` se meta neparsuje), `###` nadpis nevytváří sekci, `#` bez mezery před sebou se nepovažuje za poznámku (`src/soubor#1.py` zůstane celá cesta), `nastav_chips_dir(None/"")` záměrně nemění globální `CHIPS_DIR`. |
| 2026-07-26 | pozn. | `stav:` ve frontmatteru ponechán na `ready` — přepnutí na `gated`/`merged` je krok orchestrátora, ne agenta chipu. Adresář `tests/` je nový (v repu dosud nebyl), `__init__.py` není potřeba (`unittest discover` si cestu doplní sám). |
| 2026-07-26 | merged | brána ověřena orchestrátorem nezávisle (testy + lint), sloučeno do master, worktree uklizen |
| 2026-07-27 | merged | Sjednocení složky: `vetev:` převedena na konvenci `ai/chip-NN/<nazev>` (zavedl chip 08 — tenhle chip běžel ještě pod starým tvarem `chip/NN-<nazev>`), doplněn slovník stavů do komentáře u `stav:`. Obsah chipu nedotčen. |
