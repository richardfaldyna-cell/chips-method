"""Nezávislá kontrola hotového chipu — sbírá podklady, nerozhoduje.

Testy k vlastnímu kódu si dnes píše týž model, který ten kód napsal, takže brána
je jen tak přísná, jak přísné jsou ty testy. Tenhle modul je protiváha: co jde
ověřit strojově (rozsah změn proti nároku, testy bez assertu, odškrtnutá DoD
vedle příkazů brány), ověří sám; zbytek vypíše jako zadání pro druhého agenta.

**Není to brána.** Návratový kód 1 vrací jen kontrola rozsahu (soubor mimo
sekci „Dotčené soubory" je tvrdé pravidlo metodiky) — všechno ostatní jsou
podklady pro člověka, ne verdikt o merge.

**Nález vs. otázka.** Posuzující řádky výpisu jsou dvojího druhu a nesmí
splynout. NÁLEZ tvrdí, že něco je špatně (soubor mimo nárok, nedotčený nárok,
test bez assertu) — takový řádek je potřeba vyřešit. OTÁZKA říká, co ověřit,
protože to nástroj rozhodnout neumí; typicky poměr odškrtnutých bodů DoD
k příkazům brány, kde je nepoměr normální stav (většina bodů se ověřuje testy
uvnitř sady, ne vlastním příkazem). Kdyby se otázka vypsala jako nález, čtenář
si na řádky, které nic neznamenají, zvykne a přeskočí i ten pravý — táž vada,
jakou u placeholderů v `chip_lint.py` řešil chip 15, a stejné řešení: hlásit
úžeji, ne tišeji.

Použití:
    python tools/chip_review.py 07                    # podklady o chipu 07
    python tools/chip_review.py 07 --repo C:/projekt  # chip v cizím repu
    python tools/chip_review.py 07 --commit main..HEAD
    python tools/chip_review.py 07 --zadani           # zadání pro reviewer agenta
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from chip_common import ROOT, nacti_vse, nastav_chips_dir, pridej_arg_dir, utf8_vystup
from chip_gate import prikazy as prikazy_brany
from chip_lint import prekryv, vzor

# `- [x] popis` v Definition of done; značka se drží zvlášť, ať jde odškrtnuté
# vypsat vedle neodškrtnutých (chip_common vrací jen texty).
DOD_RADEK = re.compile(r"^\s*-\s*\[([ xX])\]\s*(.+)$", re.M)

# `git --numstat` hlásí přejmenování jako `dir/{a.py => b.py}`; zajímá nás cíl.
PRESUN = re.compile(r"\{[^{}]*? => ([^{}]*?)\}")

DOKUMENTACE = {".md", ".html", ".txt", ".rst"}

ZADANI_REVIEW = """\
Jsi REVIEWER chipu {id} — {nazev}. Ten kód jsi nepsal; tvoje role je nezávisle
ověřit, co tvrdí někdo jiný. Nepřebírej jeho závěry, ověřuj je.

Co si přečti, v tomhle pořadí:
1. CELÝ brief: {brief}   (ne jen Issues — i Eskalaci a Log)
2. strojové podklady: python tools/chip_review.py {id} --repo {repo}
3. diff commitu: git -C {repo} show HEAD
4. testy, které chip přidal — čti je jako kód, ne jako seznam jmen

