---
chip: 12
nazev: slice-run
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
vetev: ai/chip-12/slice-run
worktree: ../CHIPS-chip-12
---

# CHIP 12 — zastaralé dosazení v chip_slice a useknuté zadání v chip_run

Dva nálezy z code review. První je zvlášť poučný: přesně tahle chyba už
byla jednou opravena v `chip_new.py` — ale oprava se zastavila u prvního
výskytu vzoru a druhý (v `chip_slice.py`) zůstal.

## Issues

- [x] #1 — **`chip_slice.text_briefu()` dosazuje starý tvar `vetev:`**
      (ř. ~271): nahrazuje `vetev: chip/NN-kratky-nazev-s-pomlckami`, ale
      šablona má od včerejška `vetev: ai/chip-NN/kratky-nazev-s-pomlckami`.
      `.replace()` bez shody tiše selže → vygenerovaný brief nese doslovný
      placeholder, chip_run z něj založí nesmyslnou větev a hook ji nepozná.
      Oprav dosazení na aktuální tvar šablony.
- [x] #2 — **test proti rozejití se šablonou** — stejný princip jako
      `test_kazdy_replace_v_chip_new_ma_vzor_v_sablone` v
      `tests/test_chip_new.py`: projdi všechny `.replace("…")` v
      `chip_slice.py` a ověř, že vzor v `TEMPLATE.md` existuje. Tím se
      tahle třída chyb zamkne i pro druhý výskyt.
- [x] #3 — **`chip_run --spustit` přes `claude.cmd` usekne zadání**
      (ř. ~177): víceřádkové zadání jako jeden argv element cmd.exe usekne
      na prvním newline — agent dostane jen první řádek. Oprav: zadání
      předávat bezpečně i pro .cmd shim — zapiš ho do dočasného souboru
      a spusť `claude "$(< soubor)"`-ekvivalent NE; nejjednodušší robustní
      cesta na Windows: `subprocess.run([exe], input=zadani, ...)` nefunguje
      (claude čte prompt z argv) → použij `subprocess.list2cmdline` jen pro
      skutečné .exe, a pro `.cmd`/`.bat` shim zadání ulož do temp souboru
      a předej `claude --prompt-file` NEEXISTUJE-LI ten přepínač, pak:
      detekuj `.cmd`/`.bat` příponu a v tom případě spusť přes
      `["cmd", "/c", exe, zadani]` s nahrazením newline za mezery NE — to
      mění obsah. Rozhodni podle skutečného chování: ověř si na místě, co
      `claude` na tomhle stroji je (`shutil.which`), a zvol řešení, které
      **prokazatelně doručí celé víceřádkové zadání**. Pokud žádné bezpečné
      řešení pro .cmd shim není, je legitimní odpověď: u .cmd shimu
      `--spustit` odmítnout se srozumitelnou hláškou a vypsat zadání
      k ručnímu vložení (dnešní chování bez `--spustit`).
- [x] #4 — test na #3: mock `shutil.which` vrací cestu s `.cmd` i `.exe`
      a ověř zvolené chování (doručení celého zadání / srozumitelné odmítnutí)
