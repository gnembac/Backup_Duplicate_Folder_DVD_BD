#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mdisc_lesetest_v1.0.py - Projekt "Basisdaten ermitteln" (privat)
Version 1.0 | Stand 30.10.2026, 10:00 MEZ | Autor: Claude fuer Gunter Nembach

ZWECK (NUR LESEN)
  Liest eine gebrannte Disc (M-DISC/BD) vollstaendig und protokolliert je Datei
  Lesezeit, Tempo und Lesefehler (echter Win32-Code). Pruefung je Datei:
    - .zip: jedes Mitglied wird gelesen und gegen seine CRC32 geprueft
            (Pruefung ohne Referenz - die ZIP traegt ihre Pruefsummen selbst)
    - sonst: SHA-256 (fuer den spaeteren Abgleich gegen Manifest/Bestand)
  Test T1 der M-DISC-Bewertung: Zustand der am 18.10.2026 gebrannten M-DISC
  und damit der Kette Brenner + Rohling + Brennprogramm nach 12 Tagen.

SICHERHEIT
  - Disc wird nur gelesen (open 'rb'). Geschrieben wird nur nach --out.

AUFRUF (PowerShell, PC-Windows; Disc im Brenner)
  cd D:\\_Berichte\\kopierplan\\skripte
  py mdisc_lesetest_v1.0.py                     (erkennt das optische Laufwerk selbst)
  py mdisc_lesetest_v1.0.py --laufwerk E:\\
  py mdisc_lesetest_v1.0.py --nur-liste          (nur Dateiliste, liest keine Inhalte; 1 min)
  py mdisc_lesetest_v1.0.py --sha-zip            (ZIP zusaetzlich als Ganzes SHA-256 = 2. Lesedurchgang)

AUSGABE (D:\\_Berichte\\mdisc\\)
  lesetest_<Label>_<Zeit>.csv  (UTF-8-BOM, Semikolon)
  lesetest_<Label>_<Zeit>_zusammenfassung.txt

EXIT-CODES  0 alles gelesen, 0 Fehler | 1 Befund | 2 Aufruffehler | 4 Laufwerk weg | 130 Strg+C

GRENZEN
  - Windows-Verhalten in der Linux-Sandbox nicht pruefbar: UNGETESTET bis zum ersten Lauf.
  - Ein Durchgang belegt, was das Laufwerk geliefert hat. Stille Lesefehler bei
    Nicht-ZIP-Dateien erkennt erst der Abgleich gegen Manifest/Bestand.

VERSIONSPROTOKOLL
  1.0  30.10.2026, 10:00  Erstfassung
