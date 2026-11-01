#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mdisc_ende_v1.0.py - Projekt "Basisdaten ermitteln" (privat)
Version 1.0 | Stand 31.10.2026, 21:50 MEZ | Autor: Claude fuer Gunter Nembach

ZWECK (NUR LESEN - Disc und ISO werden nie veraendert)
  Klaert den ROH-Befund D1-V1 vom 31.10.2026: Am Disc-Ende lieferte ReadFile
  nur 782.336 von 1.310.720 B (ohne Win32-Fehler) -> die letzten 258 Sektoren fehlen.
  Frage: Liegen dort Dateidaten oder nur UDF-Verwaltung/Fuellung?

  1 Laengen: Volumen (IOCTL_DISK_GET_LENGTH_INFO), Geometrie, Read Capacity, ISO
  2 UDF-Struktur aus dem ISO: AVDP (Sektor 256, N-256, N), Haupt-/Reserve-VDS,
    Partition (Start/Laenge), UDF-2.50-Metadaten-Datei und -Spiegel, LVID
  3 UDF-Kopf Disc gegen ISO: gleiche Sektoren = gleiches Layout (Uebertragbarkeit)
  4 Endbereich (Standard letzte 640 Sektoren = Nullblock im Abbild):
    je Sektor Disc lesbar? Inhalt ISO (NULL / UDF-Tag / DATEN)? Disc = ISO?

AUFRUF (PowerShell ALS ADMINISTRATOR, D1-V1 in E:, Skriptordner D:\\_Berichte\\kopierplan\\skripte)
  py mdisc_ende_v1.0.py --laufwerk E: --iso D:\\_MDISC\\MDISC_D1_2026_10_31_V1_udf25.iso
  Dauer: ca. 1-5 min (geschaetzt; laenger, falls das Laufwerk unlesbare Sektoren wiederholt liest)

AUSGABE  D:\\_Berichte\\mdisc\\ende_<LW>_<Zeit>_sektoren.csv und _zusammenfassung.txt
EXIT     0 Endbereich ohne DATEN in unlesbaren Sektoren | 1 DATEN betroffen/Abweichung | 2 Aufruffehler

VERSIONSPROTOKOLL
  1.0  31.10.2026, 21:50  Erstfassung (getestet im Container: mkudffs-UDF-2.01-Abbild + eingesetzte 2.50-Metadatenkarte,
                          Disc simuliert als Datei; Windows-IOCTL/ReadFile ungetestet)
