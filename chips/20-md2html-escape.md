---
chip: 20
nazev: md2html-escape
stav: merged          # draft | ready | running | gated | merged | blocked
zavisi_na:
repo: ..
greenfield: ne       # 'ano' = repo teprve vznikne
vetev: ai/chip-20/md2html-escape
worktree: ../CHIPS-chip-20
---

# CHIP 20 — dva nálezy chipu 18, oba zafixované expectedFailure

Chip 18 našel při psaní testů dvě vady a **neopravil je** — správně, obě byly
za hranicí jeho zadání. Oba testy v sadě existují jako `@unittest.expectedFailure`
s komentářem. Tenhle chip je má opravit a ty dva testy překlopit na normální.

1. **Surové HTML projde do výstupu.** `markdown.markdown()` pouští HTML skrz,
   takže `<script>alert(1)</script>` ve zdrojovém `.md` skončí ve výstupním
   `.html` jako živý tag. Nástroj převádí dokumentaci, ne šablony — surové HTML
   ve vstupu je vždycky buď omyl, nebo něco, co se má ukázat jako text.
2. **`--all` nepřeskakuje `__pycache__`.** Filtr zná jen `.git`.

**Dobrá zpráva k rozsahu:** žádný zdrojový `.md` v repu dnes surové HTML
nepoužívá (dva výskyty `<script>` jsou uvnitř backticků, tedy už escapované).
Oprava tedy nemá změnit ani jeden existující `.html` — a to je zároveň nejsilnější
kontrola, že je udělaná správně.

## Issues

- [x] #1 — surové HTML ve zdroji se ve výstupu objeví jako **text**, ne jako tag
      (`<script>alert(1)</script>` → viditelný text, nic se nespustí)
- [x] #2 — `test_04_script_v_markdownu_se_nedostane_jako_zivy_tag` přestává být
      `@unittest.expectedFailure` a stává se normálním testem
- [x] #3 — kód v ``` blocích a v `backtickách` zůstává **beze změny** — dnes se
      escapuje správně a nesmí se z toho stát dvojité escapování (`&amp;lt;`)
- [x] #4 — `--all` přeskakuje `__pycache__` i `.git`
- [x] #5 — `test_09_all_preskakuje_pycache` přestává být `@unittest.expectedFailure`
- [x] #6 — filtr adresářů ať je na jednom místě a pojmenovaný, ne dvě podmínky
      rozeseté v `main()` — příště se přidává třetí
- [x] #7 — **regresní důkaz:** `md2html.py --all` nad tímhle repem vyprodukuje
      `.html` **bajtově shodné** s dnešními. Postup i výsledek zapiš do Logu.
      → 28 z 29 shodných, **`chips/TEMPLATE.html` se mění** → T3, viz Log
- [x] #8 — testy k #1 a #4 nad dočasným stromem, ne nad skutečným repem
- [x] #9 — docstring modulu doplnit o to, že vstup se bere jako text, ne jako
      HTML, a proč

## Dotčené soubory  ⚠️ NÁROK

```
tools/md2html.py
tests/test_md2html.py
```

Přegenerování `.html` v repu dělá **orchestrátor po mergi**, ne ty — i kdyby
z #7 vyšlo, že se nic nezmění.

## Definition of done

- [x] `python -m unittest discover -s tests` projde a **expected failures = 0**
      (dnes 2; obě jsou právě tyhle dvě vady)
- [x] `git status --porcelain` po celém běhu sady je prázdný kromě souborů,
      které jsi vědomě změnil
- [x] důkaz k #7: `md2html.py --all` nad repem a `git status` po něm ukazuje
      **žádnou změnu** v `.html` (nebo, pokud změnu ukáže, je v Logu vypsané
      přesně které soubory a proč — to je pak T3)
      → změna v jednom souboru, vypsaná v Logu; **T3, čeká na rozhodnutí**
- [x] `.md` s blokem kódu obsahujícím `<div>` se převede tak, že v HTML je
      vidět `<div>` jako text uvnitř `<pre>`, ne prázdný element
- [x] CSS a `TEMPLATE` v `md2html.py` zůstávají nezměněné

## Ověření (brána)

```bash
python -m unittest discover -s tests -v
python tools/chip_lint.py
```

## Eskalace — co NEROZHODOVAT sám (T3)

Zastav se, zapiš do Logu a nech na uživateli:

- **nová externí závislost** (`bleach`, `nh3`, cokoli). Projekt jede na stdlib
  + `markdown`. Když čistá oprava jde jen se závislostí, zastav se a napiš to.
