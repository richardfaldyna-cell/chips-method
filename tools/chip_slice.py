"""Návrh řezu fronty úkolů na chipy — podle disjunktnosti souborů.

Řezání dnes dělá člověk ručně a u stovky issues je to úzké hrdlo. Kritérium je
přitom mechanické: dva úkoly, které sahají na týž soubor, **musí** skončit
v jednom chipu. Skupiny jsou souvislé komponenty bipartitního grafu úkol–soubor.

Nástroj **nerozhoduje, navrhuje**: vypíše skupiny, označí ty nad strop a zvlášť
vypíše úkoly, u kterých žádný soubor neví. Návratový kód je vždy 0 — brána je
`chip_lint.py`, tohle je podklad pro člověka.

Co se bere jako „úkol uvádí soubor":
  * cesta s adresářem přímo v textu (`tools/chip_slice.py`, `src/*.py`),
  * holé jméno souboru **v backticích** (`chip_lint.py`), a to jen když se
    v repu dohledá právě jeden takový soubor (`--bez-dohledani` vypne).
Nic jiného. Úkol bez souboru jde do sekce NEZAŘAZENO — odhad by vypadal jako
informace, a přitom by informací nebyl.

Použití:
    python tools/chip_slice.py --todo TODO.md
    python tools/chip_slice.py --json fronta.json
    python tools/chip_slice.py --todo TODO.md --zapsat chips/navrh
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from chip_common import (HOTOVA_ISSUE, ISSUE, ROOT, nastav_chips_dir,
                         pridej_arg_dir, utf8_vystup)
from chip_lint import prekryv, vzor

MAX_UKOLU = 20        # strop z metodiky (chip_lint hlásí totéž)
MAX_SOUBORU = 15
SIRKA = 78

# Cesta s adresářem: `adresar/soubor.pripona`. Zástupné znaky jsou povolené,
# ať se dá do fronty napsat i `src/*.py`.
CESTA = re.compile(r"(?:[\w.+\-*?\[\]]+/)+[\w.+\-*?\[\]]*[\w*?\]]\.[A-Za-z][\w*?]{0,7}")
# Holé jméno souboru, ale JEN uvnitř backticků — volný text `např. 0.041` by
# se jinak četl jako soubor s příponou.
BACKTICK = re.compile(r"`([^`\n]+)`")
JMENO = re.compile(r"^[\w.+\-]*[A-Za-z_][\w.+\-]*\.[A-Za-z][A-Za-z0-9]{0,7}$")


@dataclass
class Ukol:
    id: str
    popis: str
    soubory: list[str] = field(default_factory=list)
    # jméno → důvod, proč se nedohledalo (jen pro výpis, ne pro řez)
    nedohledane: list[str] = field(default_factory=list)


@dataclass
class Skupina:
    ukoly: list[Ukol]
    cislo: str = "00"

    @property
    def soubory(self) -> list[str]:
        out: list[str] = []
        for u in self.ukoly:
            for s in u.soubory:
                if s not in out:
                    out.append(s)
        return sorted(out)

    def prilis_velka(self, max_ukolu: int = MAX_UKOLU,
                     max_souboru: int = MAX_SOUBORU) -> str | None:
        """Popis překročení stropu, nebo None. Nerozřezává — to je na člověku."""
        duvody = []
        if len(self.ukoly) > max_ukolu:
            duvody.append(f"{len(self.ukoly)} úkolů (strop {max_ukolu})")
        if len(self.soubory) > max_souboru:
            duvody.append(f"{len(self.soubory)} souborů (strop {max_souboru})")
        return ", ".join(duvody) or None


# ---------------------------------------------------------------- vstupy

def _odrazky(text: str) -> list[tuple[str, str]]:
    """`- [ ]` odrážky včetně odsazených pokračovacích řádků.

    Úkol se v TODO.md běžně láme přes víc řádků a cesta bývá až na druhém —
    kdyby se braly jen samotné odrážky, polovina nároků by zmizela.
    Odškrtnuté (`- [x]`) se přeskakují: hotová práce se neřeže.
    """
    out: list[tuple[str, str]] = []
    aktualni: list[str] | None = None
    hotova = False
    for radek in text.splitlines():
        m = ISSUE.match(radek)
        if m:
            if aktualni is not None and not hotova:
                out.append(("", " ".join(aktualni)))
            hotova = HOTOVA_ISSUE.match(radek) is not None
            aktualni = [m.group(1).strip()]
        elif aktualni is not None and radek.strip() and radek[:1].isspace():
            aktualni.append(radek.strip())
        else:
            if aktualni is not None and not hotova:
                out.append(("", " ".join(aktualni)))
            aktualni, hotova = None, False
    if aktualni is not None and not hotova:
        out.append(("", " ".join(aktualni)))
    return out


def cesty_z_textu(text: str, repo: Path | None = None,
                  dohledat: bool = True) -> tuple[list[str], list[str]]:
    """(nalezené cesty, jména bez jednoznačného umístění) — nic se nehádá."""
    nalezene: list[str] = []
    # windowsová cesta v textu (`tools\chip_run.py`) je pořád nárok na týž soubor
    for c in CESTA.findall(text.replace("\\", "/")):
        c = c.strip(".,;:)»")
        if c and c not in nalezene:
            nalezene.append(c)

    nejasne: list[str] = []
    if dohledat and repo is not None and repo.is_dir():
        for kus in BACKTICK.findall(text):
            kus = kus.strip().strip(".,;:")
            if "/" in kus or not JMENO.match(kus):
                continue
            shody = sorted(p for p in repo.rglob(kus)
                           if p.is_file() and ".git" not in p.parts)
            if len(shody) == 1:
                rel = shody[0].relative_to(repo).as_posix()
                if rel not in nalezene:
                    nalezene.append(rel)
            elif kus not in nejasne:
                # 0 shod = soubor v repu není, 2+ = neví se který; obojí je
                # neurčitost, ne informace → nikam se netipuje
                nejasne.append(kus)
    return nalezene, nejasne


def nacti_todo(path: Path, repo: Path | None = None,
               dohledat: bool = True) -> list[Ukol]:
    ukoly: list[Ukol] = []
    for i, (_, popis) in enumerate(_odrazky(path.read_text(encoding="utf-8")), 1):
        soubory, nejasne = cesty_z_textu(popis, repo, dohledat)
        ukoly.append(Ukol(id=f"#{i}", popis=popis, soubory=soubory,
                          nedohledane=nejasne))
    return ukoly


def nacti_json(path: Path, repo: Path | None = None,
               dohledat: bool = True) -> list[Ukol]:
    """Alternativní vstup: `[{"id", "popis", "soubory": [...]}, …]`.

    Chybí-li `soubory`, zkusí se stejné čtení z textu jako u TODO — uvedený
    seznam ale vždycky vyhrává (je to nárok, ne odhad).
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):                      # {"issues": [...]} i holý seznam
        for klic in ("issues", "ukoly", "tasks", "items"):
            if isinstance(data.get(klic), list):
                data = data[klic]
                break
        else:
            raise ValueError("JSON musí být seznam úkolů (nebo objekt s klíčem 'issues')")
    if not isinstance(data, list):
        raise ValueError("JSON musí být seznam úkolů")

    ukoly: list[Ukol] = []
    for i, polozka in enumerate(data, 1):
        if not isinstance(polozka, dict):
            raise ValueError(f"položka {i} není objekt s klíči id/popis/soubory")
        popis = str(polozka.get("popis") or polozka.get("title") or "").strip()
        uid = str(polozka.get("id") or i)
        if not uid.startswith("#"):
            uid = f"#{uid}"
        syrove = polozka.get("soubory") or polozka.get("files")
        if syrove:
            soubory = [str(s).replace("\\", "/").strip().rstrip("/") for s in syrove]
            nejasne: list[str] = []
        else:
            soubory, nejasne = cesty_z_textu(popis, repo, dohledat)
        ukoly.append(Ukol(id=uid, popis=popis, soubory=soubory, nedohledane=nejasne))
    return ukoly


