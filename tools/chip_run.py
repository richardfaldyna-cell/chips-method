"""Připraví izolovaný worktree pro chip a předá do něj zadání.

Použití:
    python tools/chip_run.py 01 --dry-run     # jen ukáže příkazy
    python tools/chip_run.py 01               # založí worktree + větev
    python tools/chip_run.py 01 --spustit     # + rovnou spustí Claude Code ve worktree
    python tools/chip_run.py 01 --stav        # + přepíše 'stav: ready' na 'running'
    python tools/chip_run.py 01 --od ai/chip-00/zaklad   # větvit z předchůdce, ne z HEAD
    python tools/chip_run.py 01 --zaloz-repo  # cílové repo teprve vznikne (init + prázdný commit)
    python tools/chip_run.py 01 --uklid       # AŽ PO MERGI odstraní worktree

`--od <ref>` je pro navazující chipy: chip B staví na práci chipu A, která
ještě není zmergovaná, takže větvení z `HEAD` by mu ji vzalo. Ref se ověřuje
`git rev-parse` ještě **před** `worktree add` (poloviční stav blokuje další
spuštění) a propíše se i do zadání pro agenta — ten musí vědět, že pod ním
leží cizí rozpracovaná práce.

`--zaloz-repo` je opačný okraj, greenfield: v čerstvě `init`nutém repu není
`HEAD`, ze kterého by `worktree add` větvil, takže se doplní prázdný kořenový
commit. Nad repem, které už historii má, `--zaloz-repo` nedělá nic. Bez něj
zůstává chybějící repo chybou (exit 1).

Bez `--spustit` Claude Code nespouští — jen vytvoří izolovaný pracovní strom
a vypíše zadání, které vložíš do nového okna. S `--spustit` ho otevře sám
(hledá `claude` na PATH). Když je `claude` npm shim (`.cmd`/`.bat`), spuštění
se odmítne: shim jde přes cmd.exe a ten usekne víceřádkové zadání na prvním
řádku — viz `je_cmd_shim()`. Worktree se založí i tak a zadání se vypíše
k ručnímu vložení.

Logika je rozdělená na čisté funkce (`cesty`, `zadani`, `brief_ke_stavu`) a na
`main()`/`uklid()`, které jediné sahají na git a na disk — kvůli testovatelnosti.
Přepis `stav:` ve frontmatteru dělá sdílený `chip_common.prepis_stav()`
(používá ho i orchestrátor při přepnutí na `merged`), ale **do kopie briefu ve
worktree** — viz `brief_ke_stavu()`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from chip_common import (ROOT, nacti_vse, nastav_chips_dir, prepis_stav,
                         pridej_arg_dir, utf8_vystup)

ZADANI = """\
Jsi orchestrátor pro CHIP {id} — {nazev}.

Brief (celý si ho přečti jako první): {brief}
Pracuješ v izolovaném git worktree: {worktree}
Větev: {vetev}
{zaklad}
Pravidla, která nesmíš porušit:
1. Měň POUZE soubory ze sekce "Dotčené soubory" v briefu. Nic jiného.
2. Hotovo = splněná Definition of done, ověřená příkazy ze sekce "Ověření (brána)".
3. Nemerguj do hlavní větve. Skonči commitem na téhle větvi.
4. Když narazíš na cokoli ze sekce "Eskalace (T3)": ZASTAV se, zapiš to do
   sekce Log v briefu a nech to na uživateli. Nehádej, nekonzultuj to jinam.
5. Když brána selže a nedokážeš to opravit v rámci nárokovaných souborů,
   přepni stav chipu na 'blocked' a napiš proč.

