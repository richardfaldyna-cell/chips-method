---
chip: 19
nazev: gate-worktree
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
greenfield: ne       # 'ano' = repo teprve vznikne
vetev: ai/chip-19/gate-worktree
worktree: ../CHIPS-chip-19
---

# CHIP 19 — brána spuštěná ručně měří špatný strom

`chip_gate.py NN` bez `--repo` vezme `repo:` z frontmatteru, což je **hlavní
strom**. Tam ale práce chipu ještě není — merguje se do něj teprve. Brána tedy
projde nad starým kódem a vrátí zelenou, která o mergovaném stavu neříká nic.

Doloženo ve vlně 5: brána chipu 18 hlásila zelenou v hlavním stromě, kde běželo
**454 testů**, zatímco ve worktree chipu jich bylo **481**. Rozdíl 27 testů je
přesně ta práce, kterou brána neviděla.

Hook to dělá správně — `hook_chip_gate.kde_overit()` hlavní strom výslovně
odmítá s odůvodněním „falešná zelená je horší než žádná". CLI a hook si tedy
dnes protiřečí a **hook má pravdu**. Tohle je nejzávažnější typ vady, jakou
tenhle projekt může mít: brána, která tvrdí zelenou o něčem jiném, než co se
merguje.

## Issues

- [x] #1 — default `chip_gate.py NN` = **worktree chipu** z frontmatteru
      (`worktree:`), ne `repo:`
- [x] #2 — `--repo <cesta>` zůstává a má přednost; je to výjimka pro vědomé
      spuštění jinde, ne běžná cesta
- [x] #3 — chybějící / nevyplněné `worktree:` → **selhat s hláškou**, ne tiše
      spadnout zpátky na `repo:`. Tichý fallback je celá tahle vada.
- [x] #4 — worktree v briefu je, ale na disku není → selhat s hláškou, která
      řekne, čím ho obnovit (`chip_run.py NN`)
- [x] #5 — cesta ve `worktree:` se řeší stejně jako v `chip_run.cesty()`:
      relativní bere jen jméno adresáře a klade ho vedle repa. Dva nástroje
      nesmí tutéž hodnotu chápat jinak.
- [x] #6 — hlavička výpisu ať jasně říká, ve kterém stromě brána běžela
      (dnes cestu vypisuje, ale nejde z ní poznat, že je to ten špatný)
- [x] #7 — když `worktree:` ukazuje na týž strom jako `repo:`, hlásit to jako
      chybu — je to táž falešná zelená, jen zapsaná v briefu (stejné pravidlo
      jako v `hook_chip_gate.kde_overit()`)
- [x] #8 — chip ve stavu `merged`: worktree už neexistuje (uklizen po mergi).
      Rozhodni a **zapiš do briefu do Logu**, jestli má takový chip brána
      odmítnout, nebo povolit `--repo`; nehádej mlčky.
