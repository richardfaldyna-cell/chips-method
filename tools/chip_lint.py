"""Ověří, že chipy jsou připravené a navzájem se nepřekrývají.

Kontroluje:
  1. platný stav ve frontmatteru
  2. přítomnost povinných sekcí a že nezůstaly nevyplněné (placeholdery)
  3. DISJUNKTNOST nárokovaných souborů napříč chipy  ← hlavní důvod existence
  4. že nárokované cesty v repu opravdu existují (u chipů ve stavu 'ready')
  5. závislosti: běžící chip s předkem `gated` je jen varování s pořadím merge
     (předek dojel, staví se na něm), předek nehotový (`draft`/`ready`/
     `running`) nebo `blocked` zůstává chyba

Dělící čára mezi chybou a varováním je jediná: **chyba = nejde s tím
pokračovat, varování = jde, ale musíš vědět v jakém pořadí.** Lint je brána
s návratovým kódem, takže každá chyba navíc někoho zastaví — a každé
změkčení na varování je tvrzení, že se postupovat dá.

Frontmatter `greenfield: ano` = repo teprve vznikne (první chip projektu):
neexistující `repo:` je pak varování a nárokované cesty se neověřují — není
proti čemu. Bez příznaku obojí zůstává chybou; příznak je vědomé prohlášení,
ne měkčí default.

Použití:
    python tools/chip_lint.py            # všechny chipy
    python tools/chip_lint.py --ready    # jen ty ve stavu ready/running

Návratový kód 1 = nález (vhodné do hooku / CI).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path, PurePosixPath
from typing import Callable, NamedTuple

from chip_common import (ROOT, STAVY, nacti_vse, nastav_chips_dir,
                         pridej_arg_dir, utf8_vystup)

POVINNE = {
    "issues": "Issues",
    "dotcene soubory": "Dotčené soubory",
    "definition of done": "Definition of done",
    "overeni brana": "Ověření (brána)",
}


class Placeholder(NamedTuple):
    """Vzorový řetězec ze šablony + JEDINÉ místo, kde jeho výskyt něco znamená.

    Hledat placeholder v celém textu briefu nejde: chip, který o něm jen píše
    (nebo ho zrovna opravuje), by dostal varování za citaci — a na trvalý šum
    si člověk zvykne a přestane ho číst, takže mu unikne to pravé. Proto se
    každý hledá tam, kde nevyplněný opravdu škodí (`kde`), a jinde se ignoruje.

    `hodnoty(c)` vrací řetězce ke kontrole — vždy jen hodnoty, ne syrový text:
    u frontmatteru hodnotu za dvojtečkou bez komentáře (`chip_common.parse` ho
    odřízne, takže `stav: ready  # …` nic nerozhodí), u nároků a issues jejich
    text. `cela_hodnota` = placeholder musí být celá hodnota, ne jen její část;
    zapíná se u cest, kde by podřetězec chytal i legitimní `balik/src/parser.py`.
    """

    text: str
    kde: str
    hodnoty: Callable[..., list[str]]
    cela_hodnota: bool = False


def _frontmatter(*klice: str) -> Callable[..., list[str]]:
    """Hodnoty vyjmenovaných klíčů frontmatteru (chybějící klíč = prázdno)."""
    return lambda c: [c.meta.get(k, "") for k in klice]


PLACEHOLDERY = (
    # Nárok je fikce, když míří na vzorovou cestu ze šablony — v próze nebo
    # v Logu je `src/parser.py` naopak běžná citace (brief 09).
    Placeholder("src/parser.py", "nárokovaná cesta v 'Dotčené soubory'",
                lambda c: c.soubory(), cela_hodnota=True),
    # Vzorové issue zůstalo neopsané. Mimo sekci Issues nevadí.
    Placeholder("#12 — stručný popis", "text issue", lambda c: c.issues()),
    # Brief bez skutečného repa se nedá spustit (chip_run podle `repo:` zakládá
    # worktree); tentýž řetězec v próze je jen ukázka tvaru.
    Placeholder("C:/cesta/k/repu", "frontmatter 'repo:'", _frontmatter("repo")),
    # Nedosazený název chipu v identitě briefu → větev `ai/chip-NN/kratky-…`.
    # ZÁMĚRNĚ jen frontmatter, ne issues: brief 12 tenhle placeholder opravoval
    # a má ho i v textu issue — kontrola issues by hlásila právě ten chip,
    # který problém řešil.
    Placeholder("kratky-nazev-s-pomlckami", "frontmatter 'nazev:'/'vetev:'",
                _frontmatter("nazev", "vetev")),
)


def zbyle_placeholdery(c) -> list[str]:
    """Hlášky o vzorových řetězcích ze šablony, které v briefu zůstaly nevyplněné.

    Jedna hláška na placeholder (víc výskytů na témž místě je pořád jeden
    nedodělek) a vždy s uvedením místa — aby bylo z hlášky vidět, co opravit.
    """
    out: list[str] = []
    for ph in PLACEHOLDERY:
        for hodnota in ph.hodnoty(c):
            if (hodnota == ph.text) if ph.cela_hodnota else (ph.text in hodnota):
                out.append(f"{c.path.name}: zůstal placeholder ze šablony: "
                           f"'{ph.text}' ({ph.kde})")
                break
    return out


def absolutni(cesta: str) -> bool:
    """`/src/x` i `C:/src/x` — PurePosixPath windowsový disk za absolutní nepovažuje."""
    return cesta.startswith(("/", "\\")) or (len(cesta) > 1 and cesta[1] == ":")


def git_koren(start: Path) -> Path | None:
    """Nejbližší adresář nad `start`, který je kořenem git stromu (jinak None).

    Ve worktree je `.git` **soubor** (obsahuje `gitdir: …`), v hlavním checkoutu
    adresář — proto se ptáme jen na existenci, ne na `is_dir()`.
    """
    try:
        p = start.resolve()
    except OSError:                      # pragma: no cover — rozbitá cesta
        p = start
    if not p.is_dir():
        p = p.parent
    for adresar in (p, *p.parents):
        if (adresar / ".git").exists():
            return adresar
    return None


def _git_spolecny_adresar(koren: Path) -> Path | None:
    """Společný `.git` adresář stromu — u worktree ukazuje do hlavního repa.

    Ekvivalent `git rev-parse --git-common-dir` bez subprocesu: `.git` jako
    soubor nese `gitdir: …/.git/worktrees/<jméno>` a část `worktrees/<jméno>`
    se odřízne. Dva stromy patří k témuž repozitáři právě tehdy, když sdílejí
    tenhle adresář. Nečitelný/neznámý tvar → None (bere se jako cizí repo).
    """
    g = koren / ".git"
    try:
        if g.is_dir():
            return g.resolve()
        radek = g.read_text(encoding="utf-8").strip().splitlines()[0]
    except (OSError, UnicodeDecodeError, IndexError):
        return None
    if not radek.startswith("gitdir:"):
        return None
    gitdir = Path(radek[len("gitdir:"):].strip())
    if not gitdir.is_absolute():
        gitdir = koren / gitdir
    if gitdir.parent.name == "worktrees":
        gitdir = gitdir.parent.parent
    try:
        return gitdir.resolve()
    except OSError:                      # pragma: no cover — rozbitá cesta
        return None


def strom_ke_kontrole(c) -> Path | None:
    """Strom, proti kterému se ověřuje existence nárokovaných cest (nálezy N2, #2).

    Leží-li brief uvnitř git stromu **téhož repozitáře** jako `repo:`, platí
    strom briefu — u chipu běžícího ve vlastním worktree ukazuje `repo:`
    z frontmatteru na HLAVNÍ strom a lint by jinak kontroloval nároky proti
    cizímu checkoutu (soubor smazaný ve worktree by tiše prošel; nález N2).

    Leží-li brief v CIZÍM repozitáři, platí `repo:` — layout ERP-CHIPS drží
    briefy v jednom repu a cílový projekt v jiném; strom briefu by tu existenci
    nároků ověřoval proti špatnému repozitáři (nález #2, chip 11). Týž
    repozitář se pozná přes společný `.git` adresář (worktree vs. hlavní
    strom sdílejí `--git-common-dir`), a `repo:` musí být kořenem svého
    stromu — jinak by se nároky přestaly vztahovat k adresáři z frontmatteru.
    Mimo git (režim `--dir` nad samostatným adresářem) se dál použije `repo:`.

    Záměrně jen tady, ne v `chip_common.repo_path()`: `chip_run.py` musí worktree
    dál zakládat podle `repo:`, ne podle místa, kde brief náhodou leží.
    """
    strom = git_koren(c.path)
    if strom is None:
        return c.repo_path()
    repo = c.repo_path()
    if repo is None:
        return strom
    repo_koren = git_koren(repo)
    if repo_koren == repo:
        spolecny = _git_spolecny_adresar(strom)
        if spolecny is not None and spolecny == _git_spolecny_adresar(repo_koren):
            return strom
    return repo


ANO = {"ano", "yes", "true", "1"}


def je_greenfield(c) -> bool:
    """Prohlašuje brief, že repo teprve vznikne? (frontmatter `greenfield: ano`)

    Bez příznaku se nic neměkčí — chybějící repo je dál chyba. Příznak je
    vědomé prohlášení autora briefu, ne default: prvních chipů v novém projektu
    je málo, kdežto překlep v `repo:` je běžný a musí zastavit.
    `chip_common.parse` odřezává komentář za `#`, takže `greenfield: ano  # …`
    funguje.
    """
    return c.meta.get("greenfield", "").strip().lower() in ANO


def ma_commity(koren: Path) -> bool:
    """Je v git stromu `koren` aspoň jeden commit? (bez subprocesu, čtením refs)

    Rozhoduje o tom, jestli je `greenfield:` už zastaralý. `git init` založí
    repozitář s prázdným `refs/heads`, takže samotná existence `.git` ještě
    neznamená, že se dá na čem stavět — greenfield chip smí do čerstvě
    inicializovaného repa dál mířit. Ref je proto první commit, který kdy
    vznikl: soubor v `refs/heads`, nebo řádek v `packed-refs` (tam je git
    po `gc` slepí). Nečitelný nebo cizí adresář = „bez commitů": příznak se
    pak nehlásí jako zastaralý, což je ta tišší strana omylu.
    """
    g = _git_spolecny_adresar(koren)
    if g is None:
        return False
    heads = g / "refs" / "heads"
    if heads.is_dir() and any(p.is_file() for p in heads.rglob("*")):
        return True
    try:
        radky = (g / "packed-refs").read_text(encoding="utf-8",
                                              errors="replace").splitlines()
    except OSError:
        return False
    return any(r.strip() and not r.startswith(("#", "^")) for r in radky)


def zkontroluj_cesty(c) -> tuple[list[str], list[str]]:
    """Nárok na soubor, který v repu není, je fikce — a lint by ji jinak odkýval.

    Kontroluje se jen u stavu 'ready' (brief hotový, chip ještě neběžel). Za běhu
    je strom rozpracovaný a mazání/přejmenování by hlásilo falešné nálezy;
    'merged'/'blocked' jsou historie.

    S `greenfield: ano` (repo teprve vznikne) se existence neověřuje vůbec —
    proti neexistujícímu repu by padly úplně všechny nároky, a hláška, která
    se ozve pokaždé, se přestane číst. Tvar cesty (relativní, bez `..`) se
    kontroluje dál: ten na repu nezávisí a rozhoduje o porovnání s ostatními
    chipy. Když repo mezitím vznikne a má commity, je příznak zastaralý a
    hlásí se — jinak by v briefu zůstal navždy a kontrolu cest tiše vypínal.
    """
    jm = c.path.name
    repo = c.repo_path()
    greenfield = je_greenfield(c)
    if repo is None:
        # Chybějící `repo:` greenfield nezachrání: chip_run podle něj zakládá
        # worktree, takže nevíme ani KDE má repo vzniknout.
        return [f"{jm}: stav '{c.stav}', ale frontmatter nemá 'repo:'"], []

    varovani: list[str] = []
    if not repo.is_dir():
        if not greenfield:
            return [f"{jm}: repo '{repo}' neexistuje (nebo to není adresář)"], []
        varovani.append(f"{jm}: repo '{repo}' zatím neexistuje — 'greenfield: ano', "
                        f"takže se počítá s tím, že ho chip teprve založí")
    elif greenfield and ma_commity(repo):
        varovani.append(f"{jm}: 'greenfield: ano', ale repo '{repo}' už existuje "
                        f"a má commity — příznak je zastaralý, smaž ho "
                        f"(dokud tam je, vypíná kontrolu nárokovaných cest)")
    if c.stav != "ready":
        return [], varovani

    # `repo:` se dál validuje (chip_run podle něj zakládá worktree), ale existence
    # nároků se ověřuje proti stromu, ve kterém brief opravdu leží — viz N2.
    repo = strom_ke_kontrole(c) or repo

    chyby: list[str] = []
    for cesta, novy in c.soubory_detail():
        p = PurePosixPath(cesta.replace("\\", "/"))
        if absolutni(cesta) or ".." in p.parts:
            chyby.append(f"{jm}: cesta '{cesta}' musí být relativní k repu, bez '..' "
                         f"— jinak nesedí ani porovnání s ostatními chipy")
            continue
        if greenfield:      # tvar sedí, existenci není proti čemu ověřovat
            continue
        if vzor(cesta):
            if not any(repo.glob(cesta)):
                chyby.append(f"{jm}: vzor '{cesta}' v repu nic nenajde")
            continue
        if (repo / cesta).exists():
            if novy:
                varovani.append(f"{jm}: '{cesta}' je označená '# nový', ale v repu "
                                f"už existuje — brief je nejspíš zastaralý")
        elif not novy:
            chyby.append(f"{jm}: nárokovaná cesta '{cesta}' v repu neexistuje "
                         f"(překlep? pokud ji chip teprve vytvoří, napiš za ni '# nový')")
    return chyby, varovani


def vzor(cesta: str) -> bool:
    """Nárok se zástupným znakem (`src/*.py`) místo konkrétní cesty."""
    return any(z in cesta for z in "*?[")


class _Zastupny:
    """Zástupný znak jako token vzoru — aby se nepletl s literálem téhož znaku."""

    def __init__(self, popis: str) -> None:
        self.popis = popis

    def __repr__(self) -> str:          # pragma: no cover — jen pro ladění
        return self.popis


HVEZDA = _Zastupny("*")   # libovolně dlouhý úsek, i přes '/' (jako fnmatch)
JEDEN = _Zastupny("?")    # právě jeden libovolný znak


def _konec_tridy(s: str, i: int) -> int:
    """Index `]`, který uzavírá třídu `[...]` začínající na `i`; -1 = nespárováno.

    Kopíruje pravidla `fnmatch`: hned za `[` smí být `!` a hned poté `]` je ještě
    člen třídy, ne její konec.
    """
    j = i + 1
    if j < len(s) and s[j] == "!":
        j += 1
    if j < len(s) and s[j] == "]":
        j += 1
    return s.find("]", j)


def _tokeny(vzorec: str) -> tuple:
    """Vzor → tokeny: `HVEZDA`, `JEDEN`, nebo literál (jednoznakový řetězec).

    Třída `[abc]` se bere konzervativně jako `JEDEN` (libovolný znak): jazyk
    vzoru se tím jen rozšíří, takže kolize může vyjít navíc, ale žádná nezmizí.
    Nespárované `[` je pro `fnmatch` literál — bereme ho stejně.
    """
    out: list = []
    i, n = 0, len(vzorec)
    while i < n:
        z = vzorec[i]
        if z == "*":
            if not out or out[-1] is not HVEZDA:      # `**` nese stejnou informaci jako `*`
                out.append(HVEZDA)
            i += 1
        elif z == "?":
            out.append(JEDEN)
            i += 1
        elif z == "[":
            konec = _konec_tridy(vzorec, i)
            if konec == -1:
                out.append(z)
                i += 1
            else:
                out.append(JEDEN)
                i = konec + 1
        else:
            out.append(z)
            i += 1
    return tuple(out)


def _prunik(a: tuple, b: tuple) -> bool:
    """Existuje řetězec, který vyhoví oběma vzorům? (rekurzivně, s memoizací)

    Znak po znaku: literály se musí shodovat, `JEDEN` sedne na cokoli, `HVEZDA`
    buď spolkne nic (posune se dál), nebo jeden znak, který v tu chvíli generuje
    protější token. Bez memoizace `(i, j)` to u dvou vzorů s více hvězdami
    exploduje exponenciálně.
    """
    memo: dict[tuple[int, int], bool] = {}
    na, nb = len(a), len(b)

    def jde(i: int, j: int) -> bool:
        klic = (i, j)
        if klic in memo:
            return memo[klic]
        if i == na and j == nb:
            vysledek = True
        elif i == na:                      # zbytek druhého vzoru musí umět prázdno
            vysledek = all(t is HVEZDA for t in b[j:])
        elif j == nb:
            vysledek = all(t is HVEZDA for t in a[i:])
        elif a[i] is HVEZDA or b[j] is HVEZDA:
            vysledek = jde(i + 1, j) or jde(i, j + 1)
        else:
            shoda = a[i] is JEDEN or b[j] is JEDEN or a[i] == b[j]
            vysledek = shoda and jde(i + 1, j + 1)
        memo[klic] = vysledek
        return vysledek

    return jde(0, 0)


def prekryv(a: str, b: str) -> bool:
    """True, když se dvě nárokované cesty překrývají (shoda, adresář ⊃ soubor, vzor).

    Vzor × vzor se rozhoduje **skutečným průnikem** obou globů (nález N1):
    `src/*.py` a `src/mo*` sdílejí `src/modul.py` → kolize, kdežto `src/a_*.py`
    a `src/b_*.py` jsou prokazatelně disjunktní → čisto. Dřív se druhý vzor bral
    doslova (`fnmatch(retezec, vzor)`), takže kolize tiše propadla všude, kde
    sdílený soubor v repu ještě neexistuje (stavy `running`/`gated`, cesty `# nový`).

    Literál bez zástupných znaků nárokuje i všechno POD sebou (adresářová
    sémantika, stejně jako větev `parents` u dvou literálů) — proto se proti
    vzoru porovnává i jako prefix jeho možných shod: `src` × `*.py` je kolize,
    protože `src/x.py` vyhoví oběma (nález #1, chip 11). Platí jen směrem
    „vzor umí matchnout cestu UVNITŘ literálu": `src` × `tests/*.py` zůstává
    False, žádná shoda `tests/*.py` pod `src` neleží.

    `*` platí schválně i přes `/` (jako `fnmatch`) a třídy `[…]` se berou jako
    „libovolný znak": raději kolize navíc — falešná tě donutí nárok zpřesnit,
    přehlédnutá ti tiše přemaže práci.
    """
    pa, pb = PurePosixPath(a.replace("\\", "/")), PurePosixPath(b.replace("\\", "/"))
    if pa == pb or pa in pb.parents or pb in pa.parents:
        return True
    sa, sb = str(pa), str(pb)
    va, vb = vzor(sa), vzor(sb)
    if not va and not vb:                 # dvě konkrétní cesty: shodu řeší už větev výše
        return False
    ta, tb = _tokeny(sa), _tokeny(sb)
    if _prunik(ta, tb):
        return True
    # Literál jako adresář: existuje shoda vzoru ležící pod ním? (`lit/*` je
    # nejvolnější cesta uvnitř — nic nepřidává, když je literál soubor bez
    # podstromu, jen kolizi navíc; přehlédnutá by tiše přemazala práci.)
    if not va and _prunik(_tokeny(sa + "/*"), tb):
        return True
    return not vb and _prunik(ta, _tokeny(sb + "/*"))


def naroky(c) -> list[tuple[str, str]]:
    """Dvojice (cesta k porovnání, původní nárok z briefu); vzory rozbalí podle repa.

    Rozbalený vzor je přesný důkaz („tenhle konkrétní soubor"), `prekryv()` řeší
    i vzory, které se v repu ještě nemají do čeho rozbalit.
    Vzor v seznamu **zůstává i po rozbalení**: rozbalit jde jen to, co už
    existuje, a nárok musí pokrýt i soubory, které chip teprve vytvoří.

    Rozbaluje se proti témuž stromu, proti kterému se ověřuje existence cest
    (`strom_ke_kontrole`) — jinak by se ve worktree hlásily soubory hlavního stromu.
    """
    repo = strom_ke_kontrole(c)
    out: list[tuple[str, str]] = []
    for cesta in c.soubory():
        out.append((cesta, cesta))
        if not (vzor(cesta) and repo is not None and repo.is_dir()):
            continue
        # Absolutní vzor nebo `..` do `repo.glob()` nesmí: `glob('C:/…/*.xlsx')`
        # vyhodí NotImplementedError dřív, než lint cokoli vypíše (nález #3,
        # chip 11). Chybu tvaru hlásí `zkontroluj_cesty`, tady se jen nerozbaluje.
        if absolutni(cesta) or ".." in PurePosixPath(cesta.replace("\\", "/")).parts:
            continue
        out.extend((p.relative_to(repo).as_posix(), cesta)
                   for p in sorted(repo.glob(cesta)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint chip briefů.")
    ap.add_argument("--ready", action="store_true",
                    help="kontrolovat jen chipy ve stavu ready/running/gated")
    pridej_arg_dir(ap)
    args = ap.parse_args()
    nastav_chips_dir(args.dir)

    chipy = nacti_vse()
    if not chipy:
        print("  žádné chipy v chips/ (kromě šablony) — nic ke kontrole")
        return 0

    if args.ready:
        chipy = [c for c in chipy if c.stav in ("ready", "running", "gated")]

    chyby: list[str] = []
    varovani: list[str] = []

    # 1 + 2 — jednotlivé chipy
    for c in chipy:
        jm = c.path.name
        if c.stav not in STAVY:
            chyby.append(f"{jm}: neplatný stav '{c.stav}' (povolené: {', '.join(STAVY)})")

        for klic, popis in POVINNE.items():
            if c.najdi(klic) is None:
                chyby.append(f"{jm}: chybí sekce '## {popis}'")

        if c.stav != "draft":
            if not c.soubory():
                chyby.append(f"{jm}: stav '{c.stav}', ale sekce 'Dotčené soubory' "
                             f"nemá žádnou cestu v ``` bloku")
            if not c.issues():
                chyby.append(f"{jm}: stav '{c.stav}', ale žádné issues")
            varovani.extend(zbyle_placeholdery(c))

        if c.stav in ("ready", "running", "gated"):
            e, v = zkontroluj_cesty(c)
            chyby.extend(e)
            varovani.extend(v)

        pocet = len(c.issues())
        if pocet > 20:
            varovani.append(f"{jm}: {pocet} issues — strop je 20, zvaž rozřezání")
        if len(c.soubory()) > 15:
            varovani.append(f"{jm}: {len(c.soubory())} nárokovaných souborů — "
                            f"nad ~15 roste šance kolize")

    # 2b — závislosti: existují, nejsou cyklické, a co běží, má předky hotové
    znam = {c.id: c for c in chipy}
    for c in chipy:
        for dep in c.zavislosti():
            if dep == c.id:
                chyby.append(f"{c.path.name}: závisí sám na sobě")
            elif dep not in znam:
                chyby.append(f"{c.path.name}: závisí na chipu {dep}, který neexistuje")
            elif c.id in znam[dep].zavislosti():
                chyby.append(f"{c.path.name}: cyklická závislost s chipem {dep}")
            elif c.stav in ("running", "gated") and znam[dep].stav != "merged":
                # Navazující chip: předek `gated` je hotový a čeká na bránu —
                # přesně tak navazující práce vypadá, jde jen o pořadí merge.
                # `blocked` naopak znamená „čeká se na rozhodnutí člověka",
                # tam se stavět nedá o nic víc než na rozdělané práci.
                if znam[dep].stav == "gated":
                    varovani.append(f"{c.path.name}: staví na chipu {dep}, který je "
                                    f"'gated' (hotový, čeká na bránu) — merguj {dep} "
                                    f"před {c.id}")
                elif znam[dep].stav == "blocked":
                    chyby.append(f"{c.path.name}: stav '{c.stav}', ale závislost {dep} "
                                 f"je 'blocked' — na blokovaném chipu se stavět nedá, "
                                 f"čeká na rozhodnutí, ne na dokončení")
                else:
                    chyby.append(f"{c.path.name}: stav '{c.stav}', ale závislost {dep} "
                                 f"je '{znam[dep].stav}' (očekává se 'merged')")
            elif c.stav == "ready" and znam[dep].stav != "merged":
                varovani.append(f"{c.path.name}: čeká na chip {dep} "
                                f"('{znam[dep].stav}') — nespouštět dřív")

    # 3 — disjunktnost napříč chipy (jen aktivní; merged/blocked už nekolidují)
    def predci(cid: str, videno: set[str] | None = None) -> set[str]:
        """Tranzitivní uzávěr závislostí (odolný vůči cyklu)."""
        videno = videno or set()
        for d in znam.get(cid, chipy[0]).zavislosti() if cid in znam else []:
            if d not in videno:
                videno.add(d)
                predci(d, videno)
        return videno

    aktivni = [c for c in chipy if c.stav in ("ready", "running", "gated")]
    naroceno = {c.path.name: naroky(c) for c in aktivni}   # vzory rozbalené jednou, ne v O(n²)
    for i, a in enumerate(aktivni):
        for b in aktivni[i + 1:]:
            # Chipy ve vztahu předek–potomek NIKDY neběží současně → překryv je v pořádku.
            if b.id in predci(a.id) or a.id in predci(b.id):
                continue
            # Hlásí se dvojice nároků z briefu (to se edituje), konkrétní soubor
            # je jen důkaz — jinak jedna kolize vypíše tři skoro stejné řádky.
            kolize: dict[tuple[str, str], tuple[str, bool]] = {}
            for x, ox in naroceno[a.path.name]:
                for y, oy in naroceno[b.path.name]:
                    if not prekryv(x, y):
                        continue
                    presny = not vzor(x) and not vzor(y)
                    if (ox, oy) not in kolize or (presny and not kolize[(ox, oy)][1]):
                        kolize[(ox, oy)] = (x if x == y else f"{x} × {y}", presny)
            for (ox, oy), (dukaz, _) in sorted(kolize.items()):
                popis = ox if ox == oy else f"{ox}  ×  {oy}"
                if dukaz != popis.replace("  ×  ", " × "):
                    popis += f"   (např. {dukaz})"
                chyby.append(f"KOLIZE {a.path.name} ↔ {b.path.name}: {popis}")

    # výstup
    print(f"  zkontrolováno {len(chipy)} chipů ({len(aktivni)} aktivních)\n")
    for v in varovani:
        print(f"  ! {v}")
    for e in chyby:
        print(f"  X {e}")

    if chyby:
        print(f"\n  NEPROŠLO — {len(chyby)} chyb, {len(varovani)} varování")
        print("  Kolize řeš přeřezáním chipů, ne ručním mergem.")
        return 1
    print(f"\n  OK — 0 chyb, {len(varovani)} varování"
          + ("" if not varovani else "  (varování nebrání spuštění)"))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    utf8_vystup()
    sys.exit(main())
