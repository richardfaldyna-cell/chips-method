"""Společné čtení chip briefů (bez externích závislostí).

Brief = `chips/NN-nazev.md` s YAML-like frontmatterem mezi `---` (plochý
`klic: hodnota`) a sekcemi `## <nadpis>`. Vlastní mini-parser místo PyYAML,
aby projekt neměl závislosti navíc.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHIPS_DIR = ROOT / "chips"

STAVY = ["draft", "ready", "running", "gated", "merged", "blocked"]

# Poznámka za cestou v sekci 'Dotčené soubory': `src/nove.py    # nový`.
# Odděluje se DVĚMA a více bílými znaky — jediná mezera před `#` je součást
# jména souboru (`docs/plan #1.md` se dřív tiše usekl na `docs/plan`; nález #4
# chipu 11). Šablona v TEMPLATE.md používá 4 mezery, takže je kompatibilní.
KOMENTAR = re.compile(r"\s{2,}#\s*(.*)$")
NOVY = re.compile(r"^(nov[ýy]|new)\b", re.I)

# Issues jako checkbox odrážky. `ISSUE` bere odškrtnuté i neodškrtnuté,
# `HOTOVA_ISSUE` jen odškrtnuté — obě mají stejný tvar, aby hotových nikdy
# nemohlo vyjít víc než celkových.
ISSUE = re.compile(r"^\s*-\s*\[[ xX]\]\s*(.+)$", re.M)
HOTOVA_ISSUE = re.compile(r"^\s*-\s*\[[xX]\]\s*(.+)$", re.M)

# `stav: ready` v prvním frontmatteru; hodnota bez okolní části řádku, aby
# případná poznámka za ní přežila přepis.
STAV_RADEK = re.compile(r"^(stav:[ \t]*)(\S+)", re.M)


def nastav_chips_dir(cesta: str | Path | None) -> Path:
    """Přepne adresář s chipy (`--dir` / env CHIPS_DIR).

    Chipy patří k projektu, kterého se týkají — u klientských zakázek se navíc
    nesmí míchat s tímhle generickým repem. Default zůstává `CHIPS/chips/`.
    """
    global CHIPS_DIR
    if cesta:
        CHIPS_DIR = Path(cesta).expanduser().resolve()
    return CHIPS_DIR


def pridej_arg_dir(ap) -> None:
    """Společný přepínač --dir pro CLI nástroje."""
    ap.add_argument("--dir", default=os.environ.get("CHIPS_DIR"),
                    help="adresář s chip briefy (default: CHIPS/chips/)")


@dataclass
class Chip:
    path: Path
    meta: dict[str, str] = field(default_factory=dict)
    sekce: dict[str, str] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.meta.get("chip", self.path.stem.split("-")[0])

    @property
    def stav(self) -> str:
        return self.meta.get("stav", "draft")

    @property
    def nazev(self) -> str:
        return self.meta.get("nazev", self.path.stem)

    def zavislosti(self) -> list[str]:
        """ID chipů, které musí být `merged` dřív (frontmatter `zavisi_na`)."""
        raw = self.meta.get("zavisi_na", "").strip()
        if not raw or raw in ("-", "[]", "nic"):
            return []
        return [x.strip().zfill(2) for x in raw.strip("[]").split(",") if x.strip()]

    def najdi(self, klic: str) -> str | None:
        """Text sekce podle normalizovaného prefixu.

        Nadpisy smí nést ozdoby (`## Dotčené soubory ⚠️ NÁROK`), proto se
        porovnává začátek klíče, ne přesná shoda.
        """
        for k, v in self.sekce.items():
            if k.startswith(klic):
                return v
        return None

    def soubory_detail(self) -> list[tuple[str, bool]]:
        """Nárokované cesty ze sekce 'Dotčené soubory' + příznak „teprve vznikne".

        Cesta smí nést poznámku za `#` oddělenou 2+ bílými znaky; `# nový`
        znamená, že soubor v repu ještě není a chip ho vytvoří (jinak by na
        něm padala kontrola existence). Jedna mezera + `#` poznámka NENÍ —
        jinak by se cesta `docs/plan #1.md` tiše usekla (nález #4, chip 11).
        """
        text = self.najdi("dotcene soubory") or ""
        out: list[tuple[str, bool]] = []
        for blok in re.findall(r"```[^\n]*\n(.*?)```", text, re.S):
            for radek in blok.splitlines():
                radek = radek.strip()
                if not radek or radek.startswith("#"):
                    continue
                m = KOMENTAR.search(radek)
                pozn = m.group(1).strip() if m else ""
                cesta = KOMENTAR.sub("", radek).strip().rstrip("/")
                if cesta:
                    out.append((cesta, bool(NOVY.match(pozn))))
        return out

    def soubory(self) -> list[str]:
        """Nárokované cesty bez poznámek — porovnává se jimi disjunktnost."""
        return [cesta for cesta, _ in self.soubory_detail()]

    def repo_path(self) -> Path | None:
        """Cesta k repu z frontmatteru; relativní se bere od adresáře s briefy."""
        raw = self.meta.get("repo", "").strip()
        if not raw:
            return None
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = self.path.parent / p
        return p.resolve()

    def issues(self) -> list[str]:
        text = self.najdi("issues") or ""
        return ISSUE.findall(text)

    def hotove_issues(self) -> list[str]:
        """Texty odškrtnutých issues (`- [x]`) — podmnožina `issues()`.

        `issues()` vrací text bez značky, takže z něj hotové poznat nejde a
        musí se počítat zvlášť ze syrové sekce. Vrací se seznam, ne číslo, aby
        šlo psát `len(hotove_issues())/len(issues())` i vypsat, co je hotové.
        """
        return HOTOVA_ISSUE.findall(self.najdi("issues") or "")


def _norm(s: str) -> str:
    """Nadpis → klíč bez diakritiky a interpunkce, pro robustní hledání sekcí."""
    prevod = str.maketrans("áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ", "acdeeinorstuuyzACDEEINORSTUUYZ")
    s = s.translate(prevod).lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def utf8_vystup() -> None:
    """Konzole na Windows jinak rozbije diakritiku ve výpisech."""
    for proud in (sys.stdout, sys.stderr):
        try:
            proud.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass


def parse(path: Path) -> Chip:
    text = path.read_text(encoding="utf-8")
    chip = Chip(path=path)

    if text.startswith("---"):
        konec = text.find("\n---", 3)
        if konec != -1:
            for radek in text[3:konec].splitlines():
                if ":" in radek and not radek.strip().startswith("#"):
                    k, _, v = radek.partition(":")
                    chip.meta[k.strip()] = v.split("#")[0].strip()
            text = text[konec + 4:]

    casti = re.split(r"^##\s+(.+)$", text, flags=re.M)
    for i in range(1, len(casti), 2):
        chip.sekce[_norm(casti[i])] = casti[i + 1]
    return chip


def prepis_stav(path: Path, novy: str = "running", ocekavany: str | None = "ready") -> bool:
    """Přepíše `stav:` ve frontmatteru; zbytek souboru zůstane bajt v bajt.

    Textově, ne přes parse+serializaci: parser výš je jednosměrný a přeuložením
    by se rozsypaly komentáře, pořadí klíčů i CRLF. Proto `read_bytes`/
    `write_bytes` a regex omezený na první frontmatter — kvůli diakritice a
    koncům řádků. `novy` je volitelný, protože orchestrátor přepíná i na jiné
    stavy než `running` (typicky `merged`). Vrací `False`, když se nemá co
    měnit (chybí frontmatter / `stav:` / jiná než očekávaná hodnota) — soubor
    se pak vůbec nezapisuje.
    """
    raw = path.read_bytes().decode("utf-8")
    if not raw.startswith("---"):
        return False
    konec = raw.find("\n---", 3)
    if konec == -1:
        return False
    m = STAV_RADEK.search(raw[:konec])
    if m is None or m.group(2) == novy:
        return False
    if ocekavany is not None and m.group(2) != ocekavany:
        return False
    path.write_bytes((raw[:m.start(2)] + novy + raw[m.end(2):]).encode("utf-8"))
    return True


def nacti_vse(vcetne_sablony: bool = False) -> list[Chip]:
    if not CHIPS_DIR.exists():
        return []
    soubory = sorted(CHIPS_DIR.glob("*.md"))
    if not vcetne_sablony:
        soubory = [p for p in soubory if p.stem != "TEMPLATE"]
    return [parse(p) for p in soubory]