- **jakákoli změna CSS nebo `TEMPLATE`** — přegenerovala by všech 24 `.html`
- zjištění, že oprava přece jen mění existující výstup (viz #7) — vypiš které
  soubory a nech rozhodnutí na uživateli
- jakýkoli zásah mimo „Dotčené soubory"

## Kontext pro agenta

- Testy: `python -m unittest discover -s tests -v`, stdlib `unittest`, **žádný
  pytest**. `tests/test_md2html.py` už existuje (27 testů, chip 18) a má
  fixturu `ZakladPrevodu`, která přesměruje `md2html.ROOT` do `tempfile` —
  stav na ni.
- **Nepřepisuj cizí testy do zelena.** Oba `@unittest.expectedFailure` testy
  mají zůstat obsahově stejné; měníš kód, ne očekávání.
- Python-markdown od verze 3 nemá `safe_mode`. Surové HTML si odkládá do
  `md.htmlStash` a vrací ho zpátky v postprocessoru — tudy vede cesta bez
  nové závislosti. Zvaž vlastní postprocessor / `md.htmlStash`; nedělej to
  hrubým `html.escape()` nad celým vstupem, to by rozbilo bloky kódu (#3).
- Konvence: ke každému `.md` patří `.html`, generuje se tímhle nástrojem.

## Log

| Datum | Stav | Poznámka |
|---|---|---|
| 2026-07-28 | ready | brief založen orchestrátorem |
| 2026-07-28 | running | Oprava #1: nová `markdown` extension `BezSurovehoHTML` v `md2html.py` odregistruje preprocesor `html_block` a řádkový vzor `html`. Tím se do `md.htmlStash` přestane ukládat **vstupní** HTML a serializér ho zapíše jako text; co si do stashe dá `fenced_code` (hotový `<pre><code>`), zůstává nedotčené — proto se bloky kódu escapují dál právě jednou (#3). Žádná nová závislost, `CSS` ani `TEMPLATE` nedotčeny. |
| 2026-07-28 | running | Oprava #4/#6: `IGNOROVANE_ADRESARE = frozenset({".git", "__pycache__"})` + `preskocit(relativni)` na modulové úrovni; `main()` volá `preskocit(p.relative_to(ROOT))`. Relativní cesta schválně — absolutní by srazila `--all` na nulu, kdyby projekt ležel pod složkou toho jména. |
| 2026-07-28 | running | Testy: oba `@unittest.expectedFailure` překlopeny na normální, **assertions beze změny**, upraveny jen docstringy (tvrdily „neopraveno"). Přidáno 14 testů (surové HTML jako text — blokové, řádkové, komentář, placeholder v nadpisu; dvojité escapování ve fenced/odsazeném bloku i v backtickách; entity; nedotčené markdown konstrukce a autolink; filtr adresářů zvlášť a hlouběji ve stromu). Vše přes fixturu `ZakladPrevodu`, tedy nad tempfile (#8). Brána: `unittest discover` **537 testů, OK, expected failures 0** (před chipem 523 / 2 expected failures); `chip_lint.py` rc 0, 0 chyb, 0 varování. |
| 2026-07-28 | running | **Regresní důkaz #7 (postup):** `git archive HEAD \| tar -x` do dvou kopií mimo repo (`pred`, `po`), do `po` zkopírován nový `tools/md2html.py`, `python tools/md2html.py --all` nad `po`, pak `cmp` každého z 29 `.html`. Kontrolní běh se **starým** kódem nad třetí kopií reprodukoval všech 29 souborů bajtově — repo je tedy s generátorem v souladu a rozdíl níž jde skutečně za opravou, ne za starým otiskem. V pracovním stromě jsem `--all` nepouštěl, žádný `.html` v repu jsem nepřegeneroval (dělá orchestrátor po mergi). |
| 2026-07-28 | running | ⚠️ **T3 — oprava přece jen mění jeden výstup.** Ze 29 `.html` je 28 bajtově shodných, mění se **`chips/TEMPLATE.html`**, a to jediným řádkem. Příčina: `chips/TEMPLATE.md:12` má `# CHIP NN — <název>` a `<název>` se dosud bralo jako neznámý **tag**. Dnešek: `<h1 id="chip-nn">CHIP NN — <název></h1>` — zástupný text je v prohlížeči **neviditelný** (prázdný element) a `id` je useknuté. Po opravě: `<h1 id="chip-nn-nazev">CHIP NN — &lt;název&gt;</h1>`. `<title>` se nemění (ten už `html.escape` řešil). Čtu to jako opravu druhé, dosud neviditelné vady téhož druhu, ale rozhodnutí je na uživateli: (a) přijmout a nechat orchestrátora přegenerovat `chips/TEMPLATE.html`, nebo (b) změnit `chips/TEMPLATE.md` na zápis v backtickách — **to už je ale nárok chipu 22, nesahal jsem na to**. Případ je zafixovaný testem `test_04_placeholder_v_nadpisu_je_videt_a_nezmizi`. |
| 2026-07-28 | running | Nález mimo nárok (neopravováno): `docs/*.md` ani `chips/*.md` kromě TEMPLATE žádné surové HTML nemají — brief to předpokládal správně, jen `chips/TEMPLATE.md` unikl (výskyt není `<script>`, ale zástupné `<název>`). |
