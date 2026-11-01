#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mdisc_brennliste_v1.4.py - Projekt "Basisdaten ermitteln" (privat)
Version 1.5 | Stand 01.11.2026, 13:00 MEZ | Autor: Claude fuer Gunter Nembach

ZWECK
  Bereitet EINE M-DISC (Variante A, Vollkopie) aus D:\\Daten vor - wie v1.0 - und
  fuellt den freien Platz mit einer REDUNDANZSCHICHT (_Redundanz\\):
  Inhalte, die im Satz nur auf GENAU EINER anderen Disc liegen, werden zusaetzlich
  auf diese Disc gelegt (Grundsatz: wichtiger Inhalt auf >= 2 Discs je Satz).
    Modus "alle"    : alle Pfade des Bereichs (werkzeuglos wiederherstellbar)
    Modus "einzeln" : je Inhalt (SHA-256) ein Pfad, der kuerzeste; weitere Pfade
                      desselben Inhalts stehen in _MANIFEST\\Manifest_Gesamt.csv
  Fuellung nach Prioritaet bis --max-gib; Einheit ganz, sonst teilweise (dateiweise).

  Der Disc-Plan (welche Einheit auf welche Disc) bleibt wie bei D1: --planwert-gib 80.

SICHERHEIT
  - D:\\Daten wird nur gelesen; Hardlinks aendern keinen Inhalt.
  - NEU v1.3 (Regel Gunter 01.11.2026): Es wird NIE etwas umbenannt, ueberschrieben oder geloescht.
    Jede Ausfuehrung legt einen NEUEN Brennordner D<n>_V<k> an; k = naechste freie Fassung.
    Ein Altordner D<n> ohne Endung (v1.0/v1.1) zaehlt als V1 und bleibt unveraendert liegen.
    Zusammenstellung/ISO heissen <Label>_V<k>.dxp / .iso (Label selbst bleibt 15 Zeichen).
  - Jede Datei wird FRISCH gehasht (SHA-256) und gegen den Plan verglichen;
    Abweichung => NICHT_BRENNEN.txt, Exit 1.
  - Pfade > --max-pfad Zeichen (relativ) kommen NICHT in die Redundanzschicht (Pilot lange Pfade offen).
  - v1.2: Datei-/Ordnernamen > 127 UTF-16-Zeichen werden fuer die Disc deterministisch gekuerzt
    (<Anfang>~<8 hex>.<Endung>, <= --max-name Zeichen). Grund: CDBurnerXP/UDF kuerzt sonst stumm auf
    127 Zeichen (gemessen D2-ISO 31.10.2026: FEHLT 1 + EXTRA 1, E115). Originalpfad steht im
    Manifest (Pfad_Daten) und in _MANIFEST\\Kurznamen_D<n>.csv. Pfad-Kollision (Gross/klein) => Exit 2.
  - NEU v1.4: Primaerpfade > --max-pfad-disc (Standard 240) Zeichen werden deterministisch gekuerzt, damit
    D:\\_MDISC\\D<n>_V<k>\\ + Pfad unter 260 Zeichen bleibt (CDBurnerXP/Windows MAX_PATH; D4: 318 Pfade, D5: 47).
    Zuerst Ordnernamen (je Ordner gleich fuer alle Dateien darunter, Form <Anfang>~<6 hex>), dann der Dateiname.
    Bereich und Einheit (Ebene 1-2) bleiben unveraendert. Original steht wie bei v1.2 in Kurznamen_D<n>.csv.
  - NEU v1.4: --fremd <Datei> (mehrfach) fuer eine Disc AUSSERHALB des Plans (D6 = Google-Takeout-ZIP):
    Ziel <--fremd-ziel>\\<Elternordner>\\<Datei>; SHA-256 wird beim Anlegen frisch gebildet (keine Planreferenz),
    Pruefung der ZIP-Inhalte per CRC in mdisc_pruefen (ISO/DISC). Redundanzschicht wie bei Plan-Discs.
  - NEU v1.4: Redundanz-Standard je Disc nach Matrix v1.49 \xa74.3 (F14 = ja): D2 Vertraulich+Dokumente, D3 Vertraulich,
    D4 Pictures, D5 Pictures+Vertraulich+Dokumente, D6 Vertraulich+Dokumente.
  - NEU v1.5: Bekannte, dokumentierte Planabweichungen (Uebergabe v1.34 \xa72, Gesamtpruefung 29.10.2026: BEKANNT 2)
    werden uebernommen: Plan-SHA (T0) -> Ist-SHA (gemessen bei der Nachpruefung Teil 8). Nur wenn Plan_Nr UND Plan-SHA
    passen; die Datei wird trotzdem frisch gehasht und muss = Ist-SHA sein (sonst HASH wie bisher). Manifest und
    Manifest_Gesamt fuehren die Ist-SHA; Nachweis in _MANIFEST\\Planabweichungen_bekannt_D<n>.csv.
    Standardliste: G182396, G186791 (Google-Drive-.lnk). Andere Liste: --bekannt <CSV Nr;SHA_Plan;SHA_Ist;Beleg>.

AUFRUF (PowerShell, PC-Windows)
  cd D:\\_Berichte\\kopierplan\\skripte
  py mdisc_brennliste_v1.5.py --disc 3                     (Trockenlauf: Plan, Redundanz, kuenftiger Ordner; nichts angelegt)
  py mdisc_brennliste_v1.5.py --disc 3 --ausfuehren        (neuer Brennordner D:\\_MDISC\\D3_V<k> + Manifeste)
  py mdisc_brennliste_v1.5.py --disc 6 --fremd D:\\_Import\\...\\takeout-...zip [--fremd ...] [--ausfuehren]
  Optionen: --redundanz Vertraulich=alle --redundanz Dokumente=einzeln   (Standard fuer D2)
            --max-gib 81.3   --max-pfad 240   --label MDISC_D2_261101   --fassung 3 (nur wenn noetig)

AUSGABE
  D:\\_MDISC\\D<n>_V<k>\\ (Brennordner; _MANIFEST\\LIESMICH.txt enthaelt Zeilen "Label: ..." und "Fassung: ...")
  D:\\_Berichte\\mdisc\\brennliste_D<n>_V<k>_<Zeit>_zusammenfassung.txt, _brennplan.csv, _redundanz.csv

EXIT-CODES 0 OK | 1 Befund/Abweichung | 2 Aufruf-/Vorbedingungsfehler

