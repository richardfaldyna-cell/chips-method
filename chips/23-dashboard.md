---
chip: 23
nazev: dashboard
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
greenfield: ne       # 'ano' = repo teprve vznikne
vetev: ai/chip-23/dashboard
worktree: ../CHIPS-chip-23
---

# CHIP 23 — orchestrátor nevidí, co se v běžících chipech děje

Když běží tři chipy naráz, jediný způsob, jak zjistit stav, je ptát se agentů —
tedy věřit tvrzení modelu o sobě samém. Přesně to je selhání, kvůli kterému
projekt vznikl. `chip_status.py` ukazuje stav z briefů v **hlavním stromě**,
kde se za běhu chipu nehýbe nic: checkboxy i soubory se mění ve worktree.

`chip_dashboard.py` má dát obrázek z **tvrdých zdrojů** — z worktree každého
chipu a z gitu. Ne z toho, co kdo napsal do souhrnu.

Rozsah schválen 2026-07-27: stavová deska + časová osa.

## Issues

- [x] #1 — nový nástroj `tools/chip_dashboard.py`, generuje `dashboard.html`
      (čisté HTML + **inline CSS**, žádný externí zdroj — stejná zásada jako
      `md2html.py`, soubor musí fungovat offline)
- [x] #2 — **data se čtou z worktree chipu**, ne z hlavního stromu; jen tam se
      hýbou checkboxy a soubory. Tohle je hlavní důvod, proč nástroj vzniká.
- [x] #3 — karta chipu: stav, název, progress z checkboxů Issues (`hotove_issues`
      / `issues`), poslední commit na jeho větvi, ocas sekce Log
- [x] #4 — karta ukazuje **právě rozeditované soubory** (`git status --porcelain`
      ve worktree) — z toho je vidět, kde agent zrovna je
- [x] #5 — karty seskupené po vlnách; pořadí podle ID
- [x] #6 — chip bez worktree (`draft`, `merged`) kartu má taky, jen bez
      živých dat — a **je z ní poznat, že živá data nejsou**, ne prázdno
      vydávané za nulu
- [x] #7 — časová osa commitů všech chip větví (tempo a prodlevy)
- [x] #8 — `--watch` režim: `<meta refresh>` v HTML + volitelné opakované
      generování; interval jako parametr
- [x] #9 — `--dir` jako všude jinde (`pridej_arg_dir`), aby šel pustit nad
      cizím repem
- [x] #10 — nástroj je **jen pro čtení**: nesmí zapsat nikam jinam než do
      výstupního HTML. Žádný `git` příkaz, který mění stav.
- [x] #11 — chybějící/rozbitý worktree nesmí shodit celý dashboard — karta
      to ukáže a zbytek se vykreslí
- [x] #12 — testy: generování nad dočasnými repy a worktree, bez zápisu do
      skutečného repa; parsování `git status`/`git log` výstupu odděleně od
      vykreslování (čisté funkce)
- [x] #13 — `dashboard.html` patří do `.gitignore`? Rozhodni a **zapiš důvod
      do Logu**; soubor sám do commitu nedávej

## Dotčené soubory  ⚠️ NÁROK

```
tools/chip_dashboard.py        # nový
tests/test_chip_dashboard.py   # nový
```

`chip_common.py` je **mimo nárok** — importuj z něj, ale needituj. Když by bylo
potřeba ho rozšířit, je to T3. `.gitignore` taky needituj (bod #13 je jen
rozhodnutí a zápis do Logu). README a metodiku dopisuje orchestrátor.

## Definition of done

- [x] `python -m unittest discover -s tests` projde a testů je **víc** než
      dnešních 523
- [x] `python tools/chip_dashboard.py` nad tímhle repem vygeneruje
      `dashboard.html`, který jde otevřít v prohlížeči a ukazuje všech 22 chipů
- [x] `dashboard.html` neobsahuje **žádný** odkaz na externí zdroj
      (`http://`, `https://`, `src=`, `<link`) — ověřeno testem
- [x] test, který postaví dva dočasné worktree s různým počtem odškrtnutých
      checkboxů a ověří, že progress na kartách odpovídá **worktree**, ne
      hlavnímu stromu — to je jádro chipu
- [x] test, že nástroj nezapíše nikam kromě výstupního souboru
- [x] `git status --porcelain` po běhu testů je prázdný kromě vědomých změn

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Zastav se, zapiš do Logu a nech na uživateli:

- **jakákoli změna `chip_common.py`** — sdílený základ, mimo nárok
- nová externí závislost (žádný Jinja, žádný Flask; HTML si sestav v Pythonu
  jako `md2html.py`)
- cokoli, co by nástroj udělalo zapisujícím (git příkaz měnící stav, mazání)
- rozsah nad rámec Issues — dashboard není chip_status, nemá řešit lint,
  bránu ani spouštění
- jakýkoli zásah mimo „Dotčené soubory"

## Kontext pro agenta

- Testy: `python -m unittest discover -s tests -v`, stdlib `unittest`, **žádný
  pytest**. Vlastní `tempfile` fixture, úklid po sobě.
- `chip_common.CHIPS_DIR` je globální stav; v `tearDown` ho vracej.
- **Přečti si `tools/chip_status.py`** — dělá textovou verzi téhož a má
  vyřešené vlny, stavy i souhrn. Neduplikuj logiku, kterou lze číst
  z `chip_common` (`issues`, `hotove_issues`, `zavislosti`, `soubory`).