# ---------------------------------------------------------------- řez

def _sjednot(ukoly: list[Ukol]) -> list[list[int]]:
    """Union-find nad indexy úkolů; spojuje se přes překryv nárokovaných cest."""
    rodic = list(range(len(ukoly)))

    def najdi(x: int) -> int:
        while rodic[x] != x:
            rodic[x] = rodic[rodic[x]]
            x = rodic[x]
        return x

    for i, a in enumerate(ukoly):
        for j in range(i + 1, len(ukoly)):
            b = ukoly[j]
            if najdi(i) == najdi(j):
                continue
            if any(prekryv(x, y) for x in a.soubory for y in b.soubory):
                rodic[najdi(j)] = najdi(i)

    komponenty: dict[int, list[int]] = {}
    for i in range(len(ukoly)):
        komponenty.setdefault(najdi(i), []).append(i)
    return [v for _, v in sorted(komponenty.items())]


def rozdel(ukoly: list[Ukol]) -> tuple[list[Skupina], list[Ukol]]:
    """(skupiny, nezařazené). Úkol bez jediného známého souboru se neřeže."""
    znamé = [u for u in ukoly if u.soubory]
    nezarazene = [u for u in ukoly if not u.soubory]

    skupiny = [Skupina(ukoly=[znamé[i] for i in slozky])
               for slozky in _sjednot(znamé)]
    for n, s in enumerate(skupiny, 1):
        s.cislo = f"{n:02d}"
    return skupiny, nezarazene


