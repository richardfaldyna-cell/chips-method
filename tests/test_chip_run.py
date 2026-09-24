"""Testy pro tools/chip_run.py.

Skutečné `claude` nespouští žádný test — `shutil.which` je vždy mockované.
Skutečný git se spouští na jediném místě: `TestUklidMetadat` potřebuje
`.git/worktrees/<jméno>` tak, jak ho vyrobí git sám, a předstíraný adresář by
tam netestoval nic. Všude jinde se repo jen předstírá (kód kouká na existenci
`.git`) a `subprocess.call` je mockovaný.
"""

from __future__ import annotations

import io
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import chip_common  # noqa: E402
import chip_run  # noqa: E402

BRIEF = """\
---
chip: 07
nazev: pokusny
stav: {stav}
zavisi_na:
{repo}vetev: chip/07-pokusny
worktree: ../repo-chip-07
---

# CHIP 07 — pokusný chip s diakritikou (ěščřžýáíé)

## Issues

- [ ] #1 — první
- [ ] #2 — druhá

## Dotčené soubory

```
tools/neco.py
```

## Definition of done

- [ ] hotovo

## Ověření (brána)

```bash
echo ok
```

## Log

| Datum | Stav | Poznámka |
|---|---|---|
"""


class ZakladChipu(unittest.TestCase):
    """Dočasné repo + jeden brief; CHIPS_DIR se v tearDown vrací zpátky.

    `CHIPS_V_REPU` přepíná mezi dvěma reálnými rozloženími: briefy vedle repa
    (režim `--dir`, cizí repo bez stopy CHIPS) a briefy uvnitř repa (výchozí
    případ). Rozdíl je podstatný pro `brief_ke_stavu()` — jen ve druhém případě
    má brief ve worktree vlastní kopii.
    """

    CHIPS_V_REPU = False

    def setUp(self) -> None:
        self._puvodni_dir = chip_common.CHIPS_DIR
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        (self.repo / ".git").mkdir(parents=True)
        self.chips = (self.repo / "chips") if self.CHIPS_V_REPU else (self.base / "chips")
        self.chips.mkdir()
        self.brief = self.chips / "07-pokusny.md"
        self.napis_brief()
        chip_common.nastav_chips_dir(self.chips)

    def tearDown(self) -> None:
        chip_common.nastav_chips_dir(self._puvodni_dir)
        self._tmp.cleanup()

    def napis_brief(self, stav: str = "ready", repo: bool = True) -> None:
        """Zapíše brief s CRLF a diakritikou (kvůli testu bajtové shody)."""
        text = BRIEF.format(stav=stav,
                            repo=f"repo: {self.repo.as_posix()}\n" if repo else "")
        self.brief.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))

    def chip(self):
        return [c for c in chip_common.nacti_vse() if c.id == "07"][0]

    def spust(self, *argv: str) -> tuple[int, str]:
        """main() s odchyceným stdout — testy nemají plivat do výstupu."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = chip_run.main(list(argv))
        return rc, buf.getvalue()


class TestCesty(ZakladChipu):
    def s_worktree(self, hodnota: str):
        """Brief s přepsanou hodnotou `worktree:` (jinak beze změny)."""
        text = self.brief.read_bytes().decode("utf-8")
        text = text.replace("worktree: ../repo-chip-07", f"worktree: {hodnota}")
        self.brief.write_bytes(text.encode("utf-8"))
        return self.chip()

    def test_vraci_repo_vetev_worktree(self) -> None:
        repo, vetev, worktree = chip_run.cesty(self.chip())
        self.assertEqual(repo, self.repo.resolve())
        self.assertEqual(vetev, "chip/07-pokusny")
        self.assertEqual(worktree, self.repo.resolve().parent / "repo-chip-07")

    def test_worktree_lezi_vedle_repa(self) -> None:
        """Z `worktree:` se bere jen jméno — cesta v briefu je relativní k repu."""
        _, _, worktree = chip_run.cesty(self.chip())
        self.assertEqual(worktree.name, "repo-chip-07")
        self.assertEqual(worktree.parent, self.repo.resolve().parent)

    def test_vyplnena_vetev_ma_prednost(self) -> None:
        """Starší brief má `vetev:` v původním tvaru — nesmí se přepsat."""
        _, vetev, _ = chip_run.cesty(self.chip())
        self.assertEqual(vetev, "chip/07-pokusny")

    def test_default_vetve_a_worktree(self) -> None:
        """Bez `vetev:` se odvodí nová konvence `ai/chip-NN/nazev`."""
        text = self.brief.read_bytes().decode("utf-8")
        text = "".join(r for r in text.splitlines(keepends=True)
                       if not r.startswith(("vetev:", "worktree:")))
        self.brief.write_bytes(text.encode("utf-8"))
        _, vetev, worktree = chip_run.cesty(self.chip())
        self.assertEqual(vetev, "ai/chip-07/pokusny")
        self.assertEqual(worktree.name, "repo-chip-07")

    def test_prazdna_vetev_se_odvodi(self) -> None:
        """`vetev:` bez hodnoty znamená „odvoď to", ne větev jménem prázdno."""
        text = self.brief.read_bytes().decode("utf-8")
        text = text.replace("vetev: chip/07-pokusny", "vetev:   ")
        self.brief.write_bytes(text.encode("utf-8"))
        _, vetev, _ = chip_run.cesty(self.chip())
        self.assertEqual(vetev, "ai/chip-07/pokusny")

    def test_odvozenou_vetev_pozna_brana_i_hook(self) -> None:
        """Nová konvence musí projít překladem zpět na ID — jinak hook ztichne."""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import chip_gate                                              # noqa: PLC0415
        import hook_chip_gate                                         # noqa: PLC0415
        vetev = chip_run.vychozi_vetev(self.chip())
        self.assertEqual(chip_gate.id_z_vetve(vetev), "07")
        self.assertEqual(hook_chip_gate.VETEV.search(vetev).group(1).zfill(2), "07")

    def test_absolutni_worktree_plati_jak_je(self) -> None:
        """Srovnáno chipem 24: absolutní zápis se nekrájí na jméno adresáře.

        Absolutní cesta na `cwd` nezávisí, takže `.name` u ní nic nechrání —
        jen by zahodil, co brief říká. Dřív tu worktree vznikal vedle repa,
        jinde, než kam se dívá brána (`chip_gate.kde_spustit()`).
        """
        jinde = self.base / "hloub" / "x-chip-07"
        _, _, worktree = chip_run.cesty(self.s_worktree(jinde.as_posix()))
        self.assertEqual(worktree, jinde)

    def test_absolutni_worktree_plati_i_bez_repa(self) -> None:
        """Absolutní cestu není podle čeho umisťovat — `repo:` u ní nehraje."""
        self.napis_brief(repo=False)
        jinde = self.base / "hloub" / "x-chip-07"
        repo, _, worktree = chip_run.cesty(self.s_worktree(jinde.as_posix()))
        self.assertIsNone(repo)
        self.assertEqual(worktree, jinde)

    def test_relativni_hluboka_cesta_da_porad_jen_jmeno(self) -> None:
        """Regrese k chipu 24: relativní větev se opravou absolutní nemění.

        Porovnává se CELÁ cesta, ne jen jméno — kdyby se `.name` u relativního
        zápisu ztratil, vyšlo by `repo.parent / "../nekde/…"` a assert spadne.
        """
        _, _, worktree = chip_run.cesty(self.s_worktree("../nekde/hloub/x-chip-07"))
        self.assertEqual(worktree, self.repo.resolve().parent / "x-chip-07")

    def test_relativni_bez_repa_zustane_holym_jmenem(self) -> None:
        """Bez `repo:` není relativní cestu k čemu vztáhnout — dnešní chování."""
        self.napis_brief(repo=False)
        _, _, worktree = chip_run.cesty(self.s_worktree("../nekde/hloub/x-chip-07"))
        self.assertEqual(worktree, Path("x-chip-07"))

    def test_bez_repa_vraci_none(self) -> None:
        self.napis_brief(repo=False)
        repo, vetev, worktree = chip_run.cesty(self.chip())
        self.assertIsNone(repo)
        self.assertEqual(vetev, "chip/07-pokusny")
        self.assertEqual(worktree.name, "repo-chip-07")

    def test_nema_vedlejsi_efekty(self) -> None:
        """Funguje i bez existujícího repa a nespustí žádný proces."""
        self.napis_brief()
        chip = self.chip()
        chip.meta["repo"] = str(self.base / "neexistuje")
        with mock.patch.object(subprocess, "call") as volani:
            repo, _, worktree = chip_run.cesty(chip)
        volani.assert_not_called()
        self.assertFalse(repo.exists())
        self.assertFalse(worktree.exists())


