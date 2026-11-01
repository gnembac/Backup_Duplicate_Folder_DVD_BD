#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mdisc_pruefen_v1.2.py - Projekt "Basisdaten ermitteln" (privat)
Version 1.2 | Stand 31.10.2026, 22:30 MEZ | Autor: Claude fuer Gunter Nembach

ZWECK (NUR LESEN - Quelle, ISO und Disc werden nie veraendert; einzige Schreibvorgaenge:
       Berichte, Register (append-only, vorher Sicherung) und das ROH-Abbild)
  Prueft einen M-DISC-Inhalt gegen sein Manifest (_MANIFEST\\Manifest_D<n>.csv)
  und gegen Zusatzmanifeste (Dateien ausserhalb des Manifests, z. B. 4 ZIP auf D1-V1).

STUFEN
  ZUSATZ    Zusatzmanifest aus der CDBurnerXP-Zusammenstellung (.dxp) erzeugen
  ORDNER    Brennordner                          (--wurzel D:\\_MDISC\\D2)
  ISO       eingebundenes ISO                    (--wurzel H:\\ [--image <ISO-Datei>])
  DISC      gebrannte Disc, dateiweise           (--wurzel E:\\ --satz A --label-soll ...)
  ABBILD    eingebundenes ROH-Abbild der Disc    (--wurzel I:\\ --image <Abbild> --label-soll ... --satz A
                                                  [--disc-laufwerk E:])
  ROH       Disc sektorweise lesen (\\\\.\\E:), optional --iso (Vergleich) und/oder --abbild
  REGISTER  Registerzeile append-only als UNGUELTIG markieren (--ungueltig "<Pruefdatum>" --disc D1 --satz A --grund ...)

NEU GEGENUEBER v1.1 (Anforderungen Uebergabe v1.53 §5, v1.54 §5 Nr. 7)
  1 ROH: Kurzlesung/Lesefehler -> gelesene Bytes behalten, nur wirklich fehlende Sektoren nullen
         (Nachlesen in 64-KiB-Stuecken, dann sektorweise); Luecken in <abbild>.luecken.csv;
         Luecken HINTER dem UDF-Partitionsende = Status ENDE_KURZ (Hinweis, keine Dateidaten, E107/E111)
  2 ROH --iso: Vergleich bis Partitionsende entscheidet; Ankerbereich dahinter getrennt ausgewiesen
  3 ABBILD: Start nur, wenn Label = --label-soll UND das Laufwerk zum eingebundenen Abbild --image gehoert
         (Get-DiskImage); sonst Abbruch ohne Register (E110). ISO: --image prueft dasselbe (empfohlen)
  4 Berichte: "nicht verglichen" statt "Abweichungen 0", wenn kein --iso (E108)
  5 Stufe REGISTER: Zeile als UNGUELTIG markieren (append-only, Sicherung vorher)
  7 ABBILD + HASH: Soll- und Ist-Hash im Befund; mit --disc-laufwerk automatischer Direktvergleich
         von der Disc: Disc = Soll und Abbild-Abweichung nur Null-Sektoren -> ABBILD_LUECKE (Hinweis, E113)
  + DISC/ABBILD/ROH-Register nur bei Label = --label-soll

AUFRUF (PowerShell, PC-Windows; Skriptordner D:\\_Berichte\\kopierplan\\skripte)
  py mdisc_pruefen_v1.2.py --stufe ORDNER --wurzel D:\\_MDISC\\D2
  py mdisc_pruefen_v1.2.py --stufe ISO    --wurzel H:\\ --image D:\\_MDISC\\MDISC_D2_<JJMMTT>.iso --label-soll MDISC_D2_<JJMMTT>
  # Admin-PowerShell, Disc aus dem ISO gebrannt:
  py mdisc_pruefen_v1.2.py --stufe ROH    --laufwerk E: --iso D:\\_MDISC\\MDISC_D2_<JJMMTT>.iso
                           --manifest D:\\_MDISC\\D2\\_MANIFEST\\Manifest_D2.csv --label-soll MDISC_D2_<JJMMTT> --satz A
  py mdisc_pruefen_v1.2.py --stufe REGISTER --ungueltig "31.10.2026 21:58:18" --disc D1 --satz A --grund "..."

AUSGABE  D:\\_Berichte\\mdisc\\pruefen_* (protokoll, befunde, zusammenfassung); Register mdisc_register.csv
EXIT     0 BESTANDEN/LESBAR | 1 BEFUND | 2 Aufruf-/Vorbedingungsfehler | 130 Strg+C

TESTS (Container, Linux, 31.10.2026): siehe Uebergabe v1.56 §3 - Windows-IOCTL, ReadFile auf \\\\.\\E:
  und Get-DiskImage sind NICHT getestet -> erster Lauf ist Test.

VERSIONSPROTOKOLL
  1.0  30.10.2026, 11:15  Erstfassung
  1.1  31.10.2026, 20:30  Zusatzmanifest/.dxp, ZIP-Test, Win32-Code, Protokoll/--ab, LANGSAM, Label, ZUSATZ/ABBILD/ROH
  1.2  31.10.2026, 22:30  ROH Luecken statt Nullblock, Partitionsgrenze, ENDE_KURZ, ISO-Vergleich bis Partitionsende,
                          Abbild-/Label-Sperre, Direktvergleich ABBILD_LUECKE, Stufe REGISTER, "nicht verglichen"
