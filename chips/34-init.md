---
chip: 34
nazev: init
stav: merged
# `stav:` přepíná ORCHESTRÁTOR, ne agent — mandát agenta je Log a checkboxy.
zavisi_na: 33
repo: ..
greenfield: ne
vetev: ai/chip-34/init
worktree: ../CHIPS-chip-34
---

# CHIP 34 — init: nasazení metody do repa jedním příkazem

Nasazení CHIPS do cizího repa jsou dnes čtyři ruční kroky (složka briefů,
registrace hooku se správnou cestou, review smyčka, ověření hooku oběma směry).
Krok, na který se zapomíná, je právě ten, bez kterého je metoda jen próza.
Chip z nich dělá `python tools/chip_init.py <repo>`.

## Issues

- [x] #1 — `tools/chip_init.py <repo>`: ověří, že `<repo>` je git repo (jinak
      exit 1, nic nezapíše)
- [x] #2 — založí `<repo>/chips/` (když chybí); nic v ní nepřepisuje
- [x] #3 — zaregistruje hook do `<repo>/.claude/settings.json`: `PreToolUse`,
      matcher `Bash|PowerShell`, `shell: bash`, cesta
      `$CLAUDE_PROJECT_DIR/<relativní cesta k tools/hook_chip_gate.py>` —
      relativní, aby fungovala na všech strojích se stejným rozložením
- [x] #4 — existující `settings.json` sloučí: zachová všechny klíče a ostatní
      hooky; když už hook s `hook_chip_gate.py` je, nepřidá druhý; neplatný
      JSON → exit 1, soubor beze změny
- [x] #5 — `--global`: registrace do `~/.claude/settings.json` s absolutní
      cestou (pro sessions s jiným kořenem); když repo leží na jiném disku než
      CHIPS a relativní cesta nejde → použije absolutní a varuje
- [x] #6 — `--hook-timeout N` (výchozí 600 s): plná brána může trvat déle než
      300 s (CHIPS sám 2026-10-16: ~360 s)
- [x] #7 — nainstaluje review smyčku (`chip_install.install`) do `~/.claude`;
      `--no-review` krok vynechá
- [x] #8 — samotest hooku nad cílovým repem: větev `ai/chip-99/does-not-exist`
      musí dostat `deny`, obyčejná větev nesmí; když (a) neprojde → exit 1
      s hláškou
- [x] #9 — `--check`: nic nezapisuje, vypíše stav všech kroků, exit 1 když
      cokoli chybí
- [x] #10 — idempotence: druhé spuštění nic nezmění (stejné bajty
      `settings.json`), exit 0
- [x] #11 — závěr: vypíše další krok (`chip_new.py 01 <nazev> --repo <repo>
      --dir <repo>/chips`) a že živé ověření v session je
      `git merge ai/chip-99/does-not-exist` po restartu
- [x] #12 — `tests/test_chip_init.py` pokrývá #1–#10 na dočasných repech
- [x] #13 — `README.md` + `README.cs.md`: nasazení jedním příkazem nahoře
      v rychlém startu, ruční registrace hooku zůstává jako vysvětlení

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_init.py          # nový
tests/test_chip_init.py     # nový
README.md
README.cs.md
```

## Definition of done

- [x] `python -m unittest discover -s tests` zelené, počet = výchozí stav
      + nové testy z `test_chip_init.py`
- [x] na čerstvém dočasném git repu: `chip_init.py <tmp> --no-review` exit 0,
      vznikne `chips/` a `.claude/settings.json`, jehož cesta k hooku po
      dosazení `<tmp>` za `$CLAUDE_PROJECT_DIR` ukazuje na existující
      `tools/hook_chip_gate.py`
- [x] druhé spuštění: exit 0 a SHA-256 `settings.json` stejné
- [x] `settings.json` s klíčem `permissions` a cizím hookem: po init oba
      zůstanou, hook CHIPS přibude jednou
- [x] neplatný JSON v `settings.json`: exit 1, SHA beze změny
- [x] `--check` na čerstvém repu: exit 1, žádný soubor nevznikne
- [x] samotest: hook na `ai/chip-99/does-not-exist` vrátí `deny` (test volá
      skutečný `hook_chip_gate.py` přes subprocess)
- [x] strength test: kopie `chip_init.py`, která settings přepíše místo
      sloučení, spadne aspoň v jednom testu
- [x] `python tools/chip_lint.py` exit 0; `python tools/chip_init.py --help`
      exit 0

## Ověření (brána)

```bash
python -m unittest discover -s tests
python tools/chip_lint.py
python tools/chip_init.py --help
```

## Eskalace — co NEROZHODOVAT sám (T3)

- změna `hook_chip_gate.py`, `chip_gate.py` nebo `.claude/settings.json`
  CHIPSu samotného
- zápis mimo `<repo>/chips/`, `<repo>/.claude/settings.json`,
  `~/.claude/settings.json` (jen s `--global`) a cíle review smyčky
- mazání čehokoli, přepis existujícího hooku jiného nástroje
- nová závislost
- soubor mimo „Dotčené soubory"

## Kontext pro agenta

- Nový kód anglicky, uživatelský povrch anglicky (repo je veřejné), bez
  domovské cesty autora v trackovaných souborech.
- Hook čte JSON ze stdin (`tool_input.command`, `cwd`) a odmítnutí vrací jako
  `hookSpecificOutput.permissionDecision = "deny"`.
- Soukromý projekt mimo tento repo má hook registrovaný ručně s cestou
  `$CLAUDE_PROJECT_DIR/../../../CHIPS/tools/hook_chip_gate.py` — přesně tvar,
  který má init vyrobit.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-10-16 | draft | založeno |
| 2026-10-16 | ready | brief vyplněn; uživatel chce „jeden příkaz k nasazení metody" |
| 2026-10-16 | gated | `tools/chip_init.py` (4 kroky: `chips/`, hook do `.claude/settings.json` s cestou relativní k `$CLAUDE_PROJECT_DIR` a sloučením, review smyčka přes `chip_install`, samotest skutečného hooku oběma směry) + 19 testů. **Brána zelená** ve vývojovém repu (849 testů, lint 0 chyb, `--help` exit 0). Kouřový test na čerstvém repu: vše ok včetně samotestu. **Důkaz síly:** init, který settings přepíše místo sloučení → 2 testy červené. **Nález během práce:** `registered()` padal s AttributeError na `hooks` jiného typu než objekt → odolný vůči tvaru, odmítnutí řeší `with_hook` (test). |
| 2026-10-16 | merged | `chip_gate.py 34` ZELENÁ, sloučeno `--no-ff`, worktree uklizen. Živé ověření: `chip_init.py --check` nad ručně nasazeným soukromým projektem = 4/4 ok (`chips/`, hook, review smyčka, samotest). |
| 2026-10-25 | merged | **Port do veřejného repa `chips-method`.** Nástroj a testy převzaté beze změny; místo `docs/install.md` (ve veřejné verzi není) odkazuje docstring na README. Počty testů v řádcích výše platí pro vývojové repo. |