VERSIONSPROTOKOLL
  1.0  30.10.2026, 11:15  Erstfassung
  1.1  31.10.2026, 20:30  Redundanzschicht, Fuellgrenze --max-gib, Label <= 16 Zeichen,
                          Manifest_Gesamt.csv + pruefen.py auf jeder Disc, Spalte Rolle im Manifest
  1.2  31.10.2026, 23:20  Namen > 127 UTF-16-Zeichen kuerzen (E115), Kurznamen_D<n>.csv, Spalte Gekuerzt,
                          Kollisionspruefung, pruefen.py = mdisc_pruefen_v1.2 (Fallback v1.1)
  1.3  01.11.2026, 00:15  Versionierte Brennordner D<n>_V<k> statt D<n> (nichts umbenennen/ueberschreiben),
                          --fassung, ISO/dxp-Name <Label>_V<k>, Zeile "Fassung:" in LIESMICH,
                          Berichtsnamen mit Fassung; Kopfkommentar korrigiert (stand faelschlich v1.1)
  1.4  01.11.2026, 12:14  Primaerpfade > --max-pfad-disc kuerzen (Ordner, dann Name), --fremd/--fremd-ziel (D6 Takeout),
                          Redundanz-Standard D2-D6 nach Matrix, Zeile "Pfade gekuerzt" in Zusammenfassung/LIESMICH
  1.5  01.11.2026, 13:00  Bekannte Planabweichungen (v1.34, G182396/G186791) uebernehmen statt NICHT_BRENNEN (D5_V1, E129);
                          --bekannt, Planabweichungen_bekannt_D<n>.csv, Zeile in Zusammenfassung/LIESMICH