class TestZadani(ZakladChipu):
    def test_obsahuje_klicove_udaje(self) -> None:
        chip = self.chip()
        _, vetev, worktree = chip_run.cesty(chip)
        with mock.patch.object(subprocess, "call") as volani:
            text = chip_run.zadani(chip, worktree, vetev)
        volani.assert_not_called()
        self.assertIn("CHIP 07 — pokusny", text)
        self.assertIn(str(worktree), text)
        self.assertIn(vetev, text)
        self.assertIn(str(self.brief.resolve()), text)

    def test_nezustal_nevyplneny_placeholder(self) -> None:
        chip = self.chip()
        _, vetev, worktree = chip_run.cesty(chip)
        text = chip_run.zadani(chip, worktree, vetev)
        self.assertNotIn("{", text)
        self.assertIn("Eskalace (T3)", text)


class TestPrepisStavu(ZakladChipu):
    """Jen napojení na sdílenou funkci — její vlastní testy jsou v `test_chip_common.py`."""

    def test_pouziva_sdilenou_funkci(self) -> None:
        """Žádná lokální kopie: `chip_run` musí volat `chip_common.prepis_stav`."""
        self.assertIs(chip_run.prepis_stav, chip_common.prepis_stav)

    def test_prepis_pres_stav_prepne_ready_na_running(self) -> None:
        pred = self.brief.read_bytes()
        with mock.patch.object(subprocess, "call", return_value=0):
            rc, _ = self.spust("07", "--stav")
        self.assertEqual(rc, 0)
        po = self.brief.read_bytes()
        self.assertEqual(po, pred.replace(b"stav: ready", b"stav: running", 1))
        self.assertEqual(po.count(b"\r\n"), pred.count(b"\r\n"))
        self.assertIn("ěščřžýáíé".encode("utf-8"), po)

    def test_neuspesny_prepis_hlasi_a_nemeni_soubor(self) -> None:
        """Když `stav:` nejde přepsat, nástroj to ohlásí a jede dál (kód 0)."""
        pred = self.brief.read_bytes()
        with mock.patch.object(subprocess, "call", return_value=0), \
                mock.patch.object(chip_run, "prepis_stav", return_value=False):
            rc, out = self.spust("07", "--stav")
        self.assertEqual(rc, 0)
        self.assertIn("nepodařilo přepsat", out)
        self.assertEqual(self.brief.read_bytes(), pred)