# ---------------------------------------------------------------- zápis

def volne_cislo(adresar: Path, od: int = 1) -> str:
    """Nejbližší volné dvojčíslí — cizí brief se nikdy nepřepisuje."""
    obsazena = set()
    if adresar.is_dir():
        for p in adresar.glob("*.md"):
            m = re.match(r"(\d+)-", p.name)
            if m:
                obsazena.add(int(m.group(1)))
    n = od
    while n in obsazena:
        n += 1
    return f"{n:02d}"


def _nahrad_sekci(text: str, nadpis: str, obsah: str) -> str:
    """Vymění tělo sekce `## <nadpis>…` až po další `##` (nadpis smí mít ozdobu)."""
    vzorec = re.compile(r"(^##\s+" + re.escape(nadpis) + r"[^\n]*\n)(.*?)(?=^##\s|\Z)",
                        re.M | re.S)
    return vzorec.sub(lambda m: m.group(1) + obsah, text, count=1)


def text_briefu(sablona: str, s: Skupina, *, cislo: str, nazev: str,
                repo: str, datum: str, max_ukolu: int = MAX_UKOLU,
                max_souboru: int = MAX_SOUBORU) -> str:
    """Draft brief ze šablony — stav zůstává `draft`, člověk ho dopisuje.

    Šablona se čte ze souboru (`chips/TEMPLATE.md`), ne z natvrdo zapsaného
    řetězce: kdyby se struktura briefu změnila, generátor by se jinak tiše
    rozešel se zbytkem projektu.
    """
    issues = "\n".join(f"- [ ] {u.id} — {u.popis}" for u in s.ukoly) or "- [ ] (doplň)"
    bloky = "\n".join(s.soubory)
    pozn = s.prilis_velka(max_ukolu, max_souboru)
    hlavicka = (f"> ⚠️ PŘÍLIŠ VELKÁ: {pozn} — rozřež na dva chipy.\n\n"
                if pozn else "")

    text = (sablona
            .replace("chip: NN", f"chip: {cislo}")
            .replace("nazev: kratky-nazev-s-pomlckami", f"nazev: {nazev}")
            .replace("repo: C:/cesta/k/repu", f"repo: {repo}")
            .replace("vetev: ai/chip-NN/kratky-nazev-s-pomlckami",
                     f"vetev: ai/chip-{cislo}/{nazev}")
            .replace("worktree: ../repo-chip-NN", f"worktree: ../repo-chip-{cislo}")
            .replace("# CHIP NN — <název>", f"# CHIP {cislo} — {nazev.replace('-', ' ')}")
            .replace("Jednou větou, co tenhle balíček řeší.",
                     "NÁVRH z `chip_slice.py` — projdi a doplň, než přepneš na `ready`.")
            .replace("| YYYY-MM-DD | draft | založeno |",
                     f"| {datum} | draft | návrh z chip_slice.py |"))
    text = _nahrad_sekci(text, "Issues", f"\n{hlavicka}{issues}\n\n")
    text = _nahrad_sekci(text, "Dotčené soubory", f"\n```\n{bloky}\n```\n\n")
    # Příklady DoD a brány ze šablony jsou pro tenhle repo smyšlené (`pytest
    # tests/test_parser.py`). Nástroj je nevymýšlí a nenechává tam viset jako
    # by platily — vyprázdní je na výzvu člověku.
    text = _nahrad_sekci(text, "Definition of done",
                         "\nMusí jít ověřit příkazem, ne názorem. **Doplň ručně** —"
                         " nástroj podmínky nevymýšlí.\n\n"
                         "- [ ] (doplň ověřitelnou podmínku)\n\n")
    text = _nahrad_sekci(text, "Ověření (brána)",
                         "\nBez zelené brány se **nemerguje**. Když selže → stav"
                         " `blocked`, otevři PR.\n\n"
                         "```bash\n# doplň příkazy brány\n```\n\n")
    return text


