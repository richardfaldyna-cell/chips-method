---
chip: 33
nazev: review-loop
stav: merged
# `stav:` přepíná ORCHESTRÁTOR, ne agent — mandát agenta je Log a checkboxy.
zavisi_na:
repo: ..
greenfield: ne
vetev: ai/chip-33/review-loop
worktree: ../CHIPS-chip-33
---

# CHIP 33 — review loop: critic + judge jako součást CHIPS

Role reviewera (§ 9 metodiky) dnes existuje jen jako text, který vypíše
`chip_review.py --zadani`, a smyčka critic → judge → oprava žije v jednom
projektu jako jeho vlastní zadání a kopie rolí. Chip z ní dělá součást CHIPS:
dvě definice subagentů, skill, který smyčku řídí se stropy, a instalátor,
který je dostane do `~/.claude` (nebo do `.claude` jednoho projektu).

## Issues

- [x] #1 — `integrations/claude-code/agents/chip-critic.md`: subagent, čerstvý
      kontext, hodnotí diff chipu proti briefu (Issues, DoD, nárok, T3), nálezy
      A/B/C s citací `soubor:řádek`, smí spustit testy a dočasně mutovat kód,
      nikdy nic nenechá změněné, nic neopravuje
- [x] #2 — `integrations/claude-code/agents/chip-judge.md`: subagent jen pro
      čtení; ověří citace nálezů v kódu, přijme / zamítne, vrátí právě jeden
      verdikt `COMPLETE` / `CONTINUE` / `ESCALATE` / `IMPOSSIBLE`; o merge
      nerozhoduje
- [x] #3 — `integrations/claude-code/skills/chip-review-loop/SKILL.md`:
      `/chip-review-loop NN [--dir <briefs>]` — předpoklady (brána zelená,
      worktree čistý), `chip_review.py` jako strojové podklady, critic,
      kontrola čistoty worktree po criticovi, judge, akce podle verdiktu
- [x] #4 — stropy smyčky ve skillu: max 3 kola, stejný HEAD jako minulé kolo →
      `ESCALATE`, tentýž nález přetrvá 2 kola → `ESCALATE`, soubor mimo nárok
      (exit 1 `chip_review.py`) → `ESCALATE` bez critica
- [x] #5 — záznam kol mimo repo:
      `<git common dir>/chips-review/NN/round-K-{evidence.txt,critic.json,judge.json}`
      — nejde do commitu, přežije `--uklid`, navazuje se z něj po přerušení