Na co odpovědět (na každý bod věta s důkazem, ne „ok"):
- Testují ty testy opravdu chování, nebo jen procházejí? Který test spadne,
  když se příslušná funkce pokazí? Zkus to — dočasně rozbij kód a pusť sadu.
- Sedí odškrtnutá Definition of done se skutečností? U každého bodu řekni,
  ČÍM je ověřený (konkrétní test / příkaz brány), nebo že ověřený není.
- Je nějaká issue odškrtnutá bez kódu, který by ji plnil?
- Je změněný soubor mimo sekci „Dotčené soubory"?
- Co se stane při vstupu, se kterým autor nepočítal (prázdno, chybějící
  soubor, cizí kódování, cesta s mezerou)?

Co NESMÍŠ:
- opravovat kód, ani „drobnost", ani překlep — jen hlásit
- mergovat, přepínat větev, cokoli pushovat
- měnit brief chipu (stav, checkboxy ani Log — to je mandát autora chipu)
- napsat „vypadá dobře" bez konkrétního důkazu

Výstup: seznam nálezů ve tvaru `soubor:řádek — co je špatně — proč to vadí`,
na konci jedna z vět: „nemám nález" / „nálezy k rozhodnutí uživatele".
Verdikt o merge nevynášíš — ten patří uživateli.
"""


class GitChyba(RuntimeError):
    """Git nešel spustit nebo odmítl rozsah — volající to hlásí uživateli."""


@dataclass
class Zmena:
    """Jeden řádek `git --numstat`: cesta a kolik řádků přibylo/ubylo."""

    cesta: str
    pridano: int = 0
    ubrano: int = 0
    binarni: bool = False


NALEZ = "nález"
OTAZKA = "otázka"


@dataclass(frozen=True)
class Signal:
    """Posuzující řádek výpisu a jeho druh — viz docstring modulu.

    `tvrdy` nese jediné tvrdé pravidlo metodiky (soubor mimo nárok); jen ono
    zvedá návratový kód. Ostatní nálezy jsou pořád jen podklad — nástroj
    nerozhoduje o merge, ani když má pravdu.
    """

    druh: str
    text: str
    tvrdy: bool = False


def nalez(text: str, tvrdy: bool = False) -> Signal:
    """Zkratka pro tvrzení „tohle je špatně"."""
    return Signal(NALEZ, text, tvrdy)


def otazka(text: str) -> Signal:
    """Zkratka pro podnět „tohle ověř" — nástroj to rozhodnout neumí."""
    return Signal(OTAZKA, text)


def vyber(signaly, druh: str) -> list[Signal]:
    """Signály jednoho druhu, v pořadí, v jakém je sekce vydaly."""
    return [s for s in signaly if s.druh == druh]


def _git(repo: Path, *args: str) -> tuple[int, str]:
    """Git bez shellu (cesty s mezerami), vrací (kód, výstup)."""
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    except OSError as e:                                   # pragma: no cover
        raise GitChyba(f"nelze spustit git: {e}") from e
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def cesta_z_numstat(cesta: str) -> str:
    """Cíl změny — u přejmenování `a => b` i `dir/{a => b}/x` vrací nový tvar."""
    cesta = PRESUN.sub(lambda m: m.group(1), cesta)
    if " => " in cesta:
        cesta = cesta.split(" => ")[-1]
    return cesta.strip().replace("//", "/").lstrip("/")


def parsuj_numstat(vystup: str) -> list[Zmena]:
    """`přidáno\\tubráno\\tcesta` → seznam změn; `-` znamená binární soubor."""
    out: list[Zmena] = []
    for radek in vystup.splitlines():
        casti = radek.split("\t")
        if len(casti) < 3 or not casti[2].strip():
            continue
        a, u = casti[0].strip(), casti[1].strip()
        binarni = a == "-" or u == "-"
        out.append(Zmena(cesta=cesta_z_numstat("\t".join(casti[2:])),
                         pridano=0 if binarni else int(a or 0),
                         ubrano=0 if binarni else int(u or 0),
                         binarni=binarni))
    return out


def zmeny(repo: Path, rozsah: str = "HEAD") -> list[Zmena]:
    """Soubory a diff stat commitu (`HEAD`) nebo rozsahu (`main..HEAD`)."""
    if ".." in rozsah:
        kod, vystup = _git(repo, "diff", "--numstat", rozsah)
    else:
        kod, vystup = _git(repo, "show", "--numstat", "--format=", rozsah)
    if kod != 0:
        raise GitChyba(f"git nedokázal přečíst rozsah '{rozsah}': {vystup.strip()}")
    return parsuj_numstat(vystup)


def ref_konce(rozsah: str) -> str:
    """Konec rozsahu — z `main..HEAD` je to `HEAD` (odtud se čte obsah souborů)."""
    return rozsah.split("..")[-1] or "HEAD"


def obsah(repo: Path, cesta: str, ref: str = "HEAD") -> str | None:
    """Text souboru z pracovního stromu, a když tam není, z commitu.

    Ve worktree hotového chipu jsou obě verze stejné; sáhnutí do commitu je
    pojistka pro `--commit` na starší revizi a pro soubory smazané po commitu.
    """
    p = repo / cesta
    if p.is_file():
        try:
            return p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
    kod, vystup = _git(repo, "show", f"{ref}:{cesta}")
    return vystup if kod == 0 else None


# --- kontrola rozsahu (#2) ------------------------------------------------

def je_vlastni_brief(chip, cesta: str) -> bool:
    """Vlastní brief chipu a jeho `.html` smí chip měnit — je to jeho mandát."""
    p = PurePosixPath(cesta.replace("\\", "/"))
    return (p.name in (chip.path.name, chip.path.stem + ".html")
            and p.parent.name in (chip.path.parent.name, "chips"))


def mimo_narok(chip, cesty) -> list[str]:
    """Cesty, které nepokrývá žádný nárok ze sekce „Dotčené soubory"."""
    naroky = chip.soubory()
    return [c for c in cesty
            if not je_vlastni_brief(chip, c)
            and not any(prekryv(c, n) for n in naroky)]


def nedotcene_naroky(chip, cesty) -> list[str]:
    """Nárokované cesty, ke kterým nevede žádná změna — nárok navíc, nebo nedodělek."""
    return [n for n in chip.soubory() if not any(prekryv(c, n) for c in cesty)]


# --- podezřelé testy (#3) -------------------------------------------------

def _jmeno(node) -> str:
    """Uzel výrazu → tečkové jméno (`unittest.TestCase`), jinak prázdný řetězec."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        zaklad = _jmeno(node.value)
        return f"{zaklad}.{node.attr}" if zaklad else node.attr
    return ""


def _testcase_tridy(strom: ast.AST) -> dict[str, ast.ClassDef]:
    """Třídy odvozené od `unittest.TestCase`, i přes vlastní mezitřídu.

    Fixní bod: `class Zaklad(unittest.TestCase)` udělá z `Zaklad` testcase a
    teprve pak se pozná `class TestNeco(Zaklad)`. Pořadí v souboru se řešit
    nemusí, opakuje se, dokud něco přibývá.
    """
    tridy = [n for n in ast.walk(strom) if isinstance(n, ast.ClassDef)]
    znam: dict[str, ast.ClassDef] = {}
    zmena = True
    while zmena:
        zmena = False
        for t in tridy:
            if t.name in znam:
                continue
            for b in t.bases:
                jm = _jmeno(b)
                if jm.split(".")[-1] == "TestCase" or jm.split(".")[-1] in znam:
                    znam[t.name] = t
                    zmena = True
                    break
    return znam


def _ma_assert(metoda) -> bool:
    """Ověřuje metoda vůbec něco? `self.assert*`, `self.fail`, holé `assert`.

    `with self.assertRaises(...)` je taky volání, takže spadne do stejné větve.
    Volání pomocné metody, která assertuje uvnitř, se nepozná — proto je nález
    „podezřelý", ne „chybný".
    """
    for uzel in ast.walk(metoda):
        if isinstance(uzel, ast.Assert):
            return True
        if isinstance(uzel, ast.Call):
            jm = _jmeno(uzel.func).split(".")[-1]
            if jm.startswith("assert") or jm in ("fail", "raises"):
                return True
    return False


def _preskocene(metoda) -> list[str]:
    """Dekorátory, které test vypnou nebo mu odpustí pád."""
    out = []
    for d in metoda.decorator_list:
        jm = _jmeno(d.func if isinstance(d, ast.Call) else d).split(".")[-1]
        if jm.startswith("skip") or jm == "expectedFailure":
            out.append(jm)
    return out


def podezrele_testy(zdroj: str, cesta: str) -> list[tuple[int, str]]:
    """Nálezy v jednom testovacím souboru: (řádek, popis).

    Přes `ast`, ne regexem — `assert` uvnitř řetězce nebo komentáře by regex
    spolkl a test bez ověření by prošel jako poctivý.
    """
    try:
        strom = ast.parse(zdroj)
    except SyntaxError as e:
        return [(e.lineno or 0, f"{cesta}: nelze naparsovat ({e.msg})")]

    nalezy: list[tuple[int, str]] = []
    for jmeno_tridy, trida in _testcase_tridy(strom).items():
        for m in trida.body:
            if not isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not m.name.startswith("test"):
                continue
            kde = f"{cesta}:{m.lineno}  {jmeno_tridy}.{m.name}"
            for dekorator in _preskocene(m):
                nalezy.append((m.lineno, f"{kde} — @{dekorator}, test se nepočítá"))
            if not _ma_assert(m):
                nalezy.append((m.lineno, f"{kde} — žádný assert, nic neověřuje"))
    return sorted(nalezy)


def je_test(cesta: str) -> bool:
    """Testovací soubor podle konvence projektu (`tests/`, `test_*.py`)."""
    p = PurePosixPath(cesta.replace("\\", "/"))
    return (p.suffix == ".py"
            and (p.name.startswith("test_") or p.stem.endswith("_test")
                 or "tests" in p.parts or "test" in p.parts))


def kodove_soubory(seznam) -> list[str]:
    """Netestovací a nedokumentační cesty commitu — kvůli chybějícím testům.

    Rozhoduje typ souboru, ne počet přidaných řádků: commit, který kód jen
    maže nebo přepisuje, je pořád zásah do kódu a test si žádá stejně.
    """
    return sorted(z.cesta for z in seznam
                  if not je_test(z.cesta)
                  and PurePosixPath(z.cesta).suffix.lower() not in DOKUMENTACE)


# --- DoD vs. realita (#4) a poměr testů ke kódu (#5) ----------------------

def dod_body(chip) -> list[tuple[bool, str]]:
    """Definition of done jako (odškrtnuto, text) — v pořadí, jak stojí v briefu."""
    return [(m.group(1).lower() == "x", m.group(2).strip())
            for m in DOD_RADEK.finditer(chip.najdi("definition of done") or "")]


def pomer(seznam) -> tuple[int, int, int]:
    """Přidané řádky (testy, kód, dokumentace) — hrubý ukazatel, ne verdikt."""
    testy = kod = dokumentace = 0
    for z in seznam:
        if je_test(z.cesta):
            testy += z.pridano
        elif PurePosixPath(z.cesta).suffix.lower() in DOKUMENTACE:
            dokumentace += z.pridano
        else:
            kod += z.pridano
    return testy, kod, dokumentace


def zadani(chip, repo: Path) -> str:
    """Text zadání pro reviewer agenta (#6) — co číst, na co odpovědět, co nesmí."""
    return ZADANI_REVIEW.format(id=chip.id, nazev=chip.nazev,
                                brief=chip.path.resolve(), repo=repo)


# --- výpis ----------------------------------------------------------------

def pocet(n: int, jeden: str, dva: str, pet: str) -> str:
    """České skloňování za číslovkou: 1 soubor / 2 soubory / 5 souborů."""
    return f"{n} {jeden if n == 1 else (dva if 2 <= n <= 4 else pet)}"


def _souboru(n: int) -> str:
    return pocet(n, "soubor", "soubory", "souborů")


def sekce_soubory(seznam) -> tuple[list[str], list[Signal]]:
    """Inventura commitu — samá data, žádné posuzování.

    Prázdný commit se tu nehlásí jako nález: kdyby chip opravdu nic neudělal,
    ozvou se nedotčené nároky v sekci rozsahu a dvojí hlášení téhož jen šumí.
    """
    radky = ["  Změněné soubory"]
    if not seznam:
        return radky + ["    — commit nemění žádný soubor"], []
    for z in sorted(seznam, key=lambda z: z.cesta):
        stat = "  bin " if z.binarni else f"{z.pridano:+5d} {-z.ubrano:+5d}"
        radky.append(f"    {stat}  {z.cesta}")
    radky.append(f"    celkem: {_souboru(len(seznam))}, "
                 f"+{sum(z.pridano for z in seznam)} -{sum(z.ubrano for z in seznam)}")
    return radky, []


def sekce_rozsah(chip, seznam) -> tuple[list[str], list[Signal]]:
    """Kontrola rozsahu (#2) — samé nálezy, tady se nic neověřuje dodatečně.

    Soubor mimo nárok i nedotčený nárok jsou tvrzení o tom, co v commitu je
    a co v něm chybí; nástroj na to má úplná data, takže se ptát nemá proč.
    """
    cesty = [z.cesta for z in seznam]
    mimo = mimo_narok(chip, cesty)
    radky = ["  Rozsah proti nároku (sekce 'Dotčené soubory')"]
    for n in chip.soubory():
        radky.append(f"    nárok: {n}" + ("   (vzor)" if vzor(n) else ""))
    if not mimo:
        radky.append("    OK — každá změna spadá pod nárok (nebo je to vlastní brief)")
    signaly = [nalez(f"MIMO NÁROK: {c}", tvrdy=True) for c in mimo]
    signaly += [nalez(f"nárok '{n}' nemá v commitu jedinou změnu")
                for n in nedotcene_naroky(chip, cesty)]
    return radky, signaly


def sekce_testy(repo: Path, seznam,
                ref: str = "HEAD") -> tuple[list[str], list[Signal]]:
    """Podezřelé testy (#3) ve všech testovacích souborech commitu.

    Chybějící testovací soubor je nález jen tam, kde vadí — u commitu, který
    sahá na kód. Chip, který mění jen dokumentaci, testy měnit nemá proč a
    hlásit mu to znamená vychovat čtenáře, který sekci přeskakuje.
    """
    radky = ["  Podezřelé testy"]
    testovaci = [z.cesta for z in sorted(seznam, key=lambda z: z.cesta)
                 if je_test(z.cesta) and not z.binarni]
    if not testovaci:
        kod = kodove_soubory(seznam)
        if not kod:
            return radky + ["    — commit nemění kód ani testy"], []
        return (radky + ["    — commit nemění žádný testovací soubor"],
                [nalez(f"commit mění kód ({', '.join(kod[:3])}"
                       f"{' …' if len(kod) > 3 else ''}), ale žádný "
                       f"testovací soubor")])
    signaly: list[Signal] = []
    for cesta in testovaci:
        text = obsah(repo, cesta, ref)
        if text is None:
            # Nástroj nemá co posoudit — to není nález o kódu, ale úkol pro čtenáře.
            signaly.append(otazka(f"{cesta}: obsah se nepodařilo přečíst — projdi "
                                  f"soubor ručně"))
            continue
        signaly += [nalez(popis) for _, popis in podezrele_testy(text, cesta)]
    # Nadpis nad prázdnem je taky šum — když jdou signály do souhrnu níž,
    # ať sekce aspoň řekne, kolik souborů prošla.
    kolik = pocet(len(testovaci), "testovací soubor", "testovací soubory",
                  "testovacích souborů")
    if signaly:
        radky.append(f"    {kolik} — co je na nich k řešení, stojí níž")
    else:
        radky.append(f"    OK — {kolik}, žádný test bez assertu ani vypnutý test")
    return radky, signaly


def sekce_dod(chip) -> tuple[list[str], list[Signal]]:
    """Odškrtnutá DoD vedle příkazů brány (#4) — ať jde porovnat tvrzení s ověřením.

    Nepoměr „víc odškrtnutých bodů než příkazů brány" je **normální stav**:
    většina bodů DoD se ověřuje testy uvnitř sady, ne vlastním příkazem
    v sekci „Ověření (brána)". Proto je to otázka, ne nález — informace
    užitečná zůstává, tvrzení o vadě se nekoná. Nálezem zůstává jen prázdno:
    brief bez jediného bodu DoD a brána bez jediného příkazu.
    """
    radky = ["  Definition of done — odškrtnuté vs. co brána opravdu spouští"]
    signaly: list[Signal] = []
    body = dod_body(chip)
    if not body:
        signaly.append(nalez("brief nemá v Definition of done jediný bod"))
    for hotovo, text in body:
        radky.append(f"    [{'x' if hotovo else ' '}] {text}")
    prikazy = prikazy_brany(chip)
    radky.append("    brána:")
    if not prikazy:
        signaly.append(nalez("brána nespouští jediný příkaz — odškrtnutí nemá "
                             "co ověřit"))
    radky.extend(f"      $ {p}" for p in prikazy)
    hotovych = sum(1 for h, _ in body if h)
    if hotovych > len(prikazy) and prikazy:
        signaly.append(otazka(f"{hotovych} odškrtnutých bodů DoD proti "
                              f"{len(prikazy)} příkazům brány — ověř, čím jsou "
                              f"kryté body bez vlastního příkazu (typicky testy "
                              f"uvnitř sady)"))
    return radky, signaly


def sekce_pomer(seznam) -> tuple[list[str], list[Signal]]:
    """Poměr přidaných řádků testů ke kódu (#5) — vypsat, nekomentovat.

    Ukazatel bez prahu: hranici „málo testů" nástroj nezná, takže z něj
    nedělá ani nález, ani otázku.
    """
    testy, kod, dok = pomer(seznam)
    p = f"{testy / kod:.2f} : 1" if kod else "—  (žádný přidaný řádek kódu)"
    return ["  Přidané řádky",
            f"    kód {kod}   testy {testy}   dokumentace {dok}",
            f"    poměr testy:kód = {p}   (ukazatel, ne verdikt)"], []


def sekce_signaly(signaly) -> list[str]:
    """Nálezy a otázky odděleně (#2, #5, #6).

    Prázdná sekce se nevypisuje vůbec: nadpis nad ničím je zvyk na přeskakování.
    Když není ani jedno, řekne se to jednou větou.
    """
    nalezy, otazky = vyber(signaly, NALEZ), vyber(signaly, OTAZKA)
    if not nalezy and not otazky:
        return ["  Bez nálezů a bez otázek — co jde ověřit strojově, sedí."]
    radky: list[str] = []
    if nalezy:
        radky.append("  Nálezy — tohle je špatně")
        radky += [f"    {'X' if s.tvrdy else '!'}  {s.text}" for s in nalezy]
        radky.append("")
    if otazky:
        radky.append("  Otázky — tohle nástroj rozhodnout neumí, ověř ty")
        radky += [f"    ?  {s.text}" for s in otazky]
        radky.append("")
    radky.append(f"  Souhrn: {pocet(len(nalezy), 'nález', 'nálezy', 'nálezů')}, "
                 f"{pocet(len(otazky), 'otázka', 'otázky', 'otázek')}.")
    return radky


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Nezávislé podklady o hotovém chipu (nerozhoduje o merge).")
    ap.add_argument("cislo", help="číslo chipu, např. 07")
    ap.add_argument("--repo", help="kořen repa, kde chip běžel (default: podle briefu)")
    ap.add_argument("--commit", default="HEAD", metavar="REF",
                    help="commit nebo rozsah ke kontrole (default: HEAD, jde i main..HEAD)")
    ap.add_argument("--zadani", action="store_true",
                    help="vypsat jen zadání pro reviewer agenta")
    pridej_arg_dir(ap)
    args = ap.parse_args(argv)
    chips_dir = nastav_chips_dir(args.dir)

    cislo = args.cislo.zfill(2)
    chip = next((c for c in nacti_vse() if c.id == cislo), None)
    if chip is None:
        print(f"! chip {cislo} nenalezen v {chips_dir}")
        return 1

    repo = Path(args.repo).expanduser().resolve() if args.repo else chip.repo_path()
    if repo is None or not repo.is_dir():
        print(f"! repo '{repo}' neexistuje — zadej --repo nebo oprav 'repo:' "
              f"v {chip.path.name}")
        return 1

    if args.zadani:
        print("=" * 72)
        print(zadani(chip, repo))
        print("=" * 72)
        return 0

    try:
        seznam = zmeny(repo, args.commit)
    except GitChyba as e:
        print(f"! {e}")
        return 1

    print(f"  REVIEW chip {chip.id} — {chip.nazev}   ({repo})")
    print(f"  brief: {chip.path.name}   stav: {chip.stav}   "
          f"issues: {len(chip.hotove_issues())}/{len(chip.issues())} hotových   "
          f"rozsah: {args.commit}\n")

    signaly: list[Signal] = []
    for radky, s in (sekce_soubory(seznam),
                     sekce_rozsah(chip, seznam),
                     sekce_testy(repo, seznam, ref_konce(args.commit)),
                     sekce_dod(chip), sekce_pomer(seznam)):
        print("\n".join(radky))
        print()
        signaly.extend(s)

    print("\n".join(sekce_signaly(signaly)))
    print()

    tvrde = [s for s in signaly if s.tvrdy]
    if tvrde:
        print(f"  X  {_souboru(len(tvrde))} mimo nárok — to je tvrdé pravidlo "
              f"metodiky, ne podklad.")
        print("     Zbytek výpisu jsou podklady pro review, ne verdikt o merge.")
        return 1
    print("  Podklady sebrány. Verdikt o merge nevynáší tenhle nástroj —")
    print(f"  zadání pro reviewer agenta: python tools/chip_review.py {chip.id} --zadani")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    utf8_vystup()
    sys.exit(main())