class TestDryRun(ZakladChipu):
    def test_nespousti_git_ani_nezaklada_worktree(self) -> None:
        with mock.patch.object(subprocess, "call") as volani:
            rc, out = self.spust("07", "--dry-run")
        self.assertEqual(rc, 0)
        volani.assert_not_called()
        self.assertIn("worktree add", out)
        self.assertFalse((self.base / "repo-chip-07").exists())

    def test_se_stavem_nesahne_na_brief(self) -> None:
        pred = self.brief.read_bytes()
        with mock.patch.object(subprocess, "call") as volani:
            rc, out = self.spust("07", "--dry-run", "--stav")
        self.assertEqual(rc, 0)
        volani.assert_not_called()
        self.assertEqual(self.brief.read_bytes(), pred)
        self.assertIn("dry-run", out)

    def test_se_spustenim_nehleda_ani_nespousti_claude(self) -> None:
        with mock.patch("shutil.which") as which, \
                mock.patch.object(subprocess, "call") as volani:
            rc, out = self.spust("07", "--dry-run", "--spustit")
        self.assertEqual(rc, 0)
        which.assert_not_called()
        volani.assert_not_called()
        self.assertIn("claude", out)

    def test_prochazi_i_kdyz_stav_neni_ready(self) -> None:
        """Dry-run je náhled, ne brána — chová se jako dosud."""
        self.napis_brief(stav="draft")
        with mock.patch.object(subprocess, "call") as volani:
            rc, _ = self.spust("07", "--dry-run")
        self.assertEqual(rc, 0)
        volani.assert_not_called()


class TestZalozeni(ZakladChipu):
    def test_vola_git_worktree_add(self) -> None:
        with mock.patch.object(subprocess, "call", return_value=0) as volani:
            rc, out = self.spust("07")
        self.assertEqual(rc, 0)
        cmd = volani.call_args[0][0]
        self.assertEqual(cmd[:2], ["git", "-C"])
        self.assertIn("worktree", cmd)
        self.assertIn("add", cmd)
        self.assertIn("chip/07-pokusny", cmd)
        self.assertIn("ZADÁNÍ PRO NOVÉ OKNO", out)

    def test_selhani_gitu_konci_jednickou(self) -> None:
        with mock.patch.object(subprocess, "call", return_value=128):
            rc, out = self.spust("07")
        self.assertEqual(rc, 1)
        self.assertIn("git worktree add selhal", out)

    def test_stav_se_prepise_az_po_zalozeni(self) -> None:
        with mock.patch.object(subprocess, "call", return_value=0):
            rc, out = self.spust("07", "--stav")
        self.assertEqual(rc, 0)
        self.assertEqual(self.chip().stav, "running")
        self.assertIn("running", out)

    def test_stav_se_neprepise_kdyz_git_selze(self) -> None:
        with mock.patch.object(subprocess, "call", return_value=1):
            rc, _ = self.spust("07", "--stav")
        self.assertEqual(rc, 1)
        self.assertEqual(self.chip().stav, "ready")


class TestBriefKeStavu(ZakladChipu):
    """Do které kopie briefu smí `--stav` psát (nález: konflikt při mergi)."""

    def test_briefy_mimo_repo_zustavaji_v_originalu(self) -> None:
        """Režim `--dir`: kopie ve worktree neexistuje, psát do originálu smí."""
        chip = self.chip()
        repo, _, worktree = chip_run.cesty(chip)
        self.assertEqual(chip_run.brief_ke_stavu(chip, repo, worktree), chip.path)

    def test_bez_repa_zustava_original(self) -> None:
        self.napis_brief(repo=False)
        chip = self.chip()
        self.assertEqual(chip_run.brief_ke_stavu(chip, None, self.base / "wt"),
                         chip.path)


class TestBriefVRepu(ZakladChipu):
    """Výchozí rozložení: briefy jsou verzované v repu, worktree má kopii."""

    CHIPS_V_REPU = True

    def kopie_ve_worktree(self) -> Path:
        """Vyrobí worktree s kopií briefu — to, co udělá `git worktree add`."""
        _, _, worktree = chip_run.cesty(self.chip())
        cil = worktree / "chips" / self.brief.name
        cil.parent.mkdir(parents=True, exist_ok=True)
        cil.write_bytes(self.brief.read_bytes())
        return cil

    def test_vraci_kopii_ve_worktree(self) -> None:
        kopie = self.kopie_ve_worktree()
        chip = self.chip()
        repo, _, worktree = chip_run.cesty(chip)
        self.assertEqual(chip_run.brief_ke_stavu(chip, repo, worktree), kopie)

    def test_bez_kopie_padne_zpet_na_original(self) -> None:
        """Netrackovaný brief se do worktree nedostane — merge se ho netýká."""
        chip = self.chip()
        repo, _, worktree = chip_run.cesty(chip)
        self.assertEqual(chip_run.brief_ke_stavu(chip, repo, worktree), chip.path)

    def test_stav_se_zapise_do_worktree_a_hlavni_strom_zustane_nedotcen(self) -> None:
        """Jádro nálezu: hlavní strom musí zůstat bajt v bajt stejný.

        Zápis do hlavního stromu tam nechal necommitnutou změnu souboru, který
        merge přepisuje — `git merge` takový merge odmítne.
        """
        pred = self.brief.read_bytes()

        # Kopii vyrábí až mock `worktree add` — kdyby existovala předem, main()
        # by skončil na „worktree už existuje" a nic by netestoval.
        def falesny_worktree_add(cmd, **_):
            self.kopie_ve_worktree()
            return 0

        with mock.patch.object(subprocess, "call", side_effect=falesny_worktree_add):
            rc, out = self.spust("07", "--stav")
        self.assertEqual(rc, 0)
        self.assertEqual(self.brief.read_bytes(), pred, "hlavní strom se nesmí měnit")
        kopie = chip_run.cesty(self.chip())[2] / "chips" / self.brief.name
        self.assertEqual(kopie.read_bytes(),
                         pred.replace(b"stav: ready", b"stav: running", 1))
        self.assertIn("ve worktree chipu", out)