"""
import argparse, csv, datetime as dt, hashlib, os, re, shutil, sys, time
from collections import OrderedDict, defaultdict

VERSION = "mdisc_brennliste_v1.5"
# v1.5: bekannte Planabweichungen (Plan_Nr -> SHA Plan T0, SHA Ist, Beleg); gemessen 29.10.2026 23:18 (Teil 8 v1.3, Nachpruefung)
BEKANNT_STANDARD = {
    "G182396": ("299d6459c64774db9e369a4d090010102fe101d72ab3b1590239c54deda7f42f",
                "18f71f143984078a174fdd0ab09bc87ebe2112400e9f41357fd370b19d600f0e",
                "Uebergabe v1.34 Abschnitt 2; Log Teil8 v1.3 LAUF 2026-10-29_2318 NACHPRUEFUNG; Drive-.lnk 29.10. 22:34:17 neu geschrieben"),
    "G186791": ("3b0eebedaf84fa14cc70eb065ad4f6882ceadc169ca05001d523e0239cd71f2a",
                "3aa804547cce8f05e8f0b5896a84041798a4fa08bccc2474688b413473139dc0",
                "Uebergabe v1.34 Abschnitt 2; Log Teil8 v1.3 LAUF 2026-10-29_2318 NACHPRUEFUNG; Drive-.lnk 29.10. 22:34:08 neu geschrieben"),
}
NAME_UDF = 127          # gemessen: CDBurnerXP 4.5.8 kuerzt Namen auf 127 UTF-16-Zeichen (D2, 31.10.2026)
BEREICHE = ["Reisen", "Pictures", "Videos", "Dokumente", "Vertraulich", "Medien_SW", "_Pruefen", "_Stand_T0"]
PLAENE = [
    "Kopierplan_Gesamt_Teil1_Reisen_2026-10-29_v1.2.csv",
    "Kopierplan_Gesamt_Teil2_Pictures_2026-10-29_v1.2.csv",
    "Kopierplan_Gesamt_Teil3_Videos_2026-10-29_v1.2.csv",
    "Kopierplan_Gesamt_Teil4_Dokumente_2026-10-29_v1.2.csv",
    "Kopierplan_Gesamt_Teil5_Vertraulich_2026-10-29_v1.2.csv",
    "Kopierplan_Gesamt_Teil6_Medien_SW_2026-10-29_v1.2.csv",
    "Kopierplan_Gesamt_Teil7__Pruefen_2026-10-29_v1.2.csv",
    "Kopierplan_Gesamt_Teil8_Snapshot_T0_2026-10-29_v1.3.csv",
]
# Prioritaet der Einheiten in der Redundanzschicht (Dokumentationspflichten zuerst, dann klein vor gross)
# Beispiel-Prioritaet (sanitisiert fuer die Veroeffentlichung; im Original die eigene Ordnerliste)
PRIO_STANDARD = ["040_Steuer", "300_Landwirtschaft", "100_PV_Anlagen", "020_Bauen_Projekte",
                 "030_Beruf", "200_Info_Wissen_Know_How", "500_EDV_IT_Computer"]
REDUNDANZ_STANDARD = {2: ["Vertraulich=alle", "Dokumente=einzeln"], 3: ["Vertraulich=alle"], 4: ["Pictures=einzeln"],
                      5: ["Pictures=einzeln", "Vertraulich=alle", "Dokumente=einzeln"], 6: ["Vertraulich=alle", "Dokumente=einzeln"]}
RED = "_Redundanz"
GIB = 2**30
BLOCK = 8 * 2**20
MANIFEST_RESERVE = 64 * 2**20   # Manifest_Gesamt + Manifest + Skripte (geschaetzt, wird gemessen)
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


def u16(t):
    return len(t.encode("utf-16-le")) // 2


def fassungen(ziel, disc):
    """Vorhandene Fassungen von disc in ziel: {k: Ordnername}. Altordner 'D<n>' ohne Endung = V1."""
    gef = {}
    if not os.path.isdir(ziel):
        return gef
    muster = re.compile(r"^%s_V(\d+)$" % re.escape(disc), re.I)
    for n in sorted(os.listdir(ziel)):
        if not os.path.isdir(os.path.join(ziel, n)):
            continue
        if n.lower() == disc.lower():
            gef.setdefault(1, n)
        m = muster.match(n)
        if m:
            gef[int(m.group(1))] = n
    return gef


def kurzname(name, max_name, grenze=NAME_UDF):
    """Deterministisch: nur Namen > grenze (Standard 127) UTF-16-Zeichen werden auf <= max_name gekuerzt."""
    if u16(name) <= grenze:
        return name
    stamm, ext = os.path.splitext(name)
    if u16(ext) > 16 or not stamm:
        stamm, ext = name, ""
    h = "~" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    rest = max_name - u16(h) - u16(ext)
    k = stamm
    while u16(k) > rest or k.endswith((" ", ".")):
        k = k[:-1]
    return k + h + ext


def kurzpfad(rel, max_name):
    return "\\".join(kurzname(t, max_name) for t in rel.split("\\"))


def kurzordner(name, ziel):
    """v1.4: Ordnername deterministisch auf <= ziel Zeichen: <Anfang>~<6 hex SHA-256 des Originals>."""
    if u16(name) <= ziel:
        return name
    h = "~" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:6]
    k = name
    while u16(k) > ziel - u16(h) or k.endswith((" ", ".")):
        k = k[:-1]
    return k + h


def pfade_kuerzen(prim, max_pfad, max_name):
    """v1.4: Primaerpfade > max_pfad kuerzen, so wenig wie moeglich.
    Gierig je zu langer Datei (laengste zuerst): den aktuell laengsten Ordnernamen ab Ebene 3 (unter Bereich\\Einheit)
    auf das noetige Mass kuerzen (mind. 16 Zeichen, Form <Anfang>~<6 hex>). Die Kuerzung gilt je Ordner einheitlich
    fuer alle Dateien darunter (Zuordnung Ordnerpfad -> Kurzname). Reicht das nicht, wird der Dateiname gekuerzt.
    Rueckgabe: (Zahl zu lang vorher, gekuerzte Ordner, gekuerzte Dateinamen, Rest)."""
    vorher = [z for z in prim if len(z["dst"]) > max_pfad]
    if not vorher:
        return 0, 0, 0, []
    basis = {id(z): z["dst"] for z in prim}
    karte = {}

    def bauen(z):
        t = z["rel"].split("\\")
        d = basis[id(z)].split("\\")
        for i in range(2, len(t) - 1):
            k = "\\".join(t[:i + 1]).lower()
            if k in karte:
                d[i] = karte[k]
        return "\\".join(d)

    for z in sorted(vorher, key=lambda z: (-len(z["dst"]), z["rel"])):
        while True:
            cur = bauen(z)
            if len(cur) <= max_pfad:
                break
            t = z["rel"].split("\\")
            d = cur.split("\\")
            kand = [(u16(d[i]), -i) for i in range(2, len(t) - 1) if u16(d[i]) > 16]
            if not kand:
                break
            lang_, mi = max(kand)
            i = -mi
            ziel = max(16, lang_ - (len(cur) - max_pfad))
            karte["\\".join(t[:i + 1]).lower()] = kurzordner(t[i], ziel)
    for z in prim:
        z["dst"] = bauen(z)
    n_name = 0
    for z in prim:
        if len(z["dst"]) > max_pfad:
            d = z["dst"].split("\\")
            ziel = max(24, u16(d[-1]) - (len(z["dst"]) - max_pfad))
            d[-1] = kurzname(d[-1], min(ziel, max_name), grenze=ziel)
            z["dst"] = "\\".join(d)
            n_name += 1
    rest = [z["dst"] for z in prim if len(z["dst"]) > max_pfad]
    return len(vorher), len(karte), n_name, rest


def plan_laden(ordner, praefix):
    zeilen = []
    pl = praefix.rstrip("\\") + "\\"
    for name in PLAENE:
        p = os.path.join(ordner, name)
        if not os.path.isfile(p):
            raise SystemExit("FEHLER: Plan fehlt: %s" % p)
        with open(p, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                ziel = r["Ziel"]
                if not ziel.startswith(pl):
                    raise SystemExit("FEHLER: Ziel ausserhalb %s: %s" % (pl, ziel))
                rel = ziel[len(pl):]
                teile = rel.split("\\")
                if len(teile) < 3:
                    raise SystemExit("FEHLER: Datei direkt unter dem Bereich (keine Einheit): %s" % ziel)
                hl = r.get("Hardlink_auf", "") or ""
                zeilen.append(dict(bereich=teile[0], einheit=teile[1], rel=rel, bytes=int(r["Bytes"]),
                                   sha=r["SHA256"].lower(), nr=r["Nr"], aktion=r["Aktion"],
                                   mtime_ns=int(r["mtime_ns"] or 0),
                                   hl=hl[len(pl):] if hl.startswith(pl) else hl))
    return zeilen


def disc_plan(zeilen, planwert):
    einheiten = OrderedDict()
    for b in BEREICHE:
        for z in sorted((z for z in zeilen if z["bereich"] == b), key=lambda z: z["einheit"]):
            e = einheiten.setdefault((b, z["einheit"]), dict(n=0, bytes=0))
            e["n"] += 1
            e["bytes"] += z["bytes"]
    rest = {z["bereich"] for z in zeilen} - set(BEREICHE)
    if rest:
        raise SystemExit("FEHLER: unbekannte Bereiche %s" % rest)
    discs, akt, summe = [], [], 0
    for key, e in einheiten.items():
        if e["bytes"] > planwert:
            raise SystemExit("FEHLER: Einheit %s/%s groesser als Planwert (%.2f GiB)" % (key[0], key[1], e["bytes"] / GIB))
        if akt and summe + e["bytes"] > planwert:
            discs.append(akt)
            akt, summe = [], 0
        akt.append(key)
        summe += e["bytes"]
    if akt:
        discs.append(akt)
    return einheiten, discs


def redundanz_auswahl(zeilen, disc, regeln, budget, max_pfad, prio, max_name=120):
    """Rueckgabe: (gewaehlt: Liste Zeilen-Kopien mit Feld 'dst', bericht: Liste Zeilen)."""
    auf = defaultdict(set)
    for z in zeilen:
        auf[z["sha"]].add(z["disc"])
    gewaehlt, bericht, rest, gesehen = [], [], budget, set()
    for regel in regeln:
        bereich, _, modus = regel.partition("=")
        if bereich not in BEREICHE or modus not in ("alle", "einzeln"):
            raise SystemExit("FEHLER: Regel %s (Form Bereich=alle|einzeln)" % regel)
        kand = [z for z in zeilen if z["bereich"] == bereich and z["disc"] != disc]
        if modus == "einzeln":
            rep = {}
            for z in kand:
                if len(auf[z["sha"]]) != 1:
                    continue        # Inhalt liegt schon auf >= 2 Discs des Satzes
                k = (len(z["rel"]), z["aktion"] != "KOPIE", z["rel"])
                if z["sha"] not in rep or k < rep[z["sha"]][0]:
                    rep[z["sha"]] = (k, z)
            kand = [v[1] for v in rep.values()]
        einheiten = defaultdict(list)
        for z in kand:
            einheiten[z["einheit"]].append(z)
        reihe = [e for e in prio if e in einheiten] + sorted(e for e in einheiten if e not in prio)
        for e in reihe:
            dateien = sorted(einheiten[e], key=lambda z: z["rel"])
            n_ok = b_ok = n_lang = n_platz = b_platz = 0
            for z in dateien:
                dst = RED + "\\" + kurzpfad(z["rel"], max_name)
                key = dst.lower()
                if key in gesehen:
                    continue
                if len(dst) > max_pfad:
                    n_lang += 1
                    continue
                if z["bytes"] > rest:
                    n_platz += 1
                    b_platz += z["bytes"]
                    continue
                gesehen.add(key)
                gewaehlt.append(dict(z, dst=dst))
                rest -= z["bytes"]
                n_ok += 1
                b_ok += z["bytes"]
            status = "VOLL" if not (n_lang or n_platz) else ("TEILWEISE" if n_ok else "AUSGELASSEN")
            bericht.append([bereich, e, modus, len(dateien), sum(z["bytes"] for z in dateien), n_ok, b_ok,
                            n_lang, n_platz, b_platz, status])
    return gewaehlt, bericht


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


def utc_iso(ns):
    return dt.datetime.fromtimestamp(ns / 1e9, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ns else ""


PRUEFEN_PS1 = r'''# pruefen.ps1 (mdisc_pruefen_v1.1, ps1) - liest diese Disc und vergleicht SHA-256 gegen das Manifest. Nur lesen.
# Aufruf: powershell -ExecutionPolicy Bypass -File <Disc>:\_MANIFEST\pruefen.ps1
param([string]$Wurzel = '', [string]$Manifest = '', [string]$Bericht = '')
$Version = 'mdisc_pruefen_v1.1 (ps1)'
if (-not $Wurzel) { $Wurzel = Split-Path -Parent $PSScriptRoot }
if (-not $Manifest) { $Manifest = (Get-ChildItem -LiteralPath (Join-Path $Wurzel '_MANIFEST') -Filter 'Manifest_D*.csv' | Select-Object -First 1).FullName }
if (-not $Bericht) { if (Test-Path -LiteralPath 'D:\_Berichte\mdisc') { $Bericht = 'D:\_Berichte\mdisc' } else { $Bericht = $env:TEMP } }
"$Version  $(Get-Date -Format 'dd.MM.yyyy HH:mm:ss')"
"Wurzel $Wurzel | Manifest $Manifest"
$rows = @(Import-Csv -LiteralPath $Manifest -Delimiter ';' -Encoding UTF8)
$soll = @{}; $erg = New-Object System.Collections.Generic.List[object]
$z = @{OK=0; FEHLT=0; GROESSE=0; HASH=0; LESEFEHLER=0; EXTRA=0}
$t0 = Get-Date; $i = 0
foreach ($r in $rows) {
    $i++; $p = Join-Path $Wurzel $r.Pfad; $soll[$r.Pfad.ToLower()] = 1; $st = 'OK'; $info = ''
    try {
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { $st = 'FEHLT' }
        else {
            $len = (Get-Item -LiteralPath $p).Length
            if ($len -ne [int64]$r.Bytes) { $st = 'GROESSE'; $info = "$len" }
            else { $h = (Get-FileHash -LiteralPath $p -Algorithm SHA256 -ErrorAction Stop).Hash.ToLower(); if ($h -ne $r.SHA256) { $st = 'HASH'; $info = $h } }
        }
    } catch { $st = 'LESEFEHLER'; $info = $_.Exception.Message }
    $z[$st]++
    if ($st -ne 'OK') { $erg.Add([pscustomobject]@{Pfad=$r.Pfad; Status=$st; Info=$info}) }
    if ($i % 500 -eq 0) { Write-Progress -Activity 'pruefen' -Status "$i / $($rows.Count)" -PercentComplete (100 * $i / $rows.Count) }
}
$mdir = (Join-Path $Wurzel '_MANIFEST').ToLower()
Get-ChildItem -LiteralPath $Wurzel -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Wurzel.TrimEnd('\').Length + 1)
    if (-not $_.FullName.ToLower().StartsWith($mdir) -and -not $soll.ContainsKey($rel.ToLower())) { $z['EXTRA']++; $erg.Add([pscustomobject]@{Pfad=$rel; Status='EXTRA'; Info=''}) }
}
$dauer = [int]((Get-Date) - $t0).TotalSeconds
$fehler = $z.FEHLT + $z.GROESSE + $z.HASH + $z.LESEFEHLER + $z.EXTRA
$ts = Get-Date -Format 'yyyy-MM-dd_HHmm'
$csv = Join-Path $Bericht ("pruefen_ps1_{0}.csv" -f $ts)
$erg | Export-Csv -LiteralPath $csv -Delimiter ';' -NoTypeInformation -Encoding UTF8
"Dateien {0} | OK {1} | FEHLT {2} | GROESSE {3} | HASH {4} | LESEFEHLER {5} | EXTRA {6} | Dauer {7} s" -f $rows.Count, $z.OK, $z.FEHLT, $z.GROESSE, $z.HASH, $z.LESEFEHLER, $z.EXTRA, $dauer
if ($fehler -eq 0) { 'ERGEBNIS: BESTANDEN' } else { "ERGEBNIS: BEFUND ($fehler)  Liste: $csv" }
if ($fehler -eq 0) { exit 0 } else { exit 1 }
'''

LIESMICH = """M-DISC {disc} - Langzeitsicherung D:\\Daten (Gunter Nembach, privat)
Label: {label} | Erstellt: {zeit} | Werkzeug: {version} | Variante A (Vollkopie, jeder Pfad als Datei)
Fassung: {fassung} | Brennordner {ordner} | Zusammenstellung/ISO {iso}.dxp / {iso}.iso
Inhalt: {n} Dateien, {bytes} Bytes ({gib:.2f} GiB)
  Primaer:    {n_p} Dateien, {gib_p:.2f} GiB  (Bereiche/Einheiten laut Brennplan)
  Redundanz:  {n_r} Dateien, {gib_r:.2f} GiB  im Ordner _Redundanz\\ (Kopien von Inhalten, deren
              Hauptablage auf einer ANDEREN Disc liegt; Liste in _MANIFEST\\Redundanz_{disc}.csv)