Průběžně aktualizuj sekci Log a checkboxy u Issues v briefu.
"""

# Vsuvka do zadání, když se větví z předchůdce (`--od`). Agent jinak vidí cizí
# rozpracovaný kód jako součást hlavní větve a začne ho „opravovat" — což je
# přesně ta kolize mezi balíčky, kvůli které chipy existují.
ZAKLAD = """
Tvoje větev vychází z '{od}', ne z hlavní větve — pod tvou prací leží
rozpracovaný kód jiného chipu. Ber ho jako dané prostředí: needituj ho ani
neopravuj, i když v něm něco vypadá nedodělaně. Nález v něm patří do sekce
Log tvého briefu, ne do commitu.
"""

# Zpráva prvního (prázdného) commitu při `--zaloz-repo`. Nese, odkud se vzal —
# v `git log` prázdného repa je to jediná stopa.
PRVNI_COMMIT = "prázdný kořenový commit (chip_run.py --zaloz-repo)"


def je_cmd_shim(exe: str) -> bool:
    """True pro `.cmd`/`.bat` wrapper (typicky npm shim), ne nativní `.exe`.

    Windows spouští `.cmd`/`.bat` přes cmd.exe a jeho parser čte příkazovou
    řádku jen po první newline — víceřádkové zadání jako jeden argv element
    by dorazilo useknuté na první řádek. Bezpečná cesta přes shim neexistuje:
    náhrada newline mezerami mění obsah zadání, `claude` neumí číst prompt
    ze souboru a obalování dalším cmd.exe problém jen posouvá. Proto se
    `--spustit` u shimu odmítá a zadání se vypíše k ručnímu vložení.
    """
    return exe.lower().endswith((".cmd", ".bat"))


def git(repo: Path, *args: str, dry: bool = False) -> int:
    cmd = ["git", "-C", str(repo), *args]
    print("  $ " + " ".join(cmd))
    if dry:
        return 0
    return subprocess.call(cmd)


def git_tise(repo: Path, *args: str) -> int:
    """Návratový kód gitu bez výpisu — pro dotazy, ne pro akce.

    `git()` výš každý příkaz vypíše, protože ukazuje, co nástroj dělá. Dotazy
    typu „je ta větev zmergovaná?" ale do výstupu nepatří: uživatele zajímá
    odpověď, ne cesta k ní.
    """
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=60).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def git_vystup(repo: Path, *args: str) -> str | None:
    """Stdout gitu bez výpisu příkazu; `None`, když git selhal nebo mlčel.

    Sourozenec `git_tise()`: ten odpovídá na ano/ne otázky návratovým kódem,
    tenhle na otázky typu „kde to leží". Na cestu uvnitř `.git` se ptáme gitu
    právě proto, aby se nemusela skládat ručně — `repo` může být samo linkované
    worktree a `.git` je v něm soubor, ne adresář.
    """
    try:
        hotovo = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                                text=True, encoding="utf-8", errors="replace",
                                timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if hotovo.returncode != 0:
        return None
    return hotovo.stdout.strip() or None


def je_zmergovana(repo: Path, vetev: str) -> bool | None:
    """Je práce větve už obsažená v HEAD? `None`, když větev neexistuje.

    `merge-base --is-ancestor` odpovídá přesně na otázku, která rozhoduje
    o úklidu — ne „existuje merge commit", ale „je ta práce už v cílové větvi"
    (projde tedy i fast-forward a rebase). Neexistující větev vrací `None`:
    není co ztratit, úklid smí proběhnout.
    """
    if git_tise(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{vetev}") != 0:
        return None
    return git_tise(repo, "merge-base", "--is-ancestor", vetev, "HEAD") == 0


def ref_existuje(repo: Path, ref: str) -> bool:
    """Ukazuje `ref` v tomhle repu na commit? Ptá se gitu, ne tvaru názvu.

    Odhad z názvu („začíná `ai/`, tak to bude větev chipu") by pustil dál
    i překlep a `worktree add` by spadl **až po tom**, co adresář vznikne —
    zbyl by poloviční stav, který blokuje další spuštění. `rev-parse --verify`
    naopak zná všechno, z čeho jde větvit (větev, tag, SHA, `HEAD~2`),
    a `^{commit}` odmítne ref, který na commit neukazuje.
    """
    return git_tise(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") == 0


def repo_ma_commity(repo: Path) -> bool:
    """Má repo aspoň jeden commit? Rozhoduje o tom, jestli `--zaloz-repo` smí sáhnout.

    Existence `.git` nestačí: `git init` bez commitu vyrobí repo, ve kterém
    `HEAD` na nic neukazuje a `worktree add` na tom padne. Tohle je ta hranice
    mezi „prázdné, doplň kořenový commit" a „cizí historie, nesahat".
    """
    return git_tise(repo, "rev-parse", "--verify", "--quiet", "HEAD") == 0


def zaloz_repo(repo: Path, *, dry: bool = False) -> int:
    """Greenfield: repo + prázdný kořenový commit, ať má `worktree add` z čeho větvit.

    Nad repem, které už commity má, tahle funkce **nedělá nic** a řekne to.
    `git init` nad cizí historií se sice tváří neškodně, ale s prázdným
    commitem navrch by přepsal větev, na které někdo stojí — a to je nevratná
    záměna. Návrat 0 znamená „pokračuj", ne „něco jsem založil".
    """
    if dry:
        # Dotaz na historii je taky spuštění gitu — dry-run nespouští nic.
        print(f"  (dry-run) kontrola historie '{repo}' se nespouští")
        if not (repo / ".git").exists():
            print(f"  (dry-run) mkdir {repo}")
            git(repo, "init", dry=True)
        git(repo, "commit", "--allow-empty", "-m", PRVNI_COMMIT, dry=True)
        return 0

    if (repo / ".git").exists() and repo_ma_commity(repo):
        print(f"  --zaloz-repo: '{repo}' už má historii — nezakládám nic")
        return 0

    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists() and git(repo, "init") != 0:
        print(f"! git init v '{repo}' selhal")
        return 1
    if git(repo, "commit", "--allow-empty", "-m", PRVNI_COMMIT) != 0:
        print("! prázdný kořenový commit se nepodařilo vytvořit")
        print("  (git na něj chce user.name a user.email — nastav je a spusť znovu)")
        return 1
    print(f"  --zaloz-repo: '{repo}' má prázdný kořenový commit, je z čeho větvit")
    return 0


def _povol_zapis(funkce, cesta: str, _chyba) -> None:
    """Handler pro `rmtree`: sundá read-only a mazání zopakuje."""
    os.chmod(cesta, stat.S_IWRITE)
    funkce(cesta)


# `onexc` je až od Pythonu 3.12; `onerror` tam je zastaralý, ale do 3.11 jediný.
# Handler bere v obou případech tři argumenty, třetí (výjimka / exc_info) nečte.
RMTREE_HANDLER = "onexc" if sys.version_info >= (3, 12) else "onerror"


def smaz_strom(cesta: Path) -> str | None:
    """Smaže adresář včetně read-only souborů; vrací text chyby, nebo `None`.

    Tohle je záchranná cesta pro `git worktree remove`, který na Windows běžně
    padá na `Permission denied`: git si v `.git/worktrees/` i ve stromě drží
    soubory jen pro čtení a `os.unlink` na ně nesáhne. Handler `_povol_zapis`
    právo doplní a mazání zopakuje — teprve když selže i to, je chyba skutečná
    (typicky otevřený soubor v jiném procesu).
    """
    try:
        shutil.rmtree(cesta, **{RMTREE_HANDLER: _povol_zapis})
    except OSError as e:
        return str(e)
    return None


def cesta_metadat(repo: Path, worktree: Path) -> Path | None:
    """Kde git drží metadata tohohle worktree (`.git/worktrees/<jméno>`).

    Ptá se `rev-parse --git-path`, neskládá `repo / ".git"`: `--git-path` míří
    do **společného** adresáře repa, takže odpoví správně i tehdy, když je
    `repo` samo linkované worktree. Odpověď bývá relativní vůči `repo`, proto
    se s ním skládá (absolutní cestu `Path.__truediv__` nechá být).
    """
    vystup = git_vystup(repo, "rev-parse", "--git-path", f"worktrees/{worktree.name}")
    if vystup is None:
        return None
    return (repo / vystup).resolve()


def metadata_patri_worktree(meta: Path, worktree: Path) -> bool:
    """Jsou metadata `meta` opravdu od `worktree`? Rozhoduje soubor `gitdir`.

    `gitdir` drží cestu k `<worktree>/.git`. Když chybí, git adresář už
    nevlastní (`prune` na něm hlásí „gitdir file does not exist") a zbytek je
    smetí po neúplném mazání — smí se dorazit. Když ukazuje jinam, sedí na tom
    jméně cizí worktree: git při kolizi jmen připojuje příponu, takže
    `.git/worktrees/<jméno>` nemusí patřit nám. Mazání je chirurgické, tohle
    je ten skalpel.
    """
    try:
        cil = (meta / "gitdir").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return True
    return bool(cil) and Path(cil).parent.resolve() == worktree.resolve()


def dokliz_metadata(repo: Path, worktree: Path) -> int:
    """Ověří, že metadata worktree zmizela — a když ne, dorazí je. 0 = pryč.

    `git worktree prune` na to sám nestačí a **jeho návratový kód to
    neprozradí**: nad mrtvým adresářem vypíše `gitdir file does not exist`,
    pak `error: failed to delete …: Permission denied` — a přesto skončí
    nulou. Chyba mazání je pro git jen poznámka, ne selhání. Úspěch se proto
    měří stavem na disku, přesně jako o pár řádků níž u pracovního stromu.

    Zbylá metadata nejsou kosmetika: git si podle nich worktree dál pamatuje,
    `worktree list` ho ukazuje a nakupené adresáře přežívaly chipy 01–24.
    """
    meta = cesta_metadat(repo, worktree)
    if meta is None:
        print("  ! nezjistil jsem, kde git drží metadata worktree — nekontroluji je")
        return 0
    if not meta.exists():
        return 0
    if not metadata_patri_worktree(meta, worktree):
        print(f"  {meta} patří jinému worktree — nesahám na něj")
        return 0
    print(f"  prune nechal metadata {meta} — mažu ručně")
    chyba = smaz_strom(meta)
    if meta.exists():
        print(f"! metadata {meta} se nepodařilo smazat: {chyba or 'adresář zůstal'}")
        print("  Dokud tam jsou, git si worktree pamatuje — smaž ten adresář ručně.")
        return 1
    return 0


def uklid(repo: Path, worktree: Path, vetev: str, cislo: str, *,
          dry: bool = False, presto: bool = False) -> int:
    """Odstraní worktree chipu — až po mergi, a doopravdy. 0 = uklizeno.

    **Uklizeno znamená obojí: pracovní strom PRYČ i metadata v
    `.git/worktrees/<jméno>` PRYČ.** Půlka úklidu není úklid — podle zbylých
    metadat si git worktree dál pamatuje.

    Tři věci, na kterých to dřív padalo:

    1. **Pořadí.** Hook od chipu 14 zamítá merge, když worktree chipu chybí —
       bránu není kde ověřit. Úklid před mergem tedy chip zablokuje a jediná
       cesta ven je hook obejít. Proto se nezmergovaná větev uklidit odmítne;
       `--presto` je vědomé opuštění chipu, ne přepínač pro pohodlí.
    2. **Tichý neúspěch nad pracovním stromem.** Návratový kód
       `git worktree remove` se zahazoval, takže `--uklid` hlásil úspěch nad
       adresářem, který na disku zůstal — a další `chip_run.py NN` pak spadl
       na „worktree už existuje". Teď se postupuje `remove` →
       `remove --force` → ruční smazání + `prune`, a když adresář přežije
       i to, vrací se 1.
    3. **Tichý neúspěch nad metadaty.** Totéž o patro níž: rc `git worktree
       prune` se nečte, protože git vrací 0 i tehdy, když adresář smazat
       nedokázal („Permission denied" jen vypíše). Proto každá cesta, která
       končí úspěchem, vede přes `dokliz_metadata()` — ta se ptá disku, ne
       gitu, a když adresář zbyl a nedá se smazat, vrací 1 i s jeho jménem.
    """
    print(f"  úklid worktree pro chip {cislo}:")

    if dry:
        # Dry-run nespouští ani dotazy: má ukázat příkazy, ne sahat na repo.
        print(f"  (dry-run) kontrola, že je '{vetev}' zmergovaná, se nespouští")
        git(repo, "worktree", "remove", str(worktree), dry=True)
        return 0

    zmergovana = je_zmergovana(repo, vetev)
    if zmergovana is False and not presto:
        print(f"! větev '{vetev}' není zmergovaná do HEAD — úklid odmítnut.")
        print("  Worktree chipu je JEDINÉ místo, kde jde spustit brána; bez něj")
        print("  hook merge zamítne a chip zůstane viset. Nejdřív merguj:")
        print(f"    python tools/chip_gate.py {cislo}")
        print(f"    git -C \"{repo}\" merge --no-ff {vetev}")
        print(f"  Chip opouštíš vědomě (blocked, zahozený)? Pak: --uklid --presto")
        return 1
    if zmergovana is None:
        print(f"  (větev '{vetev}' neexistuje — není co ztratit)")
    elif zmergovana is False:
        print(f"  --presto: uklízím i nezmergovanou větev '{vetev}'")

    if not worktree.exists():
        print(f"  worktree {worktree} na disku není — jen uklidím metadata")
        git(repo, "worktree", "prune")
        return dokliz_metadata(repo, worktree)

    for prepinace in ([], ["--force"]):
        if git(repo, "worktree", "remove", *prepinace, str(worktree)) == 0:
            if not worktree.exists():
                # `remove` metadata uklízí sám; kontrola je tu proto, aby
                # „0 = uklizeno" znamenalo totéž na všech cestách ven.
                return dokliz_metadata(repo, worktree)
            # git skončil nulou, ale adresář zůstal: typicky ignorované soubory
            # (`__pycache__`, `.venv`), na které `remove` nesahá.
            break

    print(f"  git worktree remove neuklidil {worktree} — mažu ručně")
    chyba = smaz_strom(worktree)
    git(repo, "worktree", "prune")
    if worktree.exists():
        print(f"! {worktree} se nepodařilo smazat: {chyba or 'adresář zůstal'}")
        print("  Zavři programy, které v něm mají otevřený soubor, a zkus znovu.")
        return 1
    return dokliz_metadata(repo, worktree)


def vychozi_vetev(chip) -> str:
    """Název větve odvozený z chipu: `ai/chip-NN/nazev`.

    Prefix `ai/` nese informaci, že kód psal AI agent — je vidět v názvu větve
    i v `git log`, takže při review (a u firemních repů zvlášť) nemusí nikdo
    dohledávat, odkud změna přišla. Starý tvar `chip/NN-nazev` se dál rozpozná
    (`chip_gate.id_z_vetve`, `hook_chip_gate.VETEV`), ale nové větve už se
    v něm nezakládají.
    """
    return f"ai/chip-{chip.id}/{chip.nazev}"


def cesty(chip) -> tuple[Path | None, str, Path]:
    """`(repo, vetev, worktree)` z frontmatteru chipu — bez vedlejších efektů.

    `vetev:` z frontmatteru má přednost, když je **vyplněná** — brief smí chtít
    vlastní název a starší chipy ho mají v původním tvaru. Prázdná (nebo úplně
    chybějící) hodnota znamená „odvoď to", ne „větev se jmenuje prázdno".

    Absolutní `worktree:` platí, jak je zapsaný — stejně ho čtou
    `chip_gate.kde_spustit()` i `hook_chip_gate.kde_overit()`, takže worktree
    vznikne tam, kam se pak dívá brána. Z relativního zápisu se bere jen jméno
    adresáře a worktree leží vedle repa, aby hodnota v briefu neznamenala něco
    jiného podle toho, odkud se skript pustí; absolutní cesta na `cwd` nezávisí,
    takže u ní tahle ochrana nic nekupuje a jen by zahodila, co brief říká.
    Když chybí `repo:`, je první prvek `None` (volající to hlásí) a relativní
    zápis zůstane holým jménem adresáře.
    """
    repo = chip.repo_path()
    vetev = (chip.meta.get("vetev") or "").strip() or vychozi_vetev(chip)
    zapis = Path(chip.meta.get("worktree", f"../repo-chip-{chip.id}"))
    if zapis.is_absolute():
        worktree = zapis
    else:
        worktree = (repo.parent / zapis.name) if repo is not None else Path(zapis.name)
    return repo, vetev, worktree


def zadani(chip, worktree: Path, vetev: str, od: str | None = None) -> str:
    """Text zadání pro nové okno (šablona `ZADANI` vyplněná daty chipu).

    `od` je ref, ze kterého se větvilo. Bez něj vznikne přesně dnešní text —
    zmínka o cizí rozpracované práci by tam byla lež.
    """
    return ZADANI.format(id=chip.id, nazev=chip.nazev, worktree=worktree,
                         vetev=vetev, brief=chip.path.resolve(),
                         zaklad=ZAKLAD.format(od=od) if od else "")


def brief_ke_stavu(chip, repo: Path | None, worktree: Path) -> Path:
    """Do KTERÉ kopie briefu smí `--stav` zapsat `running`.

    Když je brief verzovaný v repu, má ve worktree vlastní kopii — a jen ta
    patří k větvi chipu. Zápis do hlavního stromu měl dva důsledky, oba špatné:

    * v hlavním stromě zůstala necommitnutá změna souboru, který merge
      přepisuje, a `git merge` takový merge odmítne (`Your local changes …
      would be overwritten`) — to je ten „konflikt při mergi";
    * porušoval vlastní pravidlo „nesahej na brief běžícího chipu": tentýž
      soubor v tu chvíli edituje agent (Log, checkboxy).

    Fallback na originál je pro dva legitimní případy, kdy kopie ve worktree
    neexistuje: briefy leží mimo repo (`--dir`, cizí repo bez stopy CHIPS),
    nebo jsou v repu netrackované. V obou se do hlavního stromu psát smí —
    merge se toho souboru nedotkne, protože ho větev chipu nemá.
    """
    if repo is None:
        return chip.path
    try:
        rel = chip.path.resolve().relative_to(repo.resolve())
    except ValueError:
        return chip.path                       # brief mimo repo → není co řešit
    kopie = worktree / rel
    return kopie if kopie.exists() else chip.path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Připraví worktree pro chip.")
    ap.add_argument("cislo", help="číslo chipu, např. 01")
    ap.add_argument("--dry-run", action="store_true", help="jen vypsat příkazy")
    ap.add_argument("--uklid", action="store_true",
                    help="AŽ PO MERGI odstranit worktree chipu")
    ap.add_argument("--presto", action="store_true",
                    help="s --uklid: uklidit i nezmergovanou větev (opuštěný chip)")
    ap.add_argument("--spustit", action="store_true",
                    help="po založení worktree rovnou spustit Claude Code se zadáním")
    ap.add_argument("--stav", action="store_true",
                    help="po založení worktree přepsat stav briefu na 'running'")
    ap.add_argument("--od", metavar="REF",
                    help="větvit z daného ref (větev předchůdce, tag, SHA), ne z HEAD")
    ap.add_argument("--zaloz-repo", action="store_true",
                    help="chybějící/prázdné repo založit (git init + prázdný commit)")
    pridej_arg_dir(ap)
    args = ap.parse_args(argv)
    nastav_chips_dir(args.dir)

    cislo = args.cislo.zfill(2)
    chipy = [c for c in nacti_vse() if c.id == cislo]
    if not chipy:
        print(f"! chip {cislo} nenalezen v chips/")
        return 1
    chip = chipy[0]

    repo, vetev, worktree = cesty(chip)
    if repo is None:
        print(f"! {chip.path.name} nemá ve frontmatteru 'repo:' — nevím, kde zakládat worktree")
        return 1

    if args.zaloz_repo:
        # Dřív než kontrola `.git` níž — ta je právě to, co má `--zaloz-repo`
        # vyřešit, ne na čem má spadnout.
        if zaloz_repo(repo, dry=args.dry_run) != 0:
            return 1
    elif not (repo / ".git").exists():
        print(f"! '{repo}' není git repozitář — oprav 'repo:' ve frontmatteru "
              f"{chip.path.name}")
        return 1

    if args.uklid:
        return uklid(repo, worktree, vetev, cislo,
                     dry=args.dry_run, presto=args.presto)

    if not args.dry_run:
        if chip.stav != "ready":
            print(f"! chip {cislo} má stav '{chip.stav}', očekává se 'ready'.")
            print("  Nejdřív vyplň brief a spusť: python tools/chip_lint.py")
            return 1

        if worktree.exists():
            print(f"! worktree už existuje: {worktree}")
            print(f"  buď v něm pokračuj, nebo: python tools/chip_run.py {cislo} --uklid")
            return 1

    # Chybějící `claude` se hlásí dřív, než vznikne worktree — jinak by po
    # nesrozumitelném pádu zůstal poloviční stav, který blokuje další spuštění.
    claude_exe: str | None = None
    if args.spustit and not args.dry_run:
        claude_exe = shutil.which("claude")
        if claude_exe is None:
            print("! 'claude' není na PATH — nemám čím spustit Claude Code.")
            print("  Spusť to bez --spustit a zadání vlož do okna ručně.")
            return 1
        if je_cmd_shim(claude_exe):
            # Odmítnutí, ne tiché poškození: shim by zadání usekl (viz
            # je_cmd_shim). Worktree se založí normálně, jen se nespouští.
            print(f"! 'claude' je .cmd/.bat shim ({claude_exe}) — cmd.exe usekne")
            print("  víceřádkové zadání na prvním řádku, agent by dostal jen úvod.")
            print("  --spustit se proto přeskakuje; worktree založím a zadání níže")
            print("  vlož do okna ručně (nebo nainstaluj nativní claude.exe).")
            args.spustit = False
            claude_exe = None

    # Stejný důvod jako u `claude` výš: neexistující ref se musí ozvat dřív,
    # než `worktree add` nechá na disku poloviční stav.
    if args.od and not args.dry_run and not ref_existuje(repo, args.od):
        print(f"! ref '{args.od}' v '{repo}' neexistuje — nemám z čeho větvit.")
        print("  Větev předchozího chipu má tvar 'ai/chip-NN/nazev'; zkontroluj")
        print(f"  název přes: git -C \"{repo}\" branch -a")
        return 1

    print(f"  CHIP {cislo} — {chip.nazev}")
    print(f"  issues: {len(chip.issues())}   nárokovaných cest: {len(chip.soubory())}\n")

    # Ref jde až za `-b <vetev>`: `worktree add <cesta> -b <vetev> [<ref>]`.
    # Bez `--od` musí vzniknout bajt v bajt dnešní příkaz (větvení z HEAD).
    prikaz = ["worktree", "add", str(worktree), "-b", vetev]
    if args.od:
        prikaz.append(args.od)
    if git(repo, *prikaz, dry=args.dry_run) != 0:
        print("! git worktree add selhal")
        return 1

    if args.stav:
        # Až po `worktree add` — teprve tam vznikne kopie briefu, do které se
        # smí psát (viz brief_ke_stavu).
        cil = brief_ke_stavu(chip, repo, worktree)
        kde = "ve worktree chipu" if cil != chip.path else "v hlavním stromě"
        if args.dry_run:
            print(f"  (dry-run) stav v {chip.path.name} {kde}: "
                  f"'{chip.stav}' -> 'running'")
        elif prepis_stav(cil):
            print(f"  stav v {chip.path.name} ({kde}) přepnut na 'running'")
            if cil != chip.path:
                print("  (commitne se spolu s prací chipu; hlavní strom zůstává čistý)")
        else:
            print(f"! stav v {chip.path.name} ({kde}) se nepodařilo přepsat — "
                  f"přepiš ho ručně")

    text = zadani(chip, worktree, vetev, od=args.od)
    print("\n" + "=" * 72)
    print("ZADÁNÍ PRO NOVÉ OKNO (zkopíruj do Claude Code otevřeného ve worktree):")
    print("=" * 72)
    print(text)
    print("=" * 72)

    if args.spustit:
        if args.dry_run:
            print(f"  $ claude <zadání výše>   (cwd: {worktree})")
            return 0
        print(f"\n  spouštím Claude Code ve worktree: {worktree}\n")
        return subprocess.call([claude_exe, text], cwd=str(worktree))

    if not args.dry_run and not args.stav:
        print(f"\n  Nezapomeň přepnout stav chipu na 'running' v {chip.path.name}.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    utf8_vystup()
    sys.exit(main())