def zapis(skupiny: list[Skupina], adresar: Path, sablona: Path, *, repo: str,
          datum: str, max_ukolu: int = MAX_UKOLU,
          max_souboru: int = MAX_SOUBORU) -> list[Path]:
    adresar.mkdir(parents=True, exist_ok=True)
    text_sablony = sablona.read_text(encoding="utf-8")
    zapsane: list[Path] = []
    od = 1
    for s in skupiny:
        cislo = volne_cislo(adresar, od)
        od = int(cislo) + 1
        nazev = f"navrh-{cislo}"
        cil = adresar / f"{cislo}-{nazev}.md"
        if cil.exists():                       # pojistka; volne_cislo už to řeší
            continue
        cil.write_text(text_briefu(text_sablony, s, cislo=cislo, nazev=nazev,
                                   repo=repo, datum=datum, max_ukolu=max_ukolu,
                                   max_souboru=max_souboru), encoding="utf-8")
        zapsane.append(cil)
    return zapsane


# ---------------------------------------------------------------- výpis

def _sklonuj(n: int, jedna: str, dve: str, pet: str) -> str:
    """České skloňování za číslovkou: 1 skupina / 2 skupiny / 5 skupin."""
    return jedna if n == 1 else (dve if 2 <= n <= 4 else pet)


def _fill(text: str, odsazeni: str) -> str:
    return textwrap.fill(text, width=SIRKA, initial_indent=odsazeni,
                         subsequent_indent=" " * len(odsazeni))


