# Metodika CHIPS

Postup pro paralelní vývoj s AI agenty. Cílem není rychlost — cílem je, aby
paralelizace **nezhoršila kvalitu** oproti sériové práci.

> 🇬🇧 English translation: [methodology.md](methodology.md). Tenhle soubor je
> zdroj pravdy — když se mění pravidlo, změň obě verze.

---

## 1. Slovník

| Pojem | Význam |
|---|---|
| **chip** | uzavřený balíček práce: seznam issues + hranice + definition of done |
| **okno** | samostatná Claude Code session s vlastním kontextem a limity |
| **orchestrátor** | hlavní smyčka v okně; rozděluje práci subagentům a merguje |
| **subagent** | vedlejší instance s izolovaným kontextem (Agent tool) |
| **brána** | automatická kontrola, bez které se nesmí mergovat |
| **T3** | rozhodnutí, které chip nesmí udělat sám (viz §6) |

Pozor na vrstvy — pletou se:

```
ty  ──►  chip brief  ──►  okno (orchestrátor)  ──►  subagenti  ──►  brána  ──►  merge
         soubor            session                  Agent tool      testy
```

---

## 2. Řezání práce na chipy

**Jediné kritérium je disjunktnost souborů.** Ne stáří issues, ne priorita, ne
téma. Dva chipy, které sáhnou na stejný soubor, se srazí — a to bez ohledu na to,
jak dobře jsou popsané.

Postup:

1. **Vypiš issues** a u každé odhadni, které soubory změní.
   U nejasných to zjisti (grep, přečti issue) — hádání se tady nevyplácí.
2. **Seskup podle souborů**, ne podle témat. Issues sahající na stejný modul
   patří do jednoho chipu, i když spolu tematicky nesouvisí.
3. **Ověř disjunktnost** — `python tools/chip_lint.py` projde všechny briefy
   a nahlásí soubor, který si nárokují dva chipy.
4. **Co nejde rozřezat, nechej sériově.** Když se tři čtvrtiny issues perou o
   jeden centrální soubor, paralelizace ti nepomůže. Udělej ten soubor jako
   chip #1 a ostatní pusť až po jeho merge.

### Jak psát nárok na soubory

Cesty v sekci „Dotčené soubory" jsou **relativní k `repo:`** z frontmatteru.
Absolutní cesta nebo `..` je chyba — nárok pak nejde porovnat s ostatními chipy.

| Zápis | Význam |
|---|---|
| `src/parser.py` | konkrétní soubor, musí v repu existovat |
| `src/` | celý adresář včetně podstromu |
| `src/report_*.py` | vzor; pro kontrolu kolizí se rozbalí na skutečné soubory |
| `src/nove.py  # nový` | soubor, který chip teprve vytvoří — kontrola existence se přeskočí |

Ve stavu `ready` lint ověřuje, že nárokované cesty v repu **opravdu existují**.
Nárok na neexistující soubor je buď překlep, nebo zastaralý brief — a v obou
případech je řez chipu postavený na něčem, co tam není. Značka `# nový` je
jediná výjimka a je záměrně explicitní: musíš ji napsat, ne na ni spoléhat.

> Vzor pokrývá i soubory, které teprve vzniknou. `src/*.py` v jednom chipu tedy
> koliduje s `src/nove.py  # nový` v druhém, i když ten soubor zatím neexistuje.

### Závislosti a vlny

Disjunktnost souborů nestačí, když jeden chip staví základ, na kterém ostatní
teprve mohou začít (kostra repa, číselníky, na které se migrace odkazují).
K tomu slouží `zavisi_na:` ve frontmatteru — seznam chipů, které musí být
`merged` dřív.

Chipy se stejnou hloubkou závislostí tvoří **vlnu** a pouštějí se paralelně:

```
vlna 0:  00                    ← sériově, blokuje vše
vlna 1:  01                    ← základ pro migrace
vlna 2:  02  03  04  07  09    ← paralelně, nezávislé
vlna 3:  05  06  08  10        ← staví na vlně 2
```