class TestUklid(ZakladChipu):
    """`--uklid` patří až po mergi — a musí doopravdy uklidit."""

    def setUp(self) -> None:
        super().setUp()
        _, self.vetev, self.worktree = chip_run.cesty(self.chip())
        self.worktree.mkdir()
        (self.worktree / "soubor.txt").write_text("x", encoding="utf-8")

    def spust_uklid(self, *argv: str, zmergovana: bool | None = True):
        """`--uklid` s podstrčenou odpovědí na „je větev zmergovaná?"."""
        with mock.patch.object(chip_run, "je_zmergovana", return_value=zmergovana), \
                mock.patch.object(subprocess, "call", return_value=0) as volani:
            rc, out = self.spust("07", "--uklid", *argv)
        return rc, out, volani

    def test_nezmergovana_vetev_se_neuklidi(self) -> None:
        rc, out, volani = self.spust_uklid(zmergovana=False)
        self.assertEqual(rc, 1)
        volani.assert_not_called()
        self.assertTrue(self.worktree.exists(), "worktree se nesmí sáhnout")
        self.assertIn("není zmergovaná", out)
        self.assertIn("--presto", out)

    def test_presto_uklidi_i_nezmergovanou(self) -> None:
        rc, out, volani = self.spust_uklid("--presto", zmergovana=False)
        self.assertEqual(rc, 0)
        self.assertIn("remove", volani.call_args_list[0][0][0])
        self.assertIn("--presto", out)

    def test_zmergovana_vetev_se_uklidi(self) -> None:
        rc, _, volani = self.spust_uklid()
        self.assertEqual(rc, 0)
        cmd = volani.call_args_list[0][0][0]
        self.assertIn("worktree", cmd)
        self.assertIn("remove", cmd)

    def test_neexistujici_vetev_uklid_nezastavi(self) -> None:
        """Po ručním smazání větve není co ztratit — adresář ať zmizí taky."""
        rc, out, volani = self.spust_uklid(zmergovana=None)
        self.assertEqual(rc, 0)
        self.assertIn("neexistuje", out)
        self.assertIn("remove", volani.call_args_list[0][0][0])

    def test_selhani_gitu_vede_na_rucni_smazani(self) -> None:
        """Nález: `git worktree remove` na Windows padá na Permission denied."""
        with mock.patch.object(chip_run, "je_zmergovana", return_value=True), \
                mock.patch.object(subprocess, "call", return_value=1) as volani:
            rc, out = self.spust("07", "--uklid")
        self.assertEqual(rc, 0)
        self.assertFalse(self.worktree.exists(), "adresář musí zmizet i tak")
        self.assertIn("--force", " ".join(volani.call_args_list[1][0][0]))
        self.assertIn("prune", volani.call_args_list[-1][0][0])
        self.assertIn("mažu ručně", out)

    def test_git_vrati_nulu_ale_adresar_zustane(self) -> None:
        """Ignorované soubory (`__pycache__`) `remove` nemaže — dořeší je rmtree."""
        with mock.patch.object(chip_run, "je_zmergovana", return_value=True), \
                mock.patch.object(subprocess, "call", return_value=0):
            rc, out = self.spust("07", "--uklid")
        self.assertEqual(rc, 0)
        self.assertFalse(self.worktree.exists())
        self.assertIn("mažu ručně", out)

    def test_nesmazatelny_adresar_konci_jednickou(self) -> None:
        """Tichý úspěch nad zbylým adresářem je horší než hlášená chyba."""
        with mock.patch.object(chip_run, "je_zmergovana", return_value=True), \
                mock.patch.object(subprocess, "call", return_value=1), \
                mock.patch.object(chip_run, "smaz_strom", return_value="zamčeno"):
            rc, out = self.spust("07", "--uklid")
        self.assertEqual(rc, 1)
        self.assertTrue(self.worktree.exists())
        self.assertIn("nepodařilo smazat", out)

    def test_chybejici_worktree_jen_prune(self) -> None:
        shutil.rmtree(self.worktree)
        rc, out, volani = self.spust_uklid()
        self.assertEqual(rc, 0)
        self.assertEqual(len(volani.call_args_list), 1)
        self.assertIn("prune", volani.call_args_list[0][0][0])
        self.assertIn("na disku není", out)

    def test_dry_run_nesahne_na_nic(self) -> None:
        with mock.patch.object(chip_run, "je_zmergovana") as dotaz, \
                mock.patch.object(subprocess, "call") as volani:
            rc, out = self.spust("07", "--uklid", "--dry-run")
        self.assertEqual(rc, 0)
        dotaz.assert_not_called()
        volani.assert_not_called()
        self.assertTrue(self.worktree.exists())
        self.assertIn("dry-run", out)


class TestMetadataPatriWorktree(unittest.TestCase):
    """Skalpel před mazáním: je `.git/worktrees/<jméno>` opravdu naše?"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.meta = self.base / "meta"
        self.meta.mkdir()
        self.worktree = self.base / "wt"
        self.addCleanup(self._tmp.cleanup)

    def zapis_gitdir(self, cil: Path | str) -> None:
        (self.meta / "gitdir").write_text(f"{cil}\n", encoding="utf-8")

    def test_chybejici_gitdir_je_smeti_po_prune(self) -> None:
        """Přesně stav, který `prune` hlásí jako „gitdir file does not exist"."""
        self.assertTrue(chip_run.metadata_patri_worktree(self.meta, self.worktree))

    def test_gitdir_na_nas_worktree(self) -> None:
        self.zapis_gitdir(self.worktree / ".git")
        self.assertTrue(chip_run.metadata_patri_worktree(self.meta, self.worktree))

    def test_gitdir_jinam_znamena_cizi_worktree(self) -> None:
        """Git při kolizi jmen připojuje příponu — adresář může být cizí."""
        self.zapis_gitdir(self.base / "jiny-wt" / ".git")
        self.assertFalse(chip_run.metadata_patri_worktree(self.meta, self.worktree))

    def test_prazdny_gitdir_nestaci(self) -> None:
        self.zapis_gitdir("")
        self.assertFalse(chip_run.metadata_patri_worktree(self.meta, self.worktree))