"""
import argparse, csv, datetime as dt, hashlib, os, sys, time, zipfile

VERSION = "mdisc_lesetest_v1.0"
BLOCK = 4 * 2**20
IST_WIN = os.name == "nt"
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def jetzt():
    return dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def lang(p):
    if IST_WIN and not p.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(p)
    return p


def optische_laufwerke():
    if not IST_WIN:
        return []
    import ctypes
    k = ctypes.windll.kernel32
    maske = k.GetLogicalDrives()
    erg = []
    for i in range(26):
        if maske & (1 << i):
            lw = "%s:\\" % chr(65 + i)
            if k.GetDriveTypeW(lw) == 5:  # DRIVE_CDROM
                erg.append(lw)
    return erg


def volumen(lw):
    if not IST_WIN:
        return "k.A.", "k.A."
    import ctypes
    name = ctypes.create_unicode_buffer(261)
    fs = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(lw, name, 261, None, None, None, fs, 261)
    return (name.value or "ohne_Label", fs.value) if ok else ("k.A.", "k.A.")


def fehlertext(e):
    w = getattr(e, "winerror", None)
    return "[Win32 %s] %s" % (w, e.strerror or e) if w else "%s: %s" % (type(e).__name__, e)


def sha_datei(p):
    h = hashlib.sha256()
    n = 0
    with open(lang(p), "rb") as f:
        while True:
            b = f.read(BLOCK)
            if not b:
                break
            h.update(b)
            n += len(b)
    return h.hexdigest(), n


def zip_test(p):
    """Jedes Mitglied lesen; zipfile prueft die CRC32 beim Lesen. Rueckgabe (n, ok, fehlerliste, bytes)."""
    ok, fehler, n_bytes = 0, [], 0
    with zipfile.ZipFile(lang(p)) as z:
        infos = sorted(z.infolist(), key=lambda i: i.header_offset)
        for i in infos:
            if i.is_dir():
                ok += 1
                continue
            try:
                with z.open(i) as m:
                    while True:
                        b = m.read(BLOCK)
                        if not b:
                            break
                        n_bytes += len(b)
                ok += 1
            except zipfile.BadZipFile as e:
                fehler.append("%s: %s" % (i.filename, e))
            except OSError as e:
                fehler.append("%s: %s" % (i.filename, fehlertext(e)))
    return len(infos), ok, fehler, n_bytes


def main():
    ap = argparse.ArgumentParser(description=VERSION)
    ap.add_argument("--laufwerk", default="")
    ap.add_argument("--out", default=r"D:\_Berichte\mdisc")
    ap.add_argument("--nur-liste", action="store_true")
    ap.add_argument("--sha-zip", action="store_true")
    a = ap.parse_args()
    print(VERSION, "Start", jetzt(), flush=True)
    lw = a.laufwerk
    if not lw:
        kand = optische_laufwerke()
        if len(kand) != 1:
            print("FEHLER: optische Laufwerke gefunden: %s - bitte --laufwerk angeben" % (kand or "keine"))
            return 2
        lw = kand[0]
    if not lw.endswith("\\") and IST_WIN:
        lw += "\\"
    if not os.path.isdir(lw):
        print("FEHLER: Laufwerk nicht lesbar (Disc eingelegt?):", lw)
        return 2
    label, fs = volumen(lw)
    os.makedirs(a.out, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    stamm = os.path.join(a.out, "lesetest_%s_%s" % ("".join(c if c.isalnum() or c in "-_" else "_" for c in label), ts))
    print("Laufwerk %s | Label %s | Dateisystem %s" % (lw, label, fs), flush=True)

    dateien, dirfehler = [], []
    def onerr(e):
        dirfehler.append((getattr(e, "filename", "?"), fehlertext(e)))
    for wurzel, dirs, files in os.walk(lang(lw), onerror=onerr):
        dirs.sort()
        for n in sorted(files):
            p = os.path.join(wurzel, n)
            try:
                g = os.path.getsize(p)
            except OSError as e:
                g = -1
                dirfehler.append((p, fehlertext(e)))
            dateien.append((p, g))
    soll = sum(g for _, g in dateien if g > 0)
    print("Dateien %d | %.2f GiB | Verzeichnisfehler %d" % (len(dateien), soll / 2**30, len(dirfehler)), flush=True)

    zeilen, n_fehler, gelesen, t_start, abbruch = [], len(dirfehler), 0, time.time(), ""
    try:
        for idx, (p, g) in enumerate(dateien, 1):
            rel = p.replace("\\\\?\\", "")
            zeile = dict(Pfad=rel, Bytes=g, Typ="", SHA256="", ZIP_Mitglieder="", ZIP_OK="", ZIP_Fehler="",
                         Dauer_s="", MBps="", Status="", Fehler="")
            if a.nur_liste:
                zeile["Status"] = "NUR_LISTE"
                zeilen.append(zeile)
                continue
            if not os.path.isdir(lw):
                abbruch = "Laufwerk weg"
                break
            t0 = time.time()
            try:
                if p.lower().endswith(".zip"):
                    zeile["Typ"] = "ZIP"
                    n, ok, fl, nb = zip_test(p)
                    zeile.update(ZIP_Mitglieder=n, ZIP_OK=ok, ZIP_Fehler=" | ".join(fl[:20]))
                    if a.sha_zip:
                        zeile["SHA256"], _ = sha_datei(p)
                    zeile["Status"] = "OK" if not fl else "ZIP_FEHLER"
                    if fl:
                        n_fehler += 1
                    gelesen += g
                else:
                    zeile["Typ"] = "DATEI"
                    zeile["SHA256"], nb = sha_datei(p)
                    gelesen += nb
                    zeile["Status"] = "OK" if nb == g else "GROESSE_ABWEICHEND"
                    if nb != g:
                        n_fehler += 1
            except (OSError, zipfile.BadZipFile) as e:
                zeile["Status"] = "LESEFEHLER"
                zeile["Fehler"] = fehlertext(e) if isinstance(e, OSError) else str(e)
                n_fehler += 1
            d = time.time() - t0
            zeile["Dauer_s"] = round(d, 2)
            zeile["MBps"] = round(g / 1e6 / d, 2) if d > 0 and g > 0 else ""
            zeilen.append(zeile)
            if zeile["Status"] != "OK" or g > 500e6 or idx % 200 == 0:
                el = time.time() - t_start
                print("  %d/%d  %.2f/%.2f GiB  %.1f MB/s gesamt  %s  %s" % (
                    idx, len(dateien), gelesen / 2**30, soll / 2**30, gelesen / 1e6 / el if el else 0,
                    zeile["Status"], os.path.basename(rel)[:60]), flush=True)
    except KeyboardInterrupt:
        abbruch = "Strg+C"

    felder = ["Pfad", "Bytes", "Typ", "SHA256", "ZIP_Mitglieder", "ZIP_OK", "ZIP_Fehler", "Dauer_s", "MBps", "Status", "Fehler"]
    with open(stamm + ".csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=felder, delimiter=";")
        w.writeheader()
        w.writerows(zeilen)
        for p, t in dirfehler:
            w.writerow(dict(Pfad=p, Status="VERZEICHNISFEHLER", Fehler=t))
    dauer = time.time() - t_start
    tempi = sorted((z for z in zeilen if z["MBps"] != "" and z["Bytes"] > 50e6), key=lambda z: z["MBps"])
    zus = [
        "%s | %s" % (VERSION, jetzt()),
        "Laufwerk %s | Label %s | Dateisystem %s" % (lw, label, fs),
        "Dateien %d | Soll %d B (%.3f GiB) | gelesen %d B" % (len(dateien), soll, soll / 2**30, gelesen),
        "Dauer %.0f s (%.1f min) | Tempo gesamt %.1f MB/s" % (dauer, dauer / 60, gelesen / 1e6 / dauer if dauer else 0),
        "Status: " + ", ".join("%s %d" % (s, sum(1 for z in zeilen if z["Status"] == s))
                               for s in sorted({z["Status"] for z in zeilen})),
        "Verzeichnisfehler %d" % len(dirfehler),
        "ZIP-Mitglieder gesamt %s, davon CRC OK %s" % (
            sum(int(z["ZIP_Mitglieder"] or 0) for z in zeilen), sum(int(z["ZIP_OK"] or 0) for z in zeilen)),
        "Langsamste Dateien > 50 MB (MB/s): " + ", ".join("%s %.1f" % (os.path.basename(z["Pfad"])[:40], z["MBps"]) for z in tempi[:5]),
        "Abbruch: %s" % (abbruch or "nein"),
        "ERGEBNIS: %s" % ("NUR LISTE" if a.nur_liste else ("BEFUND (%d Fehler)" % n_fehler if n_fehler or abbruch else "BESTANDEN (alles gelesen, 0 Fehler)")),
    ]
    with open(stamm + "_zusammenfassung.txt", "w", encoding="utf-8-sig") as fh:
        fh.write("\n".join(zus) + "\n")
    print("\n".join(zus))
    print("Berichte:", stamm + ".csv")
    if abbruch == "Strg+C":
        return 130
    if abbruch:
        return 4
    return 1 if n_fehler else 0


if __name__ == "__main__":
    sys.exit(main())
