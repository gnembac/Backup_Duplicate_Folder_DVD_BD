#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
mdisc_serie_v1.0.py - Projekt "Basisdaten ermitteln" (privat)
Version 1.0 | Stand 01.11.2026, 12:18 MEZ | Autor: Claude fuer Gunter Nembach

ZWECK
  Fasst die Vorbereitung mehrerer M-DISCs zusammen (ein Befehl je Schritt, eine Statustabelle am Ende).
  Schritt ORDNER: je Disc mdisc_brennliste_v1.4 --ausfuehren (neuer Brennordner D<n>_V<k>), danach
                  mdisc_pruefen_v1.2 --stufe ORDNER. D6 = Google-Takeout (--fremd, 7 ZIP aus D:\_Import).
  Schritt ISO:    je Disc das ISO aus CDBurnerXP finden (<Label>*.iso in D:\_MDISC, juengstes), alle Abbilder
                  auswerfen, ISO schreibgeschuetzt einbinden, mdisc_pruefen_v1.2 --stufe ISO --image --label-soll,
                  wieder auswerfen.
SICHERHEIT
  Brennt nichts, loescht nichts, benennt nichts um. Neue Brennordner legt nur mdisc_brennliste an (Fassungsregel).
  Gibt es schon eine Fassung D<n>_V<k>, wird D<n> im Schritt ORDNER uebersprungen (neue Fassung nur mit --neu).
AUFRUF (PowerShell, normale Rechte, PC-Windows)
  cd D:\_Berichte\kopierplan\skripte
  py mdisc_serie_v1.0.py --schritt ORDNER            (Standard: --discs 3 4 5 6)
  py mdisc_serie_v1.0.py --schritt ISO
AUSGABE  Konsole + D:\_Berichte\mdisc\serie_<SCHRITT>_<Zeit>.txt (komplette Ausgabe aller Unterlaeufe)
EXIT     0 alle Discs OK | 1 mindestens eine Disc mit Befund/Fehler | 2 Aufruf-/Vorbedingungsfehler
TESTS    01.11.2026 Linux-Container: Schritt ORDNER mit synthetischen Plaenen (D2/D3 inkl. --fremd), Schritt ISO
         mit Testwurzel statt Einbinden (--test-wurzel). Einbinden per PowerShell (Mount-DiskImage) UNGETESTET.
