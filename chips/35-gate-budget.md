---
chip: 35
nazev: gate-budget
stav: merged
# `stav:` přepíná ORCHESTRÁTOR, ne agent — mandát agenta je Log a checkboxy.
zavisi_na: 34
repo: ..
greenfield: ne
vetev: ai/chip-35/gate-budget
worktree: ../CHIPS-chip-35
---

# CHIP 35 — gate budget: brána při vypršení zamítá

Claude Code bere vypršení hooku `PreToolUse` jako neblokující chybu: příkaz
proběhne. Brána, která běží déle než timeout hooku (CHIPS sám: plná sada
~360 s, timeout 300 s), tak merge **pustí neověřený** — fail-open přesně tam,
kde má metoda stát. Chip dává hooku vlastní rozpočet kratší než timeout: když
ho brána přečerpá, hook zamítne sám.

## Issues

- [x] #1 — `chip_gate.brana(c, repo, deadline=None)`: volitelný absolutní
      termín (`time.monotonic()`); timeout každého příkazu = min(dosavadních
      600 s, zbývající čas); po vyčerpání `False` s hláškou, že došel rozpočet
      — nikdy `True`
- [x] #2 — `hook_chip_gate.py --budget N` (sekundy): termín pro `brana`;
      vyčerpání → `deny` s hláškou, jak bránu ověřit ručně (`chip_gate.py NN`)
      a že je třeba zvýšit timeout hooku a `--budget`
- [x] #3 — bez `--budget` výchozí rozpočet 240 s — pod timeoutem 300 s starších
      registrací, takže i ty zamítají místo propuštění; neplatná hodnota
      `--budget` → výchozí, hook nespadne
- [x] #4 — rozpočet zahrnuje i čas před bránou (start hooku), ne jen příkazy
      brány
- [x] #5 — `chip_init.py` zapisuje příkaz s `--budget <timeout - 60>`;
      `--hook-timeout` pod 90 → exit 2 s hláškou
- [x] #6 — `.claude/settings.json` CHIPSu: timeout 600, příkaz s `--budget 540`
- [x] #7 — testy: `brana` s prošlým termínem nespustí nic a vrátí `False`,
      příkaz delší než zbytek rozpočtu → `False`; hook s `--budget` přes
      subprocess na pomalé bráně → `deny`; `chip_init` zapíše `--budget`
- [x] #8 — README (CS i EN): ruční registrace s `--budget`, odstavec proč
      (timeout = fail-open); `.html` přegenerovat

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_gate.py
tools/hook_chip_gate.py
tools/chip_init.py
.claude/settings.json       # nový
tests/test_chip_gate.py
tests/test_chip_init.py
README.md
README.cs.md
```

## Definition of done

- [x] `python -m unittest discover -s tests` zelené, počet = výchozí stav
      + nové testy
- [x] hook s `--budget 2` nad chipem, jehož brána je
      `python -c "import time; time.sleep(30)"`, vrátí `deny` do 15 s
- [x] strength test: `brana`, která termín ignoruje, shodí aspoň jeden test
- [x] `python tools/chip_lint.py` exit 0;
      `python tools/hook_chip_gate.py --budget 5 < /dev/null` exit 0

## Ověření (brána)

```bash
python -m unittest discover -s tests
python tools/chip_lint.py
python tools/chip_init.py --help
```

## Eskalace — co NEROZHODOVAT sám (T3)

- změna rozhodovací logiky hooku mimo rozpočet (co je merge, co je chip
  větev, kde se ověřuje)
- jakákoli cesta, kdy vyčerpaný rozpočet vede na propuštění
- nová závislost
- soubor mimo „Dotčené soubory"

## Kontext pro agenta

- Hook vrací odmítnutí přes `zamitni()` (`hookSpecificOutput.permissionDecision
  = "deny"`) a exit 0.
- `chip_gate.spust` už timeout převádí na exit 124 — stačí mu předat menší číslo.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-10-16 | draft | založeno |
| 2026-10-16 | ready | z TODO po chipu 34: timeout hooku 300 s < brána ~360 s; zjištěno, že vypršení = fail-open |
| 2026-10-16 | gated | `chip_gate.brana(deadline)` + `COMMAND_TIMEOUT`; hook `--budget` (výchozí 240 s, `START` při spuštění skriptu, `main(argv, start)`); `chip_init` zapisuje `--budget timeout-60`, min. timeout 90, poznámka u registrace bez `--budget`; `.claude/settings.json` 600/540. **Nález během práce:** `spust()` se `subprocess.run(shell=True, timeout)` na Windows zabil jen shell, vnuk držel rouru → 30 s příkaz pod 2 s timeoutem trval 30 s; dosavadní 600 s timeout brány tedy nic nezastavoval. `Popen` + `kill_tree` (`taskkill /T`, `killpg`) + test. **Brána zelená** ve vývojovém repu (869 testů, lint 0 chyb). **Důkaz síly:** brána ignorující termín (v oddělené kopii) → 6 testů červených. |
| 2026-10-16 | merged | `chip_gate.py 35` ZELENÁ, sloučeno `--no-ff`, worktree uklizen. |
| 2026-10-25 | merged | **Port do veřejného repa `chips-method`.** Hlášky brány a hooku zůstávají české (značka `chip_gate.ROZPOCET_VYCERPAN`, podle které hook pozná vyčerpání). Vývojová verze chipu měla navíc opravu parseru na anglický klíč `status:`; veřejný parser zná jen `stav:`, takže tady není co opravovat. Počty testů v řádcích výše platí pro vývojové repo. |