- [x] #9 — testy ke všem bodům výš, včetně regrese: `--repo` se chová jako dnes
- [x] #10 — docstring modulu + `--help` u `--repo` doplnit o nové chování

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_gate.py
tests/test_chip_gate.py
```

`tools/hook_chip_gate.py` je **mimo nárok** — hook už to dělá správně a jeho
`kde_overit()` je vzor, podle kterého se řídíš. Dokumentaci (`/chip` skill,
metodika) dopisuje orchestrátor.

## Definition of done

- [x] `python -m unittest discover -s tests` projde a testů je **víc** než
      dnešních 523
- [x] test, který postaví brief s `worktree:` mířícím do stromu, kde brána
      projde, a `repo:` do stromu, kde **neprojde** — a ověří, že `chip_gate`
      bez `--repo` vrátí výsledek podle **worktree**, ne podle repa.
      Tenhle test je jádro chipu: dnes by selhal.
- [x] test, který ověří, že bez vyplněného `worktree:` nástroj **selže**
      (nenulový kód) a nespustí ani jeden příkaz brány
- [x] `python tools/chip_gate.py 19 --repo <libovolný strom>` se chová jako dnes
- [x] `tools/chip_gate.py` nemá žádný nový import mimo stdlib

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Zastav se, zapiš do Logu a nech na uživateli:

- **jakákoli změna `hook_chip_gate.py`** — je mimo nárok a je to jediné tvrdé
  vynucení v celém projektu
- změna tvaru názvu větve nebo `id_z_vetve()` — hook na tom stojí
- rozhodnutí z issue #8, pokud by znamenalo, že brána u `merged` chipu mlčky
  projde (to je zpátky falešná zelená)
- jakýkoli zásah mimo „Dotčené soubory"
- nová externí závislost

## Kontext pro agenta

- Testy: `python -m unittest discover -s tests -v`, stdlib `unittest`, **žádný
  pytest**. Vlastní `tempfile` fixture, úklid po sobě.
- `chip_common.CHIPS_DIR` je globální stav; v `tearDown` ho vracej.
- `tests/test_chip_gate.py` už má základ `Zaklad` s dočasným repem a metodu
  `worktree(cislo)`, která staví skutečný git strom — nové testy pověs na ně.
- **Přečti si `hook_chip_gate.kde_overit()` a jeho docstring dřív, než začneš.**
  Je tam vysvětlené, proč se hlavní strom odmítá; tvoje verze má být stejné
  pravidlo, jen ve druhém nástroji. Kde to jde, chovej se identicky —
  rozcházející se kopie téhož pravidla jsou v tomhle projektu opakovaná vada.
- `chip_gate.brana(chip, repo)` volá hook, takže **její signatura se nesmí
  změnit** — hook ji importuje. Měň `main()`, ne `brana()`.
- Sladění s `chip_run.cesty()` (bod #5) čti, ale `chip_run.py` needituj.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-28 | ready | brief založen orchestrátorem |
| 2026-07-28 | running | `chip_gate.kde_spustit()` + přepsaný `main()`: bez `--repo` se měří worktree z briefu, `brana()` beze změny (hook si ji importuje) |
| 2026-07-28 | running | **rozhodnutí #8** — chip ve stavu `merged`: brána ODMÍTNE (exit 1) a v hlášce poradí `--repo`. Po mergi je hlavní větev směs všech chipů; zelená odtamtud o tomhle chipu neplatí, takže tichý přechod na `repo:` by byla táž falešná zelená, jen u jiného stavu. `--repo` zůstává vědomou cestou, jak bránu nad zmergovaným stavem spustit. |
| 2026-07-28 | running | **nález (mimo nárok, neopraveno)** — u ABSOLUTNÍ hodnoty `worktree:` bere `chip_run.cesty()` jen jméno adresáře a klade ho vedle repa, kdežto `hook.kde_overit()` i nový `kde_spustit()` ji respektují, jak je. `chip_run` tedy worktree založí jinde, než kam se brána dívá. Není to falešná zelená (brána strom nenajde a selže), ale je to past. Zdokumentováno testem `test_absolutni_cesta_se_s_chip_run_rozchazi` (`@unittest.expectedFailure`) — sada si o tom řekne, až se to opraví. Rozhodnutí, kterou stranu srovnat, je na uživateli. |
| 2026-07-28 | running | pravidlo je nově zapsané dvakrát (CLI + hook), protože hláška musí radit podle kontextu. Že se kopie nerozejdou ve VERDIKTU, drží `test_brana_a_hook_resi_worktree_stejne` — stejná pojistka jako u `VETEV_CHIP` |
| 2026-07-28 | running | brána: 546 testů (523 → +23, z toho 1 nový expectedFailure = nález výš; 2 původní patří chipu 20), lint rc 0. `python tools/chip_gate.py 19` teď běží v `CHIPS-chip-19`, ne v hlavním stromě. HTML k briefu NEPŘEGENEROVÁNO — `md2html.py` drží chip 20 |
