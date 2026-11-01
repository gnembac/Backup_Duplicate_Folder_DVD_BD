#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""medien_pruefen v1.5 (28.10.2026, 10:05 MEZ) - ALLES IN EINEM: Inventar -> Vergleich -> Import -> Teilrettung -> Statusmeldung fuer EIN Medium.
NEU in v1.5 (Anlass: Disc 2644 - ABBRUCHREGEL nach 25 Lesefehlern in Folge, obwohl jeder Fehler nur 0,03 s kostete; 10.055 gelesene Dateien wurden NICHT verglichen/importiert):
  * ABBRUCH = TEILLAUF, KEIN VERLUST: Bei jeder Abbruchregel (Exit 3), Strg+C (130) und Laufwerk-weg (4, nur ohne Import) laufen Vergleich, Import und Teilrettung
    fuer alle bis dahin gelesenen Dateien trotzdem; nicht gelesene Dateien stehen als NICHT_GELESEN in Inventar/DB/Bericht. Aufruf wiederholen setzt fort. --kein-teilimport schaltet ab.
  * Abbruchregel zeitbewusst: --max-fehler-folge greift nur, wenn die Fehler in Folge zusammen >= --folge-min-s (60) Sekunden gekostet haben (schnelle Fehler sind billig -> weiterlesen).
  * TEILRETTUNG (Standard, --ohne-rettung schaltet ab): Dateien mit Lesefehler/Zeitlimit/Import-Kopierfehler werden blockweise gelesen (64 KiB -> 2048-Byte-Sektor), defekte Sektoren
    uebersprungen, uebersprungene Zonen in Durchgang 2 nachgeholt; lesbare Teile werden nach D:/Archiv_Medien/<Nr>/_TEILRETTUNG/<Pfad> geschrieben (Luecken = Nullbytes) + <Datei>.luecken.csv.
    Existiert ein Bestands-Kandidat gleicher Groesse, werden die lesbaren Bereiche Byte fuer Byte verglichen: identisch -> BESTAETIGT_IM_BESTAND (nichts abgelegt, eigene Temp-Datei entfernt),
    sonst TEIL_GERETTET (abgelegt). Wiederholter Aufruf liest nur noch die Luecken (Sidecar) und fuellt sie auf. Zeitbudget --rettung-max-min (90) / --rettung-datei-max-min (20).
  * Oeffnen mit Wiederholung (--open-wiederholen 2) und Ersatz-Oeffnung per CreateFileW (inkl. BACKUP_SEMANTICS); echter Win32-Fehlercode im Grund (Errno 13 war nur das CRT-Abbild).
  * --luecken: GAP-Bericht ueber alle Medien aus medien.sqlite (Nummernluecken, offene Discs, ungedeckte/unverifizierte Dateien, M-DISC, Dubletten) -> _GAP_Report_<ts>.txt/.csv.
  * Ausgabe <Nr>_rettung_<ts>.csv und <Nr>_rettung_naechste_schritte_<ts>.txt (ddrescue/7-Zip-Befehle fuer nicht oeffnbare Dateien).
  * STATUS: in Linux-Sandbox mit simulierten Fehlern getestet (--testhook BAD/OPENERR). UNGETESTET unter Windows: CreateFileW-Ersatzoeffnung, Verhalten des UDF-Treibers bei 2048-Byte-Lesen.
NEU in v1.4 (Anlass: Disc 2614 - einzelne Lesezugriffe blockierten 793 s bzw. 7222 s; Tempo-Regel rechnete nach Fortsetzen falsch):
  * SKIP-MODUS (Standard, --ohne-skip schaltet ab): Eine Datei wird UEBERSPRUNGEN (Status LESEFEHLER, Grund ZEITLIMIT_*/TEMPO_*/HAENGT_*),
    wenn ein Lesezugriff >= --chunk-timeout-s dauert, die langsamen Zugriffe einer Datei zusammen >= --datei-fehlzeit-s ergeben
    oder das Dateitempo nach --min-mbs-nach-s unter --min-mbs liegt. Der Rest der Disc wird weitergelesen; uebersprungene
    Dateien laufen durch die bestehende Namenssuche und stehen in <Nr>_uebersprungen_<ts>.csv.
  * Kleinere Lesebloecke (--chunk-kib, Standard 256 statt 1024) und Vorsichtsmodus (64 KiB) nach dem ersten langsamen/fehlerhaften Zugriff
    fuer den Rest der Datei und die naechsten --vorsicht-dateien Dateien: begrenzt, wie lange ein einzelner Zugriff in schlechter Zone blockiert.
  * HAENGT-Schutz: Zugriff blockiert >= --haengt-abbruch-s -> Windows CancelSynchronousIo (Versuch); >= --haengt-hart-s -> Datei im
    Checkpoint als uebersprungen sichern und Prozess beenden (Exit 3); erneuter Aufruf macht mit der naechsten Datei weiter.
  * Tempo-Regel korrigiert: zaehlt nur gesund gelesene Bytes/Zeit DIESES Laufs (kein Fehlalarm mehr nach Fortsetzen mit wenigen Dateien).
  * Checkpoint-Spalte 7 "Grund"; --max-fehlzeit-min Standard 60; --langsam-s Standard 10; Zeitlimit-Skips zaehlen nicht zu --max-fehler-folge.
  * Checkpoint bleibt nach Abschluss erhalten (Kopie <Nr>_inventar_fertig_<ts>.csv): erneuter Aufruf liest nichts neu, --fehler-wiederholen nur die fehlgeschlagenen/uebersprungenen Dateien.
  * v1.3-Checkpoints (6 Spalten) werden uebernommen.
  * Danach: --fehler-wiederholen mit hoeheren Grenzen oder ddrescue-Image fuer die uebersprungenen Dateien.
  * STATUS: in Linux-Sandbox mit simulierten Verzoegerungen getestet (--testhook). UNGETESTET unter Windows: CancelSynchronousIo am echten Laufwerkstreiber,
    Prozessende bei blockierendem Treiber, Durchsatz mit 256-KiB-Bloecken (Rueckfall: --chunk-kib 1024).
NEU in v1.3 (Anlass: Disc 2614, drei Laeufe ohne Ergebnis, >20 h):
  * Fortschritt mit Tempo (MB/s) alle --herzschlag s; meldet auch, wenn ein einzelner Lesezugriff haengt.
  * Fortsetzen nach Abbruch: jede Datei wird sofort in <Nr>_inventar_laufend.csv gesichert; erneuter Aufruf macht weiter.
  * Abbruchregeln statt Dauerlauf: --max-fehler-folge, --max-fehlzeit-min, --max-minuten (Exit 3 = fortsetzbar).
  * Laufwerk-weg-Erkennung (Exit 4): Dateien werden dann NICHT als Lesefehler gebucht.
  * --vorab    : nur Metadaten (Name, Groesse, Datum) gegen den Bestand abgleichen; liest KEINE Dateiinhalte der Disc.
  * --schnelltest: Stichproben-Lesetest mit Zeitmessung + Tempo; Empfehlung Direktlauf oder Image.
  * --mapfile  : ddrescue-Image mit Luecken erkennen; Import ungedeckter Dateien dann gesperrt (--image-luecken-ok).
  * <Nr>_lesetempo_<ts>.csv (Dauer/MB/s je Datei), UTF-8-sichere Konsole (kein Absturz bei Sonderzeichen).
Aufruf (nur die Nummer eingeben, der Rest laeuft automatisch):
  py medien_pruefen_v1.5.py 2614 --vorab           # 1. Schritt bei Problem-Discs: Deckung ohne Lesen der Disc
  py medien_pruefen_v1.5.py 2614 --schnelltest     # 2. Schritt: Disc-/Laufwerkzustand in wenigen Minuten
  py medien_pruefen_v1.5.py 2603                   # Normalfall (fragt nach der Nummer, wenn weggelassen)
  py medien_pruefen_v1.5.py 2603 --nur-pruefen     # nichts kopieren (Trockenlauf des Imports)
  py medien_pruefen_v1.5.py 2603 --mdisc-ok        # M-DISC fuer dieses Medium gebrannt UND verifiziert -> Register
  py medien_pruefen_v1.5.py 2614 --laufwerk G:\\ --mapfile D:\\Medien_Images\\2614.map   # gemountetes ddrescue-Image
