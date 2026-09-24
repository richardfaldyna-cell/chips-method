---
chip: 04
nazev: run-spusteni
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-04/run-spusteni
worktree: ../CHIPS-chip-04
---

# CHIP 04 — `chip_run.py`: spuštění okna a testovatelnost

`chip_run.py` dnes udělá worktree a vypíše zadání, které musíš ručně
zkopírovat. Zároveň je celý v jedné `main()`, takže se nedá testovat.

## Issues

- [x] #1 — vytáhnout z `main()` čistou funkci `cesty(chip)` → `(repo, vetev, worktree)`, bez vedlejších efektů
- [x] #2 — vytáhnout čistou funkci `zadani(chip, worktree, vetev)` → text zadání (dnes inline `ZADANI.format(...)`)
- [x] #3 — `--spustit`: po založení worktree rovnou spustit Claude Code ve worktree se zadáním
- [x] #4 — když `claude` není na PATH, `--spustit` skončí srozumitelnou hláškou a kódem 1 (ne tracebackem)
- [x] #5 — `--stav`: po úspěšném založení worktree přepsat ve frontmatteru briefu `stav: ready` → `running`
- [x] #6 — přepis frontmatteru zachová zbytek souboru bajt v bajt (včetně CRLF a diakritiky)
- [x] #7 — `--dry-run` nesmí sáhnout na disk ani spustit git; platí i pro `--stav` a `--spustit`
- [x] #8 — návratové kódy: chip nenalezen = 1, chybí `repo:` = 1, repo není git = 1, worktree už existuje = 1, stav != `ready` = 1
- [x] #9 — testy pro `cesty()`, `zadani()`, přepis stavu, chybějící `claude` a všechny návratové kódy z #8
- [x] #10 — aktualizovat docstring modulu (dnes tvrdí „Nespouští Claude Code")

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_run.py
tests/test_chip_run.py       # nový
```

Nesmíš měnit `chip_common.py` ani `chip_lint.py` — když ti tam něco chybí,
dopočítej si to u sebe a zapiš do Logu, že by to patřilo do společného modulu.

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] `python tools/chip_run.py 04 --dry-run` funguje dál jako dnes (vypíše příkazy, nic neprovede)
- [x] `cesty()` i `zadani()` jsou volatelné bez gitu a bez disku, pokryté testy
- [x] žádný test nespustí skutečný `git worktree add` ani skutečné `claude` (mockuj `subprocess`)
- [x] pouze standardní knihovna (žádné nové závislosti)

## Ověření (brána)

Bez zelené brány se **nemerguje**. Když selže → stav `blocked`, popiš proč v Logu.

```bash
python -m unittest discover -s tests -v
python tools/chip_run.py 04 --dry-run
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Při zásahu do čehokoli z tohoto seznamu: **zastav, zapiš do Logu, nehádej.**

- změna `chip_common.py` nebo `chip_lint.py` (nárokují si je jiné chipy)
- nová závislost mimo stdlib
- jakýkoli `git push`, `git merge` nebo zápis do jiné větve
- automatické mazání worktree bez `--uklid`
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- Dnešní stav: `git()` je tenký wrapper nad `subprocess.call`, `ZADANI` je
  šablona textu, všechno ostatní je v `main()`. Zachovej stávající chování
  a hlášky — mění se struktura, ne UX.
- `--spustit` spouštěj přes `subprocess.call([claude_exe, zadani], cwd=worktree)`,
  cestu hledej `shutil.which("claude")`. Na Windows to může být `claude.cmd` —
  `shutil.which` to vyřeší, natvrdo psaný název ne.
- Přepis stavu dělej **textově** (najdi řádek `stav:` mezi prvními `---`), ne
  přes přeparsování a serializaci — parser v `chip_common` je jednosměrný a
  serializaci neumí.
- Testy: `unittest.mock.patch("subprocess.call")` a `patch("shutil.which")`.
  Dočasné repo si vyrob přes `tempfile.TemporaryDirectory()`; `git init` v testu
  nedělej, stačí vytvořit prázdný adresář `.git`, protože kód testuje jen jeho existenci.
- `chip_common.nastav_chips_dir()` přepíná adresář s briefy; v `tearDown` ho vrať zpátky.
- Import v testu: `sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))`.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-26 | ready | založeno orchestrátorem |
| 2026-07-26 | running | refaktor: `cesty()`, `zadani()`, `prepis_stav()` vytaženy z `main()`; `main(argv)` kvůli testům |
| 2026-07-26 | running | `--spustit` kontroluje `shutil.which("claude")` **před** `git worktree add` — jinak by po chybějícím claude zůstal poloviční worktree, který blokuje další spuštění |
| 2026-07-26 | running | `prepis_stav()` (textový zápis frontmatteru) by patřil do `chip_common.py`, ale ten si nárokuje jiný chip → ponecháno lokálně v `chip_run.py`, ke sloučení po merge |
| 2026-07-26 | gated | brána zelená: 29 testů OK, `--dry-run` výstup shodný s předchozím chováním, `chip_lint.py` 0 chyb |
| 2026-07-26 | merged | brána ověřena orchestrátorem nezávisle (testy + lint), sloučeno do master, worktree uklizen |
| 2026-07-27 | merged | Sjednocení složky: `vetev:` převedena na konvenci `ai/chip-NN/<nazev>` (zavedl chip 08 — tenhle chip běžel ještě pod starým tvarem `chip/NN-<nazev>`), doplněn slovník stavů do komentáře u `stav:`. Obsah chipu nedotčen. |