Quelle: D:\\Daten, Stand Gesamtpruefung 29.10.2026 23:47 (VollHash BESTANDEN).{fremd_txt}{bek_txt}

Wiederherstellen:
  Primaerdaten: Ordner direkt kopieren.
  Redundanz "alle": _Redundanz\\<Bereich>\\... ist vollstaendig (alle Pfade).
  Redundanz "einzeln": je Inhalt ein Pfad; weitere Pfade desselben Inhalts (gleiche SHA256)
    in _MANIFEST\\Manifest_Gesamt.csv - Datei kopieren und unter diesem Namen ablegen.
  Gekuerzte Namen/Pfade ({n_k} Dateien): Namen ueber 127 Zeichen sind auf der Disc als <Anfang>~<8 hex>.<Endung>
    abgelegt (UDF/CDBurnerXP-Grenze); Pfade ueber {max_pfad} Zeichen haben gekuerzte Ordnernamen <Anfang>~<6 hex>
    (Windows MAX_PATH). Originalpfad: _MANIFEST\\Kurznamen_{disc}.csv bzw. Spalte Pfad_Daten.

Pruefen (nur lesen):
  Windows:  powershell -ExecutionPolicy Bypass -File <Laufwerk>:\\_MANIFEST\\pruefen.ps1
            oder py <Laufwerk>:\\_MANIFEST\\pruefen.py --stufe DISC --wurzel <Laufwerk>:\\ --satz A
  Linux:    cd <Mountpunkt> && sha256sum -c --quiet _MANIFEST/Manifest_{disc}.sha256
  Soll: alle Dateien OK, keine Meldung.