Exit-Codes: 0 geprueft/OK | 1 OFFEN (Befund) | 3 Abbruchregel (fortsetzbar) | 4 Laufwerk weg | 130 Strg+C.
Medium (Disc) wird nur LESEND angefasst. Kopiert wird nur nach --ziel (D:\\Archiv_Medien\\<Nr>\\), nie ueberschrieben/geloescht.
Berichte: --out (D:\\_Berichte\\medien): <Nr>_inventar.csv, <Nr>_vergleich_<ts>.csv, <Nr>_bericht_<ts>.txt, medien.sqlite."""
import argparse, csv, datetime, hashlib, os, re, shutil, sqlite3, sys, threading, time, unicodedata
try:
    sys.stdout.reconfigure(errors="replace"); sys.stderr.reconfigure(errors="replace")
except Exception: pass
P = argparse.ArgumentParser()
P.add_argument("medium", nargs="?", default="")
P.add_argument("--laufwerk", default="", help="nur noetig, wenn das Laufwerk nicht automatisch erkannt wird (auch gemountetes Image)")
P.add_argument("--out", default=r"D:\_Berichte\medien")
P.add_argument("--ziel", default=r"D:\Archiv_Medien")
P.add_argument("--mdisc-register", default="")
P.add_argument("--ref", action="append", default=[], help='weitere Referenz "KLASSE|ORT|PFAD", z. B. NAS')
P.add_argument("--ohne-standard-refs", action="store_true")
P.add_argument("--auch-muell", action="store_true", help="Muell (Thumbs.db, ~$, .tmp) mit importieren")
P.add_argument("--nur-pruefen", action="store_true")
P.add_argument("--ueberschreiben", action="store_true", help="Nummer darf mit anderer Disc neu belegt werden")
P.add_argument("--mdisc-ok", action="store_true")
P.add_argument("--ignoriere", action="append", default=[], help="nicht lesbare Datei bewusst ueberspringen: Teil des Pfads (mehrfach moeglich); wird im Bericht als AKZEPTIERTE AUSNAHME ausgewiesen")
P.add_argument("--name-akzeptieren", action="store_true", help="Lesefehler-Datei auch bei reinem Namenstreffer (nur Dateiname gleich, Ordner abweichend) als gedeckt werten")
# ---- neu v1.3
P.add_argument("--vorab", action="store_true", help="NUR Metadaten-Abgleich (Name+Groesse+Datum) gegen den Bestand, liest keine Disc-Inhalte")
P.add_argument("--schnelltest", action="store_true", help="NUR Stichproben-Lesetest mit Zeitmessung, keine Hash-/Import-Schritte")
P.add_argument("--schnell-jedes", type=int, default=3, help="Schnelltest: jede N-te Datei (Dateien ab 64 MiB immer)")
P.add_argument("--schnell-langsam-s", type=float, default=3.0, help="Schnelltest: Stichprobe (256 KiB) laenger als N s = LANGSAM")
P.add_argument("--langsam-s", type=float, default=10.0, help="Normallauf: ein Lesezugriff (Block) laenger als N s = LANGSAM (v1.3: 20)")
P.add_argument("--max-fehler-folge", type=int, default=25, help="Abbruch nach N aufeinanderfolgenden Lesefehlern (0 = aus)")
P.add_argument("--max-fehlzeit-min", type=float, default=60.0, help="Abbruch, wenn in langsamen/fehlerhaften Zugriffen/uebersprungenen Dateien zusammen N Minuten verbraucht sind (0 = aus)")
P.add_argument("--max-minuten", type=float, default=0.0, help="Abbruch nach N Minuten Inventar-Gesamtzeit (0 = aus; Schnelltest: Standard 20)")
P.add_argument("--max-prognose-h", type=float, default=3.0, help="Abbruch, wenn die Restzeit (bei gemessenem Tempo) mehr als N Stunden betraegt (0 = aus)")
P.add_argument("--tempo-fenster-min", type=float, default=5.0, help="Tempo-Regel greift erst nach N Minuten Lesezeit")
P.add_argument("--herzschlag", type=int, default=30, help="Statuszeile alle N Sekunden")
P.add_argument("--neu", action="store_true", help="angefangenen Lauf verwerfen und von vorn beginnen")
P.add_argument("--fehler-wiederholen", action="store_true", help="beim Fortsetzen auch frueher fehlgeschlagene Dateien erneut lesen")
P.add_argument("--mapfile", default="", help="ddrescue-Mapfile des Images (erkennt ungelesene Bereiche)")
P.add_argument("--image-luecken-ok", action="store_true", help="Import ungedeckter Dateien trotz Luecken im Image erlauben")
# ---- neu v1.4 (Skip-Modus)
P.add_argument("--ohne-skip", action="store_true", help="Skip-Modus aus (Verhalten wie v1.3: nie wegen Zeit ueberspringen)")
P.add_argument("--chunk-kib", type=int, default=256, help="Lesebloecke in KiB (v1.3: 1024). Kleiner = Zeitlimits greifen frueher")
P.add_argument("--chunk-timeout-s", type=float, default=45.0, help="Skip: ein einzelner Lesezugriff dauerte >= N s -> Datei ueberspringen")
P.add_argument("--datei-fehlzeit-s", type=float, default=150.0, help="Skip: langsame Zugriffe (>= --langsam-s) einer Datei zusammen >= N s -> Datei ueberspringen")
P.add_argument("--min-mbs", type=float, default=0.25, help="Skip: Dateitempo unter N MB/s ...")
P.add_argument("--min-mbs-nach-s", type=float, default=90.0, help="... gilt erst nach N s Lesezeit in dieser Datei")
P.add_argument("--vorsicht-dateien", type=int, default=10, help="nach langsamem/fehlerhaftem Zugriff: so viele Folgedateien mit 64-KiB-Bloecken lesen")
P.add_argument("--haengt-abbruch-s", type=float, default=120.0, help="Zugriff blockiert >= N s: CancelSynchronousIo versuchen (nur Windows; 0 = aus)")
P.add_argument("--haengt-hart-s", type=float, default=600.0, help="Zugriff blockiert >= N s: Datei als uebersprungen sichern, Prozess beenden (Exit 3; 0 = aus)")
P.add_argument("--testhook", action="append", default=[], help=argparse.SUPPRESS)   # Selbsttest: "TEIL=SEK[@MiB]", "TEIL=ERR[@MiB]", "TEIL=BAD@vonKiB-bisKiB", "TEIL=OPENERR"
# ---- neu v1.5
P.add_argument("--ohne-rettung", action="store_true", help="Teilrettung aus (nur v1.4-Verhalten: Lesefehler-Dateien nur per Namenssuche)")
P.add_argument("--rettung-max-min", type=float, default=90.0, help="Teilrettung: Gesamtbudget in Minuten")
P.add_argument("--rettung-datei-max-min", type=float, default=20.0, help="Teilrettung: Budget je Datei in Minuten")
P.add_argument("--rettung-block-kib", type=int, default=64, help="Teilrettung: Start-Blockgroesse in KiB (bei Fehler Viertelung bis 2048 Byte)")
P.add_argument("--folge-min-s", type=float, default=60.0, help="Abbruchregel Fehler-in-Folge greift nur, wenn diese Fehler zusammen >= N s gekostet haben (0 = nur Anzahl)")
P.add_argument("--open-wiederholen", type=int, default=2, help="Oeffnen einer Datei N-mal wiederholen, danach Ersatz-Oeffnung (Windows)")
P.add_argument("--kein-teilimport", action="store_true", help="bei Abbruch KEIN Vergleich/Import der bis dahin gelesenen Dateien")
P.add_argument("--luecken", action="store_true", help="GAP-Bericht ueber alle Medien aus medien.sqlite (braucht keine Disc)")
a = P.parse_args()
a.skip = not a.ohne_skip
a.chunk_timeout_s = max(a.chunk_timeout_s, a.langsam_s)
REG = a.mdisc_register or os.path.join(a.out, "mdisc_register.csv")
STD = [("DOCUMENTS", "NVMe", r"C:\Users\<USER>\Documents"), ("PICTURES", "NVMe", r"C:\Users\<USER>\Pictures"),
       ("DRIVE", "CLOUD", r"C:\Users\<USER>\Meine Ablage (<google-account>)"), ("ARCHIV", "NVMe", r"D:\2025_02_Backup_all_HDs"),
       ("ARCHIV_DOK", "NVMe", r"D:\Archiv_Dokumente"), ("ARCHIV_VIDEO", "NVMe", r"D:\Archiv_Video"),
       ("EBOOKS_TEMP", "NVMe", r"D:\Ebooks_temp"), ("MEDIEN_IMPORT", "NVMe", a.ziel)]
SKIP = {"_quarantaene", "$recycle.bin", "system volume information", ".tmp.drivedownload", "@eadir", ".synologyworkingdirectory"}
MUELL_NAMEN = {"thumbs.db", "desktop.ini", ".ds_store"}
LW_WEG = {21, 55, 1110, 1111, 1112, 1167, 1617}   # ERROR_NOT_READY, DEV_NOT_EXIST, MEDIA_CHANGED, BUS_RESET, NO_MEDIA_IN_DRIVE, DEVICE_NOT_CONNECTED, DEVICE_REMOVED
def lp(p):
    p = os.path.abspath(p)
    if os.name != "nt" or p.startswith("\\\\?\\"): return p
    return "\\\\?\\UNC\\" + p[2:] if p.startswith("\\\\") else "\\\\?\\" + p
def unlp(p): return p[4:] if p.startswith("\\\\?\\") and not p.startswith("\\\\?\\UNC") else p
def ist_muell(n):
    l = n.lower(); return l in MUELL_NAMEN or l.startswith("~$") or l.endswith(".tmp") or l.endswith(".jpg_128x96")
def blake(p):
    h = hashlib.blake2b(digest_size=20)
    with open(lp(p), "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
def nk(p): return unicodedata.normalize("NFC", p).replace("/", "\\").lower()
def keyn(p, n): return "\\".join(nk(p).split("\\")[-n:])
def key2(p): return keyn(p, 2)
def dkey(d): return keyn(d, 2 if len(nk(d).split("\\")) >= 2 else 1)
def stufe(rel, cand):
    cd, cc = nk(rel).split("\\"), nk(cand).split("\\")
    if len(cd) >= 2 and len(cc) >= 2:
        pd, pc = cd[-2], cc[-2]
        if pd == pc: return 1
        if min(len(pd), len(pc)) >= 8 and (pd.startswith(pc) or pc.startswith(pd)): return 2
    return 3
def vol(root):
    if os.name != "nt": return ("k.A.", "k.A.", "")
    try:
        import ctypes
        lab = ctypes.create_unicode_buffer(261); fs = ctypes.create_unicode_buffer(261); ser = ctypes.c_uint32(0)
        ctypes.windll.kernel32.GetVolumeInformationW(ctypes.c_wchar_p(os.path.splitdrive(root)[0] + "\\"), lab, 261, ctypes.byref(ser), None, None, fs, 261)
        return (lab.value, fs.value, "%08X" % ser.value)
    except Exception as e: return ("k.A.", "k.A. (%s)" % e, "")
def optische_laufwerke():
    if os.name != "nt": return []
    import ctypes, string
    k = ctypes.windll.kernel32; bits = k.GetLogicalDrives(); res = []
    for i, l in enumerate(string.ascii_uppercase):
        if (bits >> i) & 1 and k.GetDriveTypeW(l + ":\\") == 5:
            try: os.listdir(l + ":\\"); res.append(l + ":\\")
            except OSError: pass
    return res
def register_lesen():
    vm = {}
    if os.path.exists(REG):
        with open(REG, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"): vm[r["Medium"]] = (r.get("MDisc", ""), r.get("Verifiziert", "").upper() == "JA")
    return vm
def fcode(e): return getattr(e, "winerror", None) or getattr(e, "errno", None) or 0
def _hook_open(p):
    for th in a.testhook:
        teil, _, r_ = th.partition("=")
        if r_.startswith("OPENERR") and teil.lower() in p.lower(): raise OSError(13, "Permission denied (Selbsttest OPENERR)")
def win_createfile(p, backup):
    """Windows: CreateFileW direkt (alle Share-Modi). Rueckgabe (Handle|None, Win32-Fehlercode)."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    h = k.CreateFileW(lp(p), 0x80000000, 7, None, 3, 0x08000000 | (0x02000000 if backup else 0), None)   # GENERIC_READ, SHARE_ALL, OPEN_EXISTING, SEQUENTIAL_SCAN [| BACKUP_SEMANTICS]
    if h is None or h == ctypes.c_void_p(-1).value: return None, ctypes.get_last_error()
    return h, 0
def open_lesen(p, roh=False):
    """Datei lesend oeffnen: Wiederholung, dann Ersatz-Oeffnung (Windows). Bei Misserfolg OSError mit Attribut .winfehler (echter Win32-Code)."""
    letzter = None
    for v in range(max(a.open_wiederholen, 0) + 1):
        try:
            _hook_open(p)
            return open(lp(p), "rb", buffering=0) if roh else open(lp(p), "rb")
        except OSError as e:
            letzter = e
            if fcode(e) in LW_WEG: break
            if v < a.open_wiederholen: time.sleep(0.5)
    if os.name == "nt" and letzter is not None:
        for backup in (False, True):
            try:
                h, err = win_createfile(p, backup)
                if h:
                    import msvcrt
                    fd = msvcrt.open_osfhandle(h, os.O_RDONLY | getattr(os, "O_BINARY", 0))
                    print("   HINWEIS: Ersatz-Oeffnung per CreateFileW%s erfolgreich: %s" % (" (BACKUP_SEMANTICS)" if backup else "", p[-70:]))
                    return os.fdopen(fd, "rb", buffering=0)
                letzter.winfehler = err
            except Exception: pass
    raise letzter
def fmeld(e): return (("[Win32 %s] " % e.winfehler) if getattr(e, "winfehler", 0) else "") + str(e)[:120]
def lw_ok(root_):
    try: os.listdir(lp(root_)); return True
    except OSError: return False
def typ_min(used):
    for gr, n in ((0.7e9, "CD"), (4.7e9, "DVD-5"), (8.5e9, "DVD-DL"), (25e9, "BD-R/RE 25 GB"), (50e9, "BD-R DL 50 GB")):
        if used <= gr: return n
    return "BD-XL"