- **Přečti si `tools/md2html.py`** — jak se v tomhle projektu staví
  samostatné HTML s inline CSS. Drž stejný styl, ať to nevypadá jako cizí
  nástroj. Barvy stavů ať jsou čitelné v light i dark (`color-scheme`).
- Cestu k worktree ber z frontmatteru `worktree:` a řeš ji stejně jako
  `chip_run.cesty()`: relativní = jméno adresáře vedle repa. Ty soubory jen
  čti, needituj.
- Rozdělení na čisté funkce (parsování, sestavení HTML) a jednu funkci se
  vstupy/výstupy je v tomhle projektu konvence — kvůli testovatelnosti.
- Nástroj poběží i ve chvíli, kdy agenti právě zapisují. Počítej s tím, že
  soubor může být rozeditovaný, a nepadej na tom.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-28 | ready | brief založen orchestrátorem |
| 2026-07-28 | running | #1–#12 hotové: `tools/chip_dashboard.py` + `tests/test_chip_dashboard.py`. Rozděleno na čisté funkce (`parsuj_status`, `parsuj_commity`, `ocas_logu`, `zkrat`, `stari`, `souhrn`, `sestav_html`) a jedno místo s I/O (`karta_chipu`/`posbirej`/`main`). Bez závislostí; HTML se skládá v Pythonu jako v `md2html.py`, paleta i `color-scheme: light dark` převzaté odtamtud. Vlny a skloňování se berou z `chip_status` (`spocitej_vlny`, `_chipu`), issues/závislosti z `chip_common` — neduplikováno. |
| 2026-07-28 | running | **Nález v cizím kódu (neopravováno, jen hlásím):** `chip_run.brief_ke_stavu()` hledá kopii briefu přes `relative_to(repo:)`. To platí jen při čtení z hlavního stromu — dashboard se ale běžně pouští z worktree některého chipu, kde `relative_to` selže a všechny karty by tiše spadly zpátky na briefy toho jednoho worktree, tedy přesně na data, která se nehýbou. Proto má dashboard vlastní `brief_ve_worktree()`, které mapuje přes kořen stromu (první rodič s `.git`). `chip_run.py` needitován (mimo nárok). |
| 2026-07-28 | running | Živý důkaz issue #2 nad pěti běžícími worktree: `chip_status.py --dir <hlavní strom>` hlásí `ready 5, merged 17, issues 140/192`; `chip_dashboard.py` nad týmiž briefy, ale s živými daty, hlásí `running 5, merged 17, issues 177/192`. Rozdíl je 37 odškrtnutých issues a 5 přepnutých stavů, které z hlavního stromu vidět nejsou. Z worktree se proto bere i `stav:` — `chip_run.py --stav` ho zapisuje do kopie ve worktree, ne do originálu. |
| 2026-07-28 | running | #10 jen pro čtení: git jde výhradně přes `_git()` s whitelistem `POVOLENE_GIT` (`log`, `status`, `for-each-ref`), cokoli jiného je `ChybaJenCteni`. Adresář výstupu se nezakládá (`mkdir` je taky zápis) — chybějící rodič je exit 1. Ověřeno třemi testy: whitelist, záznam všech `subprocess.run` během sběru a snímek stromu před/po. `.git` je ze snímku vynechán schválně — tam si `git status` osvěžuje vlastní `index`, s nástrojem to nesouvisí. |
| 2026-07-28 | running | #6/#11: karta bez živých dat vždycky říká PROČ (`worktree … na disku není`, `chybí .git`, `git … selhal`, `brief nemá repo:`), a u chipu ve stavu `running`/`gated` je to navíc varování nahoře na desce. Rozbitý worktree shodí jen svoji kartu, zbytek se vykreslí. Odlišuje se i „poslední commit je jen společný základ, chip zatím nic neodevzdal“ — čerstvá větev zdědí historii, jinak by to vypadalo, že agent už commitoval. |
| 2026-07-28 | running | **#13 rozhodnutí: `dashboard.html` PATŘÍ do `.gitignore`.** Konvence workspace verzuje HTML generované z `.md` — tenhle soubor žádný `.md` zdroj nemá. Je to snímek okamžiku (relativní časy, `git status`, rozeditované soubory), mění se při každém běhu, v pěti worktree by kolidoval, a zmergovaný by tvrdil stav, který už neplatí. `.gitignore` je mimo nárok, takže řádek `dashboard.html` doplní orchestrátor; v commitu chipu soubor není a testy ho negenerují (píšou do `tempfile`). |
| 2026-07-28 | running | Brána: `python -m unittest discover -s tests -v` → **609 testů, OK** (před chipem 523, +86; 2 expected failures patří chipu 20, nedotčeny). `python tools/chip_lint.py` → rc 0, 0 chyb, 0 varování. `git status --porcelain` čistý kromě nárokovaných souborů. Ručně nad tímhle repem: `python tools/chip_dashboard.py` → `dashboard.html`, 22 karet, 0 odkazů ven (`http://`, `https://`, `src=`, `<link`, `<script`); párovost značek hlídá test přes `html.parser`. V grafickém prohlížeči soubor otevřen nebyl — vizuální kontrola zůstává na uživateli. Žádný T3, `chip_common.py` nedotčen. |
| 2026-07-28 | running | `chips/23-dashboard.html` **nepřegenerováno** — `md2html.py --all` sahá na všechny `.md` v repu, tedy i na briefy ostatních běžících chipů, a `.html` k briefu není v „Dotčených souborech“. Patří orchestrátorovi po merge (stejně jako u chipu 14). |