class TestUklidMetadat(ZakladChipu):
    """`--uklid` ručí i za metadata, ne jen za pracovní adresář.

    Jediná třída v tomhle souboru, která pouští skutečný git: obsah
    `.git/worktrees/<jméno>` (`gitdir`, `commondir`, `logs/`, `refs/`) vyrábí
    git a právě na něm celá oprava stojí.

    `git worktree lock` je tu jen páka, jak přimět `prune`, aby adresář mlčky
    nechal být — na Windows to v praxi dělá `Permission denied` po
    `gitdir file does not exist`. Obě cesty končí stejně: **rc 0 a adresář
    pořád na disku**, a to je stav, který `uklid()` musí uvidět.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("git") is None:                       # pragma: no cover
            raise unittest.SkipTest("git není na PATH")

    def setUp(self) -> None:
        super().setUp()
        _, self.vetev, self.worktree = chip_run.cesty(self.chip())
        self.git("init", "-q")
        self.git("-c", "user.name=t", "-c", "user.email=t@t",
                 "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty",
                 "-m", "zaklad")
        self.git("worktree", "add", "-q", str(self.worktree), "-b", self.vetev)
        self.meta = chip_run.cesta_metadat(self.repo, self.worktree)
        self.assertTrue(self.meta and self.meta.is_dir(), "fixture: metadata chybí")

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                       capture_output=True)

    def test_cesta_metadat_plati_i_kdyz_je_repo_samo_worktree(self) -> None:
        """Proto se cesta bere přes `--git-path`, ne skládáním `repo / '.git'`.

        V linkovaném worktree je `.git` **soubor**; `--git-path worktrees/…`
        míří do společného adresáře repa, takže odpoví stejně z obou stran.
        """
        self.assertTrue((self.worktree / ".git").is_file())
        self.assertEqual(chip_run.cesta_metadat(self.worktree, self.worktree),
                         self.meta)

    def test_prune_nechal_metadata_uklid_je_dorazi(self) -> None:
        """Jádro chipu: strom smazaný ručně, `prune` rc 0, adresář zůstal."""
        (self.meta / "HUSK").write_text("zbytek po nedokončeném prune",
                                        encoding="utf-8")
        self.git("worktree", "lock", str(self.worktree))
        shutil.rmtree(self.worktree)

        rc, out = self.spust("07", "--uklid")

        self.assertEqual(rc, 0, out)
        self.assertIn("na disku není", out)
        self.assertIn("prune nechal metadata", out)
        self.assertFalse(self.meta.exists(), "metadata musí zmizet i tak")

    def test_metadata_se_dorazi_i_po_rucnim_smazani_stromu(self) -> None:
        """Druhá cesta k `prune`: `worktree remove` selhal, mazalo se ručně."""
        self.git("worktree", "lock", str(self.worktree))

        rc, out = self.spust("07", "--uklid")

        self.assertEqual(rc, 0, out)
        self.assertIn("mažu ručně", out)
        self.assertFalse(self.worktree.exists())
        self.assertFalse(self.meta.exists())

    def test_uspesny_remove_metadata_neresi(self) -> None:
        """Regrese: když `remove` uklidí obojí sám, nic se nedomazává."""
        with mock.patch.object(chip_run, "smaz_strom") as maz:
            rc, out = self.spust("07", "--uklid")

        self.assertEqual(rc, 0, out)
        maz.assert_not_called()
        self.assertNotIn("mažu ručně", out)
        self.assertFalse(self.worktree.exists())
        self.assertFalse(self.meta.exists())

    def test_nesmazatelna_metadata_konci_jednickou(self) -> None:
        """Tichá nula nad zbylým adresářem je přesně ta chyba, co se opravuje."""
        self.git("worktree", "lock", str(self.worktree))
        shutil.rmtree(self.worktree)
        with mock.patch.object(chip_run, "smaz_strom", return_value="zamčeno"):
            rc, out = self.spust("07", "--uklid")

        self.assertEqual(rc, 1)
        self.assertTrue(self.meta.exists())
        self.assertIn(self.meta.name, out)
        self.assertIn("zamčeno", out)

    def test_cizi_metadata_stejneho_jmena_zustanou(self) -> None:
        """Mazání je chirurgické: na cizí adresář se nesahá, ani když sedí jméno."""
        self.git("worktree", "lock", str(self.worktree))
        (self.meta / "gitdir").write_text(
            f"{(self.base / 'jiny-wt' / '.git').as_posix()}\n", encoding="utf-8")
        shutil.rmtree(self.worktree)

        rc, out = self.spust("07", "--uklid")

        self.assertEqual(rc, 0, out)
        self.assertTrue(self.meta.exists())
        self.assertIn("patří jinému worktree", out)

    def test_neznama_cesta_k_metadatum_uklid_nezastavi(self) -> None:
        """Když se git na cestu nedá zeptat, hlásí se to — ale strom je pryč."""
        with mock.patch.object(chip_run, "cesta_metadat", return_value=None):
            rc, out = self.spust("07", "--uklid")

        self.assertEqual(rc, 0, out)
        self.assertIn("nezjistil jsem", out)
        self.assertFalse(self.worktree.exists())


class TestSmazStrom(unittest.TestCase):
    """Read-only soubory jsou přesně to, na čem `git worktree remove` padá."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.strom = Path(self._tmp.name) / "wt"
        (self.strom / "vnorene").mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)

    def test_smaze_i_read_only_soubory(self) -> None:
        soubor = self.strom / "vnorene" / "objekt"
        soubor.write_text("x", encoding="utf-8")
        soubor.chmod(stat.S_IREAD)
        self.assertIsNone(chip_run.smaz_strom(self.strom))
        self.assertFalse(self.strom.exists())

    def test_neexistujici_strom_hlasi_chybu(self) -> None:
        chyba = chip_run.smaz_strom(self.strom / "neni")
        self.assertIsInstance(chyba, str)
        self.assertTrue(chyba)

    def test_handler_odpovida_verzi_pythonu(self) -> None:
        """`onexc` je až od 3.12 — na 3.11 by `rmtree` spadl na TypeError."""
        with mock.patch.object(chip_run.shutil, "rmtree") as rmtree:
            self.assertIsNone(chip_run.smaz_strom(self.strom))
        ocekavany = "onexc" if sys.version_info >= (3, 12) else "onerror"
        self.assertEqual(set(rmtree.call_args.kwargs), {ocekavany})
        self.assertIs(rmtree.call_args.kwargs[ocekavany], chip_run._povol_zapis)