def vypis(skupiny: list[Skupina], nezarazene: list[Ukol], *,
          max_ukolu: int = MAX_UKOLU, max_souboru: int = MAX_SOUBORU) -> None:
    zarazenych = sum(len(s.ukoly) for s in skupiny)
    print(f"  Návrh řezu: {len(skupiny)} "
          f"{_sklonuj(len(skupiny), 'skupina', 'skupiny', 'skupin')}, "
          f"{zarazenych} zařazených, {len(nezarazene)} nezařazených úkolů\n")
    for s in skupiny:
        pozn = s.prilis_velka(max_ukolu, max_souboru)
        znacka = f"   ⚠️ PŘÍLIŠ VELKÁ: {pozn} — rozřež" if pozn else ""
        print(f"  skupina {s.cislo}  "
              f"({len(s.ukoly)} {_sklonuj(len(s.ukoly), 'úkol', 'úkoly', 'úkolů')}, "
              f"{len(s.soubory)} "
              f"{_sklonuj(len(s.soubory), 'soubor', 'soubory', 'souborů')}){znacka}")
        for u in s.ukoly:
            print(_fill(f"{u.id} {u.popis}", "    - "))
        print(_fill(", ".join(s.soubory), "    soubory: "))
        print()

    if nezarazene:
        print("  NEZAŘAZENO — doplň soubory ručně "
              "(nástroj je nehádá, viz Eskalace v metodice):")
        for u in nezarazene:
            print(_fill(f"{u.id} {u.popis}", "    - "))
            if u.nedohledane:
                print(_fill("zmíněno, ale v repu se nedohledalo jednoznačně: "
                            + ", ".join(u.nedohledane), "      "))
        print()
    print(_fill("Návrh, ne rozhodnutí — projdi ho a oprav, teprve pak "
                "přepínej stavy na 'ready'.", "  "))


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Návrh řezu fronty úkolů na chipy (podle disjunktnosti souborů).")
    ap.add_argument("--todo", default=None, help="soubor s odrážkami '- [ ]' (default: TODO.md)")
    ap.add_argument("--json", dest="json_soubor", default=None,
                    help="alternativní vstup: seznam {id, popis, soubory}")
    ap.add_argument("--repo", default=None, help="kořen repa (default: kořen CHIPS)")
    ap.add_argument("--zapsat", nargs="?", const="", default=None,
                    metavar="ADRESAR", help="vygenerovat draft briefy do adresáře")
    ap.add_argument("--bez-dohledani", action="store_true",
                    help="nedohledávat holá jména souborů v repu")
    ap.add_argument("--max-ukolu", type=int, default=MAX_UKOLU)
    ap.add_argument("--max-souboru", type=int, default=MAX_SOUBORU)
    ap.add_argument("--datum", default=None, help="YYYY-MM-DD (default: dnes)")
    pridej_arg_dir(ap)
    args = ap.parse_args(argv)
    chips_dir = nastav_chips_dir(args.dir)

    repo = Path(args.repo).expanduser().resolve() if args.repo else ROOT
    dohledat = not args.bez_dohledani

    try:
        if args.json_soubor:
            ukoly = nacti_json(Path(args.json_soubor), repo, dohledat)
        else:
            todo = Path(args.todo) if args.todo else repo / "TODO.md"
            if not todo.is_file():
                print(f"  ! zdroj úkolů neexistuje: {todo}")
                return 0
            ukoly = nacti_todo(todo, repo, dohledat)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"  ! nečitelný vstup: {e}")
        return 0

    if not ukoly:
        print("  žádné otevřené úkoly — není co řezat")
        return 0

    skupiny, nezarazene = rozdel(ukoly)
    vypis(skupiny, nezarazene, max_ukolu=args.max_ukolu,
          max_souboru=args.max_souboru)

    if args.zapsat is not None:
        cil = Path(args.zapsat) if args.zapsat else chips_dir
        sablona = chips_dir / "TEMPLATE.md"
        if not sablona.is_file():
            sablona = ROOT / "chips" / "TEMPLATE.md"
        if not sablona.is_file():
            print(f"\n  ! chybí šablona {sablona} — briefy se nezapsaly")
            return 0
        zapsane = zapis(skupiny, cil, sablona, repo=repo.as_posix(),
                        datum=args.datum or dt.date.today().isoformat(),
                        max_ukolu=args.max_ukolu, max_souboru=args.max_souboru)
        print(f"\n  zapsáno {len(zapsane)} draft briefů do {cil}")
        for p in zapsane:
            print(f"    {p.name}")
        print("  dál: projdi je, doplň Ověření a stav přepni na 'ready';"
              "\n       kontrola: python tools/chip_lint.py")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    utf8_vystup()
    sys.exit(main())
