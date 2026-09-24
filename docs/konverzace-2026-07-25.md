# Konverzace 2026-07-25 — vznik projektu CHIPS

Záznam diskuse, ze které projekt vznikl. Uloženo na žádost uživatele.
Účastníci: **Richard** / **Claude** (Claude Code, Opus 5).

---

## 1. Otázka: „Co jsou chipy a jak orchestrují AI?"

První kolo bylo nedorozumění — slovo „chipy" mohlo znamenat hardware (GPU/TPU)
nebo něco v Claude Code. Po upřesnění šlo o **Skills a subagenty v Claude Code**.

### Co je Skill

Skill = složka se souborem `SKILL.md`. Žádný kód, žádný proces, žádné API.

```
~/.claude/skills/sync-tasks/
└── SKILL.md      ← frontmatter (name + description) + instrukce v markdownu
```

Na startu session se do kontextu načte **jen `description`**. Tělo souboru se
načte teprve ve chvíli, kdy se skill zavolá — to je **progressive disclosure**.
Bez toho by desítky nainstalovaných skillů sežraly kontext dřív, než uživatel
napíše první slovo. Proto je `description` nejdůležitější řádek celého skillu:
je to jediné, podle čeho se model rozhoduje, jestli skill načíst.

Aktivace: buď explicitně (`/sync-tasks`), nebo automaticky podle shody záměru
s popisem.

### Skill neorchestruje AI, orchestruje model

Skill není agent — neběží, nemá vlastní model, nic nespouští. Je to **předpis,
kterým se model řídí místo své výchozí úvahy**. Skutečnou práci často dělá
deterministický skript; skill jen říká, jak ho použít. (Příklad z workspace:
`sync-tasks` = skript `sync_tasks.py` + procedura „nejdřív `--dry-run`,
shrň, počkej na souhlas, pak zapiš".)

### Pět vrstev orchestrace

| Vrstva | Co to je | Kontext |
|---|---|---|
| **Skill** | markdown instrukce načtená do modelu | sdílený |
| **Subagent** | druhá instance s vlastním kontextem | izolovaný |
| **MCP server** | externí proces poskytující nástroje | mimo model |
| **Hook** | skript spuštěný harnessem při události | žádný |
| **Workflow** | JS skript orchestrující N subagentů | řídí ostatní |

**Skill vs. subagent** — jediné rozhodnutí, které je potřeba umět:

- **Skill**, když má jinak pracovat hlavní model. Výsledek zůstává v hovoru,
  vidíš každý krok, můžeš zasáhnout.
- **Subagent**, když chceš práci *odstínit*. Vlastní čistý kontext, vrátí jen
  závěr. Cena: nevidí hovor, ty nevidíš jeho práci.

Subagenti běží **paralelně** — to je ta „orchestrace": ne AI řídící AI, ale
rozdělení nezávislé práce místo sériového zpracování.

---

## 2. Otázka: „Někdo používá nějaké chips k řízení celého vývoje s AI"

Doložené screenshotem promptu (parafráze):

> Chci v několika oknech rozjet maximum úkolů, které se stanou orchestrátory a
> budou volat agenty Opus 5 effort Max… mergovat bude samotný orchestrátor (jen
> pro zásadní T3 bude vyžadovat mé schválení) po důsledné kontrole. Předpoklad
> je 10 orchestrátorů, kteří přes agenty vyřeší 10–20 issues… **Připrav tedy
> minimálně 10 chipů, které dohromady vyřeší nejméně 100 issues.** Pokud si
> nebudou vědět rady, mohou konzultovat s Codex, Gemini, případně Grok…
> Já nechci do toho vůbec vstupovat, musí být vše absolutně autonomní… vždy ať
> se raději víc kontroluje, kvalita je víc než kvantita nebo rychlost.

### Závěr: „chip" není termín

Neexistuje technologie, feature ani standard toho jména. V dokumentaci Claude
Code ani Anthropic to nenajdeš. Autor promptu si slovo zavedl sám. Znamená:

> **chip = balíček práce** — uzavřený objem úkolů (10–20 issues), který dostane
> jeden orchestrátor a odpracuje ho nezávisle na ostatních.

Metafora pokerového žetonu. Standardní názvy pro totéž: *work packet*, *batch*,
*task bundle*.

> **Filtr na AI-dev žargon:** když slyšíš termín, zkus ho najít v oficiální
> dokumentaci. Když tam není, je to něčí metodika — může být dobrá, ale posuzuj
> ji podle toho, co dělá, ne podle toho, jak se jmenuje.

### Architektura, kterou prompt popisuje

```
        ty  ─── napíšeš 10 "chipů" (= 10 zadání)
         │
    ┌────┼────┬────────┬─────────┐
    ▼    ▼    ▼        ▼         ▼
  okno1 okno2 okno3  ...       okno10      ← samostatné session
    │                                         "orchestrátoři"
    ▼
  ┌─ subagent ── issue #12
  ├─ subagent ── issue #13
  └─ subagent ── issue #14
    │
    ▼
  orchestrátor zkontroluje + zmerguje sám
  (T3 = kritické → čeká na schválení)
```

Mapování slangu na skutečnost:

| Slang | Skutečnost |
|---|---|
| „chip" | textové zadání / soubor s briefem pro jedno okno |
| „okno" | samostatná Claude Code session |
| „orchestrátor" | hlavní smyčka v tom okně |
| „agenti" | subagenti přes Agent tool |
| „effort Max" | reálný přepínač reasoning effortu |
| „konzultovat s Codex/Gemini/Grok" | CLI těch nástrojů přes Bash |

### Tři díry v původním plánu

1. **Deset oken píše do jednoho repa.** Prompt to vůbec neřeší. Nejde o git
   konflikty, ale o tiše ztracené změny. Řešení: git worktrees.
2. **Konzultace s cizími modely nepřidává správnost.** Nemají přístup k repu ani
   historii; shoda tří modelů = průměr tří dohadů. Skutečný druhý názor v kódu
   jsou testy a build.
3. **„Absolutně autonomní" + „kvalita nad kvantitou" si odporují**, pokud
   neexistuje automatická brána. Bez ní „důsledná kontrola" znamená jen, že si
   model sám o sobě řekl, že to zkontroloval.

> **Klíčové pravidlo:** autonomie se nedává promptem, ale ověřováním. Věta
> „buď důsledný" je přání. Sílu má hook, který zablokuje commit, nebo CI, které
> nepustí merge.

### Šest doporučení, ze kterých vznikla metodika

1. Řezat issues podle **nezávislosti souborů**, ne podle stáří.
2. Každý balíček = **vlastní git worktree**.
3. Brief balíčku uložit **jako soubor** (`chips/01-*.md`).
4. **Brána místo dohledu** — žádný merge bez zeleného `/ship`.
5. **Začít se třemi, ne deseti** — zjistit spotřebu a slabá místa.
6. **Jeden chip napřed celý ručně**, ať je vzor, jak vypadá dobrý výstup.

---

## 3. Rozhodnutí

Richard: *„vytvoř mi z toho projekt CHIPS, líbí se mi to a mohli bychom to
zkusit"* → založen tento projekt (v kořeni workspace, jako
nástroj napříč workspace).

Body 1–6 výše se staly obsahem [metodika.md](metodika.md); slovo „chip" dostalo
backronym **C**ontained **H**ands-off **I**ssue **P**acket.