`chip_lint.py` hlídá, že závislost existuje, není cyklická a že běžící chip má
předky ve stavu `merged`. **Šířka vlny, ne počet chipů, určuje, kolik oken má
smysl pustit** — deset chipů ve čtyřech vlnách znamená nejvýš pět oken naráz.

### Strop chipu

| Metrika | Doporučení | Proč |
|---|---|---|
| issues | 10–20 | víc se nevejde do jednoho kontextu |
| dotčené soubory | ~15 | nad tím roste šance kolize s jiným chipem |
| doba běhu | pár hodin | delší běh = větší ztráta při selhání |
| **nezávislé opravy s důkazem** | **~2–3** | čtyři narazí na strop jedné odpovědi |

Když strop nesedí, chip rozřež. Dva menší chipy jsou vždycky lepší než jeden,
který nedojede.

**Vedle spotřeby existuje druhá mez: hustota zadání.** Spotřeba (~100 tis.
tokenů na chip) se hlídá sama a projeví se varováním. Hustota ne — chip se
čtyřmi nezávislými opravami, ke každé regresní důkaz, narazí na limit **jedné
odpovědi** a spadne bez varování uprostřed práce (chip 10, vlna 4).

**Řež podle povahy práce, ne podle počtu issues.** Chip 10 se dělil na „odkud
nástroj bere vstup" (parsování) a „kdy má zamítnout" (rozhodovací pravidla) —
ne na „první dva nálezy" a „druhé dva". Mechanické dělení nutí agenta přepínat
mezi dvěma způsoby uvažování uvnitř jednoho chipu, což je právě ta hustota,
kvůli které se řeže.

**Pozor na pojmenování rozřezaných chipů.** Očekávaná volba `10a`/`10b` by
tady rozbila bránu: hook i `chip_gate` matchují číslo chipu jako `(\d+)`,
takže větev `ai/chip-10a/…` se rozpozná jako **chip 10** a ověří se cizí brief.
Nová čísla na konci řady jsou bezpečnější — pojmenování se přizpůsobí nástroji,
protože nástroj je vynucovací bod.

---

## 3. Izolace: worktree, ne složka

Nejčastější chyba je pustit N session nad stejným working tree. Výsledkem nejsou
git konflikty (ty bys aspoň viděl), ale **tiše ztracené změny** — dvě session
načtou soubor, obě ho zapíšou, druhý zápis přemaže první.

Řešení je `git worktree`: jeden repozitář, N nezávislých checkoutů.

```bash
git worktree add ../repo-chip-01 -b ai/chip-01/refaktor-parseru
```

Každé okno pracuje ve své složce, na své větvi, s vlastním indexem. Merguje se
až na konci a případný konflikt řeší git normálně a viditelně.

Claude Code na to má `EnterWorktree` (pro session) a subagenti parametr
`isolation: "worktree"`. `tools/chip_run.py` to udělá za tebe.

**Navazující chip se větví z předchůdce, ne z HEAD.** Když chip B staví na
práci chipu A, která ještě není zmergovaná, vzalo by mu větvení z HEAD přesně
to, na čem má stavět:

```bash
python tools/chip_run.py 02 --od ai/chip-01/zaklad
```

Agent takového chipu dostane v zadání navíc větu, že pod jeho prací leží cizí
rozpracovaný kód — **needituje ho ani neopravuje**, nález v něm patří do Logu.
Bez toho by nedodělaný kód předchůdce považoval za součást hlavní větve a
„spravil" ho, čímž by vyrobil právě tu kolizi mezi balíčky, kvůli které chipy
existují. Lint navazující dvojici pustí a jen připomene pořadí merge —
předek `gated` je varování, `blocked` nebo nehotový předek zůstává chyba.

**Greenfield: první chip v projektu, který ještě není.** V čerstvě `init`nutém
repu není `HEAD`, ze kterého by `worktree add` větvil, a lint padá na
neexistujícím repu i na nárokovaných cestách. Obojí se řeší vědomým
prohlášením, ne měkčím defaultem:

```yaml
greenfield: ano      # ve frontmatteru briefu — repo teprve vznikne
```

```bash
python tools/chip_run.py 01 --zaloz-repo    # git init + prázdný kořenový commit
```