"""
import argparse, csv, datetime as dt, os, struct, sys, time

VERSION = "mdisc_ende_v1.0"
S = 2048
GIB = 2**30
IST_WIN = os.name == "nt"
TAGS = {1: "PVD", 2: "AVDP", 3: "VDP", 4: "IUVD", 5: "PD", 6: "LVD", 7: "USD", 8: "TD", 9: "LVID",
        256: "FSD", 257: "FID", 258: "AED", 259: "IE", 260: "TE", 261: "FE", 262: "EAHD", 263: "USE",
        264: "SBD", 265: "PIE", 266: "EFE"}
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

if IST_WIN:
    import ctypes
    from ctypes import wintypes
    _k = ctypes.WinDLL("kernel32", use_last_error=True)
    _k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                               wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _k.CreateFileW.restype = wintypes.HANDLE
    _k.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _k.ReadFile.restype = wintypes.BOOL
    _k.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_longlong, ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD]
    _k.SetFilePointerEx.restype = wintypes.BOOL
    _k.CloseHandle.argtypes = [wintypes.HANDLE]
    _k.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _k.DeviceIoControl.restype = wintypes.BOOL
    _UNG = wintypes.HANDLE(-1).value


class Disc:
    """Liest Sektoren vom Geraet (Windows) oder aus einer Datei (Test). lesen() -> (bytes, info)."""

    def __init__(self, pfad):
        self.datei = None
        if IST_WIN and pfad.startswith("\\\\.\\"):
            h = _k.CreateFileW(pfad, 0x80000000, 3, None, 3, 0, None)
            if h is None or h == _UNG:
                raise ctypes.WinError(ctypes.get_last_error())
            self.h = h
            self.buf = ctypes.create_string_buffer(64 * S)
        else:
            self.datei = open(pfad, "rb")

    def lesen(self, pos, n):
        if self.datei:
            self.datei.seek(pos)
            return self.datei.read(n), ""
        if not _k.SetFilePointerEx(self.h, pos, None, 0):
            e = ctypes.get_last_error()
            return b"", "[Win32 %d] Seek" % e
        got = wintypes.DWORD(0)
        if not _k.ReadFile(self.h, self.buf, n, ctypes.byref(got), None):
            e = ctypes.get_last_error()
            return b"", "[Win32 %d] %s" % (e, ctypes.FormatError(e).strip())
        return self.buf.raw[:got.value], ""

    def ioctl(self, code, n):
        if self.datei:
            return None
        out = ctypes.create_string_buffer(n)
        r = wintypes.DWORD(0)
        ok = _k.DeviceIoControl(self.h, code, None, 0, out, n, ctypes.byref(r), None)
        return out.raw[:r.value] if ok else None

    def laengen(self):
        """Laengenangaben des Geraets (k.A., wenn IOCTL nicht unterstuetzt)."""
        erg = {}
        b = self.ioctl(0x0007405C, 8)                      # IOCTL_DISK_GET_LENGTH_INFO
        erg["Volumen GET_LENGTH_INFO"] = struct.unpack("<q", b[:8])[0] if b and len(b) >= 8 else None
        b = self.ioctl(0x000700A0, 256)                    # IOCTL_DISK_GET_DRIVE_GEOMETRY_EX
        erg["Geometrie DiskSize"] = struct.unpack("<q", b[24:32])[0] if b and len(b) >= 32 else None
        b = self.ioctl(0x002D5140, 32)                     # IOCTL_STORAGE_READ_CAPACITY
        if b and len(b) >= 32:
            _, _, bl, nb, dl = struct.unpack("<IIIxxxxqq", b[:32])
            erg["ReadCapacity Bloecke x Groesse"] = nb * bl
            erg["ReadCapacity DiskLength"] = dl
        else:
            erg["ReadCapacity DiskLength"] = None
        return erg

    def schliessen(self):
        if self.datei:
            self.datei.close()
        else:
            _k.CloseHandle(self.h)


def tag(sek):
    """UDF-Tag pruefen: (Name, Ort) oder None. Prueft Kennung, Version und Pruefsumme."""
    if len(sek) < 16:
        return None
    tid, ver, cs = struct.unpack("<HHB", sek[:5])
    if tid not in TAGS or ver not in (2, 3):
        return None
    if (sum(sek[0:4]) + sum(sek[5:16])) & 0xFF != cs:
        return None
    return TAGS[tid], struct.unpack("<I", sek[12:16])[0]


def klasse(sek):
    if not sek:
        return "LEER"
    if not any(sek):
        return "NULL"
    t = tag(sek)
    return "UDF-%s" % t[0] if t else "DATEN"


def udf_struktur(iso, n_sek):
    """Liest die UDF-Verwaltung aus dem ISO. Rueckgabe dict mit absoluten Sektoren."""
    u = {"avdp": {}, "teile": []}

    def sek(i):
        iso.seek(i * S)
        return iso.read(S)

    for name, i in (("256", 256), ("N-256", n_sek - 257), ("N", n_sek - 1)):
        t = tag(sek(i))
        u["avdp"][name] = (i, t is not None and t[0] == "AVDP")
    a = sek(256)
    if not (tag(a) and tag(a)[0] == "AVDP"):
        u["fehler"] = "kein AVDP in Sektor 256 - kein UDF?"
        return u
    ml, mo, rl, ro = struct.unpack("<IIII", a[16:32])
    u["vds"] = (mo, ml // S)
    u["rvds"] = (ro, rl // S)
    for i in range(mo, mo + min(ml // S, 64)):
        d = sek(i)
        t = tag(d)
        if not t:
            continue
        if t[0] == "PD":
            u["p_start"], u["p_len"] = struct.unpack("<II", d[188:196])
        elif t[0] == "LVD":
            u["lvid"] = struct.unpack("<II", d[432:440])[::-1]   # (Ort, Laenge B)
            n_maps = struct.unpack("<I", d[268:272])[0]
            p = 440
            for _ in range(n_maps):
                typ, ln = d[p], d[p + 1]
                if typ == 2 and b"UDF Metadata Partition" in d[p + 4:p + 36]:
                    u["meta"], u["meta_spiegel"], u["meta_bitmap"] = struct.unpack("<III", d[p + 40:p + 52])
                p += ln if ln else 6
        elif t[0] == "TD":
            break
    return u


def main():
    ap = argparse.ArgumentParser(description=VERSION)
    ap.add_argument("--laufwerk", default="E:")
    ap.add_argument("--geraet-datei", default="", help="Test: Datei statt Laufwerk")
    ap.add_argument("--iso", required=True)
    ap.add_argument("--laenge-bytes", type=int, default=0, help="Soll-Laenge (Standard: ISO-Groesse)")
    ap.add_argument("--sektoren", type=int, default=640, help="Endbereich in Sektoren (640 = Nullblock Abbild)")
    ap.add_argument("--max-fehler", type=int, default=400)
    ap.add_argument("--out", default=r"D:\_Berichte\mdisc")
    a = ap.parse_args()

    if not os.path.isfile(a.iso):
        print("FEHLER: ISO nicht gefunden:", a.iso); return 2
    lw = a.laufwerk.rstrip(":\\").upper()
    geraet = a.geraet_datei or "\\\\.\\%s:" % lw
    try:
        d = Disc(geraet)
    except OSError as e:
        print("FEHLER: Laufwerk nicht roh lesbar: %s -> PowerShell 'Als Administrator ausfuehren'" % e); return 2
    iso_len = os.path.getsize(a.iso)
    soll = a.laenge_bytes or iso_len
    n_sek = soll // S
    print("%s Start %s | %s | ISO %s (%d B)" % (VERSION, dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S"), geraet, a.iso, iso_len), flush=True)

    z = ["%s | %s | %s | ISO %s" % (VERSION, dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S"), geraet, a.iso), "",
         "1 LAENGEN (B | Sektoren | GiB)"]
    lg = {"ISO-Datei": iso_len}
    lg.update(d.laengen() if not a.geraet_datei else {"Testdatei": os.path.getsize(a.geraet_datei)})
    for k, v in lg.items():
        z.append("  %-32s %s" % (k, "k.A." if v is None else "%d | %d | %.4f" % (v, v // S, v / GIB)))

    iso = open(a.iso, "rb")
    u = udf_struktur(iso, iso_len // S)
    z += ["", "2 UDF-STRUKTUR ISO (absolute Sektoren; N = letzter Sektor = %d)" % (iso_len // S - 1)]
    for k, (i, ok) in u["avdp"].items():
        z.append("  AVDP %-6s Sektor %-10d %s" % (k, i, "vorhanden" if ok else "nicht vorhanden"))
    if "fehler" in u:
        z.append("  " + u["fehler"])
    else:
        z.append("  Haupt-VDS    Sektor %d, %d Sektoren" % u["vds"])
        z.append("  Reserve-VDS  Sektor %d, %d Sektoren" % u["rvds"])
        if "p_start" in u:
            z.append("  Partition    Start %d, Laenge %d, Ende %d" % (u["p_start"], u["p_len"], u["p_start"] + u["p_len"] - 1))
        if "lvid" in u:
            z.append("  LVID         Sektor %d" % u["lvid"][0])
        if "meta" in u and "p_start" in u:
            for k in ("meta", "meta_spiegel", "meta_bitmap"):
                v = u[k]
                z.append("  %-12s Sektor %s" % ({"meta": "Metadaten", "meta_spiegel": "Meta-Spiegel", "meta_bitmap": "Meta-Bitmap"}[k],
                                                  "k.A." if v == 0xFFFFFFFF else u["p_start"] + v))

    # 3 Kopf Disc gegen ISO
    kopf = [16, 17, 18, 256]
    if "vds" in u:
        kopf += list(range(u["vds"][0], u["vds"][0] + min(u["vds"][1], 16)))
    kopf_g = kopf_u = 0
    ungleich = []
    for i in kopf:
        b, inf = d.lesen(i * S, S)
        iso.seek(i * S)
        bi = iso.read(S)
        if b == bi:
            kopf_g += 1
        else:
            kopf_u += 1
            ungleich.append("%d(%s%s)" % (i, klasse(bi), (" " + inf) if inf else ""))
    z += ["", "3 UDF-KOPF DISC = ISO: gleich %d | ungleich %d %s" % (kopf_g, kopf_u, " ".join(ungleich))]

    # 4 Endbereich
    k = min(a.sektoren, n_sek)
    erster = n_sek - k
    print("Endbereich: %d Sektoren ab %d (%.4f GiB) ..." % (k, erster, erster * S / GIB), flush=True)
    os.makedirs(a.out, exist_ok=True)
    stamm = os.path.join(a.out, "ende_%s_%s" % (lw if not a.geraet_datei else "TEST", dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")))
    zl = {"lesbar": 0, "kurz": 0, "fehler": 0, "gleich": 0, "ungleich": 0}
    kl_unl, kl_les, kl_alle = {}, {}, {}
    erster_unl, fehlerzahl, t0 = None, 0, time.time()
    with open(stamm + "_sektoren.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Sektor", "Offset_B", "Disc", "Disc_Bytes", "ISO_Inhalt", "Disc_gleich_ISO", "Info"])
        for i in range(erster, n_sek):
            t = time.time()
            b, inf = d.lesen(i * S, S)
            iso.seek(i * S)
            bi = iso.read(S)
            kl = klasse(bi)
            kl_alle[kl] = kl_alle.get(kl, 0) + 1
            if len(b) == S:
                st = "LESBAR"
                zl["lesbar"] += 1
                gl = "ja" if b == bi else "nein"
                zl["gleich" if gl == "ja" else "ungleich"] += 1
                kl_les[kl] = kl_les.get(kl, 0) + 1
            else:
                st = "FEHLER" if inf else "KURZ"
                zl["fehler" if inf else "kurz"] += 1
                gl = "-"
                erster_unl = i if erster_unl is None else erster_unl
                kl_unl[kl] = kl_unl.get(kl, 0) + 1
                if inf:
                    fehlerzahl += 1
            w.writerow([i, i * S, st, len(b), kl, gl, (inf + " " if inf else "") + "%.2f s" % (time.time() - t)])
            if fehlerzahl >= a.max_fehler:
                break
    d.schliessen()
    iso.close()

    unl = zl["kurz"] + zl["fehler"]
    p_ende = None
    z += ["", "4 ENDBEREICH letzte %d Sektoren (%d ... %d), Dauer %.0f s" % (k, erster, n_sek - 1, time.time() - t0),
          "  Disc lesbar %d | kurz (Ende ohne Fehler) %d | Lesefehler %d | erster unlesbarer Sektor %s" % (
              zl["lesbar"], zl["kurz"], zl["fehler"], "-" if erster_unl is None else "%d (= N-%d)" % (erster_unl, n_sek - 1 - erster_unl)),
          "  lesbare Sektoren Disc = ISO: gleich %d | ungleich %d" % (zl["gleich"], zl["ungleich"]),
          "  ISO-Inhalt gesamt Endbereich:      " + ", ".join("%s %d" % kv for kv in sorted(kl_alle.items())),
          "  ISO-Inhalt der UNLESBAREN Sektoren: " + (", ".join("%s %d" % kv for kv in sorted(kl_unl.items())) or "-"),
          "  ISO-Inhalt der lesbaren Sektoren:   " + (", ".join("%s %d" % kv for kv in sorted(kl_les.items())) or "-")]
    if "rvds" in u and erster_unl is not None:
        r0, rn = u["rvds"]
        z.append("  Reserve-VDS (%d-%d) %s" % (r0, r0 + rn - 1, "UNLESBAR" if r0 + rn - 1 >= erster_unl else "lesbar"))
    p_ende = u["p_start"] + u["p_len"] - 1 if "p_start" in u else None
    if p_ende is not None and erster_unl is not None:
        z.append("  Partitionsende %d %s erster unlesbarer Sektor %d -> %s" % (
            p_ende, "<" if p_ende < erster_unl else ">=", erster_unl,
            "alle Dateidaten liegen im lesbaren Bereich (strukturell)" if p_ende < erster_unl else "Partition reicht in den unlesbaren Bereich"))
    for nm, sv in (("Meta-Spiegel", "meta_spiegel"), ("Meta-Bitmap", "meta_bitmap")):
        if sv in u and "p_start" in u and u[sv] != 0xFFFFFFFF and erster_unl is not None:
            z.append("  %s (FE) Sektor %d %s" % (nm, u["p_start"] + u[sv], "UNLESBAR" if u["p_start"] + u[sv] >= erster_unl else "lesbar"))

    daten_unl = kl_unl.get("DATEN", 0)
    p_ok = p_ende is not None and erster_unl is not None and p_ende < erster_unl
    if "fehler" in u:
        erg = "UDF-STRUKTUR IM ISO NICHT ERKANNT - Bewertung nur ueber Inhaltsklassen; Stufe ABBILD entscheidet"
        daten_unl = daten_unl or (1 if unl else 0)
    elif unl == 0:
        erg = "ENDE LESBAR (0 unlesbare Sektoren im Endbereich) - ROH-Befund nicht reproduziert"
    elif daten_unl == 0 and zl["ungleich"] == 0:
        erg = "ENDBEREICH OHNE DATEN: %d unlesbare Sektoren enthalten im ISO nur NULL/UDF-Verwaltung%s -> Dateiinhalt nicht betroffen (Ableitung); Nachweis Dateien = Stufe ABBILD" % (
            unl, ", ausserhalb der Partition" if p_ok else "")
    else:
        erg = "DATEN BETROFFEN ODER ABWEICHUNG: unlesbar mit DATEN %d, lesbar ungleich ISO %d -> Stufe ABBILD/DISC entscheidet" % (daten_unl, zl["ungleich"])
    z += ["", "ERGEBNIS: " + erg, "Berichte: " + stamm + "_*"]
    with open(stamm + "_zusammenfassung.txt", "w", encoding="utf-8-sig") as fh:
        fh.write("\n".join(z) + "\n")
    print("\n".join(z))
    return 0 if (unl == 0 or (daten_unl == 0 and zl["ungleich"] == 0)) else 1


if __name__ == "__main__":
    sys.exit(main())
