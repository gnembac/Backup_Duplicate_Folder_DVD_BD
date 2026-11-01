#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mdisc_sektorvergleich_v1.1.py - Projekt "Basisdaten ermitteln" (privat)
Version 1.1 | Stand 01.11.2026, 12:40 MEZ | Autor: Claude fuer Gunter Nembach

ZWECK (NUR LESEN - ISO und Disc werden nie veraendert; geschrieben werden nur Berichte)
  Klaert, WAS in den Sektoren abweicht, die mdisc_pruefen (Stufe ROH --iso) als ABWEICHUNG_ISO
  gemeldet hat, und ob DATEIINHALTE betroffen sind.
  Teil 1 ISO (immer, ohne Disc, ca. 1 min): liest alle UDF-File-Entries (FE/EFE) des ISO, bildet daraus
         die Lage jeder Datei (Extents) und das Dateiende im letzten Sektor (EOF-Offset).
         Je 4-MiB-Block: Zahl der "angebrochenen letzten Dateisektoren" gegen Sektoren_ungleich.
  Teil 2 Disc (--laufwerk E:, Admin): liest Stichprobe (--stichprobe N) oder alle (--alle) abweichenden
         Bloecke erneut und ordnet jeden ungleichen Sektor zu:
           NACH_EOF    letzter Sektor einer Datei, Abweichung erst ab dem Dateiende -> Fuellbytes, Inhalt gleich
           FE_FELDER   ISO-Sektor ist FE/EFE (Verwaltung)
           DESKRIPTOR  anderer UDF-Deskriptor
           FREI        Sektor gehoert zu keiner Datei
           DATEN       Abweichung innerhalb von Dateidaten (vor dem Dateiende)      -> kritisch
           UNKLAR      Zuordnung nicht moeglich (z. B. Extent-Fortsetzung)            -> kritisch bis geklaert
  CRC-/Lueckenbereiche aus der Befund-CSV: betroffene Dateien (FE-Sektor, Groesse, mit --manifest
  Kandidatenpfade gleicher Groesse) werden aufgelistet; diese Bloecke werden nicht gelesen.

AUFRUF (Skriptordner D:\\_Berichte\\kopierplan\\skripte)
  py mdisc_sektorvergleich_v1.1.py --iso D:\\_MDISC\\MDISC_D2_261101.iso
       --befunde D:\\_Berichte\\mdisc\\pruefen_ROH_E_2026-11-01_080714_befunde.csv
       [--manifest D:\\_MDISC\\D2_V3\\_MANIFEST\\Manifest_D2.csv] [--laufwerk E: [--stichprobe 40 | --alle]]
AUSGABE  D:\\_Berichte\\mdisc\\sektorvergleich_<ts>_{bloecke.csv, sektoren.csv, luecken_dateien.csv, zusammenfassung.txt}
EXIT     0 keine kritische Abweichung | 1 DATEN/UNKLAR | 2 Aufruf-/Vorbedingungsfehler | 130 Strg+C

TESTS    01.11.2026 Linux-Container, synthetisches UDF-aehnliches Abbild (FE/EFE mit short_ad/long_ad,
         Fuellbytes nach EOF, Datenfehler vor EOF, freie Sektoren, Lueckenbereich). Windows-Rohzugriff =
         Klasse Leser aus mdisc_pruefen_v1.2; v1.0 lief unter Windows (01.11.2026 11:26). Die Abbildung
         Extent -> Sektor (Partitionsstart + LBN) ist an CDBurnerXP-ISO NICHT getestet: Plausibilitaetszeilen
         in der Zusammenfassung pruefen.
VERSIONSPROTOKOLL
  1.0  01.11.2026, 11:40  Erstfassung (Klasse FUELLBYTES nur, wenn ISO hinter der Abweichung Null ist)
  1.1  01.11.2026, 12:40  Fehlalarm v1.0 behoben: Dateiende aus den UDF-Extents (NACH_EOF), Klassen FREI/UNKLAR,
                          Teil 1 je Block "angebrochene letzte Sektoren", Dateien in CRC-Luecken, --manifest
