"""PreToolUse hook: zablokuje `git merge` chip větve, dokud brána není zelená.

Tohle je jediné místo, kde je pravidlo „merge až po zelené bráně" vynucené,
ne jen napsané. Metodika rozlišuje tři úrovně: instrukce v promptu (obejdeš
i nechtěně), skill (obejdeš, když ho nezavoláš) a hook (neobejdeš) — tenhle
soubor je ta třetí.

Rozsah je schválně úzký, aby hook neotravoval mimo CHIPS:
  1. příkaz musí obsahovat `git merge`
  2. mergovaná větev musí být `ai/chip-NN/...` nebo starý `chip/NN-...`
     (čte se z argumentu za `merge`, ne odkudkoli z příkazu)
  3. u cílového repa musí jít najít chip briefy — viz `kde_jsou_briefy()`
     (repo se hledá tam, kde merge běží: `git -C` u merge, `cd` před ním,
     jinak cwd session)
Když kterákoli podmínka neplatí, hook mlčky pustí dál.

Podmínka 3 byla dřív jen „repo má adresář `chips/`", a tím se vylučovala tvrdá
brána s nulovou stopou v cizím repu: briefy uložené mimo repo (`--dir`) hook
neviděl a **mlčky pouštěl červené merge**. Signály jsou proto tři — vlastní
`chips/`, marker `.chips` a env `CHIPS_DIR`.

Podmínka 2 je nejcitlivější místo celého projektu: když hook tvar větve
nepozná, **mlčky pustí merge s červenou bránou** — brána pak vypadá, že
funguje, a nefunguje. Proto se tvar větve nesmí měnit bez testu v
`tests/test_chip_gate.py` (třída `TestHook`).

Když všechny tři platí, hook bránu ověřit MUSÍ. Nemůže-li (chybí worktree
chipu, nebo je v něm necommitnutá práce, takže by se ověřoval jiný stav, než
jaký se merguje), zamítá — neověří místo toho něco jiného. Zelená nad cizím
stavem je horší než žádná: vypadá jako důkaz a není.

Vstup: JSON na stdin (`tool_input.command`, `cwd`). Výstup: nic (povoleno),
nebo JSON s `permissionDecision: deny` a důvodem.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

MERGE = re.compile(r"\bgit\b[^|;&\n]*\bmerge\b")

# Části složeného příkazu, které shell spouští samostatně. Bez tohohle dělení
# hook četl větev i cílové repo z libovolného místa řetězce — a `git branch -d
# ai/chip-04/x && git merge ai/chip-05/y` pak ověřil bránu chipu 04 a pustil
# merge chipu 05.
ODDELOVAC = re.compile(r"\|\||&&|[|;&\n]")

# Přepínače `git merge`, které berou hodnotu jako SAMOSTATNÝ token. Ten token
# se musí přeskočit, jinak by `-m "merge ai/chip-01/x"` vypadal jako mergovaná
# větev. `-S`/`--gpg-sign` a `--log` sem nepatří — hodnotu berou jen připojenou.
HODNOTOVE_PREPINACE = {"-m", "--message", "-F", "--file", "-s", "--strategy",
                       "-X", "--strategy-option", "--into-name"}

# Musí poznat oba tvary větve — nový `ai/chip-08/nazvy-vetvi` i starý
# `chip/08-nazvy-vetvi` (starší větve v repu). Schválně stejné jádro jako
# `chip_gate.VETEV_CHIP`, ale zapsané zvlášť: hook běží před KAŽDÝM příkazem
# shellu a `chip_gate` se importuje až po projití levných podmínek. Že se obě
# kopie nerozejdou, hlídá test `test_hook_a_brana_poznaji_stejne_vetve`.
# `[\w./-]*` jen dojede zbytek jména (u nového tvaru i lomítko před názvem);
# na výsledek nemá vliv, drží ale shodu s celým jménem větve v příkazu.
VETEV = re.compile(r"(?:\bai/chip-|\bchip/)(\d+)[\w./-]*")
GIT_C = re.compile(r"\bgit\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+)")
CD = re.compile(r"\bcd\s+(\"[^\"]+\"|'[^']+'|\S+)")

# Soubor v kořeni repa, kterým se repo přihlásí k CHIPS, aniž by v něm briefy
# ležely. Jeden netrackovaný dotfile (`.git/info/exclude`) je stopa, se kterou
# se dá žít i v klientském repu — adresář `chips/` s desítkou briefů ne.
MARKER = ".chips"


def odvoz(s: str) -> str:
    return s.strip().strip("\"'")


def segmenty(prikaz: str) -> list[str]:
    """Příkaz rozdělený na části oddělené `&&`, `||`, `;`, `|` a novým řádkem."""
    return ODDELOVAC.split(prikaz)


def tokeny(text: str) -> list[str]:
    """Text rozdělený na argumenty; uvozovaný celek zůstane jedním tokenem.

    Kvůli `-m "merge ai/chip-01/x"` — zprávu s mezerami je nutné vidět jako
    jeden argument, aby se dala celá přeskočit a nespletla se s názvem větve.
    """
    return re.findall(r"""(?:[^\s"']+|"[^"]*"|'[^']*')+""", text)


def merge_tokeny(segment: str) -> list[str] | None:
    """Tokeny za `git merge` v segmentu, nebo None, když segment merge nespouští.

    `merge` se hledá jako celý token po tokenu s `git`, ne podřetězcem: jinak by
    `git -C /nekde/merge/repo status` vypadalo jako merge a hook by z toho
    segmentu bral cílové repo.
    """
    toks = tokeny(segment)
    for i, t in enumerate(toks):
        if t == "merge" and any(re.search(r"\bgit\b", x) for x in toks[:i]):
            return toks[i + 1:]
    return None


def pozicni(args: list[str]) -> list[str]:
    """Poziční argumenty `merge` (názvy větví) — bez přepínačů a jejich hodnot.

    Neznámý `-x` se bere jako přepínač bez hodnoty: raději jeden token navíc
    k prozkoumání (a případné zamítnutí) než přeskočený název větve.
    """
    out: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":                             # dál už jsou jen poziční
            out.extend(args[i + 1:])
            break
        if a.startswith("-") and len(a) > 1:
            i += 2 if a in HODNOTOVE_PREPINACE else 1
            continue
        out.append(a)
        i += 1
    return out


def cisla_chipu(prikaz: str) -> list[str]:
    """Čísla chipů větví, které se doopravdy mergují — z argumentů za `merge`.

    Dřív se bral první chip token kdekoli v příkazu, takže stačilo zmínit jiný
    chip před merge (`git branch -d ai/chip-04/x && git merge ai/chip-05/y`)
    a brána se ověřila u cizího chipu. Bere se každý poziční argument každého
    merge — `git merge A B` (octopus) musí projít bránou obou.
    """
    cisla: list[str] = []
    for seg in segmenty(prikaz):
        for arg in pozicni(merge_tokeny(seg) or []):
            m = VETEV.search(odvoz(arg))
            if m and m.group(1).zfill(2) not in cisla:
                cisla.append(m.group(1).zfill(2))
    return cisla


def slozit(base: Path, cesta: str) -> Path:
    """Cesta z příkazu složená s dosavadním pracovním adresářem.

    Relativní cesta patří k cwd session, ne k cwd hook procesu — hook běží tam,
    kde ho spustil Claude Code. Když výsledek není adresář, drží se dosavadní
    základ: špatný odhad repa je horší než žádný (brána by se ověřila jinde).
    """
    p = Path(cesta)
    if not p.is_absolute():
        p = base / p
    return p if p.is_dir() else base


def cilove_repo(prikaz: str, cwd: str | None) -> Path:
    """Kde se merge odehraje: `git -C …` u merge > `cd …` před ním > cwd session.

    `git -C` se bere JEN ze segmentu, který merge spouští. Dřív stačilo, aby
    `-C` patřilo jinému volání (`git -C jinde status && git merge …`), a hook
    ověřoval bránu v cizím repu — a když tam `chips/` není, mlčel a červený
    merge prošel. `cd` naopak platí i pro následující segmenty, takže se sbírá
    ze všech segmentů až po merge (postupně, takže `cd a && cd b` sedí).
    """
    segs = segmenty(prikaz)
    idx = next((i for i, s in enumerate(segs) if merge_tokeny(s) is not None), None)
    base = Path(cwd or os.getcwd())
    for seg in segs[:idx + 1] if idx is not None else segs:
        m = CD.search(seg)
        if m:
            base = slozit(base, odvoz(m.group(1)))
    if idx is not None:
        m = GIT_C.search(segs[idx])
        if m:
            base = slozit(base, odvoz(m.group(1)))
    return base


def git_koren(start: Path) -> Path | None:
    """Kořen git stromu nad `start` (`.git` je ve worktree soubor, ne adresář)."""
    try:
        p = start.resolve()
    except OSError:                                       # pragma: no cover
        return None
    if not p.is_dir():
        p = p.parent
    for adresar in (p, *p.parents):
        if (adresar / ".git").exists():
            return adresar
    return None


class NeniKdeOverit(Exception):
    """Bránu není kde (nebo podle čeho) spustit — merge se zamítá, ne obchází.

    Schválně výjimka, ne `None`: `kde_overit()` dřív vracelo `Path` a nikdy
    neselhalo, takže volající neměl co ošetřovat — a tichý fallback se dal
    přehlédnout při čtení i při úpravě. `None` by šlo ignorovat stejně snadno
    (`Path` z něj neudělá chybu hned, ale až někde hluboko v bráně); výjimka
    projde skrz a merge zamítne.

    Text výjimky je hláška PRO UŽIVATELE: vždy říká, co má udělat, ne jen co
    je špatně.
    """


def z_markeru(koren: Path) -> Path:
    """Adresář s briefy podle markeru `.chips` v kořeni repa.

    Bere se první neprázdný řádek, který není komentář (`#`) — cesta k briefům,
    absolutní nebo relativní ke kořeni repa. Zbytek souboru smí být poznámka
    pro člověka, který ho najde a neví, co to je.

    Když marker existuje a použitelnou cestu nedává, ZAMÍTÁ se. Marker nikdo
    nezaloží omylem: je to vědomé přihlášení repa k CHIPS, a mlčet nad
    překlepem v cestě by znamenalo pustit červený merge přesně tam, kde si
    uživatel bránu výslovně přál.
    """
    soubor = koren / MARKER
    try:
        radky = soubor.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        raise NeniKdeOverit(
            f"marker {soubor} nejde přečíst: {e}. Oprav práva k souboru, nebo "
            f"marker smaž — dokud tam je, bere se repo jako řízené CHIPS.")

    raw = next((r.strip() for r in radky
                if r.strip() and not r.strip().startswith("#")), "")
    if not raw:
        raise NeniKdeOverit(
            f"marker {soubor} neobsahuje cestu — nevím, kde chip briefy hledat. "
            f"Napiš do něj adresář s briefy (absolutní, nebo relativní ke "
            f"kořeni repa).")

    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = koren / p
    if not p.is_dir():
        raise NeniKdeOverit(
            f"marker {soubor} ukazuje na '{raw}', což není adresář ({p}). "
            f"Oprav cestu, nebo marker smaž.")
    return p


def z_env(koren: Path, chip_common) -> Path | None:
    """Briefy z `CHIPS_DIR` — ale jen když se aspoň jeden hlásí k tomuhle repu.

    Env proměnná je globální, repo konkrétní. Bez ověření by `CHIPS_DIR`
    nastavené kvůli projektu A rozhodovalo i o merge v projektu B: hook by tam
    hledal cizí briefy, nenašel je a merge zamítl s hláškou o chipu, který
    s repem nemá nic společného. Proto se adresář přijme, teprve když v něm
    leží brief s `repo:` mířícím sem — jinak se tváří, jako by nebyl.

    Vrací `None` (mlčení) místo výjimky schválně: na rozdíl od markeru není
    `CHIPS_DIR` přihláškou konkrétního repa, takže z něj nejde odvodit, že
    tady brána chybí.
    """
    raw = (os.environ.get("CHIPS_DIR") or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    if not p.is_dir():
        return None

    puvodni = chip_common.CHIPS_DIR
    try:
        chip_common.nastav_chips_dir(p)
        for chip in chip_common.nacti_vse():
            try:
                if chip.repo_path() == koren.resolve():
                    return p
            except OSError:                               # pragma: no cover
                continue
    finally:
        chip_common.CHIPS_DIR = puvodni
    return None


def kde_jsou_briefy(koren: Path, chip_common) -> Path | None:
    """Adresář s chip briefy pro `koren`; `None` = CHIPS tohle repo neřídí.

    Tři signály, v tomhle pořadí:

    | Signál | Kdy platí | Pro co je |
    |---|---|---|
    | `chips/` v repu | adresář existuje | výchozí případ (CHIPS, vlastní projekty) |
    | marker `.chips` | soubor existuje | repo, kde po metodice nesmí zůstat stopa |
    | env `CHIPS_DIR` | ukazuje na briefy tohoto repa | session s jedním projektem |

    Pořadí je od nejkonkrétnějšího k nejobecnějšímu: co je v repu, ví o repu
    víc než globální proměnná. Marker se kontroluje až po `chips/`, aby v repu,
    které má obojí, rozhodovaly briefy uvnitř.
    """
    vlastni = koren / "chips"
    if vlastni.is_dir():
        return vlastni
    if (koren / MARKER).is_file():
        return z_markeru(koren)
    return z_env(koren, chip_common)


def kde_overit(chip, koren: Path) -> Path:
    """Worktree chipu — jediný strom, ve kterém smí brána běžet.

    Dřív se při chybějícím worktree spadlo zpátky na hlavní strom s
    odůvodněním „lepší ověřit něco než nic". Je to přesně obráceně: do
    hlavního stromu se teprve merguje, práci chipu z definice NEMÁ — brána
    tam projde nad starým kódem a vrátí zelenou, která o mergovaném stavu
    neříká nic. Falešná zelená je horší než žádná: kvůli ní se merguje bez
    ověření, a to je právě to, kvůli čemu hook existuje.

    Vyhazuje `NeniKdeOverit`, když worktree chybí, není vyplněný, nebo
    ukazuje na strom, do kterého se merguje.
    """
    raw = (chip.meta.get("worktree") or "").strip()
    if not raw:
        raise NeniKdeOverit(
            f"brief {chip.path.name} nemá vyplněné 'worktree:' — bránu není kde "
            f"ověřit, hlavní strom práci chipu nemá. Doplň cestu do briefu a "
            f"worktree založ.")

    wt = Path(raw)
    if not wt.is_absolute():
        wt = koren.parent / Path(raw).name
    if not wt.is_dir():
        raise NeniKdeOverit(
            f"worktree chipu neexistuje ({wt}) — bránu není kde ověřit. Obnov ho "
            f"a merguj až po zelené bráně, nebo merguj vědomě mimo hook a "
            f"vysvětli uživateli, co tím obcházíš.")

    # Merge se odehrává v `koren`. Když tam ukazuje i `worktree:`, brána by
    # běžela nad cílovým stromem — tedy nad stavem PŘED mergem. To je táž
    # falešná zelená jako fallback výš, jen zapsaná v briefu.
    if wt.resolve() == koren.resolve():
        raise NeniKdeOverit(
            f"'worktree:' v briefu ukazuje na strom, do kterého se merguje "
            f"({koren}) — brána by tam ověřila stav PŘED mergem, ne práci "
            f"chipu. Oprav 'worktree:' na vlastní strom chipu a založ ho.")
    return wt


def necommitnute(strom: Path) -> list[str]:
    """Řádky `git status --porcelain` ve stromě chipu; prázdný seznam = čisto.

    Merge bere COMMITNUTÝ tip větve, brána běží nad working tree. Když se ty
    dva rozcházejí, verdikt platí o jiném stavu, než jaký se merguje — a mýlí
    v obou směrech: zelená nad rozdělanou opravou, která v commitu není, i
    červená nad experimentem, který se nemerguje.

    Netrackované soubory se počítají taky: co není v commitu, to se nemerguje,
    a brána nad tím projít nesmí. Ignorované soubory (`__pycache__`) git do
    `--porcelain` sám nedává.

    Vyhazuje `NeniKdeOverit`, když se stav zjistit nedá — nevědět, co ve
    stromě je, se pro potřeby brány rovná nemít ho.
    """
    # Import až tady: hook běží před KAŽDÝM příkazem shellu a k `git` se
    # dostane jen u chip merge, tedy pár desítek volání za celý projekt.
    import subprocess

    try:
        p = subprocess.run(["git", "-C", str(strom), "status", "--porcelain"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise NeniKdeOverit(
            f"stav worktree ({strom}) nejde zjistit: {e}. Merge zablokován — "
            f"bez znalosti stavu nelze říct, jestli brána ověří to, co se "
            f"merguje. Ověř, že 'git' je na PATH a worktree je v pořádku.")
    if p.returncode != 0:
        # Nejčastější případ v provozu: po `chip_run.py NN --uklid` git smaže
        # `.git`, ale adresář se zbytky (ignorované soubory) na disku zůstane.
        # `is_dir()` na něj tedy sedne a teprve `git status` ukáže, že to worktree
        # není — pro bránu je to totéž jako chybějící strom.
        raise NeniKdeOverit(
            f"'git status' ve worktree ({strom}) skončil s kódem {p.returncode}: "
            f"{(p.stderr or '').strip()[:200]} Není to git strom chipu — typicky "
            f"zbytek adresáře po úklidu worktree. Založ worktree znovu, nebo "
            f"oprav 'worktree:' v briefu.")
    return [r for r in p.stdout.splitlines() if r.strip()]


def zamitni(duvod: str) -> None:
    """Zamítnutí ve tvaru, kterému rozumí PreToolUse."""
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": duvod,
    }}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0                                  # nerozumím vstupu → nepřekážím

    prikaz = (data.get("tool_input") or {}).get("command") or ""
    if not MERGE.search(prikaz):
        return 0                                  # 1) není to merge

    cisla = cisla_chipu(prikaz)
    if not cisla:
        return 0                                  # 2) není to chip větev

    koren = git_koren(cilove_repo(prikaz, data.get("cwd")))
    if koren is None:
        return 0                                  # 3) není to git strom

    # Až teď se platí za import — hook běží před každým příkazem shellu, ale
    # sem se dostane jen u merge chip větve, tedy pár desítek volání za projekt.
    # Import je před podmínkou 3, protože `kde_jsou_briefy` potřebuje umět
    # přečíst briefy, aby ověřila, že `CHIPS_DIR` patří k tomuhle repu.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import chip_common
        import chip_gate
    except ImportError as e:                              # pragma: no cover
        zamitni(f"CHIPS brána: nelze načíst nástroje ({e}). "
                f"Merge zablokován, protože bránu nelze ověřit.")
        return 0

    try:
        chips = kde_jsou_briefy(koren, chip_common)
    except NeniKdeOverit as e:
        zamitni(f"CHIPS brána: merge chip větve zablokován — chip briefy nejde "
                f"najít.\n  {e}")
        return 0
    if chips is None:
        return 0                                  # 3) repo neřídí CHIPS

    chip_common.nastav_chips_dir(chips)
    # Mergovaných větví může být víc (octopus) — zamítá se na první červené.
    for cislo in cisla:
        chip = chip_gate.najdi_chip(cislo, None)
        if chip is None:
            zamitni(f"CHIPS brána: větev chipu {cislo} nemá brief v {chips}. "
                    f"Merge zablokován — bez briefu není co ověřit.")
            return 0

        # Brána musí běžet ve stromě CHIPU, ne v hlavním. V hlavním stromě práce
        # chipu ještě není (merge se teprve chystá), takže by se ověřoval starý
        # stav — a u repa, kde import skriptu spouští pipeline, dokonce sáhla na
        # živá data. Když strom chipu není nebo neodpovídá tomu, co se merguje,
        # zamítá se HNED na téhle větvi — u octopus merge nemá smysl ověřovat
        # zbytek, celý merge stejně neprojde.
        try:
            strom = kde_overit(chip, koren)
            zmeny = necommitnute(strom)
        except NeniKdeOverit as e:
            zamitni(f"CHIPS brána chipu {cislo} ({chip.nazev}) NEJDE OVĚŘIT — "
                    f"merge zablokován.\n  {e}\n"
                    f"  Worktree chipu založíš/obnovíš: "
                    f"python tools/chip_run.py {cislo}   "
                    f"(úklid `--uklid` patří AŽ po mergi).")
            return 0

        if zmeny:
            zamitni(f"CHIPS brána chipu {cislo} ({chip.nazev}): ve worktree jsou "
                    f"necommitnuté změny — brána by ověřovala jiný stav, než jaký "
                    f"se merguje. Merge zablokován.\n"
                    f"  ({strom})\n"
                    + "\n".join(f"  {r}" for r in zmeny[:10])
                    + (f"\n  … a další ({len(zmeny)} položek celkem)"
                       if len(zmeny) > 10 else "")
                    + "\n\nVe worktree chipu změny commitni (nebo zahoď) a merguj "
                      "znovu — merge bere commitnutý tip větve, ne working tree.")
            return 0

        ok, hlaseni = chip_gate.brana(chip, strom)
        if ok:
            continue

        zamitni(f"CHIPS brána chipu {cislo} ({chip.nazev}) NEPROŠLA — merge zablokován.\n"
                f"  (ověřováno ve stromě: {strom})\n"
                + "\n".join(hlaseni)
                + "\n\nOprav to ve worktree chipu, nebo přepni stav na 'blocked' "
                  "a popiš důvod v Logu briefu. Bránu ručně: "
                  f"python tools/chip_gate.py {cislo} --repo \"{strom}\"")
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):                     # pragma: no cover
        pass
    sys.exit(main())
