---
chip: 21
nazev: review-signal
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
greenfield: ne       # 'ano' = repo teprve vznikne
vetev: ai/chip-21/review-signal
worktree: ../CHIPS-chip-21
---

# CHIP 21 — reviewer tvrdí nález tam, kde má položit otázku

`chip_review.py` vypisuje řádek typu „N odškrtnutých DoD proti M příkazům
brány". Tváří se jako nález, ale je to **falešný signál**: většina bodů DoD se
ověřuje testy uvnitř sady, ne samostatným příkazem v sekci „Ověření (brána)".
Poměr 8 : 2 je tedy normální stav, ne podezření.

Vada není v tom, že by to bylo nepravdivé — je v tom, že to **vypadá jako
nález**. Reviewer, který hlásí šum, si vychová čtenáře, který ho přeskakuje;
pak mu unikne i ten řádek, který je pravý. Je to táž vada, jakou opravoval
chip 15 u placeholderů v lintu, jen v jiném nástroji.

Řešení není řádek smazat — informace je užitečná. Je to **přeformulovat na
otázku**, tedy na to, čím ve skutečnosti je: podnětem k ověření, ne verdiktem.

## Issues

- [x] #1 — řádek o poměru DoD × příkazy brány se vypisuje jako **otázka pro
      reviewera**, ne jako nález (např. „ověř, čím jsou kryté body DoD, které
      nemají vlastní příkaz brány")
- [x] #2 — otázky jsou ve výstupu **vizuálně oddělené** od nálezů; z výstupu
      musí jít poznat, co je zjištění a co podnět
- [x] #3 — projdi zbylé řádky, které `chip_review.py` vypisuje, a rozhodni
      u každého, jestli je to nález, nebo otázka. Co je otázka, přesuň.
      Rozhodnutí u každého zapiš do Logu — je to hlavní obsah tohohle chipu.
- [x] #4 — skutečné nálezy zůstávají nálezy: soubor mimo nárok, nedotčený
      nárok, podezřelý test (`podezrele_testy`) — ty se **nepřesouvají**
- [x] #5 — počty v souhrnu ať rozlišují nálezy a otázky, ne jedno číslo
- [x] #6 — když nejsou žádné nálezy ani otázky, ať to nástroj řekne jednou
      větou a nevypisuje prázdné sekce
- [x] #7 — testy: řádek o DoD se za normálního stavu (8 DoD, 2 příkazy) **neobjeví
      mezi nálezy**; dnešní chování by test neprošlo
- [x] #8 — testy k rozdělení nález/otázka a k souhrnu
- [x] #9 — docstring modulu doplnit o to, proč se rozlišuje nález a otázka

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_review.py
tests/test_chip_review.py
```

## Definition of done

- [x] `python -m unittest discover -s tests` projde a testů je **víc** než
      dnešních 523
- [x] `python tools/chip_review.py 17` (zmergovaný chip) nevypíše řádek o DoD
      mezi nálezy; dnes ho tam vypíše
- [x] test, který postaví chip s 8 body DoD a 2 příkazy brány a ověří, že
      **počet nálezů je 0** — to je jádro chipu
- [x] test, který ověří, že soubor změněný mimo nárok je pořád **nález**
- [x] výstup nástroje projde očima: v Logu je vzorový výstup před a po

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Zastav se, zapiš do Logu a nech na uživateli:

- **zeslabení kontrol, které jsou skutečné nálezy** (mimo nárok, nedotčený
  nárok, podezřelý test) — reviewer je poslední síto po bráně
- úplné odstranění informace místo jejího přeformulování
- jakýkoli zásah mimo „Dotčené soubory"
- nová externí závislost

## Kontext pro agenta

- Testy: `python -m unittest discover -s tests -v`, stdlib `unittest`, **žádný
  pytest**. Vlastní `tempfile` fixture, úklid po sobě.
- `chip_common.CHIPS_DIR` je globální stav; v `tearDown` ho vracej.
- **Přečti si `chip_lint.PLACEHOLDERY` a docstring třídy `Placeholder`.** Je
  tam napsané, proč se šum v nástroji řeší zúžením, ne ztlumením — chip 15
  řešil přesně tenhle druh vady a jeho odůvodnění platí i tady.
- `chip_review.py` je **podklad pro člověka/agenta**, ne brána — nevrací
  exit 1 při nálezu. Tím spíš musí být jeho výstup čitelný.
- `dod_body()` a `pomer()` jsou funkce, kterých se to týká nejvíc.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-28 | ready | brief založen orchestrátorem |
| 2026-07-28 | running | **#3 — rozhodnutí u KAŽDÉHO vypisovaného řádku.** (a) `— commit nemění žádný soubor` = DATA: prázdný commit se ohlásí sám v nedotčených nárocích, druhý poplach o téže věci je šum. (b) řádky souborů + `celkem:` = DATA (inventura). (c) `nárok: …` = DATA. (d) `X MIMO NÁROK: …` = **NÁLEZ, tvrdý** (jediný, co zvedá rc) — beze změny. (e) `OK — každá změna spadá pod nárok` = DATA. (f) `! nárok '…' nemá v commitu jedinou změnu` = **NÁLEZ** — beze změny, nástroj má úplná data o tom, co v commitu je a co ne, ptát se nemá proč. (g) `! commit nemění žádný testovací soubor` = **ROZDĚLENO**: sahá-li commit na kód, je to NÁLEZ a nově jmenuje ty soubory (`commit mění kód (tools/x.py), ale žádný testovací soubor`); mění-li commit jen dokumentaci, není to signál vůbec, jen věta „commit nemění kód ani testy". Zúžení, ne ztlumení — přesně postup chipu 15 u placeholderů: hlásit tam, kde chybějící test škodí, a nikde jinde. (h) `! …: obsah se nepodařilo přečíst` = **OTÁZKA** — to není tvrzení o kódu, ale přiznání, že nástroj nemá co posoudit; text nově říká, co udělat („projdi soubor ručně"). (i) `podezrele_testy` (bez assertu / @skip / @expectedFailure / nelze naparsovat) = **NÁLEZ** — beze změny. (j) `OK — N testovacích souborů…` = DATA; opraveno skloňování („1 testovacích soubor" → „1 testovací soubor"). (k) `! brief nemá v DoD jediný bod` = **NÁLEZ** (odškrtnutí nemá co ověřit). (l) `[x] text` = DATA. (m) `! žádný příkaz — odškrtnutí nemá co ověřit` = **NÁLEZ**, přeformulováno na „brána nespouští jediný příkaz…" (chip bez brány se nesmí mergovat). (n) `! N odškrtnutých bodů proti M příkazům brány — čím je ověřený zbytek?` = **OTÁZKA** (jádro chipu), nově „ověř, čím jsou kryté body bez vlastního příkazu (typicky testy uvnitř sady)"; navíc se nevydává, když brána nemá ani jeden příkaz — tam už mluví nález (m) a dvojí hlášení téhož je šum. (o) `kód/testy/dokumentace` + `poměr testy:kód` = DATA: ukazatel bez prahu, práh nástroj nezná, takže z něj nedělá ani nález, ani otázku. |
| 2026-07-28 | running | **#1/#2/#5/#6 — jak.** Nový `Signal(druh, text, tvrdy)` + zkratky `nalez()` / `otazka()` / `vyber()`; každá `sekce_*` vrací `(řádky, signály)` místo holých řádků, takže o druhu rozhoduje místo vzniku, ne formátování. Sekce ve výpisu nesou jen DATA, posuzující řádky sbírá `sekce_signaly()` a tiskne je pod sebe: „Nálezy — tohle je špatně" (`X` = tvrdé pravidlo metodiky, `!` = podklad) a „Otázky — tohle nástroj rozhodnout neumí, ověř ty" (`?`). Prázdná sekce se nevypíše (nadpis nad ničím je taky návod k přeskakování), a když není ani jedno, je to jedna věta „Bez nálezů a bez otázek — co jde ověřit strojově, sedí." Souhrn počítá odděleně a skloňuje („Souhrn: 2 nálezy, 1 otázka." / „0 nálezů, 1 otázka."). Návratový kód se nezměnil: 1 jen u tvrdých signálů (soubor mimo nárok), zbytek pořád podklad. Sekce „Podezřelé testy" nikdy nezůstane holým nadpisem — když signály putují dolů, řekne aspoň, kolik souborů prošla. |
| 2026-07-28 | running | **#7/#8 — testy: 523 → 546 (+23), žádný stávající test neoslaben.** Jádro: `test_pomer_dod_a_brany_je_otazka_ne_nalez` (8 bodů : 2 příkazy → nálezů 0, otázka 1) a end-to-end `test_normalni_pomer_dod_nedela_nalez` (čistý commit + 8:2 → rc 0, „Souhrn: 0 nálezů, 1 otázka.", řetězec „Nálezy" ve výstupu vůbec není). Protipól k oslabení: `test_soubor_mimo_narok_je_tvrdy_nalez`, `test_soubor_mimo_narok_zustava_nalezem` (hlášku hledá v části výstupu ZA nadpisem Nálezy, ne kdekoli), `test_nedotceny_narok_je_nalez_ne_otazka`, `test_podezrely_test_je_nalez`. K zúžení (g): `test_kod_bez_jedineho_testu_je_nalez` vs. `test_commit_jen_s_dokumentaci_nic_nehlasi`. Dál `test_neprecteny_soubor_je_otazka`, `test_brief_bez_bodu_dod_je_nalez`, `test_brana_bez_prikazu_je_nalez`, `test_vyrovnany_pomer_nevyda_zadny_signal`, `test_sekce_neni_nikdy_holy_nadpis` a třída `TestVypisSignalu` (7 testů na rozdělení, značky, skloňování a jednu větu prázdného stavu). Nové fixture pomůcky `prepis_dod(dod, prikazy)` a `ciste_zmeny()` jsou přídavek, stávající `Zaklad` se chová stejně. |
| 2026-07-28 | running | **Vzorový výstup PŘED a PO** (chip 17, commit `24c3528`; PŘED = `git show HEAD:tools/chip_review.py` pouštěné vedle). PŘED, sekce DoD končila: „$ python -m unittest discover -s tests -v / $ python tools/chip_lint.py / **! 5 odškrtnutých bodů proti 2 příkazům brány — čím je ověřený zbytek?**" a výpis zavíralo „Podklady sebrány." — jediný `!` celého běhu byl přitom falešný poplach, u zmergovaného a prověřeného chipu. PO: sekce DoD končí u příkazů brány, a pod výpisem stojí „Otázky — tohle nástroj rozhodnout neumí, ověř ty / ? 5 odškrtnutých bodů DoD proti 2 příkazům brány — ověř, čím jsou kryté body bez vlastního příkazu (typicky testy uvnitř sady)" a „**Souhrn: 0 nálezů, 1 otázka.**". Kontrola opačným směrem (HEAD hlavního repa, kde chip 17 nárok opravdu nedotkl): 12 nálezů (10× MIMO NÁROK + 2× nedotčený nárok) v sekci Nálezy, otázka o DoD zvlášť — nálezy se rozdělením neztratily. |
| 2026-07-28 | running | Brána: `python -m unittest discover -s tests -v` → **546 testů, OK (expected failures=2 — patří chipu 20, nesaháno)**; `python tools/chip_lint.py` → „0 chyb, 0 varování", rc 0. Změněné soubory: `tools/chip_review.py`, `tests/test_chip_review.py` (+ tenhle brief). Žádná nová závislost (stdlib `dataclasses`). **T3: nic.** Skutečné nálezy jsem nezeslabil ani nesmazal — mimo nárok, nedotčený nárok i podezřelý test zůstaly nálezy a jsou na to nové testy; informace o poměru DoD nezmizela, jen se přeformulovala na otázku. `.html` k briefu nepřegenerováno: `md2html.py` je nárok běžícího chipu 20 a HTML dělá orchestrátor po merge. |
