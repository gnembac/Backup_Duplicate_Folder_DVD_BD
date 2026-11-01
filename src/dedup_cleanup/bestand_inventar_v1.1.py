#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bestand_inventar_v1.1.py – Projekt "Basisdaten ermitteln" (privat)
Version 1.1 | Stand 29.10.2026, ca. 11:15 MEZ (Geraetezeit 10:08 UTC) | Autor: Claude fuer Gunter Nembach

ZWECK
  Reine Inventur (NUR LESEN) aller Quellen fuer die Konsolidierung D:\\Daten
  (Analyse_GAP_Konsolidierung_D_Daten v1.1, Phase P1). Erfasst je Datei:
  Wurzel, relativer Pfad, Groesse, mtime, SHA-256, Attribute. Die Auswertung
  (Einheiten R1, Ursprungsquelle R8, Reiseordner, F-Z14, Dubletten) macht
  Claude anschliessend aus der Ausgabe.

SICHERHEIT
  - Quellen werden nur gelesen (open 'rb'); nichts wird verschoben, kopiert,
    umbenannt oder geloescht. Symlinks/Junctions werden nicht verfolgt.
  - Cloud-Platzhalter (Attribut OFFLINE/RECALL_ON_DATA_ACCESS) werden NICHT
    geoeffnet (kein ungewollter Download), nur gelistet.
  - Geschrieben wird ausschliesslich in den Berichtsordner
    (Standard D:\\_Berichte\\bestand_inventar).

AUFRUF (PowerShell, PC-Windows)
  1) Probelauf ohne Hash (schnell, zaehlt nur):
       py bestand_inventar_v1.1.py --nur-zaehlen
  2) Vollinventur mit SHA-256 (wiederaufnehmbar; Abbruch mit Strg+C, erneuter
     Aufruf setzt fort):
       py bestand_inventar_v1.1.py
  2b) NAS-Freigabe mit erfassen (Freigabe am PC einmal im Explorer oeffnen,
      Anmeldung speichern; Adresse wie im Browser, ohne http:// und :5000):
       py bestand_inventar_v1.1.py --wurzel NAS \\\\<NAS-Adresse>\\private_confidential ursprung
  3) Danach an Claude: Ordner D:\\_Berichte\\bestand_inventar\\<Zeitstempel>\\
     (zusammenfassung.txt, inventar.csv.gz, ausnahmen.csv, fehler.csv)

VERSIONSPROTOKOLL
  1.0  29.10.2026  Erstfassung
  1.1  29.10.2026  Music, Desktop, Downloads aus den Standardwurzeln entfernt; NAS-Aufruf dokumentiert