"""
import argparse, csv, datetime as dt, glob, hashlib, os, shutil, struct, subprocess, sys, time, zipfile
import xml.etree.ElementTree as ET

VERSION = "mdisc_pruefen_v1.2"
BLOCK = 4 * 2**20
CHUNK = 64 * 1024
S = 2048
GIB = 2**30
IST_WIN = os.name == "nt"
LANGSAM_S, LANGSAM_MBS = 30.0, 1.0
FEHLER_STATI = ("FEHLT", "GROESSE", "HASH", "LESEFEHLER", "EXTRA", "ZIP_FEHLER", "ABBILD_FEHLER")
TAGS = {1: "PVD", 2: "AVDP", 3: "VDP", 4: "IUVD", 5: "PD", 6: "LVD", 7: "USD", 8: "TD", 9: "LVID",
        256: "FSD", 257: "FID", 261: "FE", 266: "EFE"}
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def jetzt():
    return dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def lang(p):
    if IST_WIN and not p.startswith("\\\\?\\") and not p.startswith("\\\\.\\"):
        p = os.path.abspath(p)
        return "\\\\?\\UNC\\" + p[2:] if p.startswith("\\\\") else "\\\\?\\" + p
    return p


def fehlertext(e):
    w = getattr(e, "winerror", None)
    return "[Win32 %s] %s" % (w, e.strerror or e) if w else "%s: %s" % (type(e).__name__, e)


# ---------------------------------------------------------------- Windows-Lesen (Win32-Code, E101)
if IST_WIN:
    import ctypes
    from ctypes import wintypes
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _k32.ReadFile.restype = wintypes.BOOL
    _k32.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_longlong, ctypes.POINTER(ctypes.c_longlong), wintypes.DWORD]
    _k32.SetFilePointerEx.restype = wintypes.BOOL
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                     ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _k32.DeviceIoControl.restype = wintypes.BOOL
    _UNGUELTIG = wintypes.HANDLE(-1).value


class Leser:
    """Liest eine Datei oder ein Geraet; Fehler als OSError mit winerror. Test: geraet=True + Datei."""

    def __init__(self, pfad, geraet=False, fehler_sektoren=None):
        self.geraet = geraet
        self.fs = fehler_sektoren or set()
        self.pos = 0
        self.win = IST_WIN and (not geraet or pfad.startswith("\\\\.\\"))
        if self.win:
            flags = 0 if geraet else 0x08000000  # FILE_FLAG_SEQUENTIAL_SCAN
            h = _k32.CreateFileW(pfad if geraet else lang(pfad), 0x80000000, 3, None, 3, flags, None)
            if h is None or h == _UNGUELTIG:
                raise ctypes.WinError(ctypes.get_last_error())
            self.h = h
            self.buf = ctypes.create_string_buffer(BLOCK)
        else:
            self.f = open(pfad, "rb")

    def seek(self, pos):
        self.pos = pos
        if self.win:
            if not _k32.SetFilePointerEx(self.h, pos, None, 0):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            self.f.seek(pos)

    def lesen(self, n=BLOCK):
        if self.fs:   # Test: simulierter Sektorfehler (ganzer Lesevorgang schlaegt fehl, wie ReadFile)
            a, b = self.pos // S, (self.pos + n - 1) // S
            if any(a <= s <= b for s in self.fs):
                raise OSError(23, "Datenfehler (CRC-Pruefung) [Test]")
        if self.win:
            got = wintypes.DWORD(0)
            if not _k32.ReadFile(self.h, self.buf, n, ctypes.byref(got), None):
                raise ctypes.WinError(ctypes.get_last_error())
            self.pos += got.value
            return self.buf.raw[:got.value]
        b = self.f.read(n)
        self.pos += len(b)
        return b

    def laenge(self):
        """Nur Geraet: Laenge in Bytes (IOCTL_DISK_GET_LENGTH_INFO), sonst None."""
        if not (self.win and self.geraet):
            return None
        out = ctypes.c_longlong(0)
        r = wintypes.DWORD(0)
        ok = _k32.DeviceIoControl(self.h, 0x0007405C, None, 0, ctypes.byref(out), 8, ctypes.byref(r), None)
        return out.value if ok else None

    def schliessen(self):
        if self.win:
            _k32.CloseHandle(self.h)
        else:
            self.f.close()


class SektorAdapter:
    """seek/read-Schnittstelle fuer udf_struktur ueber einen Leser (Geraet: nur ganze Sektoren)."""

    def __init__(self, le):
        self.le, self.p = le, 0

    def seek(self, p):
        self.p = p

    def read(self, n):
        try:
            self.le.seek(self.p)
            return self.le.lesen(n)
        except OSError:
            return b""


def sha_lesen(p, zaehler=None):
    h = hashlib.sha256()
    n = 0
    le = Leser(p)
    try:
        while True:
            b = le.lesen()
            if not b:
                break
            h.update(b)
            n += len(b)
            if zaehler is not None:
                zaehler[0] += len(b)
    finally:
        le.schliessen()
    return h.hexdigest(), n


def volumen(lw):
    if not IST_WIN:
        return os.environ.get("MDISC_TEST_LABEL", "k.A.")
    name = ctypes.create_unicode_buffer(261)
    ok = _k32.GetVolumeInformationW(os.path.splitdrive(os.path.abspath(lw))[0] + "\\", name, 261, None, None, None, None, 0)
    return name.value if ok else "k.A."


def image_laufwerk(image):
    """Laufwerksbuchstabe, unter dem die Abbild-/ISO-Datei eingebunden ist ('' = nicht eingebunden, None = Fehler)."""
    if not IST_WIN:
        return os.environ.get("MDISC_TEST_IMAGE_LW", "")
    cmd = "$i = Get-DiskImage -ImagePath '%s'; if ($i.Attached) { ($i | Get-Volume).DriveLetter }" % image.replace("'", "''")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        print("FEHLER Get-DiskImage:", e)
        return None
    if r.returncode != 0:
        print("FEHLER Get-DiskImage:", (r.stderr or r.stdout).strip()[:300])
        return None
    return r.stdout.strip().upper()[:1]


def csv_lesen(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def disc_name(man):
    return os.path.splitext(os.path.basename(man))[0].replace("Manifest_", "")


# ---------------------------------------------------------------- UDF (aus mdisc_ende_v1.0, unveraendert in der Logik)
def tag(sek):
    if len(sek) < 16:
        return None
    tid, ver, cs = struct.unpack("<HHB", sek[:5])
    if tid not in TAGS or ver not in (2, 3):
        return None
    if (sum(sek[0:4]) + sum(sek[5:16])) & 0xFF != cs:
        return None
    return TAGS[tid], struct.unpack("<I", sek[12:16])[0]


def udf_struktur(f):
    """Partition (Start, Laenge) aus AVDP 256 -> Haupt-VDS -> PD. Rueckgabe dict oder {'fehler': ...}."""
    def sek(i):
        f.seek(i * S)
        return f.read(S)
    a = sek(256)
    t = tag(a)
    if not (t and t[0] == "AVDP"):
        return {"fehler": "kein AVDP in Sektor 256 (kein UDF oder unlesbar)"}
    ml, mo = struct.unpack("<II", a[16:24])
    u = {"vds": (mo, ml // S)}
    for i in range(mo, mo + min(ml // S, 64)):
        d = sek(i)
        t = tag(d)
        if not t:
            continue
        if t[0] == "PD":
            u["p_start"], u["p_len"] = struct.unpack("<II", d[188:196])
        elif t[0] == "TD":
            break
    if "p_start" not in u:
        u["fehler"] = "keine Partition (PD) im Haupt-VDS"
    else:
        u["p_ende"] = u["p_start"] + u["p_len"] - 1
    return u


# ---------------------------------------------------------------- Stufe ZUSATZ (unveraendert v1.1)
def dxp_dateien(dxp):
    baum = ET.parse(dxp).getroot()
    comp = baum.find("compilation")
    if comp is None:
        raise SystemExit("FEHLER: kein <compilation> in %s" % dxp)
    label = comp.get("name", "")
    erg = []

    def lauf(knoten, rel):
        for k in knoten:
            if k.tag == "file":
                erg.append(((rel + "\\" if rel else "") + k.get("name"), k.get("path", ""), k.get("date", "")))
            elif k.tag == "dir":
                p = k.get("path", "")
                lauf(k, "" if p in ("\\", "") else p.strip("\\"))
    lauf(comp, "")
    return label, erg


def stufe_zusatz(a):
    if not (a.dxp and a.manifest):
        print("FEHLER: --dxp und --manifest angeben"); return 2
    label, dateien = dxp_dateien(a.dxp)
    soll = {r["Pfad"].lower() for r in csv_lesen(a.manifest)}
    disc = disc_name(a.manifest)
    extra = [d for d in dateien if d[0].lower() not in soll and not d[0].lower().startswith("_manifest\\")]
    print("%s | Zusammenstellung %s | Label %s (%d Zeichen) | Dateien %d | im Manifest %d | Zusatz %d" % (
        VERSION, a.dxp, label, len(label), len(dateien), len(dateien) - len(extra), len(extra)), flush=True)
    if len(label) >= 16:
        print("HINWEIS: Label hat %d Zeichen; CDBurnerXP kuerzt auf 16 -> Soll-Label MDISC_D<n>_JJMMTT (15 Zeichen)" % len(label))
    zeilen, fehler = [], 0
    for rel, quelle, datum in extra:
        st, sha, n, mt, info = "OK", "", 0, "", ""
        try:
            s = os.stat(lang(quelle))
            mt = dt.datetime.fromtimestamp(s.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            t = time.time()
            sha, n = sha_lesen(quelle)
            info = "%.0f s" % (time.time() - t)
            if datum:
                d_dxp = dt.datetime.strptime(datum, "%Y-%m-%d %H:%M:%S")
                if abs((dt.datetime.fromtimestamp(s.st_mtime) - d_dxp).total_seconds()) > 2:
                    st = "QUELLE_GEAENDERT"
                    info += " | Quelle %s, Zusammenstellung %s -> Referenz unsicher, ZIP-Test entscheidet" % (mt, datum)
        except OSError as e:
            st, info = "QUELLE_FEHLT", fehlertext(e)
            fehler += 1
        zeilen.append([rel, n, sha, quelle, mt, datum, st, info])
        print("  %-18s %s  %d B  %s" % (st, rel, n, info), flush=True)
    os.makedirs(a.out, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    ziel = os.path.join(a.out, "Zusatzmanifest_%s_%s.csv" % (disc, ts))
    with open(ziel, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Pfad", "Bytes", "SHA256", "Quelle", "Quelle_mtime_lokal", "dxp_datum", "Status", "Info"])
        w.writerows(zeilen)
    print("Zusatzmanifest: %s | Label (Soll fuer --label-soll): %s" % (ziel, label))
    return 1 if fehler else 0


# ---------------------------------------------------------------- ZIP-Innenpruefung (unveraendert v1.1)
def zip_test(p):
    ok = fehl = nicht = 0
    erste = ""
    try:
        with open(lang(p), "rb") as fh, zipfile.ZipFile(fh) as zf:
            for zi in zf.infolist():
                if zi.is_dir():
                    continue
                if zi.flag_bits & 1:
                    nicht += 1
                    continue
                try:
                    with zf.open(zi) as e:
                        while e.read(BLOCK):
                            pass
                    ok += 1
                except NotImplementedError:
                    nicht += 1
                except (zipfile.BadZipFile, OSError, EOFError) as ex:
                    fehl += 1
                    erste = erste or "%s: %s" % (zi.filename, ex)
    except (zipfile.BadZipFile, OSError) as ex:
        return "ZIP_FEHLER", "Verzeichnis nicht lesbar: %s" % ex
    info = "Eintraege OK %d | Fehler %d | nicht pruefbar %d%s" % (ok, fehl, nicht, (" | " + erste) if erste else "")
    if fehl:
        return "ZIP_FEHLER", info
    return ("ZIP_OK" if not nicht else "ZIP_TEIL"), info


# ---------------------------------------------------------------- Direktvergleich Abbild <-> Disc (Nr. 7, E113)
def direkt_vergleich(p_abb, p_disc, soll):
    """Liest dieselbe Datei aus Abbild und von der Disc. Rueckgabe (status, info)."""
    try:
        la, ld = Leser(p_abb), Leser(p_disc)
    except OSError as e:
        return "HASH", "Direktvergleich nicht moeglich: %s" % fehlertext(e)
    h = hashlib.sha256()
    diff = nicht_null = 0
    erster = -1
    off = 0
    try:
        while True:
            ba, bd = la.lesen(), ld.lesen()
            if not ba and not bd:
                break
            h.update(bd)
            if ba != bd:
                for k in range(0, max(len(ba), len(bd)), S):
                    sa, sd = ba[k:k + S], bd[k:k + S]
                    if sa != sd:
                        diff += 1
                        erster = off + k if erster < 0 else erster
                        if any(sa):
                            nicht_null += 1
            off += max(len(ba), len(bd))
    except OSError as e:
        return "HASH", "Direktvergleich: Disc nicht lesbar %s" % fehlertext(e)
    finally:
        la.schliessen()
        ld.schliessen()
    hd = h.hexdigest()
    info = "Disc %s | Sektoren Abbild<>Disc %d ab Byte %d | davon im Abbild nicht Null %d" % (
        "= Soll" if hd == soll else "UNGLEICH Soll (%s)" % hd, diff, erster, nicht_null)
    if hd != soll:
        return "HASH", info
    if diff and nicht_null == 0:
        return "ABBILD_LUECKE", info
    return "ABBILD_FEHLER", info + " -> Disc gut, Abbild an anderer Stelle falsch: Ursache klaeren"


# ---------------------------------------------------------------- Stufen ORDNER/ISO/DISC/ABBILD
def stufe_dateien(a):
    w = a.wurzel
    if not w or not os.path.isdir(w):
        print("FEHLER: Wurzel nicht lesbar:", w); return 2
    man = a.manifest or (sorted(glob.glob(os.path.join(w, "_MANIFEST", "Manifest_D*.csv"))) or [""])[0]
    if not man or not os.path.isfile(man):
        print("FEHLER: Manifest nicht gefunden unter", os.path.join(w, "_MANIFEST")); return 2
    lab = volumen(w)
    # ---- Vorbedingungen (Nr. 3, E110)
    if a.stufe in ("DISC", "ABBILD"):
        if a.satz not in ("A", "B"):
            print("FEHLER: --satz A oder B angeben (Stufe %s)" % a.stufe); return 2
        if not a.label_soll:
            print("FEHLER: --label-soll angeben (Stufe %s, Register nur bei gleichem Label)" % a.stufe); return 2
        if lab != a.label_soll:
            print("FEHLER: Label Ist %s <> Soll %s -> falsches Laufwerk/Medium, nichts geprueft (E110)" % (lab, a.label_soll)); return 2
    if a.stufe == "ABBILD" and not a.image:
        print("FEHLER: --image <Abbild-Datei> angeben (Stufe ABBILD, E110)"); return 2
    if a.image and a.stufe in ("ISO", "ABBILD"):
        il = image_laufwerk(a.image)
        wl = os.path.splitdrive(os.path.abspath(w))[0][:1].upper() if IST_WIN else os.environ.get("MDISC_TEST_WURZEL_LW", "")
        if IST_WIN and il is None:
            print("FEHLER: Get-DiskImage nicht ausfuehrbar -> PowerShell als Administrator"); return 2
        if not il or il != wl:
            print("FEHLER: %s ist nicht als %s: eingebunden (eingebunden als: %s) -> Abbild/ISO einbinden bzw. --wurzel korrigieren (E110)"
                  % (a.image, wl, il or "nicht eingebunden")); return 2
    disc = disc_name(man)
    soll = [dict(r, _rolle="MANIFEST") for r in csv_lesen(man)]
    zus = []
    for zp in a.zusatz:
        for r in csv_lesen(zp):
            if r.get("Status", "OK") == "QUELLE_FEHLT" or not r.get("SHA256"):
                r["SHA256"] = ""
            zus.append(dict(r, _rolle="ZUSATZ"))
    alle = soll + zus
    soll_bytes = sum(int(r["Bytes"] or 0) for r in alle)
    luecken_info = ""
    if a.stufe == "ABBILD":
        lp = a.image + ".luecken.csv"
        if os.path.isfile(lp):
            lz = csv_lesen(lp)
            inp = sum(int(r["Anzahl"]) for r in lz if r["Bereich"] != "HINTER_PARTITION")
            luecken_info = "Abbild-Luecken (ROH v1.2): %d Bereiche, davon %d Sektoren innerhalb/vor der Partition" % (len(lz), inp)
        else:
            luecken_info = "Abbild-Luecken: keine .luecken.csv (Abbild aus ROH v1.1? Endblock genullt, E113)"
    print("%s Start %s | Stufe %s | Disc %s | Label %s" % (VERSION, jetzt(), a.stufe, disc, lab), flush=True)
    print("Manifest %d Dateien + Zusatz %d | %.2f GiB" % (len(soll), len(zus), soll_bytes / GIB), flush=True)
    if luecken_info:
        print(luecken_info, flush=True)

    os.makedirs(a.out, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    stamm = os.path.join(a.out, "pruefen_%s_%s_%s" % (disc, a.stufe, ts))
    proto = open(stamm + "_protokoll.csv", "w", newline="", encoding="utf-8-sig")
    pw = csv.writer(proto, delimiter=";")
    pw.writerow(["Nr", "Rolle", "Pfad", "Status", "Bytes", "Dauer_s", "MB_s", "Pos_GiB", "Pos_Prozent", "Info"])

    z = {k: 0 for k in ("OK", "FEHLT", "GROESSE", "HASH", "LESEFEHLER", "EXTRA", "MTIME_HINWEIS", "LANGSAM",
                        "ZIP_OK", "ZIP_TEIL", "ZIP_FEHLER", "OHNE_REFERENZ", "ABBILD_LUECKE", "ABBILD_FEHLER")}
    befunde, pfade = [], set()
    gelesen = [0]
    pos = 0
    t0 = letzte = time.time()
    abbruch = ""
    try:
        for i, r in enumerate(alle, 1):
            rel = r["Pfad"]
            pfade.add(rel.lower())
            bytes_soll = int(r["Bytes"] or 0)
            if i < a.ab:
                pos += bytes_soll
                continue
            p = os.path.join(w, rel.replace("\\", os.sep))
            st, info, td = "OK", "", 0.0
            try:
                s = os.stat(lang(p))
                if s.st_size != bytes_soll:
                    st, info = "GROESSE", "ist %d" % s.st_size
                else:
                    t = time.time()
                    sha, _ = sha_lesen(p, gelesen)
                    td = time.time() - t
                    if not r["SHA256"]:
                        st, info = "OHNE_REFERENZ", sha
                    elif sha != r["SHA256"].lower():
                        st, info = "HASH", "Ist %s | Soll %s" % (sha, r["SHA256"].lower())
                        if a.stufe == "ABBILD" and a.disc_laufwerk:
                            dl = a.disc_laufwerk.rstrip(":\\/").upper()
                            pd = os.path.join(dl + ":\\" if IST_WIN else a.disc_laufwerk, rel.replace("\\", os.sep))
                            print("  HASH %s -> Direktvergleich mit %s ..." % (rel, pd), flush=True)
                            st, i2 = direkt_vergleich(p, pd, r["SHA256"].lower())
                            info += " | " + i2
                    elif r.get("mtime_utc"):
                        soll_t = dt.datetime.strptime(r["mtime_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
                        if abs(s.st_mtime - soll_t) > 2:
                            z["MTIME_HINWEIS"] += 1
            except FileNotFoundError:
                st = "FEHLT"
            except OSError as e:
                st, info = "LESEFEHLER", fehlertext(e)
            mbs = bytes_soll / 1e6 / td if td else 0.0
            if st == "OK" and td > LANGSAM_S and mbs < LANGSAM_MBS:
                z["LANGSAM"] += 1
                befunde.append((r["_rolle"], rel, "LANGSAM", "%.0f s, %.2f MB/s" % (td, mbs), pos))
            z[st] += 1
            if st != "OK":
                befunde.append((r["_rolle"], rel, st, info, pos))
            pw.writerow([i, r["_rolle"], rel, st, bytes_soll, "%.2f" % td, "%.2f" % mbs, "%.3f" % (pos / GIB),
                         "%.2f" % (100.0 * pos / soll_bytes if soll_bytes else 0), info])
            pos += bytes_soll
            if time.time() - letzte > 10:
                proto.flush()
                letzte = time.time()
                el = time.time() - t0
                print("  %d/%d  %.2f/%.2f GiB  %.1f MB/s  Befunde %d" % (
                    i, len(alle), pos / GIB, soll_bytes / GIB, gelesen[0] / 1e6 / el if el else 0,
                    sum(1 for b in befunde if b[2] not in ("LANGSAM", "ABBILD_LUECKE"))), flush=True)
        if a.zip_test:
            for r in zus:
                if r["Pfad"].lower().endswith(".zip"):
                    p = os.path.join(w, r["Pfad"].replace("\\", os.sep))
                    if not os.path.isfile(lang(p)):
                        continue
                    print("  ZIP-Test %s ..." % r["Pfad"], flush=True)
                    t = time.time()
                    st, info = zip_test(p)
                    z[st] += 1
                    befunde.append(("ZUSATZ", r["Pfad"], st, info + " | %.0f s" % (time.time() - t), -1))
        mdir = os.path.join(w, "_MANIFEST").lower()
        for wurzel, dirs, files in os.walk(lang(w)):
            for n in files:
                p = os.path.join(wurzel, n).replace("\\\\?\\", "")
                if p.lower().startswith(mdir):
                    continue
                rel = os.path.relpath(p, w).replace(os.sep, "\\")
                if rel.lower() not in pfade:
                    z["EXTRA"] += 1
                    befunde.append(("-", rel, "EXTRA", "", -1))
    except KeyboardInterrupt:
        abbruch = "Strg+C"
    proto.close()
    dauer = time.time() - t0
    fehler = sum(z[k] for k in FEHLER_STATI) + z["OHNE_REFERENZ"]
    with open(stamm + "_befunde.csv", "w", newline="", encoding="utf-8-sig") as fh:
        cw = csv.writer(fh, delimiter=";")
        cw.writerow(["Rolle", "Pfad", "Status", "Info", "Pos_GiB_Manifestreihenfolge", "Pos_Prozent"])
        for rolle, rel, st, info, ps in befunde:
            cw.writerow([rolle, rel, st, info, "%.3f" % (ps / GIB) if ps >= 0 else "",
                         "%.2f" % (100.0 * ps / soll_bytes) if ps >= 0 and soll_bytes else ""])
    teil = " (Teillauf ab Nr. %d - fuer Nachweis Gesamtlauf noetig)" % a.ab if a.ab > 1 else ""
    zusatz_txt = ""
    if z["ABBILD_LUECKE"]:
        zusatz_txt = ", %d Datei(en) direkt von Disc = Soll (ABBILD_LUECKE)" % z["ABBILD_LUECKE"]
    ergebnis = "ABGEBROCHEN" if abbruch else (
        ("BESTANDEN" + zusatz_txt + teil) if fehler == 0 else "BEFUND (%d)%s" % (fehler, teil))
    zusf = ["%s | %s | Stufe %s | Wurzel %s | Label %s%s" % (VERSION, jetzt(), a.stufe, w, lab,
                                                           " | Image %s" % a.image if a.image else ""),
            "Disc %s | Manifest %s | Zusatz %s" % (disc, man, ", ".join(a.zusatz) or "-"),
            "Soll %d Dateien (Manifest %d + Zusatz %d), %d B (%.2f GiB) | gelesen %d B" % (
                len(alle), len(soll), len(zus), soll_bytes, soll_bytes / GIB, gelesen[0]),
            "OK %d | FEHLT %d | GROESSE %d | HASH %d | LESEFEHLER %d | EXTRA %d | OHNE_REFERENZ %d | ABBILD_LUECKE %d | ABBILD_FEHLER %d" % (
                z["OK"], z["FEHLT"], z["GROESSE"], z["HASH"], z["LESEFEHLER"], z["EXTRA"], z["OHNE_REFERENZ"],
                z["ABBILD_LUECKE"], z["ABBILD_FEHLER"]),
            "ZIP-Test: OK %d | TEIL %d | FEHLER %d | Hinweise: LANGSAM %d, Zeitstempel %d" % (
                z["ZIP_OK"], z["ZIP_TEIL"], z["ZIP_FEHLER"], z["LANGSAM"], z["MTIME_HINWEIS"]),
            "Dauer %.0f s (%.1f min) | Tempo %.1f MB/s" % (dauer, dauer / 60, gelesen[0] / 1e6 / dauer if dauer else 0)]
    if luecken_info:
        zusf.append(luecken_info)
    if a.label_soll:
        zusf.append("Label: Soll %s | Ist %s | %s" % (a.label_soll, lab, "gleich" if lab == a.label_soll else "ABWEICHEND (Hinweis)"))
    zusf.append("ERGEBNIS: %s" % ergebnis)
    if a.stufe in ("DISC", "ABBILD") and ergebnis.startswith("BESTANDEN") and not teil:
        register(a, disc, lab, man, len(soll), sum(int(r["Bytes"]) for r in soll), len(zus),
                 sum(int(r["Bytes"] or 0) for r in zus),
                 ("BESTANDEN (Abbild" + zusatz_txt + ")") if a.stufe == "ABBILD" else ergebnis, stamm)
        zusf.append("Register ergaenzt: %s" % os.path.join(a.out, "mdisc_register.csv"))
    with open(stamm + "_zusammenfassung.txt", "w", encoding="utf-8-sig") as fh:
        fh.write("\n".join(zusf) + "\n")
    print("\n".join(zusf))
    for rolle, rel, st, info, ps in befunde[:20]:
        print("  %s  %s  %s  %s" % (st, rolle, rel, info))
    print("Berichte:", stamm + "_*")
    return 130 if abbruch else (0 if fehler == 0 else 1)


def register(a, disc, label, man, n, b, nz, bz, ergebnis, stamm):
    reg = os.path.join(a.out, "mdisc_register.csv")
    neu = not os.path.exists(reg)
    msha = hashlib.sha256(open(man, "rb").read()).hexdigest()
    with open(reg, "a", newline="", encoding="utf-8-sig" if neu else "utf-8") as fh:
        cw = csv.writer(fh, delimiter=";")
        if neu:
            cw.writerow(["Satz", "Disc", "Label", "Pruefdatum", "Dateien", "Bytes", "Manifest_SHA256", "Zusatz_Dateien",
                         "Zusatz_Bytes", "Ergebnis", "Bericht", "Lagerort", "Naechster_Lesetest"])
        cw.writerow([a.satz, disc, label, jetzt(), n, b, msha, nz, bz, ergebnis,
                     os.path.basename(stamm) + "_zusammenfassung.txt", "", ""])


# ---------------------------------------------------------------- Stufe REGISTER (Nr. 5)
def stufe_register(a):
    reg = os.path.join(a.out, "mdisc_register.csv")
    if not (a.ungueltig and a.disc and a.satz in ("A", "B") and a.grund):
        print("FEHLER: --ungueltig \"<Pruefdatum>\" --disc D<n> --satz A|B --grund \"...\" angeben"); return 2
    if not os.path.isfile(reg):
        print("FEHLER: Register fehlt:", reg); return 2
    rows = csv_lesen(reg)
    treffer = [r for r in rows if r["Satz"] == a.satz and r["Disc"] == a.disc and r["Pruefdatum"] == a.ungueltig
               and r["Ergebnis"].startswith("BESTANDEN")]
    schon = [r for r in rows if r["Satz"] == a.satz and r["Disc"] == a.disc and r["Pruefdatum"] == a.ungueltig
             and r["Ergebnis"].startswith("UNGUELTIG")]
    if not treffer:
        print("FEHLER: keine BESTANDEN-Zeile Satz %s / %s / %s im Register" % (a.satz, a.disc, a.ungueltig)); return 2
    if schon:
        print("HINWEIS: bereits als UNGUELTIG markiert - nichts geschrieben"); return 0
    sich = reg[:-4] + "_vor_%s.csv" % dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copyfile(reg, sich)
    r = treffer[0]
    with open(reg, "a", newline="", encoding="utf-8") as fh:
        csv.writer(fh, delimiter=";").writerow([a.satz, a.disc, r["Label"], a.ungueltig, "", "", "", "", "",
                                                "UNGUELTIG (%s, %s)" % (a.grund, jetzt()), r["Bericht"], "", ""])
    print("Register: Zeile %s/%s/%s als UNGUELTIG ergaenzt | Sicherung %s" % (a.satz, a.disc, a.ungueltig, sich))
    return 0


# ---------------------------------------------------------------- Stufe ROH (Nr. 1, 2, 4)
def bereich_lesen(d, pos, n, stat):
    """Liest n Bytes ab pos. Fehlende Sektoren werden genullt und als Luecke gemeldet.
    Rueckgabe (daten, [(sektor, art, info)]); art KURZ = 0 Bytes ohne Fehler, FEHLER = Win32-Fehler."""
    b, err = None, None
    try:
        d.seek(pos)
        b = d.lesen(n)
    except OSError as e:
        err = e
    if b is not None and len(b) == n:
        return b, []
    buf = bytearray(n)
    luecken = []
    off = 0
    if b:
        off = len(b) - len(b) % S
        buf[:off] = b[:off]
    stat["nachlesen"] += 1
    while off < n:
        c = min(CHUNK, n - off)
        bb = None
        try:
            d.seek(pos + off)
            bb = d.lesen(c)
        except OSError:
            bb = None
        if bb is not None and len(bb) == c:
            buf[off:off + c] = bb
            off += c
            continue
        for s_ in range(off, off + c, S):
            try:
                d.seek(pos + s_)
                bs = d.lesen(S)
                if len(bs) == S:
                    buf[s_:s_ + S] = bs
                    continue
                luecken.append(((pos + s_) // S, "KURZ", "%d B ohne Fehler" % len(bs)))
            except OSError as e:
                luecken.append(((pos + s_) // S, "FEHLER", fehlertext(e)))
                stat["fehler"] += 1
                if stat["fehler"] >= stat["max"]:
                    raise KeyboardInterrupt("max")
        off += c
    return bytes(buf), luecken


def zusammenfassen(luecken):
    """Einzelsektoren -> Bereiche [von, bis, art, info]."""
    erg = []
    for s_, art, info in sorted(luecken):
        if erg and erg[-1][1] == s_ - 1 and erg[-1][2] == art:
            erg[-1][1] = s_
        else:
            erg.append([s_, s_, art, info])
    return erg


def stufe_roh(a):
    test = bool(a.geraet_datei)
    if not IST_WIN and not test:
        print("FEHLER: Stufe ROH nur unter Windows (Test: --geraet-datei)"); return 2
    lw = a.laufwerk.rstrip(":\\").upper()
    if len(lw) != 1 and not test:
        print("FEHLER: --laufwerk z. B. E:"); return 2
    if a.satz and a.satz not in ("A", "B"):
        print("FEHLER: --satz A oder B"); return 2
    geraet = a.geraet_datei or "\\\\.\\%s:" % lw
    lab = volumen(lw + ":\\") if not test else os.environ.get("MDISC_TEST_LABEL", "k.A.")
    fs = set()
    for t_ in a.test_fehler:
        v, _, b_ = t_.partition("-")
        fs.update(range(int(v), int(b_ or v) + 1))
    try:
        d = Leser(geraet, geraet=True, fehler_sektoren=fs)
    except OSError as e:
        print("FEHLER: Laufwerk nicht roh lesbar:", fehlertext(e),
              "-> PowerShell 'Als Administrator ausfuehren' und erneut starten"); return 2
    laenge = d.laenge() or (os.path.getsize(a.geraet_datei) if test else None)
    iso = None
    if a.iso:
        iso = Leser(a.iso)
        iso_len = os.path.getsize(a.iso)
        if laenge and iso_len != laenge:
            print("HINWEIS: ISO %d B, Disc %d B - verglichen wird bis zum kleineren Wert" % (iso_len, laenge))
        laenge = min(iso_len, laenge) if laenge else iso_len
    if a.laenge_bytes:
        laenge = a.laenge_bytes
    if not laenge:
        print("FEHLER: Disc-Laenge nicht ermittelbar -> --laenge-bytes angeben"); return 2
    # UDF-Partition: aus dem ISO (Referenz) bzw. von der Disc
    u = udf_struktur(open(a.iso, "rb") if a.iso else SektorAdapter(d))
    quelle_u = "ISO" if a.iso else "Disc"
    p_ende = u.get("p_ende")
    cut = (p_ende + 1) * S if p_ende is not None else laenge
    abb = None
    if a.abbild:
        if os.path.exists(a.abbild):
            print("FEHLER: Abbild existiert bereits:", a.abbild); return 2
        frei = shutil.disk_usage(os.path.dirname(os.path.abspath(a.abbild))).free
        if frei < laenge * 1.02:
            print("FEHLER: zu wenig Platz fuer Abbild: frei %.2f GiB, noetig %.2f GiB" % (frei / GIB, laenge * 1.02 / GIB)); return 2
        abb = open(a.abbild, "wb")
    print("%s Start %s | Stufe ROH | %s | Label %s | %d B (%.2f GiB) | ISO %s | Abbild %s" % (
        VERSION, jetzt(), geraet, lab, laenge, laenge / GIB, a.iso or "-", a.abbild or "-"), flush=True)
    print("UDF-Partition (%s): %s" % (quelle_u, "Start %d, Ende %d" % (u["p_start"], p_ende) if p_ende is not None
                                      else "k.A. (%s)" % u.get("fehler")), flush=True)
    os.makedirs(a.out, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    stamm = os.path.join(a.out, "pruefen_ROH_%s_%s" % (lw if not test else "TEST", ts))
    hd, hi, hdp, hip = hashlib.sha256(), hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    stat = {"nachlesen": 0, "fehler": 0, "max": a.max_lesefehler}
    pos, luecken, abw_p, abw_a, t0, letzte, abbruch = 0, [], [], 0, time.time(), time.time(), ""
    try:
        while pos < laenge:
            n = min(BLOCK, laenge - pos)
            b, lk = bereich_lesen(d, pos, n, stat)
            if lk:
                luecken += lk
                print("  LUECKE bei %.3f GiB: %d Sektor(en), erster %d %s" % (pos / GIB, len(lk), lk[0][0], lk[0][2]), flush=True)
            hd.update(b)
            m = max(0, min(n, cut - pos))          # Anteil bis Partitionsende
            hdp.update(b[:m])
            if abb:
                abb.write(b)
            if iso:
                iso.seek(pos)
                bi = iso.lesen(n)
                hi.update(bi)
                hip.update(bi[:m])
                if bi[:m] != b[:m]:
                    k = sum(1 for o in range(0, m, S) if bi[o:o + S] != b[o:o + S])
                    abw_p.append((pos, k))
                if bi[m:] != b[m:]:
                    abw_a += sum(1 for o in range(m, n, S) if bi[o:o + S] != b[o:o + S])
            pos += n
            if time.time() - letzte > 10:
                letzte = time.time()
                el = time.time() - t0
                print("  %.2f/%.2f GiB  %.1f %%  %.1f MB/s  Luecken %d Sektoren  Abweichungen %s" % (
                    pos / GIB, laenge / GIB, 100.0 * pos / laenge, pos / 1e6 / el, len(luecken),
                    sum(k for _, k in abw_p) if iso else "nicht verglichen"), flush=True)
    except KeyboardInterrupt as e:
        abbruch = "max. Lesefehler erreicht" if str(e) == "max" else "Strg+C"
    d.schliessen()
    if iso:
        iso.schliessen()
    if abb:
        abb.close()
    dauer = time.time() - t0
    ber = zusammenfassen(luecken)
    for r in ber:
        if p_ende is None:
            r.append("PARTITION_KA")
        elif r[0] > p_ende:
            r.append("HINTER_PARTITION")
        elif r[1] < u["p_start"]:
            r.append("VOR_PARTITION")
        else:
            r.append("PARTITION")
    n_hinter = sum(r[1] - r[0] + 1 for r in ber if r[4] == "HINTER_PARTITION")
    n_innen = sum(r[1] - r[0] + 1 for r in ber if r[4] != "HINTER_PARTITION")
    n_fehler = sum(r[1] - r[0] + 1 for r in ber if r[2] == "FEHLER")
    kopf = ["Art", "Sektor_von", "Sektor_bis", "Anzahl", "Offset_B", "Pos_GiB", "Bereich", "Info"]
    zeilen = [[r[2], r[0], r[1], r[1] - r[0] + 1, r[0] * S, "%.3f" % (r[0] * S / GIB), r[4], r[3]] for r in ber]
    with open(stamm + "_befunde.csv", "w", newline="", encoding="utf-8-sig") as fh:
        cw = csv.writer(fh, delimiter=";")
        cw.writerow(kopf + ["Sektoren_ungleich"])
        for z_ in zeilen:
            cw.writerow(z_ + [""])
        for p_, k in abw_p:
            cw.writerow(["ABWEICHUNG_ISO", p_ // S, (p_ + BLOCK) // S - 1, "", p_, "%.3f" % (p_ / GIB), "PARTITION_BLOCK", "", k])
    if a.abbild:
        with open(a.abbild + ".luecken.csv", "w", newline="", encoding="utf-8-sig") as fh:
            cw = csv.writer(fh, delimiter=";")
            cw.writerow(["Art", "Sektor_von", "Sektor_bis", "Anzahl", "Offset_B", "Pos_GiB", "Bereich", "Info"])
            cw.writerows(zeilen)
    n_abw = sum(k for _, k in abw_p)
    ende_kurz = " | Hinweis ENDE_KURZ: %d Sektoren hinter Partitionsende nicht geliefert (UDF-Anker, keine Dateidaten)" % n_hinter if n_hinter else ""
    if abbruch:
        ergebnis = "ABGEBROCHEN (%s)" % abbruch
    elif n_innen:
        ergebnis = "BEFUND (Luecken %d Sektoren %s, davon Lesefehler %d)" % (
            n_innen, "innerhalb/vor der Partition" if p_ende is not None else "- Partition k.A.", n_fehler)
    elif iso and n_abw:
        ergebnis = "ABWEICHUNG ZUM ISO bis Partitionsende (%d Sektoren in %d Bloecken) - Disc nicht aus diesem ISO gebrannt? Dateiweise pruefen" % (n_abw, len(abw_p))
    elif iso:
        ergebnis = "BESTANDEN (Disc = ISO bis Partitionsende, bitgleich)" + ende_kurz
    else:
        ergebnis = "LESBAR (0 Luecken in Daten) - Inhalt nicht verglichen" + ende_kurz
    zusf = ["%s | %s | Stufe ROH | %s | Label %s" % (VERSION, jetzt(), geraet, lab),
            "Laenge %d B (%.2f GiB) | gelesen bis %d B | Bloecke a %d B | nachgelesene Bloecke %d" % (
                laenge, laenge / GIB, pos, BLOCK, stat["nachlesen"]),
            "UDF-Partition (%s): %s" % (quelle_u, "Start %d, Ende %d (= %d B)" % (u["p_start"], p_ende, cut)
                                        if p_ende is not None else "k.A. (%s)" % u.get("fehler")),
            "SHA-256 Disc gesamt %s (Luecken genullt) | bis Partitionsende %s" % (hd.hexdigest(), hdp.hexdigest())]
    if iso:
        zusf.append("SHA-256 ISO  gesamt %s | bis Partitionsende %s" % (hi.hexdigest(), hip.hexdigest()))
        zusf.append("Vergleich ISO: bis Partitionsende ungleich %d Sektoren | Ankerbereich dahinter ungleich %d Sektoren (Hinweis)" % (n_abw, abw_a))
    else:
        zusf.append("Vergleich ISO: nicht verglichen (kein --iso)")
    zusf.append("Luecken: %d Bereiche | innerhalb/vor Partition %d Sektoren | hinter Partition %d Sektoren | Lesefehler %d Sektoren" % (
        len(ber), n_innen, n_hinter, n_fehler))
    for r in ber[:10]:
        zusf.append("  %s %d ... %d (%d) %s %s" % (r[2], r[0], r[1], r[1] - r[0] + 1, r[4], r[3]))
    zusf.append("Abbild %s%s" % (a.abbild or "-", (" | Luecken: " + a.abbild + ".luecken.csv") if a.abbild else ""))
    zusf.append("Dauer %.0f s (%.1f min) | Tempo %.1f MB/s" % (dauer, dauer / 60, pos / 1e6 / dauer if dauer else 0))
    if a.label_soll:
        zusf.append("Label: Soll %s | Ist %s | %s" % (a.label_soll, lab, "gleich" if lab == a.label_soll else "ABWEICHEND"))
    zusf.append("ERGEBNIS: %s" % ergebnis)
    if a.abbild and not n_innen and not abbruch:
        zusf.append("NAECHSTER SCHRITT: Abbild einbinden, dann --stufe ABBILD --wurzel <LW>:\\ --image %s --label-soll ... --satz A|B" % a.abbild)
    if iso and ergebnis.startswith("BESTANDEN"):
        if not a.satz:
            zusf.append("Register: nicht ergaenzt (--satz fehlt)")
        elif not (a.label_soll and lab == a.label_soll):
            zusf.append("Register: nicht ergaenzt (Label Ist %s <> --label-soll %s)" % (lab, a.label_soll or "-"))
        elif not (a.manifest and os.path.isfile(a.manifest)):
            zusf.append("Register: nicht ergaenzt (--manifest <Manifest der Disc> angeben)")
        else:
            soll = csv_lesen(a.manifest)
            register(a, disc_name(a.manifest), lab, a.manifest, len(soll), sum(int(r["Bytes"]) for r in soll),
                     0, 0, "BESTANDEN (ROH=ISO bis Partitionsende%s)" % (", ENDE_KURZ %d" % n_hinter if n_hinter else ""), stamm)
            zusf.append("Register ergaenzt: %s" % os.path.join(a.out, "mdisc_register.csv"))
    with open(stamm + "_zusammenfassung.txt", "w", encoding="utf-8-sig") as fh:
        fh.write("\n".join(zusf) + "\n")
    print("\n".join(zusf))
    print("Berichte:", stamm + "_*")
    if abbruch == "Strg+C":
        return 130
    return 0 if ergebnis.startswith(("BESTANDEN", "LESBAR")) else 1


def main():
    ap = argparse.ArgumentParser(description=VERSION)
    ap.add_argument("--stufe", default="ORDNER", choices=["ZUSATZ", "ORDNER", "ISO", "DISC", "ABBILD", "ROH", "REGISTER"])
    ap.add_argument("--wurzel", default="")
    ap.add_argument("--manifest", default="")
    ap.add_argument("--zusatz", action="append", default=[], help="Zusatzmanifest-CSV (mehrfach moeglich)")
    ap.add_argument("--dxp", default="", help="Stufe ZUSATZ: CDBurnerXP-Zusammenstellung")
    ap.add_argument("--kein-zip-test", dest="zip_test", action="store_false")
    ap.add_argument("--label-soll", default="")
    ap.add_argument("--satz", default="", help="DISC/ABBILD/REGISTER (und ROH mit --iso): A oder B")
    ap.add_argument("--image", default="", help="ISO/ABBILD: eingebundene Datei (Pruefung Laufwerk, E110)")
    ap.add_argument("--disc-laufwerk", default="", help="ABBILD: bei HASH Direktvergleich von dieser Disc (z. B. E:)")
    ap.add_argument("--ab", type=int, default=1, help="Fortsetzen ab Dateinummer (Protokoll Spalte Nr)")
    ap.add_argument("--laufwerk", default="E:")
    ap.add_argument("--iso", default="")
    ap.add_argument("--abbild", default="")
    ap.add_argument("--laenge-bytes", type=int, default=0)
    ap.add_argument("--max-lesefehler", type=int, default=2000, help="ROH: Abbruch nach so vielen Fehlersektoren")
    ap.add_argument("--ungueltig", default="", help="REGISTER: Pruefdatum der Zeile")
    ap.add_argument("--disc", default="", help="REGISTER: z. B. D1")
    ap.add_argument("--grund", default="", help="REGISTER: Begruendung")
    ap.add_argument("--geraet-datei", default="", help=argparse.SUPPRESS)
    ap.add_argument("--test-fehler", action="append", default=[], help=argparse.SUPPRESS)
    ap.add_argument("--out", default=r"D:\_Berichte\mdisc")
    a = ap.parse_args()
    if a.stufe == "ZUSATZ":
        return stufe_zusatz(a)
    if a.stufe == "ROH":
        return stufe_roh(a)
    if a.stufe == "REGISTER":
        return stufe_register(a)
    return stufe_dateien(a)


if __name__ == "__main__":
    sys.exit(main())
