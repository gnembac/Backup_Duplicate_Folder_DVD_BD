#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
takeout_teilliste_v1.0.py - Projekt "Basisdaten ermitteln" (privat)
Version 1.0 | Stand 30.10.2026, 09:40 MEZ | Autor: Claude fuer Gunter Nembach

ZWECK (NUR LESEN)
  Listet den Inhalt von Google-Takeout-Teilen OHNE Entpacken - auch von
  abgebrochenen Downloads (.crdownload). Die Datei wird von vorn Eintrag fuer
  Eintrag gelesen (lokale ZIP-Kopfzeilen); verschachtelte ZIPs im Inhalt werden
  uebersprungen, nicht mitgezaehlt. Je vollstaendig gelesenem Eintrag wird die
  CRC32 geprueft (= ZIP-Test). Ergebnis: welche Produkte (Takeout/<Produkt>/)
  in welchem Teil liegen und ob die bereits geladenen Bytes intakt sind.

  Damit laesst sich entscheiden, ob die stehenden Teile von Export 2 neu
  geladen werden muessen oder ob Export 3 denselben Inhalt liefert.

SICHERHEIT
  - Dateien nur mit 'rb' geoeffnet; nichts wird verschoben, umbenannt, geloescht.
  - .crdownload-Dateien, die noch wachsen (Chrome laedt), werden uebersprungen.
  - Geschrieben wird nur in --out (Standard D:\\_Berichte\\takeout\\<Zeitstempel>\\).

AUFRUF (PowerShell, PC-Windows)
  cd D:\\_Berichte\\kopierplan\\skripte
  py takeout_teilliste_v1.0.py --ordner D:\\_Import\\Takeout_2026-10-29
  py takeout_teilliste_v1.0.py --ordner D:\\_Import\\Takeout_2026-10-29 --ohne-crc     (schneller, ohne ZIP-Test)
  py takeout_teilliste_v1.0.py --ordner D:\\_Import\\Takeout_2026-10-29 --ordner D:\\_Import\\Takout_Export_3_2026_10_30

AUSGABE
  zusammenfassung.txt, produkte.csv, ebene2.csv, eintraege_<Datei>.csv (UTF-8-BOM, Semikolon)

EXIT-CODES  0 alles gelesen, keine CRC-Fehler | 1 Befund (CRC-Fehler/Strukturfehler) | 2 Aufruffehler

VERSIONSPROTOKOLL
  1.0  30.10.2026, 09:40  Erstfassung