- [x] #6 — nálezy třídy C se nesbírají do opravy, ale do `queue.md` pro jeden
      navazující chip (§ 9: „zabal nálezy review do jednoho chipu")
- [x] #7 — `tools/chip_install.py`: zkopíruje tři soubory do `~/.claude` nebo
      `--target <dir>`, zástupný symbol `{{CHIPS_TOOLS}}` nahradí absolutní
      cestou k `tools/` tohoto klonu
- [x] #8 — `chip_install.py` nepřepíše cizí změnu: odlišný cílový soubor →
      exit 1 a beze změny, přepis jen s `--force`
- [x] #9 — `chip_install.py --check`: nic nezapisuje, exit 1 když soubor chybí
      nebo se liší od vyrenderovaného zdroje (zastaralá instalace po `git pull`)
- [x] #10 — `tests/test_chip_install.py`: instalace do prázdného cíle,
      idempotence, ochrana odlišného souboru, `--force`, `--check` ve všech
      třech stavech, nic nezapisuje; kontrakt zdrojů (frontmatter `name` =
      jméno souboru, judge bez nástrojů pro zápis, critic bez Write/Edit,
      skill obsahuje kontrolu `git status --porcelain`)
- [x] #11 — `docs/metodika.md` + `docs/methodology.md`: nový oddíl o review
      smyčce — co judge smí a nesmí (§ 6: není to hlasování, o merge rozhoduje
      brána a člověk), třídy nálezů pro kód, stropy, kdy smyčku nepouštět
- [x] #12 — `README.md` + `README.cs.md`: odstavec o review smyčce a řádky
      v layoutu; `.html` přegenerovat

## Dotčené soubory  ⚠️ NÁROK

```
integrations/claude-code/agents/chip-critic.md          # nový
integrations/claude-code/agents/chip-judge.md           # nový
integrations/claude-code/skills/chip-review-loop/SKILL.md    # nový
tools/chip_install.py          # nový
tests/test_chip_install.py     # nový
docs/metodika.md
docs/methodology.md
README.md
README.cs.md
```

## Definition of done

- [x] `python -m unittest discover -s tests` zelené a počet testů = výchozí
      stav + nové testy z `test_chip_install.py` (žádný starý test nezmizel)
- [x] `python tools/chip_install.py --target <tmp>` vytvoří přesně 3 soubory;
      žádný neobsahuje `{{CHIPS_TOOLS}}`; skill obsahuje absolutní cestu
      k `tools/` klonu
- [x] druhé spuštění téhož příkazu: exit 0, 0 zapsaných souborů
- [x] po ruční změně jednoho cílového souboru: `chip_install.py --target <tmp>`
      exit 1 a soubor beze změny (SHA stejné); `--force` exit 0 a soubor = zdroj
- [x] `chip_install.py --check --target <prázdný tmp>` exit 1 a adresář
      zůstane prázdný
- [x] strength test: kopie `chip_install.py`, která přepisuje odlišné soubory
      bez `--force`, spadne aspoň v jednom testu `test_chip_install.py`
- [x] `python tools/chip_install.py --help` exit 0
- [x] `python tools/chip_lint.py` exit 0

## Ověření (brána)

```bash
python -m unittest discover -s tests
python tools/chip_lint.py
python tools/chip_install.py --help
```

## Eskalace — co NEROZHODOVAT sám (T3)

- změna chování `chip_review.py`, `chip_gate.py` nebo hooku — review smyčka
  je nad nimi, nesmí je měnit
- skill nebo judge, který sám merguje, přepíná `stav:` briefu nebo obchází bránu
- nová závislost (jádro zůstává bez závislostí)
- zápis instalátoru mimo `--target` / `~/.claude`, mazání souborů v cíli
- soubor mimo „Dotčené soubory"

## Kontext pro agenta

- Vzor rolí: smyčka generator / critic / judge pro PRD (soukromý projekt mimo
  tento repo); tady jde o **kód** a rubrikou je brief chipu, ne obecná rubrika.
- Uživatelský povrch nových souborů (definice agentů, skill, `--help`, výstup
  instalátoru) anglicky — jsou pro cizího uživatele; nový kód anglicky včetně
  identifikátorů. Starý český kód se nepřejmenovává.
- Repo je veřejné: žádné jméno klienta ani domovská cesta autora
  v trackovaných souborech.
- Testy: stdlib `unittest`, vlastní `tempfile` fixture, úklid po sobě.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-10-16 | draft | založeno |
| 2026-10-16 | ready | brief vyplněn; zdroje mimo `.claude/` CHIPSu, aby session v tomto repu nenačetla nevyrenderovanou kopii |
| 2026-10-16 | gated | 3 zdroje v `integrations/claude-code` (chip-critic: Read/Grep/Glob/Bash, mutace a povinně čistý strom; chip-judge: jen čtení, 4 verdikty; skill `/chip-review-loop` se stropy 3 kola / stejný HEAD / opakovaný nález / soubor mimo nárok, záznam kol v `.git/chips-review/NN`), `tools/chip_install.py` + 23 testů. **Brána zelená** ve vývojovém repu (827 testů, lint 0 chyb, `--help` exit 0). **DoD ručně:** 3 soubory, 0× placeholder, absolutní cesta k `tools`; druhý běh 0 zapsaných; upravený judge odmítnut (SHA beze změny), `--force` přepsal; `--check` na prázdném cíli exit 1 a nic nezapsal. **Důkazy síly:** (a) bez ochrany odlišného souboru → 1 test červený; (b) razítko vždy platné → 3 testy červené. **Nález během práce:** po `git pull` by instalátor bez `--force` odmítl starou neupravenou kopii → přidáno razítko sha256 na konci souboru (stará kopie se aktualizuje, ručně upravená ne); a placeholder se vyrenderoval i ve větě, která ho popisovala → přeformulováno. |
| 2026-10-16 | gated | **Review smyčkou z tohoto chipu (první ostrý běh):** kolo 1 critic 0 A / 2 B / 3 C, judge CONTINUE — přijato B-1 (pravidlo na opakované id nemohlo platit, id se nerecyklují; přetrvání se pozná podle stavu `persists`/`regressed`) a B-2 (řádek Logu za každé kolo špinil trackovaný brief a shodil kontrolu čistého stromu; log kol do `.git/chips-review/NN/log.md`, do briefu jeden řádek commitem). Oprava + 3 testy kontraktu (na verzi z kola 1 padají). Kolo 2: obě B resolved, 0 A/B, judge **COMPLETE**. Fronta C (6 položek) pro navazující chip. Spotřeba: critic ~87k + ~79k, judge ~63k + ~56k tokenů (celkem ~285k). |
| 2026-10-16 | merged | `chip_gate.py 33` ZELENÁ (worktree), sloučeno `--no-ff`; worktree uklizen. Smyčka nainstalována do `~/.claude` (`chip_install.py`: 3 written); skill se objevil v seznamu skillů bez restartu, agenti až po restartu. |
| 2026-10-25 | merged | **Port do veřejného repa `chips-method`.** Ve vývojovém repu chip stavěl na vlně 26–32 (anglické rozhraní nástrojů, `pyproject.toml`, `docs/install.md`), která ve veřejné verzi není; tady zůstává české rozhraní a návod je v README. Zdroje agentů, skill a instalátor jsou převzaté beze změny (skill: `--uklid` místo `--cleanup`, `stav:` místo `status:`). Počty testů v řádcích výše platí pro vývojové repo. |