def mapfile_luecken(pfad):
    tot = bad = 0
    with open(pfad, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("#") or not line.strip(): continue
            p = line.split()
            if len(p) >= 3 and p[0].lower().startswith("0x") and p[1].lower().startswith("0x") and p[2] in "?*%/-+":
                n = int(p[1], 16); tot += n
                if p[2] != "+": bad += n
    return tot, bad
def modus_luecken():
    dbp = os.path.join(a.out, "medien.sqlite")
    if not os.path.exists(dbp): sys.exit("ABBRUCH: %s fehlt" % dbp)
    d = sqlite3.connect(dbp); tsl = datetime.datetime.now().strftime("%Y-%m-%d_%H%M"); Zl = []; csvz = []
    meds = {r[0]: r for r in d.execute("select medium,label,serial,dateien,gib,fehler,ts from medium")}
    erg = {}
    for m_, ts_, e_, det in d.execute("select medium,ts,ergebnis,details from ergebnis where ergebnis in ('OK','OFFEN') order by ts"): erg[m_] = (ts_, e_, det or "")
    nums = sorted(int(k) for k in meds if str(k).isdigit())
    Zl.append("GAP-Bericht Medienpruefung | Stand %s | Quelle %s | %d Medien in DB" % (datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), dbp, len(nums)))
    fehl = [n for n in range(nums[0], nums[-1] + 1) if n not in nums] if nums else []
    Zl.append("G1 [mittel] Nummernluecken zwischen %s und %s: %s  (Disc nicht geprueft oder Nummer nie vergeben - Fachlich klaeren)" % (nums[0] if nums else "k.A.", nums[-1] if nums else "k.A.", ", ".join(map(str, fehl)) or "keine"))
    offen = [m_ for m_ in sorted(meds) if erg.get(m_, ("", "", ""))[1] != "OK"]
    Zl.append("G2 [hoch] Medien ohne Ergebnis OK (letzter Lauf OFFEN oder nur Vorab/Schnelltest): %d -> %s" % (len(offen), ", ".join(offen) or "keine"))
    for m_ in offen: Zl.append("     %s: %s" % (m_, (erg.get(m_, ("", "", "k.A."))[2])[:200]))
    q = "select v.medium,v.status,v.pfad,v.treffer,v.muell from vergleich v join (select medium m, max(lauf) l from vergleich group by medium) x on v.medium=x.m and v.lauf=x.l"
    cnt = {}
    for m_, st_, p_, t_, mu_ in d.execute(q):
        cnt[(m_, st_, mu_)] = cnt.get((m_, st_, mu_), 0) + 1
        if st_.startswith(("LESEFEHLER", "VERZEICHNIS", "NICHT_GELESEN")): csvz.append((m_, st_, p_, t_))
    def summe(pref, mu=None): return {m_: sum(v for (mm, st_, muu), v in cnt.items() if mm == m_ and st_.startswith(pref) and (mu is None or muu == mu)) for m_ in meds}
    for titel, pref, prio in (("G3 [hoch] Lesefehler OHNE Kopie / Namenstreffer zu pruefen", "LESEFEHLER_UNGEDECKT", "hoch"), ("G3b [hoch] Lesefehler Namenstreffer anderer Ordner (zu pruefen)", "LESEFEHLER_NAME_PRUEFEN", "hoch"),
                              ("G4 [mittel] Lesefehler nur per Name gedeckt (Inhalt NICHT verifiziert)", "LESEFEHLER_GEDECKT_NAME", "mittel"), ("G5 [hoch] Verzeichnisfehler (Inhalt unbekannt)", "VERZEICHNIS_FEHLER", "hoch"),
                              ("G6 [hoch] NICHT_GELESEN (Teillauf)", "NICHT_GELESEN", "hoch"), ("G7 [niedrig] ungelesene Lesefehler ohne Namenssuche (alte Laeufe)", "LESEFEHLER", "mittel")):
        sm = {m_: v for m_, v in summe(pref).items() if v}
        if pref == "LESEFEHLER": sm = {m_: sum(v for (mm, st_, muu), v in cnt.items() if mm == m_ and st_ == "LESEFEHLER") for m_ in meds}; sm = {m_: v for m_, v in sm.items() if v}
        Zl.append("%s: %d Dateien auf %d Medien %s" % (titel, sum(sm.values()), len(sm), ", ".join("%s=%d" % kv for kv in sorted(sm.items()))))
    mu = {m_: v for m_, v in summe("NUR_AUF_DISC", "JA").items() if v}
    Zl.append("G8 [niedrig] Muell (Thumbs.db, ~$, .tmp ...) nur auf Disc/M-DISC, nicht importiert: %d Dateien auf %d Medien" % (sum(mu.values()), len(mu)))
    nm = [m_ for m_ in meds if m_ not in erg]
    vm = register_lesen() if os.path.exists(REG) else {}
    unv = [m_ for m_ in sorted(meds) if not vm.get(m_, ("", False))[1]]
    Zl.append("G9 [mittel] M-DISC (M8) NICHT verifiziert: %d von %d Medien (Register %s %s) - Discs duerfen nicht entsorgt werden" % (len(unv), len(meds), REG, "vorhanden" if vm else "FEHLT"))
    bylab = {}; byser = {}
    for m_, r in meds.items(): bylab.setdefault((r[1] or "").strip().lower(), []).append(m_); byser.setdefault(r[2], []).append(m_)
    dl = {k: v for k, v in bylab.items() if k and len(v) > 1}; ds = {k: v for k, v in byser.items() if k and len(v) > 1}
    Zl.append("G10 [niedrig] gleiche Labels (Dubletten-Verdacht, Inhalt pruefen): " + (" | ".join("%s: %s" % (k, "/".join(v)) for k, v in sorted(dl.items())) or "keine"))
    Zl.append("G11 [hoch] gleiche Seriennummer (dieselbe Disc unter 2 Nummern?): " + (" | ".join("%s: %s" % (k, "/".join(v)) for k, v in sorted(ds.items())) or "keine"))
    tr = []
    for rt, ds_, fs in os.walk(lp(os.path.join(a.ziel))):
        for fn in fs:
            if fn.endswith(".luecken.csv"):
                g = _gl(os.path.join(rt, fn))
                if g: tr.append(unlp(os.path.join(rt, fn)))
    Zl.append("G12 [hoch] Teilrettungen mit offenen Luecken (v1.5): %d Dateien" % len(tr))
    Zl.append("Hinweis: Treffer per Name/Groesse/Datum (--vorab) oder Namenssuche sind KEIN Inhaltsnachweis (Ableitung). Dateien mit Status OK sind per BLAKE2b gelesen.")
    txt = "\n".join(Zl); print(txt)
    with open(os.path.join(a.out, "_GAP_Report_%s.txt" % tsl), "w", encoding="utf-8") as f: f.write(txt + "\n")
    with open(os.path.join(a.out, "_GAP_Dateien_%s.csv" % tsl), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["Medium", "Status", "Pfad", "Treffer"]); w.writerows(sorted(csvz))
    sys.exit(0)
def _gl(pfad):
    g = []
    try:
        with open(lp(pfad), encoding="utf-8-sig", newline="") as f_:
            for r_ in csv.reader(f_, delimiter=";"):
                if len(r_) >= 3 and r_[0] != "Start": g.append(r_)
    except OSError: return []
    return g
if a.luecken: modus_luecken()
# ---- Nummer
while not re.search(r"\d{4}", a.medium or ""):
    a.medium = input("Disk-Nr. (JJNN, z. B. 2603): ").strip()
a.medium = re.search(r"\d{4}", a.medium).group(0); M = a.medium
os.makedirs(a.out, exist_ok=True)
if a.mdisc_ok:
    vm = register_lesen(); vm[M] = (vm.get(M, ("", False))[0] or "M-DISC", True)
    with open(REG, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["Medium", "MDisc", "Verifiziert"])
        for k, (md, ok) in sorted(vm.items()): w.writerow([k, md, "JA" if ok else "NEIN"])
    sys.exit("Disk %s: M-DISC als verifiziert eingetragen (%s)." % (M, REG))
# ---- Laufwerk
root = a.laufwerk
if not root:
    d = optische_laufwerke()
    if len(d) == 1: root = d[0]
    elif len(d) > 1: root = input("Mehrere Laufwerke mit Disc %s - Buchstabe waehlen: " % d).strip().upper().rstrip(":\\") + ":\\"
    else: sys.exit("ABBRUCH: keine Disc im optischen Laufwerk erkannt (oder --laufwerk E:\\ angeben).")
if not os.path.isdir(lp(root)): sys.exit("ABBRUCH: Laufwerk nicht lesbar: " + root)
lab, fsn, ser = vol(root); t_start = time.time(); ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
print("== Disk %s | Laufwerk %s | Label=%s, %s, Seriennr=%s | medien_pruefen v1.5" % (M, root, lab, fsn, ser or "k.A."))
try:
    du = shutil.disk_usage(root); print("   Volume: belegt %.2f GiB von %.2f GiB -> mindestens Typ %s (Schaetzung)" % (du.used / 2**30, du.total / 2**30, typ_min(du.used)))
except OSError as e: print("   Volume-Groesse k.A. (%s)" % str(e)[:80])
Z = {"datei": "", "off": 0, "t_read": 0.0, "n_ok": 0, "n_ges": 0, "bytes": 0, "bytes_ok": 0, "t0": time.time(), "lauf": True, "total": 0, "done_b": 0,
     "t_skip": 0.0, "n_skip": 0, "vorsicht": 0, "cancel_versucht": False, "main_tid": 0, "cur": None, "notsicherung": None, "phase": "inventar"}
class Uebersprungen(Exception):
    def __init__(self, msg, lang=None, mx=0.0): Exception.__init__(self, msg); self.lang = lang or []; self.mx = mx
def prognose_h():
    # Tempo nur aus GESUND gelesenen Dateien dieses Laufs (Zeit in uebersprungenen/fehlerhaften Dateien und Bytes aus dem Fruehlauf zaehlen nicht)
    t_ok = max(time.time() - Z["t0"] - Z["t_skip"], 1e-6); rate = Z["bytes_ok"] / t_ok
    return ((Z["total"] - Z["done_b"]) / rate / 3600.0) if rate > 0 else 0.0
def cancel_io():
    """Windows: blockierenden Lesezugriff des Hauptthreads abbrechen (CancelSynchronousIo). True = Anforderung angenommen."""
    if os.name != "nt" or not Z.get("main_tid"): return False
    try:
        import ctypes
        k = ctypes.windll.kernel32; k.OpenThread.restype = ctypes.c_void_p
        h = k.OpenThread(0x0001, False, Z["main_tid"])      # THREAD_TERMINATE
        if not h: return False
        try: return bool(k.CancelSynchronousIo(ctypes.c_void_p(h)))
        finally: k.CloseHandle(ctypes.c_void_p(h))
    except Exception: return False
def watchdog():
    last = time.time()
    while Z["lauf"]:
        time.sleep(1)
        hd = (time.time() - Z["t_read"]) if Z["t_read"] else 0.0
        if a.skip and a.haengt_abbruch_s and hd >= a.haengt_abbruch_s and not Z["cancel_versucht"]:
            Z["cancel_versucht"] = True
            print("   [%s] Zugriff blockiert seit %.0f s -> CancelSynchronousIo: %s" % (time.strftime("%H:%M:%S"), hd, "angefordert" if cancel_io() else "nicht moeglich/abgelehnt (Windows-Treiber)"))
        if a.skip and a.haengt_hart_s and hd >= a.haengt_hart_s and Z.get("notsicherung"):
            Z["notsicherung"]("HAENGT_HART: Lesezugriff blockierte %.0f s (Prozess beendet, Datei uebersprungen)" % hd)
            print("\n!!! [%s] Lesezugriff blockiert seit %.0f s (>= %.0f s): Prozess wird beendet (Inventar: Datei als uebersprungen gesichert). Aufruf wiederholen setzt fort (Inventar aus Checkpoint, Teilrettung per .luecken.csv)." % (time.strftime("%H:%M:%S"), hd, a.haengt_hart_s))
            sys.stdout.flush(); os._exit(3)
        if time.time() - last >= a.herzschlag and Z["lauf"]:
            last = time.time(); el = max(time.time() - Z["t0"], 1e-6)
            if Z.get("phase") != "inventar":
                print("   [%s] Phase %s | %.2f GiB gelesen | aktuell: %s @ %.0f MiB%s" % (time.strftime("%H:%M:%S"), Z.get("phase"), Z["bytes"] / 2**30, Z["datei"][-60:], Z["off"] / 2**20, (" | LESEZUGRIFF HAENGT seit %.0f s" % hd) if Z["t_read"] else ""))
                continue
            hang = (" | LESEZUGRIFF HAENGT seit %.0f s" % hd) if Z["t_read"] else ""
            print("   [%s] %d/%d Dateien | %.2f GiB gelesen | Mittel %.2f MB/s | Rest ca. %.1f h | uebersprungen %d | aktuell: %s @ %.0f MiB%s" % (
                time.strftime("%H:%M:%S"), Z["n_ok"], Z["n_ges"], Z["bytes"] / 2**30, Z["bytes"] / 1e6 / el, prognose_h(), Z["n_skip"], Z["datei"][-60:], Z["off"] / 2**20, hang))
def _hook(p, off, n=0):
    for th in a.testhook:
        try:
            teil, r_ = th.split("=", 1); sek, _, ab = r_.partition("@")
            if teil.lower() not in p.lower() or sek == "OPENERR": continue
            if sek == "BAD":
                s_, e_ = ab.split("-")
                if off < float(e_) * 1024 and off + max(n, 1) > float(s_) * 1024: raise OSError(5, "I/O error (Selbsttest BAD)")
                continue
            if off >= float(ab or 0) * 2**20:
                if sek == "ERR": raise OSError(13, "Permission denied (Selbsttest)")
                time.sleep(float(sek))
        except ValueError: pass
def walk_disc():
    dir_fehler = []; dir_msg = []; files = []
    def _onerr(e):
        fn = getattr(e, "filename", None)
        try: rel = os.path.relpath(unlp(fn), root) if fn else ""
        except ValueError: rel = ""
        dir_fehler.append(rel or str(e)[:120]); dir_msg.append(str(e)[:200])
    for rt, ds, fs in os.walk(lp(root), onerror=_onerr):
        for fn in fs: files.append(unlp(os.path.join(rt, fn)))
    return files, dir_fehler, dir_msg
