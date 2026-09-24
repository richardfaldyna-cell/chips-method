"""Spustí bránu chipu — příkazy ze sekce „Ověření (brána)" jeho briefu.

Brána není seznam zadrátovaný v nástroji: je to to, co si chip sám napsal do
briefu. Tenhle modul ji jen najde a spustí, takže stejný kód používá ruční
ověření i PreToolUse hook (`hook_chip_gate.py`).

Použití:
    python tools/chip_gate.py 05                  # brána chipu 05 v jeho worktree
    python tools/chip_gate.py 05 --repo C:/jinde  # vědomě jinde (výjimka)
    python tools/chip_gate.py 05 --dir C:/projekt/chips
    python tools/chip_gate.py --vetev ai/chip-05/oprava-brany     # nová konvence
    python tools/chip_gate.py --vetev chip/05-oprava-brany        # starý tvar

Bez `--repo` běží brána ve **worktree chipu** (`worktree:` z briefu), ne v tom,
co je v `repo:`. Do hlavního stromu se teprve merguje — práci chipu z definice
nemá, takže zelená odtamtud platí o starém kódu a o mergovaném stavu neříká nic.
Když worktree nejde určit, nástroj SELŽE; tichý fallback na hlavní strom je
přesně ta vada, kvůli které tenhle režim vznikl (viz `kde_spustit`).

Návratový kód 1 = brána neprošla (vhodné do hooku / CI).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from chip_common import ROOT, nacti_vse, nastav_chips_dir, pridej_arg_dir, utf8_vystup

# Z názvu větve poznáme, který brief platí. Rozpoznávají se DVA tvary:
#   `ai/chip-05/oprava-brany`  — dnešní konvence; prefix `ai/` říká už z názvu
#                                a z `git log`, že kód psal AI agent
#   `chip/05-oprava-brany`     — původní tvar; v repu jsou starší větve a musí
#                                dál fungovat (viz `hook_chip_gate.VETEV`)
# Jedna zachytávající skupina pro oba tvary — volající pak nemusí řešit, který
# padl. Nová alternativa je schválně první: `ai/chip-05/…` nesmí propadnout do
# starého vzoru a přinést číslo odjinud z řetězce.
VETEV_CHIP = re.compile(r"(?:\bai/chip-|\bchip/)(\d+)")


def id_z_vetve(vetev: str) -> str | None:
    """ID chipu z názvu větve, nebo None, když to není chip větev.

    Vrací dvojmístné ID, takže `ai/chip-5/x` i `chip/5-x` vyjdou jako `05` —
    brief se jmenuje `05-…md`, ne `5-…md`.
    """
    m = VETEV_CHIP.search(vetev)
    return m.group(1).zfill(2) if m else None


def prikazy(c) -> list[str]:
    """Příkazy brány z ``` bloku sekce „Ověření (brána)".

    Komentáře a prázdné řádky se ignorují. Když sekce žádný blok nemá, vrací
    prázdný seznam — a chip bez definované brány se nesmí mergovat automaticky.
    """
    text = c.najdi("overeni brana") or ""
    out: list[str] = []
    for blok in re.findall(r"```[^\n]*\n(.*?)```", text, re.S):
        for radek in blok.splitlines():
            radek = radek.strip()
            if radek and not radek.startswith("#"):
                out.append(radek)
    return out


def spust(repo: Path, prikaz: str, timeout: int = 600) -> tuple[int, str]:
    """Spustí jeden příkaz brány v kořeni repa; vrací (kód, výstup)."""
    try:
        p = subprocess.run(prikaz, cwd=str(repo), shell=True, timeout=timeout,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
    except subprocess.TimeoutExpired:
        return 124, f"timeout po {timeout}s"
    except OSError as e:                                  # pragma: no cover
        return 127, f"nelze spustit: {e}"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def brana(c, repo: Path) -> tuple[bool, list[str]]:
    """Spustí celou bránu chipu. Vrací (prošlo, řádky hlášení).

    Zastavuje se na prvním neúspěchu — další příkazy už stejně běží nad
    rozbitým stavem a jen by zdržovaly.
    """
    hlaseni: list[str] = []
    seznam = prikazy(c)
    if not seznam:
        return False, [f"{c.path.name}: sekce 'Ověření (brána)' nemá žádný příkaz "
                       f"— chip bez brány se nemerguje"]

    for prikaz in seznam:
        kod, vystup = spust(repo, prikaz)
        if kod == 0:
            hlaseni.append(f"  OK  {prikaz}")
            continue
        hlaseni.append(f"  X   {prikaz}   (exit {kod})")
        for radek in vystup.strip().splitlines()[-12:]:
            hlaseni.append(f"      {radek}")
        return False, hlaseni
    return True, hlaseni


def najdi_chip(cislo: str | None, vetev: str | None):
    """Chip podle čísla nebo podle názvu větve."""
    hledane = cislo.zfill(2) if cislo else (id_z_vetve(vetev or "") or "")
    if not hledane:
        return None
    for c in nacti_vse():
        if c.id == hledane:
            return c
    return None


class NeniKdeSpustit(Exception):
    """Bránu není kde spustit — nástroj selže, místo aby ověřil jiný strom.

    Schválně výjimka, ne `None` nebo návrat na `repo:`: fallback se dá
    přehlédnout při čtení i při úpravě, výjimka projde skrz a shodí návratový
    kód. Text je hláška PRO UŽIVATELE — vždy říká, co má udělat.
    """


def kde_spustit(chip, repo: Path | None) -> Path:
    """Worktree chipu — jediný strom, ve kterém má smysl bránu spouštět.

    Totéž pravidlo jako `hook_chip_gate.kde_overit()`, jen ve druhém nástroji:
    CLI a hook si nesmí protiřečit v tom, co je „ověřený stav chipu". Zapsané
    zvlášť, protože hláška musí radit podle kontextu (tady `--repo` a
    `chip_run.py`, v hooku merge); že se obě kopie nerozejdou v ROZHODNUTÍ,
    hlídá `test_brana_a_hook_resi_worktree_stejne`.

    Cesta se řeší jako v `chip_run.cesty()`: relativní zápis znamená „vedle
    repa" a bere se z něj jen jméno adresáře, aby výsledek nezávisel na tom,
    odkud se nástroj pustí. Absolutní cesta platí doslova, jak je v briefu —
    worktree pak smí ležet kdekoli, i mimo `repo.parent`, a `chip_run` ho tam
    (od chipu 24) i zakládá, takže brána měří strom, který skutečně vznikl.

    Vyhazuje `NeniKdeSpustit`, když `worktree:` chybí, na disku není, nebo
    ukazuje na týž strom jako `repo:`.
    """
    raw = (chip.meta.get("worktree") or "").strip()
    if not raw:
        raise NeniKdeSpustit(
            f"brief {chip.path.name} nemá vyplněné 'worktree:' — bránu není kde "
            f"spustit; hlavní strom práci chipu nemá, takže zelená odtamtud by "
            f"platila o starém kódu. Doplň cestu do briefu a worktree založ "
            f"(python tools/chip_run.py {chip.id}), nebo strom zadej vědomě: "
            f"--repo <cesta>.")

    wt = Path(raw).expanduser()
    if not wt.is_absolute():
        if repo is None:
            raise NeniKdeSpustit(
                f"brief {chip.path.name} má relativní 'worktree: {raw}', ale "
                f"nemá 'repo:' — relativní worktree leží vedle repa, takže bez "
                f"něj není podle čeho ho umístit. Doplň 'repo:' do briefu, nebo "
                f"zadej strom vědomě: --repo <cesta>.")
        wt = repo.parent / Path(raw).name

    if not wt.is_dir():
        raise NeniKdeSpustit(
            f"worktree chipu neexistuje ({wt}) — bránu není kde spustit. Obnov "
            f"ho: python tools/chip_run.py {chip.id}   (úklid `--uklid` patří AŽ "
            f"po mergi). Jiný strom si vynutíš vědomě: --repo <cesta>.")

    # Táž falešná zelená jako fallback výš, jen zapsaná v briefu: v `repo:` se
    # chip teprve merguje. Stejné pravidlo jako `hook_chip_gate.kde_overit()`.
    if repo is not None and wt.resolve() == repo.resolve():
        raise NeniKdeSpustit(
            f"'worktree:' v briefu ukazuje na týž strom jako 'repo:' ({repo}) — "
            f"brána by tam ověřila stav PŘED mergem, ne práci chipu. Oprav "
            f"'worktree:' na vlastní strom chipu a založ ho: "
            f"python tools/chip_run.py {chip.id}.")
    return wt


def kde_spustit_hlaska(chip, chyba: Exception) -> str:
    """Hláška k `NeniKdeSpustit` doplněná o stav chipu.

    U `merged` chipu je chybějící worktree normální stav, ne porucha: po mergi
    se uklízí. Brána se přesto NESMÍ tiše spustit v `repo:` — merge už proběhl,
    takže zelená by neplatila o chipu, ale o všem, co je v hlavní větvi.
    Uživatel si o strom musí říct sám (`--repo`); rozhodnutí viz Log chipu 19.
    """
    if chip.stav == "merged":
        return (f"{chyba}\n  Chip je ve stavu 'merged' — worktree se po mergi "
                f"uklízí, takže tohle je čekaný stav. Bránu nad hlavní větví "
                f"spusť vědomě: python tools/chip_gate.py {chip.id} --repo <repo>.")
    return str(chyba)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Spustí bránu chipu podle jeho briefu.")
    ap.add_argument("cislo", nargs="?", help="číslo chipu, např. 05")
    ap.add_argument("--vetev",
                    help="název větve (ai/chip-NN/... i starý chip/NN-...) místo čísla")
    ap.add_argument("--repo", metavar="CESTA",
                    help="strom, kde bránu spustit — VĚDOMÁ VÝJIMKA; default je "
                         "worktree chipu z briefu, protože v repu práce chipu "
                         "ještě není")
    pridej_arg_dir(ap)
    args = ap.parse_args(argv)
    nastav_chips_dir(args.dir)

    chip = najdi_chip(args.cislo, args.vetev)
    if chip is None:
        print("! chip nenalezen (zadej číslo nebo --vetev ai/chip-NN/... "
              "případně starý chip/NN-...)")
        return 1

    repo = chip.repo_path()
    if args.repo:
        strom = Path(args.repo).expanduser().resolve()
        if not strom.is_dir():
            print(f"! strom '{strom}' z --repo neexistuje")
            return 1
        # Hlavička musí říct, ČÍM strom je — jinak z cesty nejde poznat, že
        # brána běží tam, kam se teprve merguje (přesně ta falešná zelená).
        odkud = ("--repo (POZOR: hlavní strom z briefu — práce chipu v něm "
                 "ještě není)" if repo is not None and strom == repo
                 else "--repo (vědomá výjimka)")
    else:
        try:
            strom = kde_spustit(chip, repo)
        except NeniKdeSpustit as e:
            print(f"! bránu chipu {chip.id} není kde spustit — nic se nespustilo.")
            print(f"  {kde_spustit_hlaska(chip, e)}")
            return 1
        odkud = "worktree chipu z briefu"

    print(f"  BRÁNA chip {chip.id} — {chip.nazev}")
    print(f"  strom: {strom}   [{odkud}]")
    ok, hlaseni = brana(chip, strom)
    for radek in hlaseni:
        print(radek)
    print("\n  ZELENÁ — smí se mergovat" if ok else
          "\n  ČERVENÁ — nemerguj; stav 'blocked' a popiš proč v Logu")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "tools"))
    utf8_vystup()
    sys.exit(main())