"""
import argparse, binascii, bisect, csv, datetime as dt, os, struct, sys, time
from collections import Counter, defaultdict

VERSION = "mdisc_sektorvergleich_v1.1"
BLOCK = 4 * 2**20
S = 2048
SPB = BLOCK // S
GIB = 2**30
IST_WIN = os.name == "nt"
TAGS = {1: "PVD", 2: "AVDP", 3: "VDP", 4: "IUVD", 5: "PD", 6: "LVD", 7: "USD", 8: "TD", 9: "LVID",
        256: "FSD", 257: "FID", 258: "AED", 259: "IE", 260: "TE", 261: "FE", 262: "EAHD", 263: "USE",
        264: "SBD", 265: "PIE", 266: "EFE"}
FE_MAP = [(0, 16, "Tag"), (16, 36, "ICB-Tag"), (36, 48, "Uid/Gid/Rechte"), (48, 56, "Links/Satzformat"),
          (56, 72, "Laenge/Bloecke"), (72, 84, "Zugriffszeit"), (84, 96, "Aenderungszeit"),
          (96, 108, "Attributzeit"), (108, 112, "Checkpoint"), (112, 128, "EA-ICB"),
          (128, 160, "Implementierung"), (160, 168, "UniqueID"), (168, 176, "L_EA/L_AD"),
          (176, S, "EA/Zuordnung")]
EFE_MAP = [(0, 16, "Tag"), (16, 36, "ICB-Tag"), (36, 48, "Uid/Gid/Rechte"), (48, 56, "Links/Satzformat"),
           (56, 80, "Laenge/Objekt/Bloecke"), (80, 92, "Zugriffszeit"), (92, 104, "Aenderungszeit"),
           (104, 116, "Erstellzeit"), (116, 128, "Attributzeit"), (128, 136, "Checkpoint"),
           (136, 168, "EA/Stream-ICB"), (168, 200, "Implementierung"), (200, 208, "UniqueID"),
           (208, 216, "L_EA/L_AD"), (216, S, "EA/Zuordnung")]
DATEITYP = {4: "Verzeichnis", 5: "Datei", 250: "Metadatendatei", 251: "Metadaten-Spiegel", 252: "Metadaten-Bitmap"}
KRITISCH = ("DATEN", "UNKLAR")
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass


def jetzt():
    return dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def fehlertext(e):
    w = getattr(e, "winerror", None)
    return "[Win32 %s] %s" % (w, e.strerror or e) if w else "%s: %s" % (type(e).__name__, e)


# ------------------------------------------------- Leser (unveraendert aus mdisc_pruefen_v1.2, gekuerzt)
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
    _UNGUELTIG = wintypes.HANDLE(-1).value


class Leser:
    def __init__(self, pfad, geraet=False):
        self.win = IST_WIN and geraet and pfad.startswith("\\\\.\\")
        if self.win:
            h = _k32.CreateFileW(pfad, 0x80000000, 3, None, 3, 0, None)
            if h is None or h == _UNGUELTIG:
                raise ctypes.WinError(ctypes.get_last_error())
            self.h = h
            self.buf = ctypes.create_string_buffer(BLOCK)
        else:
            self.f = open(pfad, "rb")

    def lesen_ab(self, pos, n):
        if self.win:
            if not _k32.SetFilePointerEx(self.h, pos, None, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            got = wintypes.DWORD(0)
            if not _k32.ReadFile(self.h, self.buf, n, ctypes.byref(got), None):
                raise ctypes.WinError(ctypes.get_last_error())
            return self.buf.raw[:got.value]
        self.f.seek(pos)
        return self.f.read(n)

    def schliessen(self):
        if self.win:
            _k32.CloseHandle(self.h)
        else:
            self.f.close()


# ------------------------------------------------- UDF
def tag(sek, crc=True):
    if len(sek) < 16:
        return None
    tid, ver = struct.unpack_from("<HH", sek, 0)
    if tid not in TAGS or ver not in (2, 3):
        return None
    if (sum(sek[0:4]) + sum(sek[5:16])) & 0xFF != sek[4]:
        return None
    if crc:
        c, ln = struct.unpack_from("<HH", sek, 8)
        if 16 + ln <= len(sek) and binascii.crc_hqx(bytes(sek[16:16 + ln]), 0) != c:
            return None
    return TAGS[tid], tid


def partition(iso):
    """(Start, Ende) der Partition aus AVDP 256 -> VDS -> PD."""
    with open(iso, "rb") as f:
        def sek(i):
            f.seek(i * S)
            return f.read(S)
        a = sek(256)
        t = tag(a, crc=False)
        if not (t and t[0] == "AVDP"):
            return None, None, "kein AVDP in Sektor 256"
        ml, mo = struct.unpack_from("<II", a, 16)
        for i in range(mo, mo + min(ml // S, 64)):
            d = sek(i)
            t = tag(d, crc=False)
            if t and t[0] == "PD":
                ps, pl = struct.unpack_from("<II", d, 188)
                return ps, ps + pl - 1, "Start %d, Ende %d" % (ps, ps + pl - 1)
            if t and t[0] == "TD":
                break
    return None, None, "keine PD"


def fe_lesen(sek, tid):
    """(Dateityp, Groesse, [(lbn, laenge_B, art, partref)], Problem) aus FE/EFE."""
    ftyp = sek[27]
    adtyp = struct.unpack_from("<H", sek, 34)[0] & 7
    groesse = struct.unpack_from("<Q", sek, 56)[0]
    o_ea, basis = (168, 176) if tid == 261 else (208, 216)
    l_ea, l_ad = struct.unpack_from("<II", sek, o_ea)
    ad0 = basis + l_ea
    if ad0 + l_ad > S:
        return ftyp, groesse, [], "AD_ZU_LANG"
    ext, problem = [], ""
    if adtyp == 3:
        return ftyp, groesse, [], "EINGEBETTET"
    schritt = 8 if adtyp == 0 else (16 if adtyp == 1 else 0)
    if not schritt:
        return ftyp, groesse, [], "AD_TYP_%d" % adtyp
    for o in range(ad0, ad0 + l_ad - schritt + 1, schritt):
        lr, lbn = struct.unpack_from("<II", sek, o)
        art, laenge = lr >> 30, lr & 0x3FFFFFFF
        pref = struct.unpack_from("<H", sek, o + 8)[0] if adtyp == 1 else -1
        if laenge == 0:
            break
        if art == 3:
            problem = "FORTSETZUNG"
            break
        ext.append((lbn, laenge, art, pref))
    return ftyp, groesse, ext, problem


# ------------------------------------------------- Befund-CSV / Manifest
def befunde_lesen(p):
    diff, sperre = {}, []
    with open(p, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            if r["Art"] == "ABWEICHUNG_ISO":
                diff[int(r["Sektor_von"])] = int(r["Sektoren_ungleich"])
            elif r["Art"] in ("FEHLER", "KURZ"):
                sperre.append((int(r["Sektor_von"]), int(r["Sektor_bis"]), r["Art"], r.get("Bereich", "")))
    return diff, sperre


def manifest_groessen(p):
    m = defaultdict(list)
    if p and os.path.isfile(p):
        with open(p, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh, delimiter=";"):
                try:
                    m[int(r["Bytes"])].append(r["Pfad"])
                except (KeyError, ValueError):
                    pass
    return m


# ------------------------------------------------- Teil 1: ISO
class Karte:
    """Sektor -> (Datei-Nr, ist_letzter, eof_offset). Intervalle sortiert, Suche per bisect."""

    def __init__(self):
        self.iv = []           # (von, bis, nr)
        self.dateien = []      # (fe_sektor, typ, groesse, letzter_sektor, eof_offset)

    def fertig(self):
        self.iv.sort()
        self.starts = [v for v, _, _ in self.iv]

    def suche(self, s):
        """Extents ueberlappen nicht (UDF); geprueft werden die zwei Kandidaten links von s."""
        i = bisect.bisect_right(self.starts, s) - 1
        for j in (i, i - 1):
            if j >= 0 and self.iv[j][0] <= s <= self.iv[j][1]:
                return self.iv[j][2]
        return None


def teil_iso(iso, diff, p_start, p_ende):
    groesse_iso = os.path.getsize(iso)
    karte = Karte()
    st = Counter()
    fe_sektoren = []
    meta_start = None
    t0 = letzte = time.time()
    roh = []                     # (fe_sektor, tid, ftyp, groesse, ext, problem)
    with open(iso, "rb") as f:
        pos = 0
        while pos < groesse_iso:
            b = f.read(BLOCK)
            if not b:
                break
            s0 = pos // S
            zweit = b[1::S]
            i = zweit.find(1)
            while i >= 0:
                o = i * S
                if b[o] in (5, 10) and s0 + i <= p_ende:
                    sek = b[o:o + S]
                    t = tag(sek)
                    if t and t[1] in (261, 266):
                        ftyp, gr, ext, prob = fe_lesen(sek, t[1])
                        roh.append((s0 + i, t[1], ftyp, gr, ext, prob))
                        fe_sektoren.append(s0 + i)
                        if ftyp == 250 and ext:
                            meta_start = ext[0][0]
                i = zweit.find(1, i + 1)
            pos += len(b)
            if time.time() - letzte > 10:
                letzte = time.time()
                print("  ISO %.2f/%.2f GiB  FE/EFE bisher %d" % (pos / GIB, groesse_iso / GIB, len(roh)), flush=True)
    # Extents -> physische Sektoren (Annahme: LBN relativ zum Partitionsstart; Verzeichnisse mit short_ad
    # liegen bei vorhandener Metadatendatei in der Metadatenpartition)
    tails_block = Counter()
    ausserhalb = 0
    for fe_s, tid, ftyp, gr, ext, prob in roh:
        st["typ_%s" % DATEITYP.get(ftyp, ftyp)] += 1
        if prob:
            st["problem_%s" % prob] += 1
        if not ext or ftyp in (250, 251, 252):
            continue
        basis = p_start
        if ftyp == 4 and meta_start is not None and ext[0][3] == -1:
            basis = p_start + meta_start
        nr = len(karte.dateien)
        rest = gr
        letzter, eof = None, 0
        ok = True
        for lbn, laenge, art, pref in ext:
            if art != 0:
                continue
            v = basis + lbn
            n_sek = (laenge + S - 1) // S
            b_ = v + n_sek - 1
            if v < p_start or b_ > p_ende:
                ok = False
                break
            karte.iv.append((v, b_, nr))
            nutz = min(laenge, rest)
            rest -= nutz
            if nutz > 0:
                letzter = v + (nutz - 1) // S
                eof = nutz % S
        if not ok:
            ausserhalb += 1
            continue
        karte.dateien.append((fe_s, DATEITYP.get(ftyp, ftyp), gr, letzter, eof))
        if letzter is not None and eof:
            tails_block[(letzter // SPB) * SPB] += 1
            st["angebrochen"] += 1
    karte.fertig()
    zeilen, cmp = [], Counter()
    erklaerbar = 0
    for s0, k in sorted(diff.items()):
        t_ = tails_block.get(s0, 0)
        cmp["gleich" if k == t_ else ("weniger" if k < t_ else "mehr")] += 1
        erklaerbar += min(k, t_)
        zeilen.append([s0, "%.3f" % (s0 * S / GIB), k, t_])
    tails_ohne_diff = sum(v for s0, v in tails_block.items() if s0 not in diff)
    return {"karte": karte, "fe": len(roh), "st": st, "ausserhalb": ausserhalb, "meta_start": meta_start,
            "fe_erster": min(fe_sektoren) if fe_sektoren else None, "fe_letzter": max(fe_sektoren) if fe_sektoren else None,
            "cmp": cmp, "erklaerbar": erklaerbar, "tails_ohne_diff": tails_ohne_diff, "zeilen": zeilen,
            "bytes_dateien": sum(d[2] for d in karte.dateien if d[1] == "Datei"),
            "n_dateien": sum(1 for d in karte.dateien if d[1] == "Datei"), "dauer": time.time() - t0}


# ------------------------------------------------- Teil 2: Disc
def felder(offs, tid):
    m = FE_MAP if tid == 261 else EFE_MAP
    n = set()
    for o in offs:
        for a, b_, name in m:
            if a <= o < b_:
                n.add(name)
                break
    n.discard("Tag")
    return "+".join(sorted(n)) or "nur Tag"


def einordnen(s, si, sd, karte):
    offs = [i for i in range(min(len(si), len(sd))) if si[i] != sd[i]]
    ti, td = tag(si), tag(sd)
    if ti and ti[1] in (261, 266):
        return "FE_FELDER", ti[0] + ":" + felder(offs, ti[1]), offs, ti, td, None
    if ti:
        return "DESKRIPTOR", ti[0], offs, ti, td, None
    nr = karte.suche(s)
    if nr is None:
        return "FREI", "", offs, ti, td, None
    fe_s, typ, gr, letzter, eof = karte.dateien[nr]
    if s == letzter and eof and offs and offs[0] >= eof:
        return "NACH_EOF", "%s, EOF bei Byte %d" % (typ, eof), offs, ti, td, nr
    if letzter is None:
        return "UNKLAR", "%s ohne Dateiende" % typ, offs, ti, td, nr
    return "DATEN", "%s, %s, EOF %d" % (typ, "letzter Sektor" if s == letzter else "innerer Sektor", eof), offs, ti, td, nr


def teil_disc(a, iso, diff, sperre, p_ende, karte):
    def gesperrt(s0):
        return any(v <= s0 + SPB - 1 and b_ >= s0 for v, b_, _, _ in sperre)
    kand = [s0 for s0 in sorted(diff) if not gesperrt(s0)]
    ausgelassen = len(diff) - len(kand)
    if a.alle or a.stichprobe >= len(kand):
        wahl = kand
    else:
        n = max(2, a.stichprobe)
        wahl = sorted({kand[round(i * (len(kand) - 1) / (n - 1))] for i in range(n)})
    geraet = a.geraet_datei or "\\\\.\\%s:" % a.laufwerk.rstrip(":\\/").upper()
    try:
        d = Leser(geraet, geraet=True)
    except OSError as e:
        print("FEHLER: Laufwerk nicht roh lesbar:", fehlertext(e), "-> PowerShell als Administrator")
        return None
    li = Leser(iso)
    klassen = Counter()
    det_z = Counter()
    sek_zeilen, bl_zeilen = [], []
    lesefehler = jetzt_summe = csv_summe = 0
    t0 = letzte = time.time()
    try:
        for j, s0 in enumerate(wahl, 1):
            pos = s0 * S
            m = min(BLOCK, (p_ende + 1) * S - pos)
            if m <= 0:
                continue
            bi = li.lesen_ab(pos, m)
            try:
                bd = d.lesen_ab(pos, m)
            except OSError as e:
                lesefehler += 1
                bl_zeilen.append([s0, "%.3f" % (pos / GIB), diff[s0], "", "LESEFEHLER " + fehlertext(e)])
                continue
            k = 0
            for o in range(0, min(len(bi), len(bd)), S):
                si, sd = bi[o:o + S], bd[o:o + S]
                if si == sd:
                    continue
                k += 1
                s = s0 + o // S
                kl, det, offs, ti, td, nr = einordnen(s, si, sd, karte)
                klassen[kl] += 1
                if kl in ("FE_FELDER", "DESKRIPTOR"):
                    det_z[det] += 1
                null_rest = offs and not any(sd[offs[0]:])
                sek_zeilen.append([s0, s, "%.3f" % ((pos + o) / GIB), kl, det, ti[0] if ti else "", td[0] if td else "",
                                   len(offs), offs[0] if offs else "", offs[-1] if offs else "",
                                   "ja" if null_rest else "nein",
                                   karte.dateien[nr][0] if nr is not None else "", karte.dateien[nr][2] if nr is not None else ""])
            jetzt_summe += k
            csv_summe += diff[s0]
            bl_zeilen.append([s0, "%.3f" % (pos / GIB), diff[s0], k, "" if k == diff[s0] else "ANZAHL_ANDERS"])
            if time.time() - letzte > 10:
                letzte = time.time()
                print("  Disc %d/%d Bloecke  %.0f s  Klassen %s" % (j, len(wahl), time.time() - t0, dict(klassen)), flush=True)
    except KeyboardInterrupt:
        print("ABGEBROCHEN (Strg+C) - Teilergebnis wird geschrieben")
        klassen["_ABGEBROCHEN"] = 1
    finally:
        d.schliessen()
        li.schliessen()
    return {"kand": len(kand), "ausgelassen": ausgelassen, "gewaehlt": len(wahl), "lesefehler": lesefehler,
            "klassen": klassen, "det": det_z, "sek": sek_zeilen, "bl": bl_zeilen,
            "jetzt": jetzt_summe, "csv": csv_summe, "dauer": time.time() - t0}


def luecken_dateien(sperre, karte, mgr):
    """Dateien, die einen Lueckenbereich (Lesefehler) beruehren."""
    erg = []
    for v, b_, art, ber in sperre:
        if art != "FEHLER":
            continue
        gesehen = set()
        for s in range(v, b_ + 1):
            nr = karte.suche(s)
            if nr is None or nr in gesehen:
                continue
            gesehen.add(nr)
            fe_s, typ, gr, letzter, eof = karte.dateien[nr]
            kand = mgr.get(gr, [])
            erg.append([v, b_, typ, fe_s, gr, len(kand), " | ".join(kand[:3])])
        if not gesehen:
            erg.append([v, b_, "FREI", "", "", "", ""])
    return erg


# ------------------------------------------------- Hauptteil
def main():
    ap = argparse.ArgumentParser(description=VERSION)
    ap.add_argument("--iso", required=True)
    ap.add_argument("--befunde", required=True, help="pruefen_ROH_*_befunde.csv")
    ap.add_argument("--manifest", default="", help="optional: Kandidatenpfade fuer Dateien in Luecken")
    ap.add_argument("--laufwerk", default="", help="z. B. E: (Teil 2, Admin)")
    ap.add_argument("--stichprobe", type=int, default=40)
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--out", default=r"D:\_Berichte\mdisc")
    ap.add_argument("--geraet-datei", default="", help=argparse.SUPPRESS)
    a = ap.parse_args()
    for p in (a.iso, a.befunde):
        if not os.path.isfile(p):
            print("FEHLER: Datei fehlt:", p)
            return 2
    diff, sperre = befunde_lesen(a.befunde)
    if not diff:
        print("FEHLER: keine ABWEICHUNG_ISO-Zeilen in", a.befunde)
        return 2
    p_start, p_ende, pinfo = partition(a.iso)
    if p_start is None:
        print("FEHLER: UDF-Partition im ISO nicht lesbar:", pinfo)
        return 2
    print("%s Start %s | ISO %s | Partition %s" % (VERSION, jetzt(), a.iso, pinfo), flush=True)
    print("Befund-CSV: %d Bloecke / %d Sektoren ungleich | Lueckenbereiche %d" % (
        len(diff), sum(diff.values()), len(sperre)), flush=True)
    os.makedirs(a.out, exist_ok=True)
    stamm = os.path.join(a.out, "sektorvergleich_%s" % dt.datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    try:
        r1 = teil_iso(a.iso, diff, p_start, p_ende)
    except KeyboardInterrupt:
        print("ABGEBROCHEN (Strg+C) in Teil 1")
        return 130
    karte = r1["karte"]
    with open(stamm + "_bloecke.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Sektor_von", "Pos_GiB", "Ungleich_CSV", "Angebrochene_letzte_Sektoren_ISO"])
        w.writerows(r1["zeilen"])
    ld = luecken_dateien(sperre, karte, manifest_groessen(a.manifest))
    with open(stamm + "_luecken_dateien.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Luecke_von", "Luecke_bis", "Typ", "FE_Sektor", "Bytes", "Manifest_Kandidaten", "Kandidaten (max. 3)"])
        w.writerows(ld)
    st, cmp = r1["st"], r1["cmp"]
    summe = sum(diff.values())
    z = ["%s | %s | ISO %s | Befunde %s" % (VERSION, jetzt(), a.iso, a.befunde),
         "Partition: %s" % pinfo,
         "TEIL 1 ISO (%.0f s): FE/EFE %d (Sektor %s ... %s) | %s | Probleme: %s | ausserhalb Partition %d" % (
             r1["dauer"], r1["fe"], r1["fe_erster"], r1["fe_letzter"],
             ", ".join("%s %d" % (k[4:], v) for k, v in sorted(st.items()) if k.startswith("typ_")),
             ", ".join("%s %d" % (k[8:], v) for k, v in sorted(st.items()) if k.startswith("problem_")) or "keine",
             r1["ausserhalb"]),
         "  Plausibilitaet Karte: Dateien %d, Summe %d B (%.2f GiB), Metadatenpartition ab LBN %s" % (
             r1["n_dateien"], r1["bytes_dateien"], r1["bytes_dateien"] / GIB, r1["meta_start"]),
         "  angebrochene letzte Sektoren (Datei endet mitten im Sektor): %d | davon in Bloecken ohne Abweichung %d" % (
             st["angebrochen"], r1["tails_ohne_diff"]),
         "  Bloecke mit Abweichung %d: Ungleich = angebrochene %d | kleiner %d | groesser %d" % (
             len(diff), cmp["gleich"], cmp["weniger"], cmp["mehr"]),
         "  hoechstens durch Fuellbytes nach Dateiende erklaerbar: %d von %d ungleichen Sektoren (%.1f %%)" % (
             r1["erklaerbar"], summe, 100.0 * r1["erklaerbar"] / max(1, summe))]
    for r in ld:
        z.append("  Luecke %s-%s: %s FE %s, %s B, Manifest-Kandidaten %s: %s" % tuple(r))
    rc = 0
    if a.laufwerk or a.geraet_datei:
        r2 = teil_disc(a, a.iso, diff, sperre, p_ende, karte)
        if r2 is None:
            return 2
        with open(stamm + "_sektoren.csv", "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["Block_Sektor", "Sektor", "Pos_GiB", "Klasse", "Detail", "Tag_ISO", "Tag_Disc", "Bytes_ungleich",
                        "Erstes_Byte", "Letztes_Byte", "Disc_ab_Abweichung_Null", "FE_Sektor", "Datei_Bytes"])
            w.writerows(r2["sek"])
            w.writerow([])
            w.writerow(["Block_Sektor", "Pos_GiB", "Ungleich_CSV", "Ungleich_jetzt", "Hinweis"])
            w.writerows(r2["bl"])
        kl = r2["klassen"]
        null_rest = sum(1 for r in r2["sek"] if r[10] == "ja")
        z += ["TEIL 2 Disc %s (%.0f s): Bloecke gelesen %d von %d (%s) | Bloecke mit Luecke ausgelassen %d | Lesefehler %d" % (
                  a.geraet_datei or a.laufwerk, r2["dauer"], r2["gewaehlt"], r2["kand"],
                  "alle" if a.alle else "Stichprobe", r2["ausgelassen"], r2["lesefehler"]),
              "  ungleiche Sektoren jetzt %d | laut CSV %d | %s" % (
                  r2["jetzt"], r2["csv"], "gleich (Lesung reproduzierbar)" if r2["jetzt"] == r2["csv"] else "ABWEICHEND (Lesung instabil?)"),
              "  Klassen: " + " | ".join("%s %d" % (k, kl[k]) for k in
                                          ("NACH_EOF", "FE_FELDER", "DESKRIPTOR", "FREI", "DATEN", "UNKLAR") if kl[k]),
              "  Disc ab erstem abweichendem Byte bis Sektorende Null: %d von %d" % (null_rest, r2["jetzt"])]
        for det, n in r2["det"].most_common(6):
            z.append("    %-60s %d" % (det, n))
        krit = sum(kl[k] for k in KRITISCH)
        if kl.get("_ABGEBROCHEN"):
            erg = "ABGEBROCHEN (Teilergebnis)"
        elif krit:
            erg = "KRITISCH: %d Sektoren mit Abweichung in Dateidaten/unklar -> Sektoren-CSV pruefen" % krit
            rc = 1
        elif r2["jetzt"] == 0:
            erg = "nicht entschieden (keine ungleichen Sektoren gelesen)"
        else:
            erg = ("keine Abweichung in Dateidaten %s; Abweichungen nur %s" % (
                "(ALLE abweichenden Bloecke)" if a.alle else "(Stichprobe; Rest Ableitung)",
                ", ".join(k for k in kl if not k.startswith("_"))))
        z.append("ERGEBNIS: " + erg)
    else:
        z.append("TEIL 2 Disc: nicht ausgefuehrt (kein --laufwerk)")
        z.append("ERGEBNIS: nur ISO-Teil")
    with open(stamm + "_zusammenfassung.txt", "w", encoding="utf-8-sig") as fh:
        fh.write("\n".join(z) + "\n")
    print("\n".join(z))
    print("Berichte:", stamm + "_*")
    return rc


if __name__ == "__main__":
    sys.exit(main())