def db_ergebnis(erg, details):
    d0 = sqlite3.connect(os.path.join(a.out, "medien.sqlite"))
    d0.execute("create table if not exists ergebnis(medium text,ts text,ergebnis text,details text)")
    d0.execute("insert into ergebnis values(?,?,?,?)", (M, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), erg, details)); d0.commit(); d0.close()
def refs_liste(): return ([] if a.ohne_standard_refs else list(STD)) + [tuple(r.split("|", 2)) for r in a.ref]
# ================= MODUS --vorab (nur Metadaten)
def modus_vorab():
    print("[VORAB] Dateiliste der Disc (nur Metadaten; es werden KEINE Dateiinhalte gelesen) ...")
    files, dfe, dmsg = walk_disc()
    for m_ in dmsg: print("   VERZEICHNIS_FEHLER: " + m_)
    drows = []
    for p in files:
        rel = os.path.relpath(p, root)
        try: s = os.stat(lp(p)); drows.append((rel, s.st_size, int(s.st_mtime)))
        except OSError: drows.append((rel, -1, 0))
    print("   %d Dateien, %.3f GiB" % (len(drows), sum(max(x[1], 0) for x in drows) / 2**30))
    eigen = nk(os.path.abspath(os.path.join(a.ziel, M))); idx = {}
    for klasse, ort, rr in refs_liste():
        if not os.path.isdir(lp(rr)): print("   HINWEIS: Referenz nicht vorhanden/erreichbar: %s (%s)" % (klasse, rr)); continue
        n = 0
        for rt, ds, fs in os.walk(lp(rr)):
            ds[:] = [d for d in ds if d.lower() not in SKIP and nk(unlp(os.path.abspath(os.path.join(rt, d)))) != eigen]
            for fn in fs:
                try: s = os.stat(os.path.join(rt, fn))
                except OSError: continue
                idx.setdefault((s.st_size, nk(fn)), []).append((int(s.st_mtime), klasse, unlp(os.path.join(rt, fn)))); n += 1
        print("   Referenz %-13s %8d Dateien" % (klasse, n))
    res = []; cnt = {}; byt = {}
    for rel, sz, mt in drows:
        if sz == 0: st = "VORAB_LEER_0_BYTE"; hit = ""
        elif sz < 0: st = "VORAB_NICHT_LESBAR"; hit = ""
        else:
            c = idx.get((sz, nk(os.path.basename(rel.replace("\\", "/")))), [])
            g1 = [x for x in c if min(abs(x[0] - mt), abs(abs(x[0] - mt) - 3600), abs(abs(x[0] - mt) - 7200)) <= 2]
            if g1: st = "VORAB_GEDECKT"; hit = g1[0][1] + ": " + g1[0][2]
            elif c: st = "VORAB_NAME_GROESSE"; hit = c[0][1] + ": " + c[0][2]
            else: st = "VORAB_OFFEN"; hit = ""
        cnt[st] = cnt.get(st, 0) + 1; byt[st] = byt.get(st, 0) + max(sz, 0); res.append((rel, sz, mt, st, hit))
    zv = os.path.join(a.out, "%s_vorab_%s.csv" % (M, ts))
    with open(zv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["Pfad", "Groesse", "mtime_epoch", "Status", "Treffer"]); w.writerows(res)
    offen = [r for r in res if r[3] in ("VORAB_OFFEN", "VORAB_NAME_GROESSE", "VORAB_NICHT_LESBAR")]
    ok = not offen and not dfe
    zeilen = ["Disk %s VORAB-Abgleich (Metadaten): %s" % (M, "alle Dateien per Name+Groesse+Datum im Bestand gefunden" if ok else "NICHT vollstaendig gedeckt")]
    for k in sorted(cnt): zeilen.append("  %-22s %6d Dateien  %8.3f GiB" % (k, cnt[k], byt[k] / 2**30))
    if dfe: zeilen.append("  VERZEICHNIS_FEHLER %d (Inhalt unbekannt): %s" % (len(dfe), " | ".join(dfe[:5])))
    zeilen.append("ACHTUNG: Metadaten-Gleichheit ist KEIN Inhaltsnachweis (Ableitung). Datum auf Disc weicht oft um genau 1 h (Sommerzeit) ab - toleriert.")
    zeilen.append("Hash-Nachweis erst durch Lesen der Disc (Normallauf/Image). Detail: " + zv)
    for x in offen[:40]: zeilen.append("  OFFEN: %s (%d B) %s" % (x[0], x[1], x[3]))
    if len(offen) > 40: zeilen.append("  ... %d weitere in der CSV" % (len(offen) - 40))
    txt = "\n".join(zeilen); print("\n" + "=" * 70 + "\n" + txt + "\n" + "=" * 70)
    with open(os.path.join(a.out, "%s_bericht_vorab_%s.txt" % (M, ts)), "w", encoding="utf-8") as f: f.write(txt + "\n")
    db_ergebnis("VORAB_GEDECKT" if ok else "VORAB_OFFEN", "; ".join("%s=%d" % kv for kv in sorted(cnt.items())))
    sys.exit(0 if ok else 1)