Nad repem, které už historii má, `--zaloz-repo` **nedělá nic** a řekne to;
`greenfield: ano` se tam hlásí jako zastaralý příznak k smazání. Kontrola
*tvaru* cesty (relativní, bez `..`) se nevypíná ani s příznakem — je vstupem
do porovnání disjunktnosti, takže měkčit ji by znamenalo měkčit disjunktnost.

> **Úklid:** `python tools/chip_run.py 01 --uklid` — **až po mergi**, jinak se
> ti nasbírají desítky mrtvých checkoutů. Nezmergovanou větev nástroj uklidit
> odmítne (viz níž); vědomé opuštění chipu je `--uklid --presto`.

Worktree není jen pracovní složka, je to **jediné místo, kde jde spustit brána**
chipu. Proto s ním nástroje zacházejí jako se stromem, který v dané fázi vlastní
někdo jiný:

| Fáze | Kdo do worktree píše | Co do hlavního stromu NESMÍ |
|---|---|---|
| před spuštěním | `chip_run.py` (založí, přepíše `stav:`) | nic — hlavní strom zůstává čistý |
| běh chipu | agent (kód, Log, checkboxy) | agent do hlavního stromu nesahá vůbec |
| merge | git | — |
| po mergi | `chip_run.py --uklid` (smaže) | — |

Odtud plyne i to, **kterou kopii briefu smí `--stav` přepsat**: tu ve worktree,
ne v hlavním stromě. Brief je verzovaný soubor, takže ho worktree má vlastní —
a zápis do hlavního stromu by tam nechal necommitnutou změnu souboru, který
merge přepisuje. `git merge` takový merge odmítne (`Your local changes … would
be overwritten`). Pravidlo „nesahej na brief běžícího chipu" platí i pro
nástroje, ne jen pro lidi.

---

## 4. Brána: kde se rozhoduje o kvalitě

Věta „buď důsledný a vše pečlivě zkontroluj" nemá žádnou vynucovací sílu. Je to
přání. Sílu má jen něco, co **selže samo od sebe**, když je něco špatně.

Brána = posloupnost příkazů, které musí projít, jinak se nemerguje:

```bash
pytest -q                    # testy
python -m build              # build
python smoke_test.py         # smoke test proti reálným datům
```

Tři úrovně vynucení, od nejslabší po nejsilnější:

| Úroveň | Mechanismus | Dá se obejít? |
|---|---|---|
| instrukce v promptu | „zkontroluj to" | ano, i nechtěně |
| skill (`/chip`, `/ship`) | postup, který si agent načte | ano, když ho nezavolá |
| **hook** | harness spustí sám před merge | **ne** |

Třetí úroveň je od 2026-07-26 postavená: `tools/hook_chip_gate.py` visí na
PreToolUse a **zamítne `git merge` chip větve, dokud brána není zelená**.
Nemá vlastní seznam příkazů — vezme sekci „Ověření (brána)" z briefu toho
chipu, jehož větev se merguje. Vynucuje tedy přesně to, co si chip sám slíbil,
a funguje v libovolném repu.

Aby neotravoval jinde, je rozsah úzký — hook se ozve jen když platí všechno:
příkaz spouští `git merge`, mergovaná větev je `ai/chip-NN/...` (nebo starší
`chip/NN-...`) a u cílového repa jdou najít chip briefy. Jinak mlčky pustí dál.

**Briefy nemusí ležet v repu.** Dokud byl jediným signálem adresář `chips/`,
vylučovaly se dvě věci, které se vylučovat nemají: tvrdá brána a nulová stopa
v cizím repu. Kdo dal briefy stranou (`--dir`, typicky klientské repo), dostal
hook, který **mlčky pouštěl červené merge** — a brána vypadala, že funguje.
Signály jsou proto tři, od nejkonkrétnějšího k nejobecnějšímu:

| Signál | Kdy platí | Pro co je |
|---|---|---|
| `chips/` v repu | adresář existuje | výchozí případ, vlastní projekty |
| marker `.chips` | soubor existuje; první neprázdný řádek je cesta k briefům | repo, kde po metodice nesmí zůstat stopa |
| env `CHIPS_DIR` | ukazuje na briefy **tohoto** repa (`repo:`) | session nad jedním projektem |