"""
import argparse, csv, datetime as dt, os, struct, sys, time, zipfile, zlib
from collections import OrderedDict

VERSION = "takeout_teilliste_v1.0"
LFH, CDH, DDS = b"PK\x03\x04", b"PK\x01\x02", b"PK\x07\x08"
ENDE_SIG = (b"PK\x01\x02", b"PK\x05\x06", b"PK\x06\x06", b"PK\x06\x07")
BLOCK = 8 * 2**20
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def jetzt():
    return dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def lies_kopf(f, pos):
    """Lokale Kopfzeile an pos lesen. Rueckgabe (dict, None) oder (None, Grund)."""
    f.seek(pos)
    h = f.read(30)
    if len(h) < 4:
        return None, "EOF"
    if h[:4] in ENDE_SIG:
        return None, "ZENTRALVERZEICHNIS"
    if h[:4] != LFH:
        return None, "KEINE_SIGNATUR"
    if len(h) < 30:
        return None, "EOF"
    _, ver, flags, meth, mt, md, crc, cs, us, nl, xl = struct.unpack("<4sHHHHHIIIHH", h)
    rest = f.read(nl + xl)
    if len(rest) < nl + xl:
        return None, "EOF"
    roh, extra = rest[:nl], rest[nl:]
    name = roh.decode("utf-8" if flags & 0x800 else "cp437", errors="replace")
    z64 = False
    i = 0
    while i + 4 <= len(extra):
        hid, hl = struct.unpack("<HH", extra[i:i + 4])
        d = extra[i + 4:i + 4 + hl]
        if hid == 1:
            z64 = True
            j = 0
            if us == 0xFFFFFFFF and j + 8 <= len(d):
                us = struct.unpack("<Q", d[j:j + 8])[0]; j += 8
            if cs == 0xFFFFFFFF and j + 8 <= len(d):
                cs = struct.unpack("<Q", d[j:j + 8])[0]; j += 8
        i += 4 + hl
    return dict(pos=pos, flags=flags, meth=meth, crc=crc, cs=cs, us=us, name=name,
                data=pos + 30 + nl + xl, z64=z64), None


def lies_dd(f, ende, groesse_datei):
    """Datendeskriptor nach Datenende lesen. Rueckgabe (crc, cs, laenge) oder None."""
    f.seek(ende)
    b = f.read(28)
    off = 4 if b[:4] == DDS else 0
    kandidaten = []
    for breite in (8, 4):
        lang = off + 4 + 2 * breite
        if len(b) < lang:
            continue
        crc = struct.unpack("<I", b[off:off + 4])[0]
        fmt = "<QQ" if breite == 8 else "<II"
        cs, us = struct.unpack(fmt, b[off + 4:lang])
        folgt = b[lang:lang + 4]
        passt = folgt in (LFH,) + ENDE_SIG or ende + lang == groesse_datei
        kandidaten.append((passt, crc, cs, lang, breite))
    for k in kandidaten:
        if k[0]:
            return k[1], k[2], k[3]
    return None


def pruefe_datei(pfad, mit_crc, fortschritt):
    groesse = os.path.getsize(pfad)
    eintraege, befund = [], OrderedDict(ende="", hinweis="")
    t0 = letzte = time.time()
    with open(pfad, "rb", buffering=0) as f:
        pos = 0
        while True:
            k, grund = lies_kopf(f, pos)
            if k is None:
                befund["ende"] = {"ZENTRALVERZEICHNIS": "VOLLSTAENDIG (Zentralverzeichnis erreicht)",
                                  "EOF": "ANGESCHNITTEN (Dateiende waehrend Kopfzeile)",
                                  "KEINE_SIGNATUR": "STRUKTURFEHLER (keine Kopfzeile an Offset %d)" % pos}[grund]
                break
            status, crc_ist, naechste = "", None, None
            if k["flags"] & 1:
                status = "VERSCHLUESSELT"
            if not (k["flags"] & 8):
                ende = k["data"] + k["cs"]
                if ende > groesse:
                    status = "ANGESCHNITTEN"
                elif mit_crc and k["meth"] in (0, 8) and not status:
                    crc_ist, fehler = crc_bekannt(f, k)
                    status = fehler or ("CRC_OK" if crc_ist == k["crc"] else "CRC_FEHLER")
                elif not status:
                    status = "NICHT_GEPRUEFT"
                naechste = ende
            else:
                if k["meth"] != 8:
                    ende, ddl, crc_dd, fehler = suche_dd_gespeichert(f, k, groesse)
                    if fehler:
                        status = fehler
                    else:
                        k["crc"], k["cs"] = crc_dd, ende - k["data"]
                        if mit_crc and k["meth"] == 0:
                            crc_ist, fehler = crc_bekannt(f, k)
                            status = fehler or ("CRC_OK" if crc_ist == crc_dd else "CRC_FEHLER")
                        else:
                            status = "NICHT_GEPRUEFT"
                        naechste = ende + ddl
                else:
                    ende, crc_ist, fehler = inflate_bis_ende(f, k, groesse)
                    if fehler:
                        status = fehler
                    else:
                        dd = lies_dd(f, ende, groesse)
                        if dd is None:
                            status = "ANGESCHNITTEN" if ende + 12 > groesse else "STRUKTUR_UNSICHER"
                        else:
                            crc_dd, cs_dd, ddl = dd
                            k["crc"], k["cs"] = crc_dd, cs_dd
                            if cs_dd != ende - k["data"]:
                                status = "STRUKTUR_UNSICHER"
                            else:
                                status = "CRC_OK" if crc_ist == crc_dd else "CRC_FEHLER"
                            naechste = ende + ddl
            k["status"] = status
            k["spanne"] = min(naechste if naechste else groesse, groesse) - k["pos"]
            eintraege.append(k)
            if status == "ANGESCHNITTEN":
                befund["ende"] = "ANGESCHNITTEN (Dateiende im Eintrag %s)" % k["name"]
                break
            if naechste is None:
                befund["ende"] = "STRUKTURFEHLER (Eintrag %s, Methode %d mit Datendeskriptor)" % (k["name"], k["meth"])
                break
            pos = naechste
            if fortschritt and time.time() - letzte > 5:
                letzte = time.time()
                print("  %s  %.2f von %.2f GiB  %d Eintraege  %.0f s" % (
                    os.path.basename(pfad), pos / 2**30, groesse / 2**30, len(eintraege), time.time() - t0), flush=True)
    befund["gelesen_bis"] = eintraege[-1]["pos"] + eintraege[-1]["spanne"] if eintraege else 0
    befund["dauer_s"] = round(time.time() - t0, 1)
    if pfad.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(pfad) as z:
                n = len(z.infolist())
            befund["zentralverzeichnis_eintraege"] = n
            if n != len(eintraege):
                befund["hinweis"] = "Anzahl Zentralverzeichnis %d <> gelesen %d" % (n, len(eintraege))
        except Exception as e:
            befund["zentralverzeichnis_eintraege"] = "FEHLER: %s" % e
    return groesse, eintraege, befund


def crc_bekannt(f, k):
    f.seek(k["data"])
    rest, crc = k["cs"], 0
    d = zlib.decompressobj(-15) if k["meth"] == 8 else None
    try:
        while rest > 0:
            b = f.read(min(BLOCK, rest))
            if not b:
                return None, "ANGESCHNITTEN"
            rest -= len(b)
            crc = zlib.crc32(d.decompress(b) if d else b, crc)
        if d:
            crc = zlib.crc32(d.flush(), crc)
    except zlib.error:
        return None, "DEFLATE_FEHLER"
    return crc & 0xFFFFFFFF, None


def suche_dd_gespeichert(f, k, groesse):
    """Gespeicherter Eintrag mit Datendeskriptor: naechste Kopfzeile suchen, deren
    vorangehender Deskriptor die passende Laenge nennt (verschachtelte ZIPs fallen raus).
    Rueckgabe (datenende, dd_laenge, crc, fehler)."""
    start, ueber, blk = k["data"], 64, 262144
    pos = start
    while True:
        f.seek(pos)
        b = f.read(blk + ueber)
        if len(b) < 4:
            return None, None, None, "ANGESCHNITTEN"
        i = 0
        while True:
            i = b.find(b"PK", i)
            if i < 0 or i + 4 > len(b):
                break
            if b[i:i + 4] in (LFH,) + ENDE_SIG:
                c = pos + i
                for L, sig, breite in ((16, True, 4), (24, True, 8), (12, False, 4), (20, False, 8)):
                    ddp = c - L
                    if ddp < start:
                        continue
                    f.seek(ddp)
                    dd = f.read(L)
                    o = 0
                    if sig:
                        if dd[:4] != DDS:
                            continue
                        o = 4
                    crc = struct.unpack("<I", dd[o:o + 4])[0]
                    cs = struct.unpack("<Q" if breite == 8 else "<I", dd[o + 4:o + 4 + breite])[0]
                    if cs == ddp - start:
                        return ddp, L, crc, None
            i += 1
        if len(b) < blk + ueber:
            return None, None, None, "ANGESCHNITTEN"
        pos += blk
        blk = min(blk * 2, BLOCK)


def inflate_bis_ende(f, k, groesse):
    """Deflate-Strom ohne bekannte Laenge bis zum Ende lesen; liefert (ende, crc, fehler)."""
    f.seek(k["data"])
    d = zlib.decompressobj(-15)
    crc, pos, blk = 0, k["data"], 65536
    try:
        while not d.eof:
            b = f.read(blk)
            if not b:
                return None, None, "ANGESCHNITTEN"
            pos += len(b)
            crc = zlib.crc32(d.decompress(b), crc)
            blk = min(blk * 2, BLOCK)
    except zlib.error:
        return None, None, "DEFLATE_FEHLER"
    return pos - len(d.unused_data), crc & 0xFFFFFFFF, None


def produkt(name):
    t = name.replace("\\", "/").split("/")
    if len(t) > 1 and t[0] == "Takeout":
        p = t[1]
        e2 = t[2] if len(t) > 3 else "(Dateien direkt im Produktordner)"
        return p, e2
    return "(ohne Takeout/)", ""


def waechst(pfad, warte):
    a = os.path.getsize(pfad)
    time.sleep(warte)
    return os.path.getsize(pfad) != a


def main():
    ap = argparse.ArgumentParser(description=VERSION)
    ap.add_argument("--ordner", action="append", required=True)
    ap.add_argument("--out", default=r"D:\_Berichte\takeout")
    ap.add_argument("--ohne-crc", action="store_true")
    ap.add_argument("--auch-laufend", action="store_true", help="auch wachsende .crdownload lesen")
    ap.add_argument("--warte-s", type=float, default=5.0)
    a = ap.parse_args()
    print(VERSION, "Start", jetzt(), flush=True)
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    out = os.path.join(a.out, ts)
    os.makedirs(out, exist_ok=True)

    dateien = []
    for o in a.ordner:
        if not os.path.isdir(o):
            print("FEHLER: Ordner fehlt:", o); return 2
        for n in sorted(os.listdir(o)):
            if n.lower().endswith((".zip", ".crdownload")):
                dateien.append(os.path.join(o, n))
    if not dateien:
        print("Keine .zip/.crdownload gefunden."); return 2
    laufend = set()
    if not a.auch_laufend:
        cr = [p for p in dateien if p.lower().endswith(".crdownload")]
        if cr:
            groessen = {p: os.path.getsize(p) for p in cr}
            time.sleep(a.warte_s)
            laufend = {p for p in cr if os.path.getsize(p) != groessen[p]}

    zus = ["%s | Lauf %s | CRC-Pruefung: %s" % (VERSION, jetzt(), "nein" if a.ohne_crc else "ja"), ""]
    prod_rows, e2_rows, befund_gesamt = [], [], 0
    for p in dateien:
        bn = os.path.basename(p)
        if p in laufend:
            zus.append("%s: UEBERSPRUNGEN (waechst noch, Chrome laedt)" % bn); print(zus[-1]); continue
        print("Lese", bn, flush=True)
        try:
            groesse, ein, bef = pruefe_datei(p, not a.ohne_crc, True)
        except PermissionError as e:
            zus.append("%s: GESPERRT (%s)" % (bn, e)); print(zus[-1]); continue
        stamm = os.path.splitext(bn)[0].replace(" ", "_")
        with open(os.path.join(out, "eintraege_%s.csv" % stamm), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["Offset", "Name", "Produkt", "Ebene2", "Methode", "Flags", "CSize", "USize", "Spanne_B", "CRC_Soll", "Status"])
            for k in ein:
                pr, e2 = produkt(k["name"])
                w.writerow([k["pos"], k["name"], pr, e2, k["meth"], k["flags"], k["cs"], k["us"], k["spanne"], "%08x" % k["crc"], k["status"]])
        prod, e2s = OrderedDict(), OrderedDict()
        for k in ein:
            pr, e2 = produkt(k["name"])
            for key, ziel in ((pr, prod), ((pr, e2), e2s)):
                s = ziel.setdefault(key, dict(n=0, b=0, von=k["pos"], bis=k["pos"], ok=0, fehler=0, sonst=0))
                s["n"] += 1; s["b"] += k["spanne"]; s["bis"] = k["pos"]
                if k["status"] == "CRC_OK": s["ok"] += 1
                elif k["status"] in ("CRC_FEHLER", "DEFLATE_FEHLER", "STRUKTUR_UNSICHER"): s["fehler"] += 1
                else: s["sonst"] += 1
        for pr, s in prod.items():
            prod_rows.append([bn, pr, s["n"], s["b"], round(s["b"] / 2**30, 3), s["von"], s["bis"], s["ok"], s["fehler"], s["sonst"]])
        for (pr, e2), s in e2s.items():
            e2_rows.append([bn, pr, e2, s["n"], s["b"], round(s["b"] / 2**30, 3), s["ok"], s["fehler"], s["sonst"]])
        nf = sum(1 for k in ein if k["status"] in ("CRC_FEHLER", "DEFLATE_FEHLER", "STRUKTUR_UNSICHER"))
        nok = sum(1 for k in ein if k["status"] == "CRC_OK")
        if nf or bef["ende"].startswith("STRUKTUR"):
            befund_gesamt += 1
        start_block = len(zus)
        zus.append("%s" % bn)
        zus.append("  Groesse %d B (%.3f GiB) | gelesen bis %d B (%.1f %%) | Dauer %s s" % (
            groesse, groesse / 2**30, bef["gelesen_bis"], 100.0 * bef["gelesen_bis"] / groesse if groesse else 0, bef["dauer_s"]))
        zus.append("  Ende: %s" % bef["ende"])
        zus.append("  Eintraege %d | CRC_OK %d | Fehler %d | sonstige %d" % (len(ein), nok, nf, len(ein) - nok - nf))
        if "zentralverzeichnis_eintraege" in bef:
            zus.append("  Zentralverzeichnis: %s Eintraege" % bef["zentralverzeichnis_eintraege"])
        if bef["hinweis"]:
            zus.append("  HINWEIS: %s" % bef["hinweis"])
        for pr, s in prod.items():
            zus.append("    %-40s %8d Eintr. %9.3f GiB  CRC_OK %d  Fehler %d" % (pr, s["n"], s["b"] / 2**30, s["ok"], s["fehler"]))
        zus.append("")
        print("\n".join(zus[start_block:]), flush=True)

    with open(os.path.join(out, "produkte.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Datei", "Produkt", "Eintraege", "Spanne_B", "GiB", "Offset_von", "Offset_bis", "CRC_OK", "Fehler", "Sonstige"])
        w.writerows(prod_rows)
    with open(os.path.join(out, "ebene2.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Datei", "Produkt", "Ebene2", "Eintraege", "Spanne_B", "GiB", "CRC_OK", "Fehler", "Sonstige"])
        w.writerows(e2_rows)
    zus.append("ERGEBNIS: %s" % ("BEFUND (CRC-/Strukturfehler, siehe oben)" if befund_gesamt else "keine CRC-/Strukturfehler in den gelesenen Eintraegen"))
    with open(os.path.join(out, "zusammenfassung.txt"), "w", encoding="utf-8-sig") as fh:
        fh.write("\n".join(zus) + "\n")
    print(zus[-1]); print("Berichte:", out); print(VERSION, "Ende", jetzt())
    return 1 if befund_gesamt else 0


if __name__ == "__main__":
    sys.exit(main())
