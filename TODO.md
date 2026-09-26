# TODO — CHIPS

## Další krok

- [x] **Absolutní `worktree:` chápou `chip_run` a brána opačně** — vyřešeno
      chipem 24 (2026-07-31): `chip_run.cesty()` absolutní cestu ctí, jak je
      zapsaná, stejně jako `chip_gate.kde_spustit()` i `hook.kde_overit()`.
      Relativní zápis se nezměnil (jen jméno adresáře, vedle repa) — na `cwd`
      nezávisí jen absolutní cesta, u ní ta ochrana nic nekupovala.
      `@unittest.expectedFailure` z chipu 19 zrušen, sada je čistě zelená.
- [ ] Zostřit hranici T3: „přidání logiky" si chip 01 a 03 vyložily opačně
- [ ] **Brána se blíží limitu?** Na Windows naměřeno ~70 s na běh (692 testů),
      na Linuxu stejná sada běží ~5 s — nejdřív zjistit, co je na Windows
      pomalé (git subprocess, antivirus), než vznikne zkratka. Pouští se po každém
      mergi. Zvážit `--rychla` variantu pro merge a plnou jen na konci vlny.
- [ ] **Patří `.html` briefu agentovi, nebo orchestrátorovi?** Chip 23 ho
      schválně nepřegeneroval („`.html` k briefu není v Dotčených souborech,
      patří orchestrátorovi"), chip 25 ho přegeneroval sám. Obě čtení jsou
      obhajitelná a `chip_lint.py` ani `TEMPLATE.md` neříkají které. Rozhodnout
      a zapsat do metodiky — teď to závisí na tom, koho se zeptáš.
- [ ] **`--spustit` z orchestrátorského shellu potřebuje KRÁTKÝ timeout.**
      Ověřeno na chipu 25 třemi pokusy: spuštění rovnou na pozadí → Claude Code
      se vyhodnotí jako neinteraktivní a hned skončí (exit 0, nula práce);
      dlouhý timeout → po vypršení se proces **zabije** i s rozdělanou prací
      (exit 143). Funguje jen krátký limit, po kterém se běh přesune na pozadí
      a doběhne. Zapsat do metodiky k `--spustit`, je to past, ne detail.

- [x] **Zadání od `chip_run.py` posílalo agenta do briefu v hlavním stromě** —
      vyřešeno 2026-09-26: `zadani()` bere `brief=brief_ke_stavu(...)`, takže
      zadání ukazuje na kopii ve worktree (tu, kterou `--stav` přepisuje);
      originál jen když kopie neexistuje (`--dir`, netrackovaný brief).
      Nalezeno při vlně 0 stránky CHIPS na webu; test
      `test_zadani_posila_agenta_do_kopie_ve_worktree` na staré verzi padá.

## Brána

- [ ] Marker `.chips` a `CHIPS_DIR` zná zatím jen hook — ostatní nástroje chtějí
      `--dir`. Sjednotit (`chip_common`), až to začne vadit v praxi.
- [ ] Definovat konkrétní bránu pro cizí pilotní repo (testy / build / smoke)
- [ ] Napojit na existující skill `/ship` místo duplikace postupu

## Nástroje

- [x] `chip_dashboard.py`: vizuální kontrola proběhla 2026-07-31 — hlavička,
      karty po vlnách, log a patička sedí. **Ověřeno jen na zelené větvi:**
      snímek se všemi chipy `merged` a bez živých worktree nevyrenderuje ani
      jednu z tříd `stav-draft/ready/running/gated/blocked/jiny`, `varovani`,
      `zdroj spatne`, `ul.zmeny` a `.osa` — ty čekají na kontrolu, až poběží
      ostrý chip (nebo přes fixturu `--dir`). Vzhled zbytku neviděl nikdo.
- [x] `chip_run.py --uklid` hlásil úspěch i když `git worktree prune` nechal
      v `.git/worktrees/` mrtvý adresář (git vrací rc 0 i při „Permission
      denied") — vyřešeno chipem 25 (2026-07-31): úspěch se měří stavem na
      disku, zbylá metadata se dorazí rekurzivně a jen po ověření `gitdir`,
      ať se nesmažou metadata cizího worktree. 24 nakupených adresářů z chipů
      01–24 smeteno ručně.
- [ ] `git_koren()` / `strom_ke_kontrole()` z `chip_lint.py` přesunout do
      `chip_common.py`, až je bude potřebovat i jiný nástroj (nález chipu 05).
      **Kandidátů přibývá**: vlastní `git_koren` má i `hook_chip_gate.py`
      a `chip_dashboard.brief_ve_worktree()`.

## Ověřit v praxi

- [ ] Sedí strop 10–20 issues / ~15 souborů? Pilot běžel na 7–12 issues na chip.
- [ ] Prázdná hodnota ve frontmatteru (`stav:` bez hodnoty) neaktivuje fallback —
      nechat, nebo brát jako chybějící klíč? (nález chipu 03, zafixováno testem)

## Hotovo

- [x] Metodika sepsána (`docs/metodika.md`) — 2026-07-25
- [x] Šablona chip briefu (`chips/TEMPLATE.md`) — 2026-07-25
- [x] `chip_new.py`, `chip_lint.py`, `chip_run.py`, `md2html.py` — 2026-07-25
- [x] Záznam konverzace, ze které projekt vznikl — 2026-07-25
- [x] `chip_lint.py`: existence nárokovaných cest v repu (stav `ready`),
      značka `# nový`, vzory rozbalené proti repu — 2026-07-26
- [x] **Pilot na tomhle repu: 6 chipů ve 2 vlnách, 6/6 merged, 0 blocked** — 2026-07-26
- [x] Testy: 0 → 201 (`python -m unittest discover -s tests -v`) — 2026-07-26
- [x] `chip_status.py` — přehled chipů, vln a stavů (chip 02) — 2026-07-26
- [x] `chip_run.py`: `--spustit` (Claude Code ve worktree) a `--stav`
      (ready → running), čisté funkce `cesty()`/`zadani()` (chip 04) — 2026-07-26
- [x] `chip_lint.py`: skutečný průnik dvou vzorů + kontrola proti stromu,
      ve kterém chip pracuje (chip 05, nálezy N1 a N2) — 2026-07-26
- [x] `hotove_issues()` a `prepis_stav()` sloučeny do `chip_common.py` (chip 06) — 2026-07-26
- [x] Spotřeba tokenů změřena: ~80–110 tis. na chip — 2026-07-26
- [x] **Tvrdý hook**: `hook_chip_gate.py` na PreToolUse zamítne merge chip větve
      s červenou bránou; ověřeno živým pokusem o merge — 2026-07-26
- [x] `chip_gate.py` — spustí bránu z briefu (sdílí ji hook i skill) — 2026-07-26
- [x] Skill `/chip` (`.claude/skills/chip/SKILL.md`) — 2026-07-26
- [x] **Druhý pilot — cizí repo `pilot-repo`**: 7 chipů zmergováno, 7/7 zelená
      brána, 0 → 235 testů, 9 nálezů v produkčním kódu, 5 skriptů poprvé
      importovatelných bez spuštění pipeline, 7 oprav v zápisové cestě PBIP
      nástroje; hlavní strom prokazatelně nedotčen (manifest 6037 souborů
      před/po) — 2026-07-26
- [x] **Role reviewera ověřena v praxi**: nezávislý agent s mutačním testováním
      našel dvakrát to, co brána minula (`chip_review.py`) — 2026-07-26
- [x] **Vlna 4 — 10 nálezů z externího code review opraveno**: chipy 11–14
      (chip 10 rozříznut na 13/14 kvůli hustotě zadání), 366 → 413 testů,
      4/4 zelená brána. Průběh a poučení: `docs/vlna-4-preruseno.md` — 2026-07-27
- [x] **Hook už nemá falešné poplachy** — `merge` se hledá jako celý token po
      tokenu `git` uvnitř segmentu, ne jako podřetězec. Ověřeno naživo: `echo`,
      `grep` i `git commit -m` s frází o mergi chip větve projdou, skutečný
      merge se zamítne (chip 13) — 2026-07-27
- [x] `strom_ke_kontrole()` ověřuje, že nalezený git strom je opravdu tentýž
      repozitář jako `repo:` (chip 11, nález #2) — 2026-07-27
- [x] **Složka `chips/` sjednocena**: 8 briefů převedeno na konvenci větve
      `ai/chip-NN/nazev`, 6 doplněn slovník stavů, smazán osiřelý HTML — 2026-07-27
- [x] **Úklid worktree vynucen, ne jen doporučen**: `--uklid` odmítne
      nezmergovanou větev (`merge-base --is-ancestor`), opuštěný chip jde
      uklidit `--presto`. Pořadí kroků doplněno do `/chip` i metodiky — 2026-07-28
- [x] **`--uklid` doopravdy uklidí**: `remove` → `remove --force` → ruční
      `rmtree` (sundá read-only) → `worktree prune`; zbylý adresář končí
      kódem 1 místo tichého úspěchu. Ověřeno naživo na read-only zbytku — 2026-07-28
- [x] **`--stav` píše do kopie briefu ve worktree**, ne do hlavního stromu —
      hlavní strom po `chip_run.py NN --stav` zůstává čistý (`git status`
      prázdný), merge tedy nemá na čem spadnout — 2026-07-28
- [x] **Vlna 6 — pět chipů naráz**: chipy 19–23, 5/5 merged, 0 zásahů mimo
      nárok, 523 → 676 testů. Součet po každém mergi seděl
      (548 → 562 → 585 → 590 → 676) — 2026-07-28
- [x] **`chip_gate.py` měří worktree chipu, ne hlavní strom** — chybějící
      `worktree:` selže místo tichého fallbacku; `--repo` zůstává vědomou
      výjimkou. `test_brana_a_hook_resi_worktree_stejne` hlídá, že se CLI
      a hook nerozejdou ve verdiktu (chip 19) — 2026-07-28
- [x] **`md2html.py` bere vstup jako text, ne jako HTML** — extension
      `BezSurovehoHTML`, bez nové závislosti; `--all` přeskakuje `__pycache__`.
      Regresní důkaz: 28 z 29 `.html` bajtově shodných, `TEMPLATE.html` se mění
      o jeden řádek (zástupný text `<název>` byl dosud neviditelný — druhá,
      skrytá instance téže vady). Změna přijata uživatelem (chip 20) — 2026-07-28
- [x] **`chip_review.py` rozlišuje nález, otázku a data** — o druhu rozhoduje
      místo vzniku, ne formátování. Na chipu 17: dřív 1 nález (a byl planý),
      dnes 0 nálezů + 1 otázka (chip 21) — 2026-07-28
- [x] **Slovník stavů je v generovaném briefu**, ne jen v metodice — ve
      frontmatteru šablony, s větou, že `stav:` přepíná orchestrátor. Zrušen
      duplicitní inline seznam. Test porovnává šablonu s `chip_common.STAVY`
      (chip 22) — 2026-07-28
- [x] **`chip_dashboard.py`** — živá deska z worktree a gitu, `--watch`,
      offline HTML. Doložila sama sebe: nad pěti běžícími chipy 177/192 issues
      proti 140/192 z hlavního stromu. `dashboard.html` do `.gitignore`
      (chip 23) — 2026-07-28
- [x] **Vlna 5 — první vlna odbavená subagenty místo oken**: chipy 16–18,
      3/3 merged, 0 zásahů mimo nárok, 454 → 523 testů. Součet po každém mergi
      seděl (476 → 496 → 523), tedy nulová kolize mezi chipy — 2026-07-28
- [x] **`chip_run.py --od <ref>`** — navazující chip se větví z předchůdce;
      ref ověřen (`rev-parse --verify …^{commit}`) PŘED `worktree add`, zadání
      pro agenta říká, že cizí rozpracovaný kód se needituje (chip 16) — 2026-07-28
- [x] **Greenfield**: `chip_run.py --zaloz-repo` (init + prázdný kořenový
      commit, nad existující historií nedělá nic) + `greenfield: ano` ve
      frontmatteru, se kterým lint neexistenci repa a cest jen varuje.
      Kontrola tvaru cesty se nevypíná — je vstupem do disjunktnosti
      (chipy 16 a 17) — 2026-07-28
- [x] **`chip_lint`: navazující chip je varování, ne chyba** — předek `gated`
      pustí a připomene pořadí merge; `blocked` a nehotový předek zůstávají
      chyba (chip 17) — 2026-07-28
- [x] **`md2html.py` dostal první testy** — 27 testů, včetně kontroly, že sada
      nesáhne na `.html` ve skutečném repu; `main()` vrací 1 při chybějícím
      souboru (chip 18) — 2026-07-28
- [x] **Hook najde briefy i mimo repo** — marker `.chips` a ověřený `CHIPS_DIR`
      vedle adresáře `chips/`. Konec dilematu „tvrdá brána NEBO nulová stopa
      v cizím repu"; rozbitý marker zamítá místo mlčení. Ověřeno naživo:
      stejný červený merge bez markeru prošel, s markerem zamítnut — 2026-07-28