Marker stačí netrackovat (`.git/info/exclude`) — jeden dotfile je stopa, se
kterou se dá žít i v cizím repu; adresář s desítkou briefů ne. A protože marker
nikdo nezaloží omylem, **rozbitý marker zamítá** místo aby mlčel: překlep
v cestě by jinak vypnul bránu přesně tam, kde si ji uživatel výslovně přál.

U `CHIPS_DIR` je to obráceně — je to globální proměnná, ne přihláška konkrétního
repa. Přijme se jen tehdy, když v ní leží brief hlásící se k tomuhle repu; jinak
by proměnná nastavená kvůli projektu A rozhodovala o merge v projektu B.

**Větev se bere z argumentu za `merge`, ne odkudkoli z příkazu.** Složený
příkaz `git branch -d ai/chip-04/x && git merge ai/chip-05/y` by jinak nechal
ověřit bránu chipu 04 a pustil merge chipu 05. Totéž platí pro `git -C` — bere
se jen ten, který patří samotnému mergi. U octopus merge (`git merge A B`) musí
projít brána **každé** větve.

**Když bránu není kde ověřit, hook zamítá** — neověřuje náhradní strom:

| Situace | Proč zamítnout |
|---|---|
| worktree chipu neexistuje | brána v hlavním stromě by ověřila kód **bez změn chipu** a vrátila falešnou zelenou |
| ve worktree jsou necommitnuté změny | merge bere commitnutý tip, brána by tedy měřila jiný stav, než jaký se merguje |
| stav worktree nejde zjistit | nevědět, co ve stromě je, se pro potřeby brány rovná nemít ho |

Praktický důsledek: **úklid worktree patří až po mergi.** Kdo uklidí dřív,
nemerguje — a jediná cesta ven je obejít vlastní bránu. Proto to není jen
doporučení: `chip_run.py NN --uklid` nezmergovanou větev uklidit **odmítne**
(`merge-base --is-ancestor`, takže projde i fast-forward). Opuštěný chip se
uklízí vědomě přes `--uklid --presto`.

Ručně tutéž bránu spustíš `python tools/chip_gate.py NN` — **taky ve worktree
chipu**, ne v hlavním stromě. Do 2026-07-28 to CLI dělalo obráceně a tiše:
brána chipu 18 hlásila zelenou nad hlavním stromem se 454 testy, zatímco ve
worktree jich bylo 481. Rozdíl 27 testů byla přesně ta práce, o které měla
brána rozhodovat. Když `worktree:` chybí nebo není vyplněný, nástroj dnes
**selže** — tichý fallback na hlavní strom byl celá ta vada.

**Za běhu vlny ti `chip_status.py` lže.** Čte briefy v hlavním stromě, kde se
za běhu chipu nehýbe nic — checkboxy i soubory se mění ve worktree. Živý stav
dává `python tools/chip_dashboard.py`: čte z worktree každého chipu a z gitu,
tedy z tvrdých zdrojů, ne z toho, co agent napsal do souhrnu. Při vlně 6 byl
rozdíl 37 odškrtnutých issues a pět stavů.

**Když brána selže, chip nekončí mergem, ale otevřeným PR.** To je celý rozdíl
mezi „autonomní" a „bez dohledu".

---

## 5. Definition of done

Musí jít ověřit příkazem, ne názorem. Test:

| ❌ neměřitelné | ✅ měřitelné |
|---|---|
| „parser je zrefaktorovaný" | „`pytest tests/test_parser.py` projde, `parser.py` < 300 řádků" |
| „kód je čistší" | „`ruff check` bez nálezů" |
| „funguje to" | „smoke test na `data/sample.xlsx` vrátí 42 řádků" |

Když DoD nejde napsat jako příkaz, chip ještě není připravený k puštění.

### Měřitelná ≠ silná

