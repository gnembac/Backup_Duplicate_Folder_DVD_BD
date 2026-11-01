"""Unit tests for the deterministic UDF name/path shortening in mdisc_brennliste.

Background: CDBurnerXP 4.5.8 (UDF 2.50) silently truncates file and folder names
longer than 127 UTF-16 code units. A silently truncated name breaks the manifest
(FEHLT 1 + EXTRA 1 in the ISO check). The tool therefore shortens names
deterministically *before* the burn folder is built and logs the mapping.
"""
import importlib.util
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "mdisc_archival" / "mdisc_brennliste_v1.5.py"


@pytest.fixture(scope="module")
def bl():
    spec = importlib.util.spec_from_file_location("mdisc_brennliste", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_u16_counts_utf16_code_units(bl):
    assert bl.u16("abc") == 3
    assert bl.u16("äöü") == 3
    assert bl.u16("\U0001F600") == 2  # surrogate pair


def test_short_names_unchanged(bl):
    name = "a" * 127 + ".jpg"
    assert bl.u16(name) > 127
    short = "Segeltoern_2015.jpg"
    assert bl.kurzname(short, 120) == short


def test_long_name_shortened_deterministic_with_extension(bl):
    name = "x" * 200 + ".MP4"
    k1 = bl.kurzname(name, 120)
    k2 = bl.kurzname(name, 120)
    assert k1 == k2                      # deterministic
    assert bl.u16(k1) <= 120             # within limit
    assert k1.endswith(".MP4")           # extension kept
    assert "~" in k1                     # hash marker present


def test_different_long_names_get_different_short_names(bl):
    a = "y" * 150 + "_A.pdf"
    b = "y" * 150 + "_B.pdf"
    assert bl.kurzname(a, 120) != bl.kurzname(b, 120)


def test_kurzordner_limit_and_marker(bl):
    name = "Ordner_" + "z" * 80
    k = bl.kurzordner(name, 40)
    assert bl.u16(k) <= 40
    assert "~" in k
    assert bl.kurzordner("kurz", 40) == "kurz"


def test_fassungen_detects_versions(bl, tmp_path):
    for n in ("D2", "D2_V2", "D2_V3", "D3_V1", "D2_V2_alt"):
        (tmp_path / n).mkdir()
    f = bl.fassungen(str(tmp_path), "D2")
    assert f == {1: "D2", 2: "D2_V2", 3: "D2_V3"}


def test_pfade_kuerzen_brings_paths_under_limit(bl):
    rel = "Reisen\\Einheit\\" + "\\".join(["Unterordner_mit_sehr_langem_Namen_" + str(i) for i in range(3)]) + "\\datei.jpg"
    prim = [{"rel": rel, "dst": rel}]
    vorher, n_ordner, n_name, rest = bl.pfade_kuerzen(prim, 100, 120)
    assert vorher == 1
    assert rest == []
    assert len(prim[0]["dst"]) <= 100
    # unit folders (levels 0 and 1) are never shortened
    assert prim[0]["dst"].startswith("Reisen\\Einheit\\")


def test_pfade_kuerzen_reports_residual_instead_of_hiding_it(bl):
    # 8 nested folders cannot be shortened below 16 characters each -> the
    # residual must be reported (the caller then refuses to build the disc).
    rel = "Reisen\\Einheit\\" + "\\".join(["Unterordner_mit_sehr_langem_Namen_" + str(i) for i in range(8)]) + "\\datei.jpg"
    prim = [{"rel": rel, "dst": rel}]
    vorher, n_ordner, n_name, rest = bl.pfade_kuerzen(prim, 120, 120)
    assert vorher == 1
    assert len(rest) == 1