class TestSpustit(ZakladChipu):
    def test_chybejici_claude_konci_jednickou(self) -> None:
        with mock.patch("shutil.which", return_value=None), \
                mock.patch.object(subprocess, "call") as volani:
            rc, out = self.spust("07", "--spustit")
        self.assertEqual(rc, 1)
        volani.assert_not_called()          # ani git worktree add
        self.assertIn("není na PATH", out)
        self.assertNotIn("Traceback", out)

    def test_spusti_claude_se_zadanim_ve_worktree(self) -> None:
        exe = "C:/fake/claude.exe"
        with mock.patch("shutil.which", return_value=exe), \
                mock.patch.object(subprocess, "call", return_value=0) as volani:
            rc, _ = self.spust("07", "--spustit")
        self.assertEqual(rc, 0)
        argv, kwargs = volani.call_args_list[-1]
        self.assertEqual(argv[0][0], exe)
        self.assertIn("CHIP 07", argv[0][1])
        self.assertEqual(kwargs["cwd"], str(self.repo.resolve().parent / "repo-chip-07"))

    def test_exe_dostane_cele_viceradkove_zadani(self) -> None:
        """Nativní .exe dostává zadání jako jeden argv element — vcelku,
        včetně newline a posledního řádku."""
        exe = "C:/fake/claude.exe"
        with mock.patch("shutil.which", return_value=exe), \
                mock.patch.object(subprocess, "call", return_value=0) as volani:
            rc, _ = self.spust("07", "--spustit")
        self.assertEqual(rc, 0)
        chip = self.chip()
        _, vetev, worktree = chip_run.cesty(chip)
        text = volani.call_args_list[-1][0][0][1]
        self.assertEqual(text, chip_run.zadani(chip, worktree, vetev))
        self.assertIn("\n", text)
        self.assertIn("Průběžně aktualizuj", text)      # poslední řádek dorazil

    def test_cmd_shim_se_odmitne_a_claude_se_nespusti(self) -> None:
        """cmd.exe usekne víceřádkový argv na prvním newline — u .cmd shimu
        se --spustit odmítá s hláškou a zadání se vypíše k ručnímu vložení
        (dnešní chování bez --spustit). Worktree se založí normálně."""
        exe = "C:/fake/claude.cmd"
        with mock.patch("shutil.which", return_value=exe), \
                mock.patch.object(subprocess, "call", return_value=0) as volani:
            rc, out = self.spust("07", "--spustit")
        self.assertEqual(rc, 0)
        for argv, _ in [c for c in volani.call_args_list]:
            self.assertEqual(argv[0][0], "git",
                             f"kromě gitu se nesmí spustit nic: {argv[0]}")
        self.assertIn(".cmd/.bat shim", out)
        self.assertIn("usekne", out)
        self.assertIn("vlož do okna ručně", out)
        self.assertIn("ZADÁNÍ PRO NOVÉ OKNO", out)      # fallback: ruční vložení

    def test_bat_shim_se_odmitne_i_s_velkymi_pismeny(self) -> None:
        with mock.patch("shutil.which", return_value="C:/fake/CLAUDE.BAT"), \
                mock.patch.object(subprocess, "call", return_value=0) as volani:
            rc, out = self.spust("07", "--spustit")
        self.assertEqual(rc, 0)
        self.assertTrue(all(c[0][0][0] == "git" for c in volani.call_args_list))
        self.assertIn(".cmd/.bat shim", out)

    def test_je_cmd_shim_pozna_jen_cmd_a_bat(self) -> None:
        for exe, shim in [("C:/x/claude.cmd", True), ("C:/x/claude.BAT", True),
                          ("C:/x/claude.exe", False), ("claude", False),
                          ("C:/x/claude.cmd.exe", False)]:
            with self.subTest(exe=exe):
                self.assertIs(chip_run.je_cmd_shim(exe), shim)

    def test_navratovy_kod_claude_se_propaguje(self) -> None:
        with mock.patch("shutil.which", return_value="claude"), \
                mock.patch.object(subprocess, "call", side_effect=[0, 3]):
            rc, _ = self.spust("07", "--spustit")
        self.assertEqual(rc, 3)