Dateien in _MANIFEST:
  Manifest_{disc}.csv      Pfad;Bytes;SHA256;mtime_utc;Plan_Nr;Aktion;Rolle;Pfad_Daten;Gekuerzt (UTF-8, Semikolon)
  Kurznamen_{disc}.csv     gekuerzte Disc-Pfade mit Originalpfad
  Manifest_{disc}.sha256   dieselben Pruefsummen im Format von sha256sum
  Manifest_Gesamt.csv      alle Pfade von D:\\Daten mit Disc-Zuordnung (Stand {datum})
  Brennplan_Stand_{datum}.csv  Einteilung aller Discs
  Redundanz_{disc}.csv     Auswahl der Redundanzschicht je Einheit
  Pruefsummen_Manifest.txt SHA-256 der Manifestdateien
Satz (A im Haus / B ausser Haus) steht auf dem Innenring der Disc, nicht im Inhalt.
"""


def main():
    ap = argparse.ArgumentParser(description=VERSION)
    ap.add_argument("--disc", type=int, required=True)
    ap.add_argument("--daten", default=r"D:\Daten")
    ap.add_argument("--plan-praefix", default=r"D:\Daten")
    ap.add_argument("--plaene", default=r"D:\_Berichte\kopierplan")
    ap.add_argument("--ziel", default=r"D:\_MDISC")
    ap.add_argument("--out", default=r"D:\_Berichte\mdisc")
    ap.add_argument("--planwert-gib", type=float, default=80.0, help="Disc-Einteilung (wie D1, nicht aendern)")
    ap.add_argument("--max-gib", type=float, default=81.3, help="Fuellgrenze inkl. Redundanz (D1-V1 = 81,38 GiB ISO)")
    ap.add_argument("--kapazitaet-gib", type=float, default=90.23, help="gemessen T0 30.10.2026")
    ap.add_argument("--redundanz", action="append", default=None, help="Bereich=alle|einzeln (mehrfach)")
    ap.add_argument("--max-pfad", type=int, default=240, help="Redundanzschicht: laengere Pfade auslassen")
    ap.add_argument("--max-pfad-disc", type=int, default=240, help="v1.4: Primaerpfade auf <= so viele Zeichen kuerzen")
    ap.add_argument("--fremd", action="append", default=[], help="v1.4: Datei ausserhalb des Plans (absolut), mehrfach; nur fuer Disc > Plan")
    ap.add_argument("--fremd-ziel", default="_Google_Takeout", help="v1.4: Zielordner der --fremd-Dateien auf der Disc")
    ap.add_argument("--max-name", type=int, default=120, help="Kuerzungsziel fuer Namen > 127 UTF-16-Zeichen (E115)")
    ap.add_argument("--label", default="")
    ap.add_argument("--fassung", type=int, default=0, help="Fassung V<k> erzwingen (Standard: naechste freie)")
    ap.add_argument("--bekannt", default="", help="v1.5: CSV Nr;SHA_Plan;SHA_Ist;Beleg statt Standardliste (v1.34)")
    ap.add_argument("--ausfuehren", action="store_true")
    a = ap.parse_args()
    modus = "AUSFUEHREN" if a.ausfuehren else "TROCKENLAUF"
    print(VERSION, "Start", jetzt(), "|", modus, flush=True)
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    datum = dt.datetime.now().strftime("%Y-%m-%d")
    os.makedirs(a.out, exist_ok=True)
    disc = "D%d" % a.disc
    label = a.label or "MDISC_%s_%s" % (disc, dt.datetime.now().strftime("%y%m%d"))
    if len(label) > 16:
        print("FEHLER: Label %s hat %d Zeichen; CDBurnerXP kuerzt auf 16 (D1: MDISC_D1_2026103)" % (label, len(label))); return 2
    # ---- Fassung (v1.3): nie umbenennen/ueberschreiben, immer neuer Ordner D<n>_V<k>
    vorhanden = fassungen(a.ziel, disc)
    fas = a.fassung or (max(vorhanden) + 1 if vorhanden else 1)
    if fas < 1:
        print("FEHLER: --fassung muss >= 1 sein"); return 2
    fas_name = "%s_V%d" % (disc, fas)
    zielwurzel = os.path.join(a.ziel, fas_name)
    iso_name = "%s_V%d" % (label, fas)
    if fas in vorhanden or os.path.exists(zielwurzel):
        print("FEHLER: Fassung %s existiert bereits (%s) - nichts angelegt, nichts umbenannt" % (fas_name, vorhanden.get(fas, zielwurzel))); return 2
    regeln = a.redundanz if a.redundanz is not None else REDUNDANZ_STANDARD.get(a.disc, [])
    if a.planwert_gib != 80.0:
        print("WARNUNG: --planwert-gib %.1f weicht von D1 (80) ab -> Disc-Einteilung verschiebt sich" % a.planwert_gib)
    if a.max_gib > a.kapazitaet_gib - 1:
        print("FEHLER: --max-gib groesser als Kapazitaet minus 1 GiB"); return 2

    zeilen = plan_laden(a.plaene, a.plan_praefix)
    # ---- v1.5: bekannte Planabweichungen uebernehmen (nur bei passender Plan_Nr UND Plan-SHA, sonst Abbruch)
    bekannt = dict(BEKANNT_STANDARD)
    if a.bekannt:
        bekannt = {}
        with open(a.bekannt, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                bekannt[r["Nr"]] = (r["SHA_Plan"].lower(), r["SHA_Ist"].lower(), r.get("Beleg", ""))
    nr_idx = defaultdict(list)
    for z in zeilen:
        if z["nr"] in bekannt:
            nr_idx[z["nr"]].append(z)
    bek_fehler = ["%s fehlt im Plan" % n for n in bekannt if not nr_idx.get(n)]
    bek_fehler += ["%s %d Planzeilen" % (n, len(v)) for n, v in nr_idx.items() if len(v) != 1]
    bek_fehler += ["%s Plan-SHA %s... <> Liste %s..." % (n, v[0]["sha"][:12], bekannt[n][0][:12])
                   for n, v in nr_idx.items() if len(v) == 1 and v[0]["sha"] != bekannt[n][0]]
    if bek_fehler:
        print("FEHLER: bekannte Planabweichungen passen nicht zum Plan, nichts angelegt: " + " | ".join(bek_fehler)); return 2
    bek_treffer = []
    for n, (sp, si, bel) in bekannt.items():
        z = nr_idx[n][0]
        z["sha_plan"], z["sha"], z["beleg"] = sp, si, bel
        bek_treffer.append(z)
    einheiten, discs = disc_plan(zeilen, a.planwert_gib * GIB)
    if a.fremd:
        if a.disc <= len(discs):
            print("FEHLER: --fremd nur fuer eine Disc ausserhalb des Plans (> %d)" % len(discs)); return 2
    elif not 1 <= a.disc <= len(discs):
        print("FEHLER: Disc %d gibt es im Plan nicht (1..%d); Discs ausserhalb des Plans nur mit --fremd" % (a.disc, len(discs))); return 2
    dmap = {k: "D%d" % i for i, d in enumerate(discs, 1) for k in d}
    for z in zeilen:
        z["disc"] = dmap[(z["bereich"], z["einheit"])]

    zus = ["%s | %s | %s | Label %s" % (VERSION, jetzt(), modus, label),
           "Fassung %s | Brennordner %s | vorhandene Fassungen: %s | Zusammenstellung/ISO %s.dxp / %s.iso" % (
               fas_name, zielwurzel, ", ".join("V%d=%s" % (k, v) for k, v in sorted(vorhanden.items())) or "keine",
               iso_name, iso_name),
           "Planzeilen %d | %.2f GiB | Planwert %.1f GiB | Fuellgrenze %.2f GiB | Kapazitaet %.2f GiB | Redundanz %s" % (
               len(zeilen), sum(z["bytes"] for z in zeilen) / GIB, a.planwert_gib, a.max_gib, a.kapazitaet_gib,
               ", ".join(regeln) or "keine"), ""]
    rows_plan = []
    for i, d in enumerate(discs, 1):
        b = sum(einheiten[k]["bytes"] for k in d)
        n = sum(einheiten[k]["n"] for k in d)
        zus.append("D%d: %3d Einheiten %7d Dateien %7.2f GiB  %s/%s ... %s/%s" % (i, len(d), n, b / GIB, d[0][0], d[0][1], d[-1][0], d[-1][1]))
        for k in d:
            rows_plan.append(["D%d" % i, k[0], k[1], einheiten[k]["n"], einheiten[k]["bytes"]])
    plan_csv = os.path.join(a.out, "brennliste_%s_%s_brennplan.csv" % (fas_name, ts))
    with open(plan_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Disc", "Bereich", "Einheit", "Dateien", "Bytes"])
        w.writerows(rows_plan)

    if not 20 <= a.max_name <= NAME_UDF:
        print("FEHLER: --max-name 20..%d" % NAME_UDF); return 2
    prim = [dict(z, dst=kurzpfad(z["rel"], a.max_name), rolle="PRIMAER") for z in zeilen if z["disc"] == disc]
    fremd = []
    for i, p in enumerate(a.fremd, 1):
        if not os.path.isfile(lang(p)):
            print("FEHLER: --fremd Datei fehlt: %s" % p); return 2
        s = os.stat(lang(p))
        eltern = os.path.basename(os.path.dirname(os.path.abspath(p))) or "Quelle"
        rel = "%s\\%s\\%s" % (a.fremd_ziel, eltern, os.path.basename(p))
        fremd.append(dict(bereich=a.fremd_ziel, einheit=eltern, rel=rel, bytes=s.st_size, sha="", nr="F%d" % i,
                          aktion="FREMD", mtime_ns=s.st_mtime_ns, hl="", disc=disc, src=os.path.abspath(p),
                          dst=kurzpfad(rel, a.max_name), rolle="PRIMAER"))
    prim += fremd
    prim.sort(key=lambda z: (BEREICHE.index(z["bereich"]) if z["bereich"] in BEREICHE else len(BEREICHE), z["rel"]))
    if fremd:
        zus.append("%s (ausserhalb Plan, --fremd): %d Dateien %.2f GiB nach %s\\ (SHA-256 wird beim Anlegen gebildet)" % (
            disc, len(fremd), sum(z["bytes"] for z in fremd) / GIB, a.fremd_ziel))
        for z in fremd:
            zus.append("  FREMD %s  %d B  <-  %s" % (z["dst"], z["bytes"], z["src"]))
    p_bytes = sum(z["bytes"] for z in prim)
    budget = int(a.max_gib * GIB) - p_bytes - MANIFEST_RESERVE
    red, bericht = redundanz_auswahl(zeilen, disc, regeln, max(budget, 0), a.max_pfad, PRIO_STANDARD, a.max_name)
    for z in red:
        z["rolle"] = "REDUNDANZ"
    r_bytes = sum(z["bytes"] for z in red)
    red_csv = os.path.join(a.out, "brennliste_%s_%s_redundanz.csv" % (fas_name, ts))
    kopf = ["Bereich", "Einheit", "Modus", "Kandidaten", "Kand_Bytes", "Gewaehlt", "Gew_Bytes",
            "Pfad_zu_lang", "Kein_Platz", "Kein_Platz_Bytes", "Status"]
    with open(red_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(kopf)
        w.writerows(bericht)
    zus += ["", "Gewaehlt %s: Primaer %d Dateien %.2f GiB | Redundanz %d Dateien %.2f GiB | Summe %.2f GiB (Grenze %.2f)" % (
        disc, len(prim), p_bytes / GIB, len(red), r_bytes / GIB, (p_bytes + r_bytes) / GIB, a.max_gib)]
    for b in bericht:
        zus.append("  R %-11s %-34s %-7s %5d/%5d Dateien %6.2f/%6.2f GiB  lang %d  Platz %d  %s" % (
            b[0], b[1][:34], b[2], b[5], b[3], b[6] / GIB, b[4] / GIB, b[7], b[8], b[10]))
    n_lang, n_ord, n_nam, rest_lang = pfade_kuerzen(prim, a.max_pfad_disc, a.max_name)
    zus.append("Primaer-Pfade > %d Zeichen (relativ): vorher %d | gekuerzt: %d Ordner, %d Dateinamen | danach > %d: %d" % (
        a.max_pfad_disc, n_lang, n_ord, n_nam, a.max_pfad_disc, len(rest_lang)))
    for d_ in rest_lang[:10]:
        zus.append("  ZU_LANG  %s" % d_)
    # ---- Namen > 127 (E115): Kuerzung, Restpruefung, Kollisionen
    kurz = [z for z in prim + red if z["dst"] != (RED + "\\" + z["rel"] if z["rolle"] == "REDUNDANZ" else z["rel"])]
    zu_lang = [z["dst"] for z in prim + red if max(u16(t) for t in z["dst"].split("\\")) > NAME_UDF]
    gesehen, koll = {}, []
    for z in prim + red:
        k = z["dst"].lower()
        if k in gesehen:
            koll.append((gesehen[k], z["rel"], z["dst"]))
        gesehen[k] = z["rel"]
    kid = {id(z) for z in kurz}
    for z in prim + red:
        z["gekuerzt"] = "ja" if id(z) in kid else ""
    n_n127 = sum(1 for z in prim + red if max(u16(x) for x in z["rel"].split("\\")) > NAME_UDF)
    bek_disc = [z for z in bek_treffer if z["disc"] == disc]
    zus.append("Bekannte Planabweichungen (v1.34) uebernommen: %d im Plan, davon %d auf %s (Ist-SHA statt Plan-SHA, frisch nachgeprueft)" % (
        len(bek_treffer), len(bek_disc), disc))
    for z in bek_disc:
        zus.append("  BEKANNT  %s  %s  Plan %s... -> Ist %s..." % (z["nr"], z["rel"], z["sha_plan"][:12], z["sha"][:12]))
    zus.append("Namen > %d UTF-16-Zeichen gekuerzt (auf <= %d): %d Dateien | danach > %d: %d | Kollisionen: %d" % (
        NAME_UDF, a.max_name, n_n127, NAME_UDF, len(zu_lang), len(koll)))
    zus.append("Disc-Pfad weicht vom Pfad in D:\\Daten ab (Kurznamen_%s.csv): %d Dateien (Primaer %d, Redundanz %d)" % (
        disc, len(kurz), sum(1 for z in kurz if z["rolle"] == "PRIMAER"), sum(1 for z in kurz if z["rolle"] == "REDUNDANZ")))
    for z in kurz[:10]:
        zus.append("  KURZ  %s  <-  %s" % (z["dst"].split("\\")[-1], z["rel"].split("\\")[-1]))
    for z in [z for z in prim if z["dst"].split("\\")[:-1] != z["rel"].split("\\")[:-1]][:3]:
        zus.append("  PFAD  %s  <-  %s" % (z["dst"], z["rel"]))
    for k1, k2, d_ in koll[:10]:
        zus.append("  KOLLISION  %s  |  %s  ->  %s" % (k1, k2, d_))
    if zu_lang or koll or rest_lang:
        zus.append("ERGEBNIS: FEHLER - Namen/Pfade zu lang oder Pfad-Kollision, nichts angelegt")
        print("\n".join(zus)); return 2
    print("\n".join(zus), flush=True)
    if not a.ausfuehren:
        zus.append("TROCKENLAUF: nichts angelegt. Ausfuehren legt NEU an: %s | Plan: %s | Redundanz: %s" % (zielwurzel, plan_csv, red_csv))
        open(os.path.join(a.out, "brennliste_%s_%s_zusammenfassung.txt" % (fas_name, ts)), "w", encoding="utf-8-sig").write("\n".join(zus) + "\n")
        print(zus[-1]); return 0

    # ---------------- Ausfuehren
    if IST_WIN and os.path.splitdrive(os.path.abspath(a.ziel))[0].lower() != os.path.splitdrive(os.path.abspath(a.daten))[0].lower():
        print("FEHLER: Ziel und D:\\Daten muessen auf demselben Laufwerk liegen (Hardlinks)"); return 2
    mdir = os.path.join(zielwurzel, "_MANIFEST")
    os.makedirs(mdir)            # wirft Fehler, falls der Ordner inzwischen existiert (kein Ueberschreiben)
    cache, man, befund = {}, [], []
    t0 = letzte = time.time()
    gelesen = 0
    alle = prim + red
    for i, z in enumerate(alle, 1):
        src = z.get("src") or os.path.join(a.daten, z["rel"].replace("\\", os.sep))
        dst = os.path.join(zielwurzel, z["dst"].replace("\\", os.sep))
        st = "OK"
        try:
            s = os.stat(lang(src))
            if s.st_size != z["bytes"]:
                st = "GROESSE"
            else:
                key = (s.st_dev, s.st_ino)
                if key in cache and s.st_ino:
                    sha = cache[key]
                else:
                    sha, n = sha_datei(src)
                    gelesen += n
                    cache[key] = sha
                if not z["sha"]:
                    z["sha"] = sha          # --fremd: keine Planreferenz, Hash frisch gebildet
                elif sha != z["sha"]:
                    st = "HASH"
            os.makedirs(lang(os.path.dirname(dst)), exist_ok=True)
            os.link(lang(src), lang(dst))
        except FileNotFoundError:
            st = "FEHLT"
        except OSError as e:
            st = "FEHLER [%s] %s" % (getattr(e, "winerror", None) or e.errno, e.strerror)
        if st != "OK":
            befund.append((z["dst"], st))
        man.append(z)
        if time.time() - letzte > 5:
            letzte = time.time()
            print("  %d/%d Dateien, %.2f GiB gehasht, %.0f s" % (i, len(alle), gelesen / GIB, time.time() - t0), flush=True)

    mcsv = os.path.join(mdir, "Manifest_%s.csv" % disc)
    with open(mcsv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Pfad", "Bytes", "SHA256", "mtime_utc", "Plan_Nr", "Aktion", "Rolle", "Pfad_Daten", "Gekuerzt"])
        for z in man:
            w.writerow([z["dst"], z["bytes"], z["sha"], utc_iso(z["mtime_ns"]), z["nr"], z["aktion"], z["rolle"], z["rel"],
                        z["gekuerzt"]])
    with open(os.path.join(mdir, "Kurznamen_%s.csv" % disc), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Pfad_Disc", "Pfad_Daten", "Bytes", "SHA256"])
        for z in man:
            if z["gekuerzt"]:
                w.writerow([z["dst"], z["rel"], z["bytes"], z["sha"]])
    msha = os.path.join(mdir, "Manifest_%s.sha256" % disc)
    with open(msha, "w", newline="\n", encoding="utf-8") as fh:
        for z in man:
            fh.write("%s  %s\n" % (z["sha"], z["dst"].replace("\\", "/")))
    red_sha = {z["sha"] for z in red}
    with open(os.path.join(mdir, "Manifest_Gesamt.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Pfad_Daten", "Bytes", "SHA256", "mtime_utc", "Plan_Nr", "Aktion", "Hardlink_auf", "Disc_primaer",
                    "Redundanz_auf_%s" % disc])
        for z in zeilen:
            w.writerow([z["rel"], z["bytes"], z["sha"], utc_iso(z["mtime_ns"]), z["nr"], z["aktion"], z["hl"], z["disc"],
                        "ja" if z["sha"] in red_sha else ""])
        for z in fremd:
            w.writerow([z["src"], z["bytes"], z["sha"], utc_iso(z["mtime_ns"]), z["nr"], z["aktion"], "", disc, ""])
    with open(os.path.join(mdir, "Brennplan_Stand_%s.csv" % datum), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Disc", "Bereich", "Einheit", "Dateien", "Bytes"])
        w.writerows(rows_plan)
    bek_man = [z for z in man if "sha_plan" in z]
    if bek_man:
        with open(os.path.join(mdir, "Planabweichungen_bekannt_%s.csv" % disc), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["Plan_Nr", "Pfad", "Pfad_Daten", "Bytes", "SHA_Plan_T0", "SHA_Ist_Disc", "Rolle", "Beleg"])
            for z in bek_man:
                w.writerow([z["nr"], z["dst"], z["rel"], z["bytes"], z["sha_plan"], z["sha"], z["rolle"], z["beleg"]])
    with open(os.path.join(mdir, "Redundanz_%s.csv" % disc), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(kopf)
        w.writerows(bericht)
    with open(os.path.join(mdir, "pruefen.ps1"), "w", newline="\r\n", encoding="utf-8-sig") as fh:
        fh.write(PRUEFEN_PS1)
    for v in ("mdisc_pruefen_v1.2.py", "mdisc_pruefen_v1.1.py"):
        py = os.path.join(os.path.dirname(os.path.abspath(__file__)), v)
        if os.path.isfile(py):
            shutil.copyfile(py, os.path.join(mdir, "pruefen.py"))
            zus.append("pruefen.py auf der Disc = %s" % v)
            break
    with open(os.path.join(mdir, "LIESMICH.txt"), "w", newline="\r\n", encoding="utf-8-sig") as fh:
        fh.write(LIESMICH.format(disc=disc, label=label, zeit=jetzt(), version=VERSION, n=len(man),
                                 bytes=p_bytes + r_bytes, gib=(p_bytes + r_bytes) / GIB, n_p=len(prim), gib_p=p_bytes / GIB,
                                 n_r=len(red), gib_r=r_bytes / GIB, datum=datum, n_k=sum(1 for z in man if z["gekuerzt"]),
                                 fassung=fas_name, ordner=zielwurzel, iso=iso_name, max_pfad=a.max_pfad_disc,
                                 bek_txt=("\nBekannte Planabweichungen: %d Datei(en) mit Ist-SHA statt Plan-SHA (T0), Nachweis"
                                          " _MANIFEST\\Planabweichungen_bekannt_%s.csv." % (len(bek_man), disc)) if bek_man else "",
                                 fremd_txt=("\nZusatzquelle (ausserhalb D:\\Daten): %d Dateien in %s\\, SHA-256 beim Anlegen gebildet;"
                                            " Herkunft in Manifest_Gesamt.csv (Aktion FREMD)." % (len(fremd), a.fremd_ziel)) if fremd else ""))
    with open(os.path.join(mdir, "Pruefsummen_Manifest.txt"), "w", newline="\r\n", encoding="utf-8") as fh:
        for f in sorted(os.listdir(mdir)):
            if f != "Pruefsummen_Manifest.txt":
                fh.write("%s  %s\n" % (sha_datei(os.path.join(mdir, f))[0], f))
    if befund:
        with open(os.path.join(zielwurzel, "NICHT_BRENNEN.txt"), "w", encoding="utf-8-sig") as fh:
            fh.write("Abweichungen gegen den Plan - diesen Ordner NICHT brennen:\n")
            for rel, st in befund:
                fh.write("%s;%s\n" % (st, rel))
    shutil.copyfile(mcsv, os.path.join(a.out, "Manifest_%s_%s.csv" % (fas_name, ts)))
    m_bytes = sum(os.path.getsize(os.path.join(mdir, f)) for f in os.listdir(mdir))
    gesamt = m_bytes + p_bytes + r_bytes
    zus += ["", "Brennordner %s angelegt: %d Hardlinks (Primaer %d, Redundanz %d), %.2f GiB frisch gehasht in %.0f s" % (
        zielwurzel, len(man) - sum(1 for _, s in befund if s.startswith(("FEHLT", "FEHLER"))), len(prim), len(red),
        gelesen / GIB, time.time() - t0),
        "Umfang inkl. _MANIFEST (%.1f MiB): %d B (%.2f GiB) | Grenze %.2f GiB | Reserve bis Kapazitaet %.2f GiB" % (
            m_bytes / 2**20, gesamt, gesamt / GIB, a.max_gib, a.kapazitaet_gib - gesamt / GIB),
        "Label fuer CDBurnerXP: %s | Dateisystem UDF 2.50 | Ordnerinhalt von %s in die Wurzel ziehen" % (label, zielwurzel),
        "Zusammenstellung speichern: %s | ISO speichern: %s" % (
            os.path.join(a.ziel, iso_name + ".dxp"), os.path.join(a.ziel, iso_name + ".iso")),
        "Abweichungen gegen Plan: %d" % len(befund)]
    for rel, st in befund[:20]:
        zus.append("  %s  %s" % (st, rel))
    zus.append("ERGEBNIS: %s" % ("BEFUND - NICHT BRENNEN (siehe NICHT_BRENNEN.txt)" if befund else "BRENNBEREIT (0 Abweichungen)"))
    open(os.path.join(a.out, "brennliste_%s_%s_zusammenfassung.txt" % (fas_name, ts)), "w", encoding="utf-8-sig").write("\n".join(zus) + "\n")
    print("\n".join(zus[-(7 + min(len(befund), 20)):]))
    return 1 if befund else 0


if __name__ == "__main__":
    sys.exit(main())