Příkaz je nutná podmínka, ne dostatečná. **Doda ve tvaru „nástroj vrátí 0 chyb"
je slabá, pokud nedokazuje, že kontrola vůbec proběhla.** Chip 11 měl v DoD
„lint nad ERP-CHIPS vrátí 0 chyb"; vracel je i před opravou, protože všech
11 briefů je ve stavu `draft` a kontrola cest se na ně nespouští. Agent to
odhalil sám a nahradil přímým měřením návratové hodnoty opravené funkce.

Test síly: **prošla by tahle DoD i na rozbité verzi?** Když ano, měří přítomnost
nástroje, ne chování. Silná DoD porovnává **konkrétní hodnotu před a po**, ne
exit kód.

---

## 6. Eskalace — co chip nesmí rozhodnout sám

Označ dopředu, co je **T3** (kritické). Typicky:

- změna veřejného API nebo formátu dat
- migrace schématu / nevratná operace nad daty
- cokoliv v `patients/` (citlivá data) a firemních projektech
- nová závislost, změna licence
- bezpečnostní rozhodnutí

Když chip narazí na T3, **zastaví se a otevře PR s otázkou**. Nehádá, nehlasuje.

### Proč ne „ať se poradí s jiným modelem"

Láká to: při nejistotě nechat rozhodnout Codex/Gemini/Grok a jet dál. Nefunguje
to, protože:

- ty modely **nevidí tvoje repo, historii ani dřívější rozhodnutí**;
- shoda tří modelů není pravda, ale průměr tří dohadů;
- výsledek se pak zmerguje **bez tvého vědomí** — nejistota zmizela z logu.

Druhý názor v kódu jsou **testy a build**, ne další model. Cross-model konzultace
má smysl na *návrh* (než se začne psát), ne jako náhrada tvého rozhodnutí.

---

## 7. Životní cyklus chipu

```
draft ──► ready ──► running ──► gated ──┬─► merged
                                        └─► blocked (PR + otázka)
```

| Stav | Znamená |
|---|---|
| `draft` | brief se píše, hranice ještě nejsou jisté |
| `ready` | vyplněný brief, `chip_lint.py` čistý → smí se pustit |
| `running` | běží ve worktree |
| `gated` | práce hotová, čeká na bránu |
| `merged` | brána zelená, sloučeno, worktree uklizen |
| `blocked` | narazil na T3 nebo brána selhala → čeká na tebe |

Stav drž v hlavičce briefu (`chips/NN-*.md`), ne v hlavě.

---

## 8. Doporučený rozjezd

1. **Jeden chip celý ručně**, ať víš, jak vypadá dobrý výstup a kolik to sežere.
2. **Tři chipy paralelně** — tady se ukáže, jestli řez sedí a kde to drhne.
3. **Teprve pak deset.** Deset oken s max effortem plus subagenti je enormní
   spotřeba; na limity narazíš dřív než na výsledky.

Mezi kroky vždycky vyhodnoť: kolik chipů skončilo `blocked`, kolikrát brána
chytila chybu, kolikrát jsi musel zasáhnout. Když je zásahů hodně, chyba je
skoro vždycky v **řezu** (chipy si lezou do zelí) nebo v **DoD** (nebyla
měřitelná) — ne v modelu.

---

## 9. Co ukázal pilot (2026-07-26)

První ostrý běh: šest chipů ve dvou vlnách nad tímhle repem, každý ve vlastním
worktree s vlastním oknem. Výsledek: 6/6 merged, nula `blocked`, nula zásahů
mimo nárokované soubory, nula konfliktů při merge, 0 → 201 testů.

**Co fungovalo podle návrhu**

- **Řez podle souborů drží.** Ani jeden z šesti agentů nesáhl mimo svůj nárok,
  přestože k tomu měli příležitost (chyběly jim funkce, které si museli napsat
  lokálně). Místo toho to zapsali do Logu — pět nálezů putovalo nahoru.
- **Eskalace místo hádání.** Všech šest nezávisle odmítlo přepnout `stav:` ve
  frontmatteru: mandát chipu je Log a checkboxy, stav je rozhodnutí orchestrátora.
- **`expectedFailure` jako kanál pro nález.** Chip, který našel chybu v kódu mimo
  svůj nárok, ji neopravil — zafixoval ji testem označeným `@unittest.expectedFailure`
  a poslal nahoru. Chyba tím přežila merge **viditelně** a opravující chip ji
  musel odznačit, jinak by sada spadla na `unexpected success`.