class TestRefExistuje(ZakladChipu):
    """Ověření ref se ptá gitu — z názvu se nic neodhaduje."""

    def _rev_parse(self, kod: int):
        """Podstrčí návratový kód `git rev-parse` a vrátí zachycené argv."""
        with mock.patch.object(subprocess, "run",
                               return_value=mock.Mock(returncode=kod)) as beh:
            vysledek = chip_run.ref_existuje(self.repo, "ai/chip-05/zaklad")
        return vysledek, beh.call_args[0][0]

    def test_nulovy_kod_znamena_ze_ref_existuje(self) -> None:
        existuje, cmd = self._rev_parse(0)
        self.assertTrue(existuje)
        self.assertEqual(cmd[:2], ["git", "-C"])
        self.assertIn("rev-parse", cmd)
        self.assertIn("--verify", cmd)

    def test_nenulovy_kod_znamena_ze_ref_neni(self) -> None:
        existuje, _ = self._rev_parse(1)
        self.assertFalse(existuje)

    def test_ptame_se_na_commit_ne_na_libovolny_objekt(self) -> None:
        """`^{commit}` odmítne ref, který na commit neukazuje (tag na blobu)."""
        _, cmd = self._rev_parse(0)
        self.assertEqual(cmd[-1], "ai/chip-05/zaklad^{commit}")

    def test_nazev_ref_se_neodhaduje(self) -> None:
        """Tvar názvu nerozhoduje: co git zamítne, je pryč — a naopak.

        `HEAD~2` na větev nevypadá a přesto je platný základ; `ai/chip-99/x`
        vypadá jako větev chipu a přesto existovat nemusí.
        """
        with mock.patch.object(subprocess, "run",
                               return_value=mock.Mock(returncode=0)):
            self.assertTrue(chip_run.ref_existuje(self.repo, "HEAD~2"))
        with mock.patch.object(subprocess, "run",
                               return_value=mock.Mock(returncode=1)):
            self.assertFalse(chip_run.ref_existuje(self.repo, "ai/chip-99/x"))


class TestOd(ZakladChipu):
    """`--od <ref>`: navazující chip se větví z předchůdce, ne z HEAD."""

    REF = "ai/chip-05/zaklad"

    def spust_s_od(self, *argv: str, existuje: bool = True):
        """main() s podstrčenou odpovědí na „existuje ten ref?"."""
        with mock.patch.object(chip_run, "ref_existuje", return_value=existuje), \
                mock.patch.object(subprocess, "call", return_value=0) as volani:
            rc, out = self.spust("07", *argv)
        return rc, out, volani

    def test_ref_je_posledni_argument_worktree_add(self) -> None:
        rc, _, volani = self.spust_s_od("--od", self.REF)
        self.assertEqual(rc, 0)
        cmd = volani.call_args_list[0][0][0]
        self.assertEqual(cmd[-3:], ["-b", "chip/07-pokusny", self.REF])

    def test_bez_od_vznika_presne_dnesni_prikaz(self) -> None:
        """Regrese: argv bez `--od` se nesmí lišit ani o prvek (větvení z HEAD)."""
        _, _, worktree = chip_run.cesty(self.chip())
        with mock.patch.object(subprocess, "call", return_value=0) as volani:
            rc, _ = self.spust("07")
        self.assertEqual(rc, 0)
        self.assertEqual(volani.call_args_list[0][0][0],
                         ["git", "-C", str(self.repo.resolve()), "worktree", "add",
                          str(worktree), "-b", "chip/07-pokusny"])

    def test_neexistujici_ref_konci_jednickou_pred_zalozenim(self) -> None:
        """Poloviční worktree blokuje další spuštění — proto kontrola napřed."""
        rc, out, volani = self.spust_s_od("--od", "neexistuje", existuje=False)
        self.assertEqual(rc, 1)
        volani.assert_not_called()
        self.assertFalse((self.base / "repo-chip-07").exists())
        self.assertIn("neexistuje", out)

    def test_neexistujici_ref_nesahne_ani_na_stav(self) -> None:
        with mock.patch.object(chip_run, "ref_existuje", return_value=False), \
                mock.patch.object(subprocess, "call", return_value=0):
            rc, _ = self.spust("07", "--od", "neexistuje", "--stav")
        self.assertEqual(rc, 1)
        self.assertEqual(self.chip().stav, "ready")

    def test_dry_run_ukaze_ref_a_nespusti_nic(self) -> None:
        """Náhled musí ukázat, z čeho se bude větvit — a přitom nesáhnout na git."""
        with mock.patch.object(subprocess, "call") as volani, \
                mock.patch.object(subprocess, "run") as beh:
            rc, out = self.spust("07", "--dry-run", "--od", self.REF)
        self.assertEqual(rc, 0)
        volani.assert_not_called()
        beh.assert_not_called()                 # ani ověření ref
        radek = [r for r in out.splitlines() if "worktree add" in r][0]
        self.assertTrue(radek.rstrip().endswith(self.REF), radek)
        self.assertFalse((self.base / "repo-chip-07").exists())

    def test_zadani_rekne_agentovi_z_ceho_vychazi(self) -> None:
        chip = self.chip()
        _, vetev, worktree = chip_run.cesty(chip)
        text = chip_run.zadani(chip, worktree, vetev, od=self.REF)
        self.assertIn(self.REF, text)
        self.assertIn("rozpracovaný kód jiného chipu", text)
        self.assertNotIn("{", text)

    def test_zadani_bez_od_o_zakladu_mlci(self) -> None:
        """Bez `--od` by zmínka o cizí práci byla lež — text zůstává dnešní."""
        chip = self.chip()
        _, vetev, worktree = chip_run.cesty(chip)
        self.assertNotIn("vychází z", chip_run.zadani(chip, worktree, vetev))

    def test_vypsane_zadani_nese_ref(self) -> None:
        rc, out, _ = self.spust_s_od("--od", self.REF)
        self.assertEqual(rc, 0)
        self.assertIn("ZADÁNÍ PRO NOVÉ OKNO", out)
        self.assertIn(f"vychází z '{self.REF}'", out)