# ================= MODUS --schnelltest
def modus_schnelltest():
    print("[SCHNELLTEST] Stichproben (256 KiB: Anfang/Mitte/Ende) mit Zeitmessung ...")
    files, dfe, dmsg = walk_disc()
    for m_ in dmsg: print("   VERZEICHNIS_FEHLER: " + m_)
    meta = []
    for p in files:
        try: meta.append((p, os.path.getsize(lp(p))))
        except OSError: meta.append((p, -1))
    gib = sum(max(s, 0) for _, s in meta) / 2**30
    print("   %d Dateien, %.3f GiB" % (len(meta), gib))
    SAMPLE = 256 * 1024; n_j = max(1, a.schnell_jedes)
    sel = [(p, s) for i, (p, s) in enumerate(meta) if s > 0 and (i % n_j == 0 or s >= 64 << 20)]
    limit = (a.max_minuten or 20.0) * 60; out = []; t_s = time.time(); stop = ""; last_hb = time.time()
    for n, (p, s) in enumerate(sel, 1):
        offs = [0] if s <= (1 << 20) else sorted({0, max(0, s // 2 - SAMPLE // 2), max(0, s - SAMPLE)})
        for off in offs:
            t1 = time.time(); st = "OK"; meld = ""
            try:
                with open(lp(p), "rb") as f:
                    f.seek(off); f.read(SAMPLE)
            except (OSError, ValueError) as e:
                st = "FEHLER"; meld = "%s %s" % (fcode(e), str(e)[:90])
                if (fcode(e) in LW_WEG or isinstance(e, FileNotFoundError)) and not lw_ok(root): stop = "LAUFWERK_WEG"
            dt = time.time() - t1
            if st == "OK" and dt >= a.schnell_langsam_s: st = "LANGSAM"
            out.append((os.path.relpath(p, root), s, off, round(dt, 2), st, meld))
        if time.time() - last_hb >= a.herzschlag: last_hb = time.time(); print("   [%s] %d/%d Dateien, %d Stichproben" % (time.strftime("%H:%M:%S"), n, len(sel), len(out)))
        if stop: break
        if time.time() - t_s > limit: stop = "ZEITLIMIT %.0f min" % (limit / 60); break
    # Tempo: sequentiell aus der groessten Datei (max. 32 MiB oder 20 s)
    tempo = 0.0
    if not stop and meta:
        pg, sg = max(meta, key=lambda x: x[1])
        if sg > 0:
            try:
                n_b = 0; t1 = time.time()
                with open(lp(pg), "rb") as f:
                    while n_b < (32 << 20) and time.time() - t1 < 20:
                        b = f.read(1 << 20)
                        if not b: break
                        n_b += len(b)
                tempo = n_b / 1e6 / max(time.time() - t1, 1e-6); print("   Sequenzielles Tempo (%d MiB aus %s): %.2f MB/s" % (n_b >> 20, os.path.basename(pg)[-40:], tempo))
            except (OSError, ValueError) as e: print("   Tempo-Test Fehler: %s" % str(e)[:100])
    zt = os.path.join(a.out, "%s_schnelltest_%s.csv" % (M, ts))
    with open(zt, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["Pfad", "Groesse", "Offset", "Dauer_s", "Status", "Meldung"]); w.writerows(out)
    nf = sum(1 for x in out if x[4] == "FEHLER"); nl = sum(1 for x in out if x[4] == "LANGSAM")
    ds_ = sorted(x[3] for x in out) or [0]; med = ds_[len(ds_) // 2]; p90 = ds_[int(len(ds_) * 0.9) - 1 if len(ds_) > 1 else 0]
    zeilen = ["Disk %s SCHNELLTEST: %d Stichproben in %.0f s | FEHLER %d | LANGSAM (>= %.0f s) %d (%.1f %%) | Median %.2f s | P90 %.2f s | Tempo %.2f MB/s" % (
        M, len(out), time.time() - t_s, nf, a.schnell_langsam_s, nl, 100.0 * nl / max(len(out), 1), med, p90, tempo)]
    if stop: zeilen.append("VORZEITIG BEENDET: " + stop)
    if tempo > 0: zeilen.append("Prognose Volllesen (nur Lesen, %.2f GiB): ca. %.1f h bei %.2f MB/s (berechnet)" % (gib, gib * 1024 / tempo / 3600, tempo))
    schlecht = nf > 0 or (tempo and tempo < 1.5) or nl >= 0.05 * max(len(out), 1) or stop == "LAUFWERK_WEG"
    if schlecht:
        zeilen.append("EMPFEHLUNG: KEIN Direktlauf. Erst --vorab (Deckung ohne Lesen); fuer vollstaendigen Inhalt Image mit ddrescue (medien_image_ddrescue_v1.0.sh), danach Pruefung am gemounteten Image (--laufwerk, --mapfile).")
        zeilen.append("Gegenprobe Laufwerk: gesunde Referenz-Disc (z. B. 2613) einlegen und diesen Schnelltest wiederholen; Tempo >= 4 MB/s = Laufwerk ok, Disc ist die Ursache.")
    else: zeilen.append("EMPFEHLUNG: Direktlauf moeglich (py medien_pruefen_v1.5.py %s)." % M)
    txt = "\n".join(zeilen); print("\n" + "=" * 70 + "\n" + txt + "\nDetail: " + zt + "\n" + "=" * 70)
    with open(os.path.join(a.out, "%s_bericht_schnelltest_%s.txt" % (M, ts)), "w", encoding="utf-8") as f: f.write(txt + "\n")
    db_ergebnis("SCHNELLTEST_" + ("SCHLECHT" if schlecht else "OK"), zeilen[0])
    sys.exit(4 if stop == "LAUFWERK_WEG" else (1 if schlecht else 0))
if a.vorab: modus_vorab()
if a.schnelltest: modus_schnelltest()
# ================= NORMALLAUF: DB
db = sqlite3.connect(os.path.join(a.out, "medien.sqlite"))
db.executescript("""create table if not exists medium(medium text primary key,label text,fs text,serial text,dateien int,gib real,fehler int,ts text,laufwerk text);
create table if not exists datei(medium text,pfad text,groesse int,mtime text,hash text,status text,muell text); create index if not exists di on datei(medium); create index if not exists dh on datei(hash);
create table if not exists vergleich(lauf text,medium text,pfad text,hash text,muell text,status text,orte text,klassen text,treffer text);
create table if not exists lauf(lauf text,medium text,empfehlung text,nur_auf_disc int,gib_nur_auf_disc real);
create table if not exists ergebnis(medium text,ts text,ergebnis text,details text)""")
vor = db.execute("select label,serial from medium where medium=?", (M,)).fetchone()
if vor and (vor[0], vor[1]) != (lab, ser) and not a.ueberschreiben:
    sys.exit("ABBRUCH: Nummer %s ist schon mit einer ANDEREN Disc belegt (Label %s, Seriennr %s). Falsche Nummer? Sonst --ueberschreiben." % (M, vor[0], vor[1]))
dop = db.execute("select medium from medium where label=? and serial=? and medium<>?", (lab, ser, M)).fetchall() if (lab or ser) else []
if dop: print("WARNUNG: Label/Seriennr. gleich wie Medium %s - dieselbe Disc unter zweiter Nummer?" % ", ".join(d[0] for d in dop))
if vor: print("HINWEIS: Disk %s wird neu geprueft (DB-Zeilen werden ersetzt)." % M)
# ================= 1 INVENTAR (fortsetzbar, mit Tempo und Abbruchregeln)
print("[1/4] Inventar (Hash je Datei, nur lesend; fortsetzbar; Statuszeile alle %d s) ..." % a.herzschlag)
files, dir_fehler, dir_msg = walk_disc()
szs = {}
for p_ in files:
    try: szs[p_] = os.path.getsize(lp(p_))
    except OSError: szs[p_] = -1
Z["total"] = sum(v for v in szs.values() if v > 0)
print("   %d Dateien, %.2f GiB laut Verzeichnis; Prognose bei 4,5 MB/s (1x BD): %.1f h, bei 1 MB/s: %.1f h" % (len(files), Z["total"] / 2**30, Z["total"] / 4.5e6 / 3600, Z["total"] / 1e6 / 3600))
ck = os.path.join(a.out, "%s_inventar_laufend.csv" % M); ckm = ck + ".meta"; meta_now = "%s|%s" % (lab, ser); alt = {}
if os.path.exists(ck):
    try: gleich = open(ckm, encoding="utf-8").read().strip() == meta_now
    except OSError: gleich = False
    if gleich and not a.neu:
        with open(ck, encoding="utf-8-sig", newline="") as f:
            for r in csv.reader(f, delimiter=";"):
                if len(r) >= 6 and r[0] != "Pfad": alt[r[0]] = r
        print("FORTSETZUNG: %d Dateien aus frueherem Lauf uebernommen (%s). --neu verwirft sie, --fehler-wiederholen liest nur frueher fehlgeschlagene/uebersprungene Dateien erneut." % (len(alt), ck))
    else:
        os.replace(ck, ck + ".verworfen_" + ts); print("HINWEIS: frueherer Teillauf verworfen (%s)." % ("--neu" if a.neu else "andere Disc/Nummer"))
fresh = not os.path.exists(ck)
ckf = open(ck, "w" if fresh else "a", encoding="utf-8-sig", newline=""); ckw = csv.writer(ckf, delimiter=";")
if fresh:
    ckw.writerow(["Pfad", "Groesse", "mtime", "Hash", "Status", "Muell", "Grund"]); ckf.flush()
    with open(ckm, "w", encoding="utf-8") as f: f.write(meta_now)
tf = open(os.path.join(a.out, "%s_lesetempo_%s.csv" % (M, ts)), "w", encoding="utf-8-sig", newline=""); tw = csv.writer(tf, delimiter=";")
tw.writerow(["Pfad", "Groesse", "Dauer_s", "MB_pro_s", "Langsame_Zugriffe", "Max_Zugriff_s", "Fehlercode", "Meldung"])
def blake_disc(p):
    h = hashlib.blake2b(digest_size=20); off = 0; lang = []; mx = 0.0; slow = 0.0; t_file = time.time(); klein = Z["vorsicht"] > 0
    Z["datei"] = p; Z["off"] = 0; Z["cancel_versucht"] = False
    Z["t_read"] = time.time()
    try: f = open_lesen(p)
    finally: Z["t_read"] = 0.0
    with f:
        while True:
            n_ = (64 << 10) if klein else (max(a.chunk_kib, 16) << 10)
            Z["t_read"] = time.time()
            try:
                b = f.read(n_); _hook(p, off, n_)
            except OSError as e:
                if a.skip and Z["cancel_versucht"]:     # Abbruch angefordert -> jeder Fehler danach gilt als Folge (Windows: ERROR_OPERATION_ABORTED 995; CRT-Fehlernummer kann abweichen)
                    hd = time.time() - Z["t_read"]; Z["t_read"] = 0.0
                    raise Uebersprungen("HAENGT_ABGEBROCHEN: Zugriff bei %d MiB nach %.0f s per CancelSynchronousIo beendet (Fehler %s)" % (off >> 20, hd, fcode(e)), lang, max(mx, hd))
                raise
            dt = time.time() - Z["t_read"]; Z["t_read"] = 0.0; Z["cancel_versucht"] = False
            mx = max(mx, dt)
            if dt >= a.langsam_s: lang.append((off, dt)); slow += dt; klein = True
            if not b: break
            h.update(b); off += len(b); Z["off"] = off; Z["bytes"] += len(b)
            if a.skip:
                el_f = time.time() - t_file
                if dt >= a.chunk_timeout_s: raise Uebersprungen("ZEITLIMIT_ZUGRIFF: %d-KiB-Zugriff bei %d MiB dauerte %.0f s (>= %.0f s)" % (n_ >> 10, off >> 20, dt, a.chunk_timeout_s), lang, mx)
                if slow >= a.datei_fehlzeit_s: raise Uebersprungen("ZEITLIMIT_DATEI: %.0f s in langsamen Zugriffen (>= %.0f s) bis %d MiB" % (slow, a.datei_fehlzeit_s, off >> 20), lang, mx)
                if el_f >= a.min_mbs_nach_s and off / 1e6 / el_f < a.min_mbs: raise Uebersprungen("TEMPO_DATEI: %.2f MB/s nach %.0f s (< %.2f MB/s) bei %d MiB" % (off / 1e6 / el_f, el_f, a.min_mbs, off >> 20), lang, mx)
    return h.hexdigest(), lang, mx
class Abbruch(Exception):
    def __init__(self, code, text): Exception.__init__(self, text); self.code = code; self.text = text
def stopp(code, text): raise Abbruch(code, text)
rows = []; bad_read = 0; tot = 0; t0 = time.time(); Z.update(n_ges=len(files), t0=t0, main_tid=threading.get_native_id())
folge = 0; folge_zeit = 0.0; fehlzeit = 0.0; n_lang = 0; n_wied = 0; n_neu = 0; ABBR = None; n_ng = 0
GR = {}    # Pfad -> Grund (Lesefehler/Zeitlimit/Haengt), auch aus Fruehlauf
LOCK = threading.Lock()
def notsicherung(grund_):
    c = Z.get("cur")
    if not c: return
    with LOCK:
        try: ckw.writerow([c[0], c[1], c[2], "", "LESEFEHLER", c[3], grund_]); ckf.flush(); os.fsync(ckf.fileno())
        except Exception: pass
Z["notsicherung"] = notsicherung
threading.Thread(target=watchdog, daemon=True).start()
try:
    for i, p in enumerate(files, 1):
        Z["n_ok"] = i - 1; rel = os.path.relpath(p, root); st = "OK"; h = ""; size = -1; mt = ""; lang = []; mx = 0.0; fc = 0; fmsg = ""; grund = ""; t_f = time.time(); Z["cur"] = None
        try:
            size = os.path.getsize(lp(p)); mt = datetime.datetime.fromtimestamp(os.path.getmtime(lp(p))).strftime("%Y-%m-%d %H:%M:%S"); tot += size
            Z["cur"] = (rel, size, mt, "JA" if ist_muell(os.path.basename(p)) else "NEIN")
            ra = alt.get(rel)
            if ra and ra[1] == str(size) and ra[2] == mt and (ra[4] in ("OK", "LEER_0_BYTE") or (ra[4] == "LESEFEHLER" and not a.fehler_wiederholen)):
                rows.append([rel, size, mt, ra[3], ra[4], ra[5]]); n_wied += 1; Z["done_b"] += max(size, 0)
                if ra[4] == "LESEFEHLER":
                    bad_read += 1
                    if len(ra) > 6 and ra[6]: GR[rel] = ra[6]
                continue
            if size == 0: st = "LEER_0_BYTE"
            h, lang, mx = blake_disc(p)
            Z["bytes_ok"] += max(size, 0)
        except Uebersprungen as e:
            st = "LESEFEHLER"; h = ""; grund = str(e)[:200]; fmsg = grund; mx = e.mx; n_lang += len(e.lang); lang = []
            dt_skip = time.time() - t_f; fehlzeit += dt_skip; Z["t_skip"] += dt_skip; Z["n_skip"] += 1; Z["t_read"] = 0.0; bad_read += 1
            print("   UEBERSPRUNGEN (%s): %s" % (grund.split(":")[0], rel))
        except (OSError, ValueError) as e:
            st = "LESEFEHLER"; h = ""; fc = fcode(e); fmsg = fmeld(e)
            fehlzeit += (time.time() - Z["t_read"]) if Z["t_read"] else 0.0; Z["t_read"] = 0.0; Z["t_skip"] += time.time() - t_f
            if (fc in LW_WEG or isinstance(e, FileNotFoundError)) and not lw_ok(root):
                stopp(4, "LAUFWERK_WEG: %s ist nicht mehr lesbar (Fehler %s bei %s). Datei NICHT als Lesefehler gebucht.\nUrsachen pruefen: USB-Kabel/Netzteil/Hub, Laufwerk ausgeworfen, Windows-Ereignisanzeige (Quellen cdrom, disk, usbhub)." % (root, fc, rel))
            bad_read += 1; grund = ""
        dauer = time.time() - t_f; n_neu += 1; Z["done_b"] += max(size, 0)
        if lang: n_lang += len(lang); fehlzeit += sum(d for _, d in lang)
        row = [rel, size, mt, h, st, "JA" if ist_muell(os.path.basename(p)) else "NEIN"]
        rows.append(row)
        if st == "LESEFEHLER": GR[rel] = grund or ("LESEFEHLER %s %s" % (fc, fmsg))
        with LOCK: ckw.writerow(row + [GR.get(rel, "")]); ckf.flush()
        tw.writerow([rel, size, round(dauer, 2), round(size / 1e6 / dauer, 2) if dauer > 0 and size > 0 else "", len(lang), round(mx, 1), fc or "", fmsg]); tf.flush()
        if st == "LESEFEHLER" and not grund: folge += 1; folge_zeit += dauer
        elif st != "LESEFEHLER": folge = 0; folge_zeit = 0.0
        if Z["vorsicht"] > 0: Z["vorsicht"] -= 1
        if st == "LESEFEHLER" or lang: Z["vorsicht"] = max(Z["vorsicht"], a.vorsicht_dateien)
        if i >= len(files): continue
        el = max(time.time() - t0, 1e-6)
        if a.max_fehler_folge and folge >= a.max_fehler_folge and folge % a.max_fehler_folge == 0 and folge_zeit < a.folge_min_s:
            print("   HINWEIS: %d Lesefehler in Folge, zusammen nur %.1f s (< --folge-min-s %.0f s) -> kein Abbruch, es wird weitergelesen (Fehler sind billig; Teilrettung folgt)." % (folge, folge_zeit, a.folge_min_s))
        if a.max_fehler_folge and folge >= a.max_fehler_folge and folge_zeit >= a.folge_min_s:
            stopp(3, "ABBRUCHREGEL: %d Lesefehler in Folge (letzte: %s, Fehler %s). Beschaedigte Zone: weiteres Direktlesen kostet nur Zeit.\nEmpfehlung: --vorab (Deckung ohne Lesen), Image mit ddrescue; oder --max-fehler-folge 0 bewusst weiterlesen." % (folge, rel, fc))
        if a.max_fehlzeit_min and fehlzeit >= a.max_fehlzeit_min * 60:
            stopp(3, "ABBRUCHREGEL: %.1f min in langsamen/fehlerhaften Zugriffen bzw. uebersprungenen Dateien verbraucht (%d langsame Zugriffe >= %.0f s, %d Lesefehler, davon %d uebersprungen); %d/%d Dateien erledigt.\nEmpfehlung: --schnelltest, --vorab, Image mit ddrescue; oder --max-fehlzeit-min hoeher setzen." % (fehlzeit / 60, n_lang, a.langsam_s, bad_read, Z["n_skip"], i, len(files)))
        if a.max_minuten and el >= a.max_minuten * 60:
            stopp(3, "ABBRUCHREGEL: Gesamtzeit %.1f min erreicht; %d/%d Dateien erledigt." % (el / 60, i, len(files)))
        t_ok = el - Z["t_skip"]
        if a.max_prognose_h and t_ok >= a.tempo_fenster_min * 60 and Z["bytes_ok"] >= (64 << 20) and prognose_h() > a.max_prognose_h:
            stopp(3, "ABBRUCHREGEL TEMPO: %.2f MB/s (nur gesund gelesene Dateien dieses Laufs), Restzeit ca. %.1f h (> %.1f h); %d/%d Dateien erledigt.\nGesunde Discs lesen >= 4 MB/s. Empfehlung: --vorab (Deckung ohne Lesen), --schnelltest, Image mit ddrescue (zeitbegrenzt, fortsetzbar); oder --max-prognose-h 0 bewusst weiterlesen." % (Z["bytes_ok"] / 1e6 / max(t_ok, 1e-6), prognose_h(), a.max_prognose_h, i, len(files)))
except KeyboardInterrupt:
    ABBR = Abbruch(130, "UNTERBROCHEN (Strg+C): %d Dateien gesichert. Es folgen Vergleich/Import/Teilrettung der bis hier gelesenen Dateien (Strg+C erneut = sofort beenden)." % len(rows))
except Abbruch as ex_:
    ABBR = ex_
Z["phase"] = "Auswertung"; Z["t_read"] = 0.0; Z["cur"] = None; ckf.close(); tf.close()
lw_da = True
if ABBR:
    done_ = {r[0] for r in rows}
    for p_ in files:
        rel_ = os.path.relpath(p_, root)
        if rel_ not in done_: rows.append([rel_, szs.get(p_, -1), "", "", "NICHT_GELESEN", "JA" if ist_muell(os.path.basename(p_)) else "NEIN"]); n_ng += 1
    lw_da = ABBR.code != 4
    print("\n" + "!" * 70 + "\n" + ABBR.text + "\nStand gesichert: %s | NICHT gelesen: %d von %d Dateien (Status NICHT_GELESEN).\nFortsetzen: gleichen Befehl erneut starten (--neu = von vorn)." % (ck, n_ng, len(files)))
    if a.kein_teilimport or not lw_da: print("Vergleich ohne Import/Teilrettung (%s)." % ("--kein-teilimport" if a.kein_teilimport else "Laufwerk nicht erreichbar"))
    else: print("Es folgen Vergleich, Import und Teilrettung der bis hier gelesenen Dateien (v1.5: Abbruch ist kein Datenverlust).")
    print("!" * 70)
else:
    try: shutil.copyfile(ck, ck.replace("_laufend", "_fertig_" + ts))   # Checkpoint BLEIBT (siehe v1.4)
    except OSError: pass
for e in dir_fehler: rows.append([e, -1, "", "", "VERZEICHNIS_FEHLER", "NEIN"])
for m_ in dir_msg: print("   VERZEICHNIS_FEHLER: " + m_)
akz_liste = []
for r in rows:
    if r[4] in ("LESEFEHLER", "VERZEICHNIS_FEHLER") and any(x.lower() in r[0].lower() for x in a.ignoriere):
        r[4] = "LESEFEHLER_AKZEPTIERT"; akz_liste.append(r[0])
akz = len(akz_liste)
el = max(time.time() - t0, 1e-6)
print("   %d Dateien, %.3f GiB, Lesefehler %d, Verzeichnisfehler %d | neu gelesen %d, aus Fruehlauf %d | %.2f GiB in %.0f s = %.2f MB/s | langsame Zugriffe %d" % (
    len(files), tot / 2**30, bad_read, len(dir_fehler), n_neu, n_wied, Z["bytes"] / 2**30, el, Z["bytes"] / 1e6 / el, n_lang))
if not files: sys.exit("ABBRUCH: keine Dateien sichtbar (Audio-CD, leer oder unlesbar?). Im Medienregister vermerken.")
zi = os.path.join(a.out, "%s_inventar.csv" % M)
if os.path.exists(zi): zi = os.path.join(a.out, "%s_inventar_%s.csv" % (M, ts))
with open(zi, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, delimiter=";"); w.writerow(["Pfad", "Groesse", "mtime", "Hash", "Status", "Muell"]); w.writerows(rows)
with db:
    db.execute("delete from datei where medium=?", (M,)); db.executemany("insert into datei values(?,?,?,?,?,?,?)", [[M] + r for r in rows])
    db.execute("insert or replace into medium values(?,?,?,?,?,?,?,?,?)", (M, lab, fsn, ser, len(files), tot / 2**30, bad_read + len(dir_fehler) - akz, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), root))
# ================= 2 VERGLEICH
print("[2/4] Vergleich mit Bestand (Hash, pfadunabhaengig; Lesefehler: Namenssuche) ...")
refs = refs_liste()
sizes = {r[1] for r in rows if r[4] == "OK" and r[1] > 0}; hashes = {r[3] for r in rows if r[4] in ("OK",) and r[3]}
cdb = sqlite3.connect(os.path.join(a.out, "refcache.sqlite")); cdb.execute("create table if not exists c(path text primary key, size int, mtime int, hash text)")
treffer = {}; todo = []; fehl_ref = 0
gesucht = {nk(os.path.basename(r[0].replace("\\", "/"))) for r in rows if r[4] == "LESEFEHLER"}
fdirs = [r[0] for r in rows if r[4] == "VERZEICHNIS_FEHLER"]; dirkeys = {dkey(d) for d in fdirs}
namens = {}; refdirs = {}
eigen = nk(os.path.abspath(os.path.join(a.ziel, M)))
for klasse, ort, rr in refs:
    if not os.path.isdir(lp(rr)): print("   HINWEIS: Referenz nicht vorhanden/erreichbar: %s (%s)" % (klasse, rr)); continue
    for rt, ds, fs in os.walk(lp(rr)):
        ds[:] = [d for d in ds if d.lower() not in SKIP and nk(unlp(os.path.abspath(os.path.join(rt, d)))) != eigen]
        if dirkeys:
            for k_ in {key2(unlp(rt)), keyn(unlp(rt), 1)}:
                if k_ in dirkeys: refdirs.setdefault(k_, []).append((klasse, unlp(rt), len(fs), len(ds)))
        for fn in fs:
            p = os.path.join(rt, fn)
            try: s = os.stat(p)
            except OSError: fehl_ref += 1; continue
            if gesucht and nk(fn) in gesucht: namens.setdefault(nk(fn), []).append((klasse, ort, unlp(p), s.st_size))
            if s.st_size == 0 or s.st_size not in sizes: continue
            q = unlp(p); c = cdb.execute("select size,mtime,hash from c where path=?", (q,)).fetchone()
            if c and c[0] == s.st_size and c[1] == s.st_mtime_ns:
                if c[2] in hashes: treffer.setdefault(c[2], {}).setdefault(ort, (klasse, q))
            else: todo.append((klasse, ort, q, s.st_size, s.st_mtime_ns))
print("   zu hashen (Referenz): %d Dateien, %.2f GiB" % (len(todo), sum(t[3] for t in todo) / 2**30))
for i, (klasse, ort, q, size, mt) in enumerate(todo, 1):
    try: h = blake(q)
    except OSError: fehl_ref += 1; continue
    cdb.execute("insert or replace into c values(?,?,?,?)", (q, size, mt, h))
    if h in hashes: treffer.setdefault(h, {}).setdefault(ort, (klasse, q))
    if i % 500 == 0: cdb.commit(); print("   %d/%d" % (i, len(todo)))
cdb.commit()
# ---- Namenssuche fuer Lesefehler-Dateien (kein Hash moeglich) und Vergleichsordner fuer Verzeichnisfehler
fmatch = {}; fdetail = []; cand_paths = {}
if gesucht or fdirs:
    cdb.execute("create index if not exists ch on c(hash)"); cdb.commit()
    and_name = {}; and_pfad = []
    for m2, p2, h2 in db.execute("select medium,pfad,hash from datei where medium<>? and status='OK' and hash<>''", (M,)):
        and_name.setdefault(nk(os.path.basename(p2.replace("\\", "/"))), []).append((m2, p2, h2)); and_pfad.append((m2, nk(p2)))
    def phys(h2):
        for (q,) in cdb.execute("select path from c where hash=?", (h2,)):
            if nk(os.path.abspath(q)).startswith(eigen): continue
            if os.path.exists(lp(q)): return q
        return ""
    for r in rows:
        if r[4] != "LESEFEHLER": continue
        n = nk(os.path.basename(r[0].replace("\\", "/"))); kand = []; nur_disc = set()
        for klasse, ort, q, sz in namens.get(n, []): kand.append((stufe(r[0], q), klasse, ort, q, ""))
        for m2, p2, h2 in and_name.get(n, []):
            q = phys(h2)
            if q: kand.append((stufe(r[0], p2), "DISC" + m2, "NVMe", q, m2))
            else: nur_disc.add(m2)
        kand.sort(key=lambda k: (k[0], k[3])); cand_paths[r[0]] = [k[3] for k in kand]; gut = [k for k in kand if k[0] <= 2]; schwach = [k for k in kand if k[0] == 3]
        if gut or (schwach and a.name_akzeptieren): st_ = "LESEFEHLER_GEDECKT_NAME"; use = gut or schwach
        elif schwach: st_ = "LESEFEHLER_NAME_PRUEFEN"; use = schwach
        else: st_ = "LESEFEHLER_UNGEDECKT"; use = []
        best = (use or kand or [None])[0]
        discs = sorted({k[4] for k in kand if k[4]} | nur_disc)
        fmatch[r[0]] = (st_, {k[2] for k in use} if st_ == "LESEFEHLER_GEDECKT_NAME" else set(), "+".join(sorted({k[1] for k in use})), ("[S%d] %s" % (best[0], best[3])) if best else "", "+".join(discs))
        fdetail.append("%s | %s%s" % (st_, r[0], (" -> " + fmatch[r[0]][3]) if best else ""))
    for d in fdirs:
        dn = nk(d) + "\\"; cm = {}
        for m2, p2n in and_pfad:
            if p2n.startswith(dn): cm[m2] = cm.get(m2, 0) + 1
        rd = refdirs.get(dkey(d), [])
        fmatch[d] = ("VERZEICHNIS_FEHLER", set(), "", " ; ".join("%s (%d Dateien, %d Unterordner)" % (x[1], x[2], x[3]) for x in rd[:5]), "+".join("%s(%d)" % kv for kv in sorted(cm.items())))
        fdetail.append("VERZEICHNIS_FEHLER (Inhalt unbekannt) | %s | andere Discs: %s | Vergleichsordner: %s" % (d, fmatch[d][4] or "keine", fmatch[d][3] or "keine"))
    for x in fdetail[:25]: print("   " + x)
    if len(fdetail) > 25: print("   ... %d weitere im Bericht/CSV" % (len(fdetail) - 25))
vm = register_lesen(); mdisc = vm.get(M, ("", False))[1]
anderes = {}
for h, m2 in db.execute("select hash,medium from datei where medium<>? and hash<>''", (M,)): anderes.setdefault(h, set()).add(m2)
res = []; cnt = {}
for r in rows:
    st = r[4]; orte = set(); tr = {}
    if st == "OK":
        tr = treffer.get(r[3], {}); orte = set(tr.keys())
        if mdisc: orte.add("MDISC")
        st = "NUR_AUF_DISC" if not orte else ("GESICHERT_MEHRFACH" if len(orte) >= 2 else "GESICHERT_1_ORT")
    if st in ("LESEFEHLER", "VERZEICHNIS_FEHLER") and r[0] in fmatch:
        fm = fmatch[r[0]]; st = fm[0]
        res.append([r[0], r[1], r[3], r[5], st, "+".join(sorted(fm[1])), fm[2], fm[3], fm[4]])
    else:
        res.append([r[0], r[1], r[3], r[5], st, "+".join(sorted(orte)), "+".join(sorted({k for k, _ in tr.values()})), next(iter(tr.values()), ("", ""))[1], "+".join(sorted(anderes.get(r[3], set())))])
    k = (st, r[5]); cnt[k] = cnt.get(k, 0) + 1
zv = os.path.join(a.out, "%s_vergleich_%s.csv" % (M, ts))
with open(zv, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, delimiter=";"); w.writerow(["Pfad", "Groesse", "Hash", "Muell", "Status", "Orte", "Klassen", "Treffer_Pfad", "AuchAufMedium"]); w.writerows(res)
with db:
    db.executemany("insert into vergleich values(?,?,?,?,?,?,?,?,?)", [(ts, M, x[0], x[2], x[3], x[4], x[5], x[6], x[7]) for x in res])
C = lambda s, mu=None: sum(v for (a_, b_), v in cnt.items() if a_ == s and (mu is None or b_ == mu))
n_mf, n_1, n_leer, n_vf = C("GESICHERT_MEHRFACH"), C("GESICHERT_1_ORT"), C("LEER_0_BYTE"), C("VERZEICHNIS_FEHLER")
n_les_g = C("LESEFEHLER_GEDECKT_NAME"); n_les_off = C("LESEFEHLER_UNGEDECKT") + C("LESEFEHLER_NAME_PRUEFEN"); n_pruef = C("LESEFEHLER_NAME_PRUEFEN")
n_nd_all, n_nd = C("NUR_AUF_DISC"), C("NUR_AUF_DISC", "NEIN"); n_muell = C("NUR_AUF_DISC", "JA")
print("   gesichert mehrfach %d | gesichert 1 Ort %d | nur auf Disc %d (davon Muell %d) | leer %d | Lesefehler gedeckt per Name %d | Lesefehler ohne Kopie %d | Verzeichnisfehler %d" % (n_mf, n_1, n_nd_all, n_muell, n_leer, n_les_g, n_les_off, n_vf))
skip_rows = [(r[0], r[1], GR.get(r[0], "")) for r in rows if r[4] == "LESEFEHLER" and GR.get(r[0], "").startswith(("ZEITLIMIT", "TEMPO", "HAENGT"))]
n_skip_tot = len(skip_rows); gib_skip = sum(max(int(x[1]), 0) for x in skip_rows) / 2**30; zs = ""
if skip_rows:
    st_by = {x[0]: x[4] for x in res}; zs = os.path.join(a.out, "%s_uebersprungen_%s.csv" % (M, ts))
    with open(zs, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["Pfad", "Groesse", "Grund", "Deckung_Bestand"])
        for p_, s_, g_ in skip_rows: w.writerow([p_, s_, g_, st_by.get(p_, "")])
    print("   UEBERSPRUNGEN wegen Zeitlimit: %d Dateien, %.3f GiB (nicht gelesen, kein Hash) -> %s" % (n_skip_tot, gib_skip, zs))
# ================= 3 IMPORT
Z["phase"] = "Import"
imp_erlaubt = lw_da and not (ABBR and a.kein_teilimport)
liste = [x for x in res if x[4] == "NUR_AUF_DISC" and (a.auch_muell or x[3] == "NEIN")]
gb = sum(int(x[1]) for x in liste) / 2**30; zdir = os.path.join(a.ziel, M); imp_ok = imp_bad = 0; imp_rows = []; sperr = ""
if a.mapfile:
    try:
        mt_, mb_ = mapfile_luecken(a.mapfile)
        print("   Mapfile: %.3f GiB beschrieben, davon NICHT gelesen/ungesichert: %d Byte" % (mt_ / 2**30, mb_))
        if mb_ > 0 and not a.image_luecken_ok:
            sperr = "Image hat %d Byte Luecken (ddrescue-Mapfile): %d ungedeckte Dateien NICHT importiert, weil sie Nullbereiche enthalten koennen (--image-luecken-ok erzwingt den Import)" % (mb_, len(liste)) if liste else ""
            if liste: liste = []
    except OSError as e: print("   WARNUNG: Mapfile nicht lesbar: %s" % str(e)[:80])
print("[3/4] Import ungedeckter Dateien: %d Dateien, %.3f GiB -> %s %s" % (len(liste), gb, zdir, "(NUR PRUEFEN, nichts kopiert)" if a.nur_pruefen else ("(Import AUSGESETZT wegen Abbruch/Laufwerk)" if not imp_erlaubt else "")))
if liste and not a.nur_pruefen and imp_erlaubt:
    frei = shutil.disk_usage(os.path.splitdrive(os.path.abspath(a.ziel))[0] + os.sep if os.name == "nt" else "/").free / 2**30
    if gb * 1.1 > frei: sys.exit("ABBRUCH: zu wenig Platz am Ziel (%.1f GiB frei)" % frei)
    for x in liste:
        src = os.path.join(root, x[0]); dst = os.path.join(zdir, x[0]); st = "OK"
        try:
            os.makedirs(lp(os.path.dirname(dst)), exist_ok=True)
            if os.path.exists(lp(dst)): st = "SCHON_DA_GLEICH" if blake(dst) == x[2] else "KOLLISION_ZIEL_ANDERS"
            else:
                shutil.copyfile(lp(src), lp(dst) + ".part")
                if blake(dst + ".part") != x[2]: os.remove(lp(dst) + ".part"); st = "HASH_ABWEICHT"
                else: os.replace(lp(dst) + ".part", lp(dst))
        except OSError as e:
            st = "FEHLER " + fmeld(e)[:80]
            try: os.remove(lp(dst) + ".part")
            except OSError: pass
        if st in ("OK", "SCHON_DA_GLEICH"): imp_ok += 1
        else: imp_bad += 1
        imp_rows.append((x[0], x[1], st))
    with open(os.path.join(a.out, "%s_import_%s.csv" % (M, ts)), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(["Pfad", "Groesse", "Ergebnis"]); w.writerows(imp_rows)
# ================= 3b TEILRETTUNG (v1.5)
Z["phase"] = "Teilrettung"
SEKT = 2048
rdir = os.path.join(zdir, "_TEILRETTUNG"); rett_res = []
def _lg_lesen(pfad):
    g = []
    try:
        with open(lp(pfad), encoding="utf-8-sig", newline="") as f_:
            for r_ in csv.reader(f_, delimiter=";"):
                if len(r_) >= 3 and r_[0] != "Start": g.append((int(r_[0]), int(r_[1]), r_[2]))
    except (OSError, ValueError): return None
    return g
def _lg_schreiben(pfad, g):
    with open(lp(pfad), "w", encoding="utf-8-sig", newline="") as f_:
        w_ = csv.writer(f_, delimiter=";"); w_.writerow(["Start", "Ende", "Status"]); w_.writerows(g)
def _lg_merge(g):
    out = []
    for s_, e_, st_ in sorted(g):
        if out and out[-1][2] == st_ and out[-1][1] >= s_: out[-1] = (out[-1][0], max(out[-1][1], e_), st_)
        else: out.append((s_, e_, st_))
    return out
def _lies(p, f, out, cf, s0, e0, gaps, stat, ende, schnell, unbek):
    pos = s0; block = max(a.rettung_block_kib, 2) << 10; folge_ = 0; skip_ = SEKT * 8
    while pos < e0:
        if time.time() > ende: gaps.append((pos, e0, "untried")); return
        n = min(block, e0 - pos); Z["off"] = pos; Z["t_read"] = time.time(); b = b""; err = None
        try:
            _hook(p, pos, n); f.seek(pos); b = f.read(n)
        except OSError as ex: err = ex
        except ValueError as ex: err = OSError(str(ex))
        dt = time.time() - Z["t_read"]; Z["t_read"] = 0.0; Z["cancel_versucht"] = False
        if err is None and b:
            out.seek(pos); out.write(b)
            if cf is not None:
                try: cf.seek(pos); cb = cf.read(len(b))
                except OSError: cb = None
                if cb is not None and cb != b: stat["abw"] += 1; stat.setdefault("abw_off", pos)
            stat["gelesen"] += len(b); Z["bytes"] += len(b); pos += len(b); folge_ = 0
            if dt < 2.0: block = min(block * 2, 1 << 20)
            continue
        if err is None:                                   # nichts mehr lesbar: Dateiende
            if not unbek: gaps.append((pos, e0, "EOF"))
            return
        stat["fehler"] = fmeld(err)[:80]
        if n > SEKT: block = max(SEKT, n // 4); continue    # kleiner erneut versuchen
        gaps.append((pos, pos + n, "bad")); stat["bad_sek"] += 1; folge_ += 1; pos += n
        if unbek and folge_ >= 64: gaps.append((pos, pos, "Ende_unbekannt")); return
        if schnell and folge_ >= 8 and pos < e0:         # defekte Zone: ueberspringen, in Durchgang 2 nachholen
            sk = min(skip_, e0 - pos); gaps.append((pos, pos + sk, "untried")); pos += sk; skip_ = min(skip_ * 2, 4 << 20); folge_ = 0
def rette_datei(rel, size, cands, ende_global):
    p = os.path.join(root, rel)
    r = {"Pfad": rel, "Groesse": size, "Gelesen_B": 0, "Luecken_B": 0, "Luecken_n": 0, "Abweichend": "", "Vergleich": "", "Status": "", "Ziel": "", "Grund": "", "Hash_Teil": ""}
    Z["datei"] = rel; Z["off"] = 0; Z["cur"] = None
    try: f = open_lesen(p, roh=True)
    except OSError as e:
        r["Status"] = "NICHT_OEFFNENBAR"; r["Grund"] = fmeld(e)[:150]; return r
    with f:
        if size < 0:
            try: size = os.fstat(f.fileno()).st_size
            except OSError: size = -1
        r["Groesse"] = size; unbek = size < 0
        dst = os.path.join(rdir, rel); sc = dst + ".luecken.csv"; tmp = dst + ".part"; resume = False; gin = None
        if not unbek and os.path.exists(lp(dst)) and os.path.exists(lp(sc)):
            gin = _lg_lesen(sc)
            try: resume = gin is not None and os.path.getsize(lp(dst)) == size
            except OSError: resume = False
        cand = ""
        if not resume and size > 0:
            for q in cands:
                try:
                    if os.path.getsize(lp(q)) == size: cand = q; break
                except OSError: pass
        r["Vergleich"] = cand
        try:
            os.makedirs(lp(os.path.dirname(dst)), exist_ok=True)
            cf = open(lp(cand), "rb") if cand else None
            if resume:
                out = open(lp(dst), "r+b"); todo = [(s_, e_) for s_, e_, st_ in gin if st_ in ("bad", "untried", "EOF")]; fix = [g_ for g_ in gin if g_[2] not in ("bad", "untried", "EOF")]
            else:
                if os.path.exists(lp(tmp)): os.remove(lp(tmp))
                out = open(lp(tmp), "w+b")
                if size > 0: out.truncate(size)
                todo = [(0, size if not unbek else 1 << 62)]; fix = []
        except OSError as e:
            r["Status"] = "ZIEL_FEHLER"; r["Grund"] = fmeld(e)[:150]; return r
        gaps = []; stat = {"gelesen": 0, "abw": 0, "bad_sek": 0}; ende = min(ende_global, time.time() + a.rettung_datei_max_min * 60)
        for s_, e_ in todo: _lies(p, f, out, cf, s_, e_, gaps, stat, ende, True, unbek)
        offen = [(s_, e_) for s_, e_, st_ in gaps if st_ == "untried"]; gaps = [g_ for g_ in gaps if g_[2] != "untried"]
        for s_, e_ in offen: _lies(p, f, out, cf, s_, e_, gaps, stat, ende, False, unbek)
        out.flush(); out.close()
        if cf: cf.close()
    gaps = _lg_merge(gaps + fix)
    lueck = sum(e_ - s_ for s_, e_, st_ in gaps if st_ != "Ende_unbekannt")
    r["Luecken_B"] = lueck; r["Luecken_n"] = len(gaps); r["Gelesen_B"] = (size - lueck) if not unbek else stat["gelesen"]
    r["Abweichend"] = stat["abw"] if cand else ""; r["Grund"] = stat.get("fehler", "") + ((" | erster Unterschied bei Byte %d" % stat["abw_off"]) if stat.get("abw") else "")
    quelle = dst if resume else tmp
    try:
        if cand and not resume and stat["abw"] == 0:
            r["Status"] = "BESTAETIGT_IM_BESTAND" if not gaps else "TEIL_BESTAETIGT_IM_BESTAND"; os.remove(lp(tmp))   # eigene Temp-Datei; Bestand deckt alle lesbaren Bytes
        elif not gaps:
            fin = os.path.join(zdir, rel)
            if not os.path.exists(lp(fin)): os.makedirs(lp(os.path.dirname(fin)), exist_ok=True); os.replace(lp(quelle), lp(fin)); r["Ziel"] = fin
            else: os.replace(lp(quelle), lp(dst)) if not resume else None; r["Ziel"] = dst
            r["Status"] = "KOMPLETT_GERETTET"; r["Hash_Teil"] = blake(r["Ziel"])
            if os.path.exists(lp(sc)): _lg_schreiben(sc, [])
        else:
            if not resume: os.replace(lp(tmp), lp(dst))
            _lg_schreiben(sc, gaps); r["Status"] = "TEIL_GERETTET"; r["Ziel"] = dst; r["Hash_Teil"] = blake(dst)
    except OSError as e:
        r["Status"] = "ZIEL_FEHLER"; r["Grund"] = fmeld(e)[:150]
    return r
rett_cands = []
if not a.nur_pruefen and not a.ohne_rettung and imp_erlaubt:
    for r_ in rows:
        if r_[4] == "LESEFEHLER": rett_cands.append((r_[0], r_[1], cand_paths.get(r_[0], [])))
    for rel_, sz_, st_ in imp_rows:
        if st_.startswith("FEHLER") or st_ == "HASH_ABWEICHT": rett_cands.append((rel_, int(sz_), []))
    rett_cands.sort(key=lambda x: (x[1] < 0, x[1]))      # kleine Dateien zuerst: viele Dateien vor dem Zeitbudget
print("[3b/4] Teilrettung: %d Dateien (Lesefehler/Zeitlimit/Kopierfehler), Budget %.0f min gesamt, %.0f min je Datei -> %s" % (len(rett_cands), a.rettung_max_min, a.rettung_datei_max_min, rdir) if rett_cands else "[3b/4] Teilrettung: nichts zu tun%s" % (" (--ohne-rettung/--nur-pruefen/kein Import)" if (a.ohne_rettung or a.nur_pruefen or not imp_erlaubt) else ""))
ende_g = time.time() + a.rettung_max_min * 60
try:
    for k_, (rel_, sz_, cands_) in enumerate(rett_cands, 1):
        if time.time() >= ende_g:
            rett_res.append({"Pfad": rel_, "Groesse": sz_, "Gelesen_B": 0, "Luecken_B": "", "Luecken_n": "", "Abweichend": "", "Vergleich": "", "Status": "NICHT_VERSUCHT_ZEITBUDGET", "Ziel": "", "Grund": "", "Hash_Teil": ""}); continue
        try: r_ = rette_datei(rel_, sz_, cands_, ende_g)
        except Exception as ex_: r_ = {"Pfad": rel_, "Groesse": sz_, "Gelesen_B": 0, "Luecken_B": "", "Luecken_n": "", "Abweichend": "", "Vergleich": "", "Status": "RETTUNG_FEHLER", "Ziel": "", "Grund": str(ex_)[:150], "Hash_Teil": ""}
        rett_res.append(r_)
        if r_["Status"] != "NICHT_OEFFNENBAR" or k_ % 25 == 0 or k_ <= 5:
            print("   [%d/%d] %-28s %s | gelesen %s B, Luecken %s B" % (k_, len(rett_cands), r_["Status"], rel_[-60:], r_["Gelesen_B"], r_["Luecken_B"]))
except KeyboardInterrupt:
    print("   Teilrettung durch Strg+C beendet (Stand je Datei gesichert; Aufruf wiederholen fuellt Luecken weiter).")
zr = os.path.join(a.out, "%s_rettung_%s.csv" % (M, ts)); zn = ""
if rett_res:
    cols = ["Pfad", "Groesse", "Gelesen_B", "Luecken_B", "Luecken_n", "Abweichend", "Vergleich", "Status", "Ziel", "Grund", "Hash_Teil"]
    with open(zr, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";"); w.writerow(cols); w.writerows([[x.get(c, "") for c in cols] for x in rett_res])
    nicht_oeff = [x for x in rett_res if x["Status"] in ("NICHT_OEFFNENBAR", "NICHT_VERSUCHT_ZEITBUDGET", "RETTUNG_FEHLER") or (x["Status"] == "TEIL_GERETTET" and x["Luecken_B"])]
    zn = os.path.join(a.out, "%s_rettung_naechste_schritte_%s.txt" % (M, ts))
    with open(zn, "w", encoding="utf-8") as f:
        f.write("Disc %s - naechste Schritte fuer %d nicht (voll) gerettete Dateien (Stand %s)\n\n" % (M, len(nicht_oeff), datetime.datetime.now().strftime("%d.%m.%Y %H:%M")))
        f.write("1. Zeitbudget/Neuversuch: gleichen Befehl erneut starten - Teilrettung liest nur noch die Luecken (.luecken.csv) und fuellt sie auf; mehr Zeit: --rettung-max-min 240 --rettung-datei-max-min 60\n")
        f.write("2. Windows als Administrator starten (PowerShell 'Als Administrator ausfuehren') und denselben Befehl wiederholen: Ersatz-Oeffnung mit BACKUP_SEMANTICS braucht SeBackupPrivilege.\n")
        f.write("3. Image mit ddrescue (Ubuntu): sudo ./medien_image_ddrescue_v1.0.sh %s ~/medien_images  (zweites Laufwerk probieren, falls Luecken bleiben)\n" % M)
        f.write("4. Dateien aus dem Image mit anderem UDF-Parser ziehen (Dateisystem-Metadaten defekt, aber Daten lesbar):\n")
        f.write("   7z x D:\\Medien_Images\\%s.iso -o\"D:\\Archiv_Medien\\%s\\_AUS_IMAGE\" -y   (7-Zip liest UDF/ISO unabhaengig vom Windows-Treiber) oder unter Linux: sudo mount -t udf -o ro,loop %s.iso /mnt/img\n" % (M, M, M))
        f.write("5. Danach: py medien_pruefen_v1.5.py %s --laufwerk <Image-Laufwerk>:\\ --mapfile D:\\Medien_Images\\%s.map\n\nBetroffene Dateien:\n" % (M, M))
        for x in nicht_oeff: f.write("  %-26s %s (%s B, Luecken %s B) %s\n" % (x["Status"], x["Pfad"], x["Groesse"], x["Luecken_B"], x["Grund"]))
    print("   Teilrettung: Bericht %s | Naechste Schritte %s" % (zr, zn))
Z["phase"] = "Bewertung"

# ================= 4 BEWERTUNG
ungedeckt = len(liste) - imp_ok if not a.nur_pruefen else len(liste)
gruende = []
if n_les_off: gruende.append("%d Lesefehler OHNE gesicherte Kopie (davon %d nur Dateiname gleich, mit --name-akzeptieren wertbar) - anderes Laufwerk/ddrescue-Image" % (n_les_off, n_pruef))
if n_vf: gruende.append("%d Verzeichnisfehler (Inhalt unbekannt; Vergleichsordner siehe Bericht) - reinigen/anderes Laufwerk/ddrescue oder nach Pruefung --ignoriere" % n_vf)
if imp_bad: gruende.append("%d Importfehler (siehe %s_import_%s.csv)" % (imp_bad, M, ts))
if sperr: gruende.append(sperr)
if ungedeckt: gruende.append("%d Dateien nicht gedeckt/importiert%s" % (ungedeckt, " (--nur-pruefen)" if a.nur_pruefen else ""))
if ABBR: gruende.insert(0, "LAUF VORZEITIG BEENDET (Code %d): %d von %d Dateien NICHT gelesen (Teillauf; Aufruf wiederholen setzt fort)" % (ABBR.code, n_ng, len(files)))
ok = not gruende
if not a.nur_pruefen:
    os.makedirs(lp(zdir), exist_ok=True)
    with open(lp(os.path.join(zdir, "_Medium_Info.txt")), "w", encoding="utf-8") as f:
        f.write("Disk %s | Label %s | %s | Seriennr %s | geprueft %s\nDateien %d, %.3f GiB | gedeckt im Bestand %d | neu importiert %d | Muell nicht importiert %d | leer %d | Lesefehler gedeckt per Name %d\nErgebnis: %s\n" % (M, lab, fsn, ser, datetime.datetime.now().strftime("%d.%m.%Y %H:%M"), len(files), tot / 2**30, n_mf + n_1, imp_ok, n_muell if not a.auch_muell else 0, n_leer, n_les_g, "OK" if ok else "; ".join(gruende)))
msg = ("Disk %s erfolgreich geprueft und archiviert%s." % (M, (" (%d Lesefehler per Namenssuche gedeckt, Inhalt der Disc-Datei NICHT verifiziert)" % n_les_g) if n_les_g else "")) if ok else ("Disk %s NICHT abgeschlossen: %s" % (M, "; ".join(gruende)))
if ok and n_skip_tot: msg = "Disk %s geprueft MIT EINSCHRAENKUNG: %d Dateien (%.3f GiB) wegen Zeitlimit nicht gelesen, nur per Namenssuche im Bestand gedeckt (Inhalt NICHT verifiziert)." % (M, n_skip_tot, gib_skip)
zusatz = []
if ok:
    zusatz.append("Dateien: %d | bereits im Bestand: %d | neu nach %s importiert: %d | Muell (nicht importiert): %d | leer (0 Byte): %d" % (len(files), n_mf + n_1, a.ziel, imp_ok, n_muell if not a.auch_muell else 0, n_leer))
    zusatz.append("Zweiter Ort M-DISC verifiziert, ABER %d Dateien nicht gelesen (siehe unten): Disc NICHT entsorgen." % n_skip_tot if (mdisc and n_skip_tot) else "Zweiter Ort M-DISC verifiziert: Disc kann entsorgt werden (Entscheidung Gunter)." if mdisc else "HINWEIS: Disc NOCH NICHT entsorgen - M-DISC (M8) brennen, verifizieren, dann: py medien_pruefen_v1.5.py %s --mdisc-ok" % M)
    if n_muell and not a.auch_muell: zusatz.append("Muell mit Inhalt (z. B. ~WRL*.tmp) bleibt nur auf Disc/M-DISC; bei Bedarf mit --auch-muell erneut importieren.")
if n_skip_tot: zusatz.append("UEBERSPRUNGEN (Zeitlimit, NICHT gelesen): %d Dateien, %.3f GiB, Liste %s. Inhalt nicht per Hash geprueft. Disc NICHT entsorgen. Nachlesen: py medien_pruefen_v1.5.py %s --fehler-wiederholen --chunk-timeout-s 180 --datei-fehlzeit-s 600 (hohe Grenzen) oder ddrescue-Image." % (n_skip_tot, gib_skip, zs, M))
if n_les_g or n_les_off or n_vf: zusatz.append("ACHTUNG Lesefehler: Eine M-DISC-Kopie DIESER Disc enthaelt die betroffenen Dateien/Ordner nicht; Kopien siehe Detailzeilen. Deckung per Namenstreffer (Pfad/Name), Inhalt der defekten Disc-Datei nicht per Hash geprueft.")
if ABBR: zusatz.insert(0, "ABBRUCH: " + ABBR.text)
if rett_res:
    _c = {}
    for x in rett_res: _c[x["Status"]] = _c.get(x["Status"], 0) + 1
    _lb = sum(int(x["Luecken_B"]) for x in rett_res if str(x["Luecken_B"]).isdigit()); _gb = sum(int(x["Gelesen_B"]) for x in rett_res if str(x["Gelesen_B"]).isdigit())
    zusatz.append("TEILRETTUNG: %d Dateien: %s | lesbar gerettet %.3f MiB, Luecken %.3f MiB | Bericht %s | naechste Schritte %s" % (len(rett_res), ", ".join("%s=%d" % kv for kv in sorted(_c.items())), _gb / 2**20, _lb / 2**20, zr, zn))
    if _c.get("TEIL_GERETTET"): zusatz.append("TEIL_GERETTET-Dateien liegen in %s (NICHT vollstaendig, Luecken = Nullbytes, Liste je Datei <Datei>.luecken.csv); sie ersetzen keine Original-Kopie." % rdir)
zusatz += ["DETAIL " + x for x in fdetail]
if akz_liste: zusatz.append("AKZEPTIERTE AUSNAHMEN (nicht lesbar, per --ignoriere uebersprungen, Inhalt NICHT gesichert): %d - %s" % (akz, " | ".join(akz_liste)))
db.execute("insert into ergebnis values(?,?,?,?)", (M, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "OK" if ok else "OFFEN", "; ".join(gruende) or "; ".join(zusatz))); db.commit()
bericht = os.path.join(a.out, "%s_bericht_%s.txt" % (M, ts))
with open(bericht, "w", encoding="utf-8") as f: f.write(msg + "\n" + "\n".join(zusatz) + "\nDauer %.0f s | Laufwerk %s | Label %s | Seriennr %s | Lesetempo %.2f MB/s | langsame Zugriffe %d\n" % (time.time() - t_start, root, lab, ser, Z["bytes"] / 1e6 / el, n_lang))
print("[4/4] Bewertung\n\n" + "=" * 70 + "\n" + msg + "\n" + "\n".join(zusatz) + "\nBericht: " + bericht + "\n" + "=" * 70)
Z["lauf"] = False
sys.exit(0 if ok else (ABBR.code if ABBR else 1))