**Co se muselo doplnit**

| Nález | Důsledek pro metodiku |
|---|---|
| Brief je sdílený soubor orchestrátora a chipu | Orchestrátor **nesmí** editovat brief běžícího chipu. Stav přepínej před spuštěním nebo až po merge. |
| `git worktree add` větví z HEAD, ne z working tree | Rozdělanou práci commitni **před** založením worktree, jinak chip dostane starý kód. |
| Lint kontroloval nároky proti hlavnímu stromu, ne proti worktree | Existence cest se musí ověřovat tam, kde chip opravdu pracuje. |
| Disjunktnost souborů ≠ disjunktnost důsledků | Sdílený základ (`chip_common.py`) může chip vlastnit, ale ne přejmenovávat. Hranici, kterou seznam cest nevyjádří, dopiš slovy do sekce Eskalace. |
| Zelená v izolaci ≠ zelená dohromady | Po **každém** merge pusť celou sadu na hlavní větvi, ne jen bránu chipu. |

**Spotřeba.** Jeden chip = zhruba 80–110 tisíc tokenů (6 chipů ≈ 550 tisíc).
To je tvrdý strop na šířku vlny: deset chipů naráz je půl milionu tokenů
v jedné vlně, a to ještě než začneš cokoli ověřovat.

### Druhý pilot: cizí repo a role reviewera (2026-07-26)

Sedm chipů nad živým firemním repem (0 → 235 testů). Přineslo dvě
věci, které první pilot ukázat nemohl.

**Reviewer je pro bránu totéž, co worktree pro izolaci.** Brána je jen tak
přísná, jak přísné jsou testy — a ty píše týž model, který psal kód. Nasadili
jsme proto **nezávislého agenta, který kód nepsal**, s jediným mandátem: hlásit,
neopravovat. Jeho metodou je **mutační testování** — rozbít kód a měřit, kolik
mutací sada zabije. Výsledek: u chipu 05 našel dvě věcné mezery, u chipu 06
tiché selhání (`exit 0`, i když se nepodařilo přečíst ani jeden soubor) a tři
nezamčené hranice. Nic z toho brána nechytila, protože všechno bylo *uvnitř*
autorovy úvahy konzistentní.

Nástroj `chip_review.py` dělá strojovou část (rozsah změn proti nároku, testy
bez assertů, DoD proti příkazům brány) a `--zadani` vypíše brief pro agenta.
**Nedělá verdikt** — sbírá podklady.

**Kde přestat.** Řetěz chip → review → chip → review → chip je z principu
sériový a trval přes hodinu. Každá vrstva našla něco nového, ale výnos klesá:
třetí chip už z poloviny jen zamykal správné chování. Levnější je **nálezy
z review zabalit do jednoho chipu** než je řešit jeden po druhém.

**Navazující chipy metodika dlouho neřešila.** Chip, který staví na
nezmergovaném předchůdci, se musí větvit z jeho větve — `chip_run.py` uměl jen
z HEAD, takže worktree se zakládal ručně, a `chip_lint` hlásil nesplněnou
závislost jako chybu. Vyřešeno vlnou 5 (2026-07-28): `chip_run.py --od <ref>`
a rozlišení stavů předka v lintu, viz §3. Merge potomka pořád přinese i práci
předka — to je vlastnost, ne vada, a proto se merguje v pořadí.

**`chip_run.py --stav` porušoval vlastní pravidlo.** Přepisoval `stav:` v briefu
v hlavním stromě, zatímco agent edituje tentýž soubor ve worktree → merge skončil
konfliktem. Pravidlo „nesahej na brief běžícího chipu" musí platit i pro nástroje,
ne jen pro lidi. Opraveno 2026-07-28: zápis jde do kopie ve worktree, hlavní strom
zůstává čistý (§3).

**Meze pilotu.** CHIPS na sobě samém je příznivý případ — malé repo, čistý
Python, žádné cizí závislosti, issues psal tentýž člověk, co je řezal. Než
tomu začneš věřit u velkého repa, zopakuj to na cizím kódu.