class TestZalozRepo(ZakladChipu):
    """`--zaloz-repo`: greenfield ano, cizí historie ne."""

    def prepis_repo(self, cesta: Path) -> None:
        """Přesměruje `repo:` v briefu jinam (repo, které ještě neexistuje)."""
        text = self.brief.read_bytes().decode("utf-8")
        text = text.replace(f"repo: {self.repo.as_posix()}", f"repo: {cesta.as_posix()}")
        self.brief.write_bytes(text.encode("utf-8"))

    def test_neexistujici_repo_se_zalozi_i_s_prvnim_commitem(self) -> None:
        nove = self.base / "nove-repo"
        self.prepis_repo(nove)
        with mock.patch.object(subprocess, "call", return_value=0) as volani:
            rc, out = self.spust("07", "--zaloz-repo")
        self.assertEqual(rc, 0)
        self.assertTrue(nove.is_dir(), "adresář repa musí vzniknout")
        prikazy = [c[0][0] for c in volani.call_args_list]
        self.assertIn("init", prikazy[0])
        self.assertIn("--allow-empty", prikazy[1])
        self.assertIn("worktree", prikazy[2])
        self.assertIn("kořenový commit", out)

    def test_repo_bez_commitu_dostane_korenovy_commit_bez_init(self) -> None:
        """`git init` už proběhl, chybí jen HEAD — init se neopakuje."""
        with mock.patch.object(chip_run, "repo_ma_commity", return_value=False), \
                mock.patch.object(subprocess, "call", return_value=0) as volani:
            rc, _ = self.spust("07", "--zaloz-repo")
        self.assertEqual(rc, 0)
        prikazy = [" ".join(c[0][0]) for c in volani.call_args_list]
        self.assertFalse(any(" init" in p for p in prikazy), prikazy)
        self.assertIn("--allow-empty", prikazy[0])

    def test_repo_s_historii_zustane_nedotcene(self) -> None:
        """Založení nad cizí historií je nevratné — smí se jen ohlásit."""
        with mock.patch.object(chip_run, "repo_ma_commity", return_value=True), \
                mock.patch.object(subprocess, "call", return_value=0) as volani:
            rc, out = self.spust("07", "--zaloz-repo")
        self.assertEqual(rc, 0)
        prikazy = [" ".join(c[0][0]) for c in volani.call_args_list]
        self.assertEqual(len(prikazy), 1, prikazy)      # jen worktree add
        self.assertIn("worktree add", prikazy[0])
        self.assertIn("už má historii", out)

    def test_bez_prepinace_chybejici_repo_konci_jednickou(self) -> None:
        """Dnešní chování zůstává: bez `--zaloz-repo` se nic nezakládá."""
        nove = self.base / "nove-repo"
        self.prepis_repo(nove)
        with mock.patch.object(subprocess, "call") as volani:
            rc, out = self.spust("07")
        self.assertEqual(rc, 1)
        volani.assert_not_called()
        self.assertFalse(nove.exists())
        self.assertIn("není git repozitář", out)

    def test_selhani_git_init_konci_jednickou(self) -> None:
        self.prepis_repo(self.base / "nove-repo")
        with mock.patch.object(subprocess, "call", return_value=1) as volani:
            rc, out = self.spust("07", "--zaloz-repo")
        self.assertEqual(rc, 1)
        self.assertEqual(len(volani.call_args_list), 1, "po pádu initu se nepokračuje")
        self.assertIn("git init", out)

    def test_selhani_commitu_konci_jednickou(self) -> None:
        self.prepis_repo(self.base / "nove-repo")
        with mock.patch.object(subprocess, "call", side_effect=[0, 1]) as volani:
            rc, out = self.spust("07", "--zaloz-repo")
        self.assertEqual(rc, 1)
        self.assertEqual(len(volani.call_args_list), 2, "worktree add se nespouští")
        self.assertIn("user.name", out)

    def test_dry_run_nezaklada_nic(self) -> None:
        nove = self.base / "nove-repo"
        self.prepis_repo(nove)
        with mock.patch.object(subprocess, "call") as volani, \
                mock.patch.object(subprocess, "run") as beh:
            rc, out = self.spust("07", "--dry-run", "--zaloz-repo")
        self.assertEqual(rc, 0)
        volani.assert_not_called()
        beh.assert_not_called()                 # ani dotaz na historii
        self.assertFalse(nove.exists())
        self.assertIn("init", out)
        self.assertIn("--allow-empty", out)

    def test_repo_ma_commity_se_pta_gitu_na_head(self) -> None:
        with mock.patch.object(subprocess, "run",
                               return_value=mock.Mock(returncode=0)) as beh:
            self.assertTrue(chip_run.repo_ma_commity(self.repo))
        cmd = beh.call_args[0][0]
        self.assertIn("rev-parse", cmd)
        self.assertEqual(cmd[-1], "HEAD")
        with mock.patch.object(subprocess, "run",
                               return_value=mock.Mock(returncode=128)):
            self.assertFalse(chip_run.repo_ma_commity(self.repo))


class TestNavratoveKody(ZakladChipu):
    def test_chip_nenalezen(self) -> None:
        with mock.patch.object(subprocess, "call") as volani:
            rc, out = self.spust("99")
        self.assertEqual(rc, 1)
        volani.assert_not_called()
        self.assertIn("nenalezen", out)

    def test_chybi_repo(self) -> None:
        self.napis_brief(repo=False)
        with mock.patch.object(subprocess, "call") as volani:
            rc, out = self.spust("07")
        self.assertEqual(rc, 1)
        volani.assert_not_called()
        self.assertIn("repo:", out)

    def test_repo_neni_git(self) -> None:
        (self.repo / ".git").rmdir()
        with mock.patch.object(subprocess, "call") as volani:
            rc, out = self.spust("07")
        self.assertEqual(rc, 1)
        volani.assert_not_called()
        self.assertIn("není git repozitář", out)

    def test_worktree_uz_existuje(self) -> None:
        (self.base / "repo-chip-07").mkdir()
        with mock.patch.object(subprocess, "call") as volani:
            rc, out = self.spust("07")
        self.assertEqual(rc, 1)
        volani.assert_not_called()
        self.assertIn("už existuje", out)

    def test_stav_neni_ready(self) -> None:
        self.napis_brief(stav="draft")
        with mock.patch.object(subprocess, "call") as volani:
            rc, out = self.spust("07")
        self.assertEqual(rc, 1)
        volani.assert_not_called()
        self.assertIn("očekává se 'ready'", out)


if __name__ == "__main__":
    unittest.main()