"""
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import os
import sqlite3
import stat
import sys
import time

VERSION = "1.1"

# ------------------------------------------------------------------ Wurzeln
# (Kennung, Pfad, Rolle) – Rolle dient nur der spaeteren Auswertung (R8)
WURZELN_STANDARD = [
    ("PIC",   r"C:\Users\<USER>\Pictures",                              "aktiv"),
    ("VID",   r"C:\Users\<USER>\Videos",                                "aktiv"),
    ("DOC",   r"C:\Users\<USER>\Documents",                             "aktiv"),
    ("GDR",   r"C:\Users\<USER>\Meine Ablage (<google-account>)",    "aktiv"),
    # MUS/DSK/DWN entfernt (v1.1): Music leer, Desktop nur Verknuepfungen,
    # Downloads jederzeit wieder ladbar -> kein Backup (Gunter 29.10.2026)
    ("KALT",  r"D:\2025_02_Backup_all_HDs",                           "ursprung"),
    ("QUAR",  r"D:\_Quarantaene",                                     "ursprung"),   # enthaelt D03
    ("QUARC", r"C:\_Quarantaene_C",                                   "ursprung"),
    ("MED",   r"D:\Archiv_Medien",                                    "ursprung"),
    ("EBK",   r"D:\Ebooks_temp",                                      "ursprung"),
    ("EXP",   r"D:\_Export",                                          "ursprung"),
    ("ADOK",  r"D:\Archiv_Dokumente",                                 "abgeleitet"),
    ("AVID",  r"D:\Archiv_Video",                                     "abgeleitet"),
]

# ------------------------------------------------------------- Regel R10
AUSNAHME_ORDNER = {
    ".synologyworkingdirectory": "R10_sync",
    "@eaDir".lower(): "R10_sync",
    "#recycle": "R10_sync",
    "#snapshot": "R10_sync",
    ".tmp.drivedownload": "R10_sync",
    ".tmp.driveupload": "R10_sync",
    "$recycle.bin": "R10_system",
    "system volume information": "R10_system",
    "node_modules": "R10_build",
    "__pycache__": "R10_build",
    ".venv": "R10_build",
    "venv": "R10_build",
    "site-packages": "R10_build",
    ".pytest_cache": "R10_build",
    ".mypy_cache": "R10_build",
    ".ipynb_checkpoints": "R10_build",
    ".tox": "R10_build",
}
AUSNAHME_DATEIEN = {
    "thumbs.db": "R10_system",
    "desktop.ini": "R10_system",
    ".ds_store": "R10_system",
    "ehthumbs.db": "R10_system",
}
AUSNAHME_ENDUNGEN = {".pyc": "R10_build", ".pyo": "R10_build"}
# Nur markiert, NICHT ausgeschlossen (Entscheidung bei der Auswertung):
GOOGLE_VERWEIS = {".gdoc", ".gsheet", ".gslides", ".gdraw", ".gform", ".gmap", ".gsite"}

ATTR_OFFLINE = 0x1000
ATTR_RECALL_OPEN = 0x40000
ATTR_RECALL_DATA = 0x400000
ATTR_REPARSE = 0x400

CHUNK = 4 * 1024 * 1024
IST_WINDOWS = os.name == "nt"


def lang(pfad: str) -> str:
    """Pfad fuer Windows mit \\\\?\\-Praefix (Pfade > 260 Zeichen)."""
    if not IST_WINDOWS:
        return pfad
    p = os.path.abspath(pfad)
    if p.startswith("\\\\?\\"):
        return p
    if p.startswith("\\\\"):
        return "\\\\?\\UNC\\" + p[2:]
    return "\\\\?\\" + p


def kurz(pfad: str) -> str:
    if pfad.startswith("\\\\?\\UNC\\"):
        return "\\\\" + pfad[8:]
    if pfad.startswith("\\\\?\\"):
        return pfad[4:]
    return pfad


def ist_junction(entry) -> bool:
    try:
        if entry.is_symlink():
            return True
        if IST_WINDOWS:
            st = entry.stat(follow_symlinks=False)
            return bool(getattr(st, "st_file_attributes", 0) & ATTR_REPARSE)
    except OSError:
        return False
    return False


def sha256_datei(pfad: str) -> str:
    h = hashlib.sha256()
    with open(lang(pfad), "rb", buffering=0) as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def db_oeffnen(pfad: str) -> sqlite3.Connection:
    con = sqlite3.connect(pfad)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("""CREATE TABLE IF NOT EXISTS datei(
        wurzel TEXT, rolle TEXT, relpfad TEXT, groesse INTEGER, mtime_ns INTEGER,
        ctime_ns INTEGER, attribute INTEGER, sha256 TEXT, status TEXT,
        pfadlaenge INTEGER, erfasst TEXT,
        PRIMARY KEY (wurzel, relpfad))""")
    con.execute("""CREATE TABLE IF NOT EXISTS ausnahme(
        wurzel TEXT, relpfad TEXT, art TEXT, grund TEXT, groesse INTEGER,
        PRIMARY KEY (wurzel, relpfad))""")
    con.execute("""CREATE TABLE IF NOT EXISTS fehler(
        wurzel TEXT, relpfad TEXT, fehler TEXT, zeit TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS lauf(
        start TEXT, ende TEXT, modus TEXT, version TEXT, bemerkung TEXT)""")
    return con


def ausnahme_ordner_dateien_zaehlen(pfad: str):
    """Zaehlt Dateien/Bytes unter einem ausgeschlossenen Ordner (nur fuer den Bericht)."""
    n = b = 0
    stapel = [pfad]
    while stapel:
        d = stapel.pop()
        try:
            with os.scandir(lang(d)) as it:
                for e in it:
                    try:
                        if ist_junction(e):
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stapel.append(kurz(e.path))
                        elif e.is_file(follow_symlinks=False):
                            n += 1
                            b += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return n, b


def inventur(con, kennung, wurzel, rolle, nur_zaehlen, stats, ausschluss_pfade):
    if not os.path.isdir(lang(wurzel)):
        stats.setdefault(kennung, {})["fehlt"] = True
        print(f"  [{kennung}] nicht vorhanden: {wurzel}")
        return
    s = stats.setdefault(kennung, {"dateien": 0, "bytes": 0, "gehasht": 0, "uebersprungen": 0,
                                    "ausnahmen": 0, "ausnahme_bytes": 0, "cloud_platzhalter": 0,
                                    "fehler": 0, "google_verweise": 0, "pfad_gt_260": 0})
    jetzt = dt.datetime.now().isoformat(timespec="seconds")
    bekannt = {}
    if not nur_zaehlen:
        for rel, g, m, h in con.execute(
                "SELECT relpfad, groesse, mtime_ns, sha256 FROM datei WHERE wurzel=?", (kennung,)):
            bekannt[rel] = (g, m, h)
    stapel = [wurzel]
    t0 = time.time()
    letzte = t0
    while stapel:
        d = stapel.pop()
        try:
            it = os.scandir(lang(d))
        except OSError as ex:
            s["fehler"] += 1
            con.execute("INSERT INTO fehler VALUES (?,?,?,?)",
                        (kennung, os.path.relpath(d, wurzel), f"scandir: {ex}", jetzt))
            continue
        with it:
            for e in it:
                pfad = kurz(e.path)
                rel = os.path.relpath(pfad, wurzel)
                name_l = e.name.lower()
                try:
                    if ist_junction(e):
                        s["ausnahmen"] += 1
                        con.execute("INSERT OR REPLACE INTO ausnahme VALUES (?,?,?,?,?)",
                                    (kennung, rel, "link", "Symlink/Junction nicht verfolgt", 0))
                        continue
                    if e.is_dir(follow_symlinks=False):
                        if os.path.normcase(pfad) in ausschluss_pfade:
                            continue
                        grund = AUSNAHME_ORDNER.get(name_l)
                        if grund:
                            n, b = ausnahme_ordner_dateien_zaehlen(pfad)
                            s["ausnahmen"] += n
                            s["ausnahme_bytes"] += b
                            con.execute("INSERT OR REPLACE INTO ausnahme VALUES (?,?,?,?,?)",
                                        (kennung, rel, "ordner", f"{grund} ({n} Dateien)", b))
                        else:
                            stapel.append(pfad)
                        continue
                    if not e.is_file(follow_symlinks=False):
                        continue
                    st = e.stat(follow_symlinks=False)
                    ext = os.path.splitext(name_l)[1]
                    grund = AUSNAHME_DATEIEN.get(name_l) or AUSNAHME_ENDUNGEN.get(ext)
                    if not grund and name_l.startswith("~$"):
                        grund = "R10_office_temp"
                    if grund:
                        s["ausnahmen"] += 1
                        s["ausnahme_bytes"] += st.st_size
                        con.execute("INSERT OR REPLACE INTO ausnahme VALUES (?,?,?,?,?)",
                                    (kennung, rel, "datei", grund, st.st_size))
                        continue
                    attr = getattr(st, "st_file_attributes", 0)
                    s["dateien"] += 1
                    s["bytes"] += st.st_size
                    if ext in GOOGLE_VERWEIS:
                        s["google_verweise"] += 1
                    if len(pfad) > 260:
                        s["pfad_gt_260"] += 1
                    if nur_zaehlen:
                        continue
                    alt = bekannt.get(rel)
                    if alt and alt[0] == st.st_size and alt[1] == st.st_mtime_ns and alt[2]:
                        s["uebersprungen"] += 1
                        continue
                    status = "OK"
                    h = None
                    if attr & (ATTR_OFFLINE | ATTR_RECALL_DATA | ATTR_RECALL_OPEN):
                        status = "CLOUD_PLATZHALTER"
                        s["cloud_platzhalter"] += 1
                    else:
                        try:
                            h = sha256_datei(pfad)
                            s["gehasht"] += 1
                        except OSError as ex:
                            status = "LESEFEHLER"
                            s["fehler"] += 1
                            con.execute("INSERT INTO fehler VALUES (?,?,?,?)",
                                        (kennung, rel, f"lesen: {ex}", jetzt))
                    con.execute("INSERT OR REPLACE INTO datei VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                (kennung, rolle, rel, st.st_size, st.st_mtime_ns,
                                 getattr(st, "st_ctime_ns", 0), attr, h, status, len(pfad), jetzt))
                except OSError as ex:
                    s["fehler"] += 1
                    con.execute("INSERT INTO fehler VALUES (?,?,?,?)",
                                (kennung, rel, f"stat: {ex}", jetzt))
                if time.time() - letzte > 15:
                    letzte = time.time()
                    if not nur_zaehlen:
                        con.commit()
                    print(f"  [{kennung}] {s['dateien']:>8} Dateien  {s['bytes']/2**30:8.2f} GiB  "
                          f"gehasht {s['gehasht']}  ({int(letzte - t0)} s)", flush=True)
    con.commit()
    print(f"  [{kennung}] fertig: {s['dateien']} Dateien, {s['bytes']/2**30:.2f} GiB, "
          f"Ausnahmen {s['ausnahmen']}, Fehler {s['fehler']} ({int(time.time() - t0)} s)")


def export(con, ausgabe):
    with gzip.open(os.path.join(ausgabe, "inventar.csv.gz"), "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["wurzel", "rolle", "relpfad", "groesse", "mtime_ns", "ctime_ns",
                    "attribute", "sha256", "status", "pfadlaenge"])
        for row in con.execute("SELECT wurzel, rolle, relpfad, groesse, mtime_ns, ctime_ns, "
                               "attribute, sha256, status, pfadlaenge FROM datei ORDER BY wurzel, relpfad"):
            w.writerow(row)
    for tab, datei, kopf in (("ausnahme", "ausnahmen.csv", ["wurzel", "relpfad", "art", "grund", "groesse"]),
                             ("fehler", "fehler.csv", ["wurzel", "relpfad", "fehler", "zeit"])):
        with open(os.path.join(ausgabe, datei), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(kopf)
            for row in con.execute(f"SELECT * FROM {tab}"):
                w.writerow(row)


def main():
    ap = argparse.ArgumentParser(description="Inventur (nur lesen) fuer D:\\Daten")
    ap.add_argument("--nur-zaehlen", action="store_true", help="ohne Hash, nur zaehlen (schnell)")
    ap.add_argument("--berichte", default=r"D:\_Berichte\bestand_inventar",
                    help="Berichtsordner (einziger Schreibort)")
    ap.add_argument("--nur", nargs="*", help="nur diese Kennungen, z. B. --nur PIC DOC")
    ap.add_argument("--wurzel", nargs=3, action="append", metavar=("KENNUNG", "PFAD", "ROLLE"),
                    help="zusaetzliche Wurzel, z. B. --wurzel NAS \\\\DS224plus\\private_confidential ursprung")
    a = ap.parse_args()

    wurzeln = list(WURZELN_STANDARD) + [tuple(x) for x in (a.wurzel or [])]
    if a.nur:
        wurzeln = [w for w in wurzeln if w[0] in set(a.nur)]

    # Schutz: Berichtsordner darf nicht in einer Quelle liegen (ausser D:\_Berichte)
    ber = os.path.normcase(os.path.abspath(a.berichte))
    for k, p, _ in wurzeln:
        if ber.startswith(os.path.normcase(os.path.abspath(p)) + os.sep):
            sys.exit(f"ABBRUCH: Berichtsordner liegt in Quelle {k} ({p}).")

    os.makedirs(a.berichte, exist_ok=True)
    stempel = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    modus = "ZAEHLEN" if a.nur_zaehlen else "HASH"
    ausgabe = os.path.join(a.berichte, f"{stempel}_{modus}")
    os.makedirs(ausgabe, exist_ok=True)
    dbpfad = os.path.join(a.berichte, "inventar.sqlite") if not a.nur_zaehlen \
        else os.path.join(ausgabe, "zaehlung.sqlite")
    con = db_oeffnen(dbpfad)
    start = dt.datetime.now().isoformat(timespec="seconds")
    ausschluss = {os.path.normcase(os.path.abspath(a.berichte)),
                  os.path.normcase(r"D:\Daten")}

    print(f"bestand_inventar v{VERSION} | {modus} | {start} | NUR LESEN | Ausgabe: {ausgabe}")
    stats = {}
    try:
        for k, p, r in wurzeln:
            inventur(con, k, p, r, a.nur_zaehlen, stats, ausschluss)
    except KeyboardInterrupt:
        con.commit()
        print("\nABGEBROCHEN (Strg+C). Erneuter Aufruf setzt fort.")
    ende = dt.datetime.now().isoformat(timespec="seconds")
    con.execute("INSERT INTO lauf VALUES (?,?,?,?,?)", (start, ende, modus, VERSION, ""))
    con.commit()

    zeilen = [f"bestand_inventar v{VERSION} | {modus} | Start {start} | Ende {ende} | NUR LESEN",
              f"Datenbank: {dbpfad}", "",
              f"{'Kennung':<6} {'Dateien':>9} {'GiB':>9} {'gehasht':>9} {'uebersp.':>9} "
              f"{'Ausnahm.':>9} {'Ausn.GiB':>9} {'Cloud':>6} {'Fehler':>7} {'G-Verw.':>8} {'>260':>6}"]
    for k, p, r in wurzeln:
        s = stats.get(k, {})
        if s.get("fehlt"):
            zeilen.append(f"{k:<6} nicht vorhanden ({p})")
            continue
        if not s:
            continue
        zeilen.append(f"{k:<6} {s['dateien']:>9} {s['bytes']/2**30:>9.2f} {s['gehasht']:>9} "
                      f"{s['uebersprungen']:>9} {s['ausnahmen']:>9} {s['ausnahme_bytes']/2**30:>9.2f} "
                      f"{s['cloud_platzhalter']:>6} {s['fehler']:>7} {s['google_verweise']:>8} "
                      f"{s['pfad_gt_260']:>6}")
    if not a.nur_zaehlen:
        export(con, ausgabe)
        zeilen += ["", "Dateien: inventar.csv.gz, ausnahmen.csv, fehler.csv"]
    text = "\n".join(zeilen)
    print("\n" + text)
    with open(os.path.join(ausgabe, "zusammenfassung.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    con.close()


if __name__ == "__main__":
    main()