### Vlna 4: co vydrží přerušení (2026-07-27)

Vlna opravovala 10 nálezů z externího code review. Všichni tři agenti spadli
uprostřed práce na limitech účtu — **ne na kódu**. Po resetu byla dokončena
celá: 10/10 nálezů, 366 → 413 testů, 4/4 zelená brána.

**Izolace obstála i při trojnásobném pádu.** Hlavní strom zůstal čistý a
nedotčený; práce dvou agentů byla v gitu na jejich větvích a dala se dopsat.
Chip, který nezačal, se prostě rozřezal a pustil znovu.

**Než pustíš agenta na „rozdělaný" chip, přečti diff — ne poznámku o něm.**
Záchranný zápis tvrdil, že u chipu 12 se neví, co je splněné; ve skutečnosti
byl hotový celý včetně Logu a odškrtané DoD. Chip 11 měl všechny čtyři opravy
nakódované a pokryté 13 testy. Kdybych věřil zápisu, agenti by přepisovali
hotovou práci.

**Chip vidí na věci, které zadání nezná.** Agent chipu 13 při opravě „ber větev
z argumentu za `merge`" objevil nález, který code review minul: octopus merge
(`git merge A B`) ověřoval bránu jen první větve a druhou pustil bez kontroly.
Vyplynulo to z opravy — když se větve berou z argumentů, je vidět, že jich může
být víc. **Dobré zadání otevírá výhled, nejen vymezuje práci.**

**Úklid worktree patří až po mergi.** Hook od chipu 14 zamítá merge, když
worktree chipu chybí — bránu není kde ověřit. Kdo uklidí dřív, nemerguje.
Od 2026-07-28 to hlídá i `--uklid` sám: nezmergovanou větev uklidit odmítne.

**Pravidlo, které drží jen v dokumentaci, se poruší nástrojem.** Všechny tři
opravy z 2026-07-28 (pořadí úklidu, cíl zápisu `--stav`, hledání briefů) měly
tentýž tvar: pravidlo bylo správně napsané v metodice a nástroj ho porušoval.
Když se v projektu objeví pravidlo, ptej se rovnou, **který kód ho může
porušit** — ne jen kdo si ho má přečíst.

Vlna 6 přidala další tři případy téhož vzorce: brána spuštěná ručně měřila
hlavní strom, `chip_status.py` ukazoval mrtvá data o běžících chipech, a
reviewer hlásil jako nález něco, co je normální stav. **Nejčastější podoba
téhle vady je „nástroj čte hlavní strom, ale pravda je ve worktree".**
Objevila se dnes čtyřikrát ve čtyřech různých souborech.

### Falešný signál je vada, i když je pravdivý

Nástroj, který hlásí šum, si vychová čtenáře, který ho přeskakuje — a tomu pak
unikne i hlášení, které je pravé. Chip 15 to řešil u placeholderů v lintu,
chip 21 u reviewera. Oba dopadly stejně: **řešením není hlášku ztlumit, ale
zúžit ji na případy, kdy skutečně škodí**, nebo ji přeformulovat na to, čím
doopravdy je.

Odtud dělící pravidlo, které stojí za to držet v každém nástroji projektu:

| | znamená | patří tam, kde |
|---|---|---|
| **nález** | „tohle je špatně" | nástroj má úplná data a může rozhodnout |
| **otázka** | „tohle ověř ty" | nástroj nemá čím rozhodnout, ale ví, kam se podívat |
| **data** | inventura | ani jedno — je to podklad, ne verdikt |

---

## 10. Antipatterny

| Antipattern | Co se stane |
|---|---|
| N oken nad jedním working tree | tiše ztracené změny |
| „buď autonomní a důsledný" bez brány | model si sám potvrdí, že to zkontroloval |
| řezání podle témat místo souborů | kolize, poslední merge vyhrává |
| hlasování modelů místo eskalace | nejistota zmizí z logu, nikdo o ní neví |
| chip bez měřitelné DoD | „hotovo" nejde ověřit, musíš číst všechno |
| rovnou 10 chipů bez pilotu | narazíš na limity a nevíš proč |