"""
import argparse, datetime as dt, glob, os, re, shutil, subprocess, sys, time

VERSION = "mdisc_serie_v1.0"
BRENNLISTE = "mdisc_brennliste_v1.4.py"
PRUEFEN = "mdisc_pruefen_v1.2.py"
TAKEOUT = [
    r"D:\_Import\Takout_Export_3_2026_10_30\takeout-20261029T234005Z-1-001.zip",
    r"D:\_Import\Takout_Export_3_2026_10_30\takeout-20261029T234005Z-2-001.zip",
    r"D:\_Import\Takout_Export_3_2026_10_30\takeout-20261029T234005Z-3-001.zip",
    r"D:\_Import\Takout_Export_3_2026_10_30\takeout-20261029T234005Z-4-001.zip",
    r"D:\_Import\Export2_Takeout_2026-10-29\takeout-20261029T224435Z-1-001.zip",
    r"D:\_Import\Export2_Takeout_2026-10-29\takeout-20261029T224435Z-2-001.zip",
    r"D:\_Import\Export2_Takeout_2026-10-29\takeout-20261029T224435Z-4-001.zip",
]
GIB = 2**30
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


class Log:
    def __init__(self, pfad):
        self.f = open(pfad, "w", encoding="utf-8-sig")
        self.pfad = pfad

    def __call__(self, *t):
        s = " ".join(str(x) for x in t)
        print(s, flush=True)
        self.f.write(s + "\n")
        self.f.flush()


def lauf(log, cmd, cwd):
    log(">>> " + " ".join(cmd))
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                         encoding="utf-8", errors="replace")
    for zeile in p.stdout:
        log(zeile.rstrip("\n"))
    return p.wait()


def fassungen(ziel, n):
    erg = []
    if os.path.isdir(ziel):
        for name in os.listdir(ziel):
            m = re.match(r"^D%d(?:_V(\d+))?$" % n, name, re.I)
            if m and os.path.isdir(os.path.join(ziel, name)):
                erg.append((int(m.group(1) or 1), name))
    return sorted(erg)


def liesmich(ordner):
    p = os.path.join(ordner, "_MANIFEST", "LIESMICH.txt")
    if not os.path.isfile(p):
        return "", ""
    t = open(p, encoding="utf-8-sig").read()
    lab = re.search(r"(?m)^Label: (\S+)", t)
    fas = re.search(r"(?m)^Fassung: (\S+)", t)
    return (lab.group(1) if lab else ""), (fas.group(1) if fas else "")


def ps(befehl):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", befehl],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def main():
    ap = argparse.ArgumentParser(description=VERSION)
    ap.add_argument("--schritt", required=True, choices=["ORDNER", "ISO"], type=str.upper)
    ap.add_argument("--discs", type=int, nargs="+", default=[3, 4, 5, 6])
    ap.add_argument("--neu", action="store_true", help="ORDNER: auch bei vorhandener Fassung eine neue anlegen")
    ap.add_argument("--ziel", default=r"D:\_MDISC")
    ap.add_argument("--out", default=r"D:\_Berichte\mdisc")
    ap.add_argument("--extra", default="", help=argparse.SUPPRESS)        # Test: Zusatzargumente fuer brennliste
    ap.add_argument("--takeout", nargs="*", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--test-wurzel", default="", help=argparse.SUPPRESS)  # Test: statt Einbinden diese Wurzel
    a = ap.parse_args()
    skripte = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(a.out, exist_ok=True)
    log = Log(os.path.join(a.out, "serie_%s_%s.txt" % (a.schritt, dt.datetime.now().strftime("%Y-%m-%d_%H%M%S"))))
    log("%s | %s | Schritt %s | Discs %s" % (VERSION, dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S"), a.schritt,
                                             " ".join("D%d" % n for n in a.discs)))
    for s in (BRENNLISTE, PRUEFEN):
        if not os.path.isfile(os.path.join(skripte, s)):
            log("FEHLER: %s fehlt in %s" % (s, skripte)); return 2
    takeout = a.takeout if a.takeout is not None else TAKEOUT
    tabelle = []
    py = sys.executable
    if a.schritt == "ORDNER":
        frei = shutil.disk_usage(a.ziel if os.path.isdir(a.ziel) else os.path.dirname(a.ziel) or ".").free / GIB
        log("Freier Platz %s: %.1f GiB | Bedarf ISOs ca. %.0f GiB (81,3 je Disc)" % (a.ziel, frei, 81.3 * len(a.discs)))
        if frei < 82 * len(a.discs):
            log("WARNUNG: Platz reicht nicht fuer alle ISOs - vor CDBurnerXP Platz schaffen (Loeschen nur durch Gunter)")
        if 6 in a.discs:
            fehlt = [p for p in takeout if not os.path.isfile(p)]
            if fehlt:
                log("FEHLER: Takeout-Dateien fehlen: " + " | ".join(fehlt)); return 2
        for n in a.discs:
            log("")
            log("===== D%d : Brennliste =====" % n)
            vorh = fassungen(a.ziel, n)
            if vorh and not a.neu:
                log("D%d hat schon Fassung(en) %s -> uebersprungen (neue Fassung nur mit --neu)" % (n, ", ".join(v for _, v in vorh)))
                tabelle.append(["D%d" % n, vorh[-1][1], "-", "uebersprungen", "-", "-"])
                continue
            cmd = [py, BRENNLISTE, "--disc", str(n), "--ausfuehren"] + (a.extra.split() if a.extra else [])
            if n == 6:
                for p in takeout:
                    cmd += ["--fremd", p]
            rc_b = lauf(log, cmd, skripte)
            neu = fassungen(a.ziel, n)
            if not neu or (vorh and neu[-1] == vorh[-1]):
                log("FEHLER: kein neuer Brennordner fuer D%d (Exit %d)" % (n, rc_b))
                tabelle.append(["D%d" % n, "-", "-", "Brennliste Exit %d" % rc_b, "-", "-"]); continue
            ordner = os.path.join(a.ziel, neu[-1][1])
            lab, fas = liesmich(ordner)
            if rc_b != 0 or os.path.exists(os.path.join(ordner, "NICHT_BRENNEN.txt")):
                tabelle.append(["D%d" % n, neu[-1][1], lab, "BEFUND (Exit %d, NICHT_BRENNEN?)" % rc_b, "nicht geprueft", "-"]); continue
            if fas != neu[-1][1]:
                log("FEHLER: LIESMICH Fassung %s <> Ordner %s" % (fas, neu[-1][1]))
            log("===== D%d : ORDNER-Pruefung %s =====" % (n, ordner))
            rc_o = lauf(log, [py, PRUEFEN, "--stufe", "ORDNER", "--wurzel", ordner], skripte)
            iso = os.path.join(a.ziel, "%s_V%d.iso" % (lab, neu[-1][0]))
            tabelle.append(["D%d" % n, neu[-1][1], lab, "BRENNBEREIT", "BESTANDEN" if rc_o == 0 else "BEFUND (Exit %d)" % rc_o, iso])
        log("")
        log("%-4s %-8s %-16s %-26s %-16s %s" % ("Disc", "Fassung", "Label", "Brennliste", "ORDNER", "ISO in CDBurnerXP speichern als"))
    else:
        for n in a.discs:
            log("")
            vorh = fassungen(a.ziel, n)
            if not vorh:
                tabelle.append(["D%d" % n, "-", "-", "kein Brennordner", "-", "-"]); continue
            k, name = vorh[-1]
            ordner = os.path.join(a.ziel, name)
            lab, fas = liesmich(ordner)
            kand = [p for p in glob.glob(os.path.join(a.ziel, lab + "*.iso"))]
            kand.sort(key=os.path.getmtime)
            if not kand:
                log("D%d: kein ISO %s*.iso in %s" % (n, lab, a.ziel))
                tabelle.append(["D%d" % n, name, lab, "ISO fehlt", "-", "-"]); continue
            iso = kand[-1]
            t_lies = os.path.getmtime(os.path.join(ordner, "_MANIFEST", "LIESMICH.txt"))
            hinweis = "" if os.path.getmtime(iso) >= t_lies else "ISO AELTER ALS BRENNORDNER (E117)"
            log("===== D%d : ISO %s (%.2f GiB, %s) | Fassung %s | Label %s %s =====" % (
                n, iso, os.path.getsize(iso) / GIB, time.strftime("%d.%m.%Y %H:%M", time.localtime(os.path.getmtime(iso))),
                name, lab, hinweis))
            if hinweis:
                tabelle.append(["D%d" % n, name, lab, os.path.basename(iso), hinweis, "-"]); continue
            if a.test_wurzel:
                wurzel, rc_m = a.test_wurzel, 0
                cmd = [py, PRUEFEN, "--stufe", "ISO", "--wurzel", wurzel, "--label-soll", lab]
            else:
                ps("Get-ChildItem '%s\\*.iso' | ForEach-Object { Dismount-DiskImage -ImagePath $_.FullName -ErrorAction SilentlyContinue | Out-Null }" % a.ziel)
                rc_m, aus, err = ps("$v = Mount-DiskImage -ImagePath '%s' -Access ReadOnly -PassThru | Get-Volume; Start-Sleep 2; "
                                    "(Get-DiskImage -ImagePath '%s' | Get-Volume).DriveLetter" % (iso, iso))
                bst = (aus.split() or [""])[-1]
                if rc_m != 0 or not re.match(r"^[A-Z]$", bst):
                    log("FEHLER Einbinden: rc %d | %s | %s" % (rc_m, aus, err))
                    tabelle.append(["D%d" % n, name, lab, os.path.basename(iso), "Einbinden fehlgeschlagen", "-"]); continue
                wurzel = bst + ":\\"
                cmd = [py, PRUEFEN, "--stufe", "ISO", "--wurzel", wurzel, "--image", iso, "--label-soll", lab]
            rc_i = lauf(log, cmd, skripte)
            if not a.test_wurzel:
                ps("Dismount-DiskImage -ImagePath '%s' | Out-Null" % iso)
            tabelle.append(["D%d" % n, name, lab, os.path.basename(iso), "BESTANDEN" if rc_i == 0 else "BEFUND (Exit %d)" % rc_i, "-"])
        log("")
        log("%-4s %-8s %-16s %-26s %-16s %s" % ("Disc", "Fassung", "Label", "ISO", "ISO-Pruefung", ""))
    for z in tabelle:
        log("%-4s %-8s %-16s %-26s %-16s %s" % tuple(z))
    ok = all((z[3] == "BRENNBEREIT" and z[4] == "BESTANDEN") or z[3] == "uebersprungen" for z in tabelle) \
        if a.schritt == "ORDNER" else all(z[4] == "BESTANDEN" for z in tabelle)
    log("ERGEBNIS: %s | Protokoll %s" % ("ALLE OK" if ok and tabelle else "NICHT ALLE OK - Protokoll an Claude", log.pfad))
    return 0 if ok and tabelle else 1


if __name__ == "__main__":
    sys.exit(main())