- [x] #5 — testy z #2 a #4 musí na PŮVODNÍ verzi selhat (doloženo v Logu)
- [x] #6 — celá stávající sada projde beze změny počtu selhání

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_slice.py
tools/chip_run.py
tests/test_chip_slice.py
tests/test_chip_run.py
```

Nesahej na `chip_new.py` ani `tests/test_chip_new.py` (vzor pro #2 z něj jen
čti), na `TEMPLATE.md`, ani na soubory chipů 10 a 11 (`hook_chip_gate.py`,
`chip_gate.py`, `chip_lint.py`, `chip_common.py` + jejich testy).

## Definition of done

- [x] `python -m unittest discover -s tests -v` projde, 0 selhání
- [x] `chip_slice --zapsat` do temp adresáře vygeneruje brief s dosazenou
      větví `ai/chip-NN/<nazev>` (skutečné NN a název, žádný placeholder) —
      spusť doopravdy, výsledek do Logu
- [x] test rozejití se šablonou existuje pro chip_slice (#2)
- [x] chování `--spustit` s .cmd shimem je definované a otestované (#3, #4)
- [x] pouze standardní knihovna

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

- změna `TEMPLATE.md`, `chip_new.py` nebo souborů chipů 10/11
- u #3: kdyby jediné řešení vyžadovalo novou závislost nebo změnu chování
  `claude` CLI — zastav se a zapiš; odmítnutí s hláškou je přijatelný výsledek
- nová závislost mimo stdlib
- soubor mimo sekci „Dotčené soubory"

## Kontext pro agenta

- Vzor testu proti rozejití: `tests/test_chip_new.py`,
  `test_kazdy_replace_v_chip_new_ma_vzor_v_sablone` — čti, neupravuj.
- `chip_slice.text_briefu()` čte šablonu z `chips/TEMPLATE.md` za běhu;
  dosazení dělá sadou `.replace()`. Zkontroluj VŠECHNY, ne jen `vetev:` —
  nález mluví o ř. 271 i 252.
- Na tomhle stroji je `claude` nativní `.exe` (`%USERPROFILE%\.local\bin\claude.exe`),
  ale test musí pokrýt i `.cmd` větev mockem — jiné stroje mají npm shim.
- Regresní důkaz: `git show HEAD:tools/chip_slice.py` + `sys.modules`.
- Konvence: hlášky česky, dvě mezery odsazení.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-27 | ready | založeno z code review (nálezy 0 a 8) |
| 2026-07-27 | ready | #1: v `text_briefu()` opraven vzor na `vetev: ai/chip-NN/kratky-nazev-s-pomlckami`. Zkontrolovány VŠECHNY `.replace()` v souboru: rozešlý byl jen `vetev:` (pův. ř. 271 v těle fce začínající na ř. 252 — druhý údaj nálezu je start `text_briefu`); ostatních 7 vzorů v šabloně sedí. Mimo šablonu je jen normalizace lomítek v `cesty_z_textu`/`nacti_json` — proto test #2 scanuje zdroják `text_briefu()`, ne celý modul. |
| 2026-07-27 | ready | #3 rozhodnutí: `.cmd`/`.bat` shim se u `--spustit` ODMÍTÁ (`je_cmd_shim()` + hláška) a běh degraduje na dnešní chování bez `--spustit`: worktree se založí, zadání se vypíše k ručnímu vložení, rc 0. Důvod: cmd.exe čte příkazovou řádku jen po první newline → useknutí; náhrada newline mění obsah, `--prompt-file` u claude neexistuje a temp soubor by chtěl změnu chování CLI (T3). Ověřeno na místě: zdejší `claude` je nativní `%USERPROFILE%/.local/bin/claude.EXE` (`shutil.which`) — `.exe` větev beze změny předává celé víceřádkové zadání jedním argv elementem (test `test_exe_dostane_cele_viceradkove_zadani`). |
| 2026-07-27 | ready | #5 regresní důkaz (git show HEAD: + sys.modules, testy z #2 a #4 proti původní verzi): 4/4 FAIL. Hlášky: „AssertionError: 'vetev: chip/NN-kratky-nazev-s-pomlckami' not found in …TEMPLATE.md — dosazení tiše propadne"; „'vetev: ai/chip-01/navrh-01' not found in …vetev: ai/chip-NN/kratky-nazev-s-pomlckami…"; „'C:/fake/claude.cmd' != 'git' — kromě gitu se nesmí spustit nic" (mock zachytil spuštění shimu s celým víceřádkovým zadáním); „False is not true" (.BAT větev). Na opravené verzi 4/4 OK. |
| 2026-07-27 | ready | DoD: `unittest discover` 366 testů, 0 selhání (před změnou 360, 0 selhání → beze změny počtu selhání, +6 testů); `chip_lint.py` rc 0 (3 varování o placeholderech existovala už před chipem). Skutečný běh `chip_slice --todo … --zapsat <temp>`: „zapsáno 1 draft briefů", frontmatter obsahuje `vetev: ai/chip-01/navrh-01`, žádný placeholder ze šablony. Jen stdlib (`inspect`, `re`, `unittest.mock`). |
