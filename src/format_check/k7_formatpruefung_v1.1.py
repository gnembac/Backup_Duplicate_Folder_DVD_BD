#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""k7_formatpruefung_v1.1.py – Formatprüfung der Disc-Dateien ohne Referenz (K-7), nur LESEN.

Stand 29.10.2026, 22:20 MEZ (v1.1) | Vorgänger v1.0 29.10.2026, 21:40 MEZ | Firma: privat | Autor: Claude | Python 3.8+ (nur Standardbibliothek; Pillow optional)

Zweck
  Disc-Importe in D:\\Archiv_Medien, zu denen es keine zweite Fassung gibt (Kopierplan-Spalte Pruefen = Formatprüfung),
  können stille Lesefehler enthalten (Muster: Zone von 16·n Sektoren à 2.048 Byte, Beginn Byte 16 im Sektor).
  Das Skript liest jede Quelle, vergleicht SHA-256 mit dem Plan und prüft den Dateiaufbau je Format.
  Auf dem Rechner wird NICHTS verändert; geschrieben werden nur Protokoll und Zusammenfassung in den Log-Ordner.

Ergebnis je Datei
  OK              Format geprüft, kein Fehler gefunden
  DEFEKT          Formatfehler gefunden -> Datei sehr wahrscheinlich verfälscht
  VERDACHT        Auffälligkeit, aber kein eindeutiger Fehler
  NICHT_PRUEFBAR  Format ohne Prüfmöglichkeit (z. B. exe, dat, ntx) – nur SHA-256 geprüft
  UEBERSPRUNGEN   Video (nur mit --mit-video geprüft)
  SHA_ABWEICHUNG  Quelle weicht vom Plan ab (Datei seit T0 geändert) – nicht weiter geprüft
  FEHLER          Datei nicht lesbar
Stärke der Prüfung
  STARK   Prüfsumme/Synchronmuster deckt jede Verfälschung auf (ZIP-CRC, PNG-CRC, SWF-zlib, VOB-Packs, M2TS-Sync)
  MITTEL  Aufbau wird vollständig durchlaufen; Verfälschung wird mit hoher Wahrscheinlichkeit, aber nicht sicher erkannt
  SCHWACH nur Kopf/Rahmen geprüft; Verfälschung im Nutzinhalt bleibt unentdeckt
  Hinweis: Ein Defekt, der zufällig gültige Daten erzeugt, bleibt bei MITTEL/SCHWACH unentdeckt (Befund Pilot: 4 von 23 JPEG decodierten trotz Defekt).

Änderungen v1.1 (29.10.2026, 22:20 MEZ) – Fehlalarme aus Lauf 2026-10-29_2148 behoben
  1. PDF: Suchmuster 'stream' traf auch das Wort 'endstream' -> Daten hinter endstream als Flate-Strom gelesen ->
     'incorrect header check'. Gegenprobe an 49 intakten, hash-geprüften PDF aus D:\\Daten\\Reisen: v1.0 31 x DEFEKT, v1.1 0 x.
  2. PDF: Flate-Strom ohne Abschlusskennung -> VERDACHT (nicht DEFEKT; 1 intakte Datei zeigt das ebenfalls).
  3. OLE (doc/xls): fehlende OLE2-Signatur -> RTF/HTML/WordPerfect erkennen, sonst VERDACHT. Begründung: Das bekannte
     Defektmuster beginnt bei Byte 16 eines Sektors, Byte 0-15 am Dateianfang sind davon nie betroffen.
  4. Word-FIB: Kennungen Word 6/95 (A5DC) und Word 2 (A5DB) gelten als gültig (v1.0 nur Word 97+ A5EC).
  5. DFM: binäre Delphi-Formulare (Kopf TPF0) sind kein Text -> NICHT_PRUEFBAR.
  6. Videos werden standardmäßig geprüft (Gunter 29.10.2026: Urlaubs-/Projektvideos bleiben erhalten);
     DVD-Video vob/ifo/bup wird übersprungen (entfällt laut Gunter), mit --mit-dvd trotzdem geprüft.
     --ohne-video überspringt alle Videos (Verhalten wie v1.0).

Aufruf (PowerShell)
  python D:\\_Berichte\\kopierplan\\skripte\\k7_formatpruefung_v1.1.py
  python D:\\_Berichte\\kopierplan\\skripte\\k7_formatpruefung_v1.1.py --max-dateien 200     (kurzer Probelauf)
  python D:\\_Berichte\\kopierplan\\skripte\\k7_formatpruefung_v1.1.py --ohne-video          (Videos überspringen)
"""
import argparse, csv, datetime, hashlib, io, os, re, struct, sys, time, zipfile, zlib, lzma
from collections import Counter

VERSION = 'k7_formatpruefung_v1.1'
LISTE = r'D:\_Berichte\kopierplan\K7_Formatpruefung_Liste_2026-10-29_v1.0.csv'
LOGORDNER = r'D:\_Berichte\kopierplan\logs'
MAXMEM = 768 * 2**20          # größere Dateien: nur SHA-256 (+ ZIP-Test über Datei)
OK, DEF, VER, NP, UEB, SHAX, FEH = 'OK', 'DEFEKT', 'VERDACHT', 'NICHT_PRUEFBAR', 'UEBERSPRUNGEN', 'SHA_ABWEICHUNG', 'FEHLER'
STARK, MITTEL, SCHWACH, KEINE = 'STARK', 'MITTEL', 'SCHWACH', ''

ZIPX = set('zip jar docx xlsx pptx docm xlsm pptm dotx xltx odt ods odp odg epub kmz xpi apk whl vsdx'.split())
OLEX = set('doc dot xls xlt xla ppt pps pot wbk msg mpp vsd pub xlw'.split())
TEXTX = set('html htm shtml xhtml js css txt xml xsl xslt dtd bat cmd ini inf csv tsv php php3 asp aspx inc java c h cpp hpp cc '
            'py pl sql svg rss url log json cfg conf reg vbs nfo rtf mht eml md tex bas pas dfm dpr lst def m sh'.split())
JPGX = {'jpg', 'jpeg', 'jpe', 'jfif'}
VIDX = set('vob mpg mpeg m2ts mts ts mp4 mov m4v 3gp avi wmv mkv flv mod tod bup ifo'.split())
try:
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    PIL = True
except Exception:
    PIL = False


def lp(p):
    """Windows-Langpfad (Quellen bis 398 Zeichen)."""
    if os.name == 'nt' and not p.startswith('\\\\?\\'):
        return '\\\\?\\' + p
    return p


u16 = lambda b, o: struct.unpack_from('<H', b, o)[0]
u32 = lambda b, o: struct.unpack_from('<I', b, o)[0]
b16 = lambda b, o: struct.unpack_from('>H', b, o)[0]
b32 = lambda b, o: struct.unpack_from('>I', b, o)[0]


# ------------------------------------------------------------------ Einzelprüfungen: Rückgabe (Ergebnis, Stärke, Detail)
def chk_zip(path_or_bytes):
    try:
        src = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, (bytes, bytearray)) else path_or_bytes
        with zipfile.ZipFile(src) as z:
            for zi in z.infolist():
                if zi.flag_bits & 0x1:
                    return NP, KEINE, 'ZIP verschlüsselt'
            bad = z.testzip()
        if bad:
            return DEF, STARK, 'ZIP-CRC falsch: ' + bad[:120]
        return OK, STARK, 'ZIP-CRC aller Einträge ok'
    except NotImplementedError as e:
        return NP, KEINE, 'ZIP-Verfahren nicht unterstützt: %s' % e
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError, ValueError, KeyError, struct.error) as e:
        return DEF, STARK, 'ZIP: %s' % str(e)[:150]
    except RuntimeError as e:
        return NP, KEINE, 'ZIP: %s' % str(e)[:150]


def chk_png(b):
    if b[:8] != b'\x89PNG\r\n\x1a\n':
        return DEF, STARK, 'keine PNG-Signatur'
    i, n = 8, len(b)
    while i + 12 <= n:
        L = b32(b, i); t = b[i + 4:i + 8]
        if i + 12 + L > n:
            return DEF, STARK, 'Chunk %r über Dateiende' % t
        if zlib.crc32(b[i + 4:i + 8 + L]) & 0xffffffff != b32(b, i + 8 + L):
            return DEF, STARK, 'CRC falsch in Chunk %r @%d' % (t, i)
        i += 12 + L
        if t == b'IEND':
            return OK, STARK, 'alle Chunk-CRC ok'
    return DEF, STARK, 'kein IEND'


MARK_OK = set(range(0xC0, 0xFF)) - set(range(0xD0, 0xD8))


def chk_jpeg(b, eingebettet=False):
    n = len(b)
    if b[:2] != b'\xff\xd8':
        return DEF, MITTEL, 'kein SOI'
    i, dri, scans = 2, 0, 0
    while True:
        if i >= n:
            return DEF, MITTEL, 'kein EOI (Ende ohne Abschluss)'
        if b[i] != 0xFF:
            return DEF, MITTEL, 'Marker erwartet @%d' % i
        while i < n and b[i] == 0xFF:
            i += 1
        if i >= n:
            return DEF, MITTEL, 'Dateiende im Marker'
        m = b[i]; i += 1
        if m == 0xD9:
            break
        if m == 0x01 or 0xD0 <= m <= 0xD7:
            continue
        if m == 0x00:
            return DEF, MITTEL, 'Marker FF00 außerhalb Scan @%d' % (i - 2)
        if i + 2 > n:
            return DEF, MITTEL, 'Segment ohne Länge'
        L = b16(b, i)
        if L < 2 or i + L > n:
            return DEF, MITTEL, 'Segmentlänge FF%02X ungültig @%d' % (m, i - 2)
        if m == 0xDD and L >= 4:
            dri = b16(b, i + 2)
        i += L
        if m == 0xDA:
            scans += 1; exp = 0
            while True:
                j = b.find(b'\xff', i)
                if j < 0 or j + 1 >= n:
                    return DEF, MITTEL, 'Scan %d ohne Ende' % scans
                k = j + 1
                while k < n and b[k] == 0xFF:
                    k += 1
                if k >= n:
                    return DEF, MITTEL, 'Scan %d ohne Ende' % scans
                c = b[k]
                if c == 0x00:
                    i = k + 1; continue
                if 0xD0 <= c <= 0xD7:
                    if dri and c - 0xD0 != exp:
                        return DEF, MITTEL, 'RST-Folge gestört (RST%d statt RST%d) @%d' % (c - 0xD0, exp, j)
                    exp = (c - 0xD0 + 1) & 7; i = k + 1; continue
                if c in MARK_OK:
                    i = j          # äußere Schleife liest den Marker ab hier
                    break
                return DEF, MITTEL, 'ungültige Bytefolge FF%02X im Bilddatenstrom @%d' % (c, j)
    if scans == 0:
        return DEF, MITTEL, 'kein Scan (SOS) vorhanden'
    if PIL and not eingebettet:
        try:
            im = Image.open(io.BytesIO(b)); im.load()
        except Exception as e:
            return DEF, MITTEL, 'Pillow-Decode: %s' % str(e)[:120]
        return OK, MITTEL, 'Markeraufbau, RST-Folge%s und Pillow-Decode ok' % ('' if dri else ' (keine RST)')
    return OK, MITTEL, 'Markeraufbau%s ok' % (' und RST-Folge' if dri else ' (keine RST-Marker)')


def lzw_gif(data, minsize, pixels):
    """LZW-Strom prüfen (Codes gültig, Pixelanzahl)."""
    if not 2 <= minsize <= 11:
        return 'LZW-Mindestgröße %d ungültig' % minsize
    clear, eoi = 1 << minsize, (1 << minsize) + 1
    size = minsize + 1; nxt = eoi + 1; prev = None; out = 0
    lens = [1] * (1 << 12)
    bitpos = 0; nbits = len(data) * 8
    val = int.from_bytes(data, 'little')
    while bitpos + size <= nbits:
        code = (val >> bitpos) & ((1 << size) - 1); bitpos += size
        if code == clear:
            size = minsize + 1; nxt = eoi + 1; prev = None; continue
        if code == eoi:
            return None if out >= pixels else 'zu wenige Pixel (%d von %d)' % (out, pixels)
        if prev is None:
            if code >= clear:
                return 'erster Code %d ungültig' % code
            out += 1; prev = code; continue
        if code < nxt:
            ln = lens[code] if code > eoi else 1
        elif code == nxt:
            ln = (lens[prev] if prev > eoi else 1) + 1
        else:
            return 'LZW-Code %d > nächster %d' % (code, nxt)
        out += ln
        if nxt < 4096:
            lens[nxt] = (lens[prev] if prev > eoi else 1) + 1
            nxt += 1
            if nxt == (1 << size) and size < 12:
                size += 1
        prev = code
    return None if out >= pixels else 'LZW-Strom endet ohne EOI (%d von %d Pixeln)' % (out, pixels)


def chk_gif(b):
    if b[:6] not in (b'GIF87a', b'GIF89a'):
        return DEF, MITTEL, 'keine GIF-Signatur'
    n = len(b); flags = b[10]; i = 13
    if flags & 0x80:
        i += 3 * (2 << (flags & 7))
    bilder = 0
    while i < n:
        t = b[i]; i += 1
        if t == 0x3B:
            rest = b[i:].rstrip(b'\x00')
            return (OK, MITTEL, '%d Bild(er), LZW ok' % bilder) if len(rest) == 0 else (VER, MITTEL, '%d Byte nach Abschlusskennung' % len(rest))
        if t == 0x21:
            i += 1
            while True:
                if i >= n: return DEF, MITTEL, 'Erweiterungsblock über Dateiende'
                s = b[i]; i += 1 + s
                if s == 0: break
        elif t == 0x2C:
            if i + 9 > n: return DEF, MITTEL, 'Bildbeschreibung abgeschnitten'
            w, h, f = u16(b, i + 4), u16(b, i + 6), b[i + 8]; i += 9
            if f & 0x80: i += 3 * (2 << (f & 7))
            if i >= n: return DEF, MITTEL, 'Bilddaten fehlen'
            ms = b[i]; i += 1; parts = []
            while True:
                if i >= n: return DEF, MITTEL, 'Bilddaten über Dateiende'
                s = b[i]; parts.append(b[i + 1:i + 1 + s]); i += 1 + s
                if s == 0: break
            err = lzw_gif(b''.join(parts), ms, w * h)
            if err: return DEF, MITTEL, 'Bild %d: %s' % (bilder + 1, err)
            bilder += 1
        else:
            return DEF, MITTEL, 'unbekannter Block 0x%02X @%d' % (t, i - 1)
    return DEF, MITTEL, 'keine Abschlusskennung (0x3B)'


RX_STREAM = re.compile(rb'(?<!end)stream\r?\n')
def chk_pdf(b):
    k = b.find(b'%PDF', 0, 1024)
    if k < 0:
        return DEF, MITTEL, 'keine PDF-Signatur'
    if b'%%EOF' not in b[-4096:]:
        return DEF, MITTEL, 'kein %%EOF am Dateiende'
    if b'/Encrypt' in b[-65536:] or b'/Encrypt' in b[:4096]:
        return OK, SCHWACH, 'verschlüsselt: nur Rahmen geprüft'
    nfl = ndct = nfehl = noffen = 0; erster = ''
    for m in RX_STREAM.finditer(b):
        s = m.end()
        d0 = b.rfind(b'<<', max(0, m.start() - 4000), m.start())
        if d0 < 0:
            continue
        dic = b[d0:m.start()]
        if b'endstream' in dic:
            continue
        lm = re.search(rb'/Length\s+(\d+)(?!\s+\d+\s+R)', dic)
        e = b.find(b'endstream', s)
        if e < 0:
            nfehl += 1; erster = erster or 'Stream ohne endstream @%d' % s; continue
        if lm:
            L = int(lm.group(1))
            if s + L <= len(b) and b[s + L:s + L + 12].lstrip(b'\r\n ').startswith(b'endstream'):
                data = b[s:s + L]
            else:
                data = b[s:e].rstrip(b'\r\n')
        else:
            data = b[s:e].rstrip(b'\r\n')
        fm = re.search(rb'/Filter\s*(\[[^\]]*\]|/\w+)', dic)
        filt = fm.group(1) if fm else b''
        erstf = re.findall(rb'/(\w+)', filt)[:1]
        if erstf in ([b'FlateDecode'], [b'Fl']):
            nfl += 1
            try:
                dz = zlib.decompressobj(); dz.decompress(data, 256 * 2**20)
                if not dz.eof and not dz.unconsumed_tail:
                    noffen += 1
            except zlib.error as ex:
                nfehl += 1; erster = erster or 'Flate-Stream @%d: %s' % (s, ex)
        elif erstf in ([b'DCTDecode'], [b'DCT']) and len(filt.split(b'/')) <= 2:
            ndct += 1
            r = chk_jpeg(data, eingebettet=True)
            if r[0] == DEF:
                nfehl += 1; erster = erster or 'JPEG-Stream @%d: %s' % (s, r[2])
    if nfehl:
        return DEF, MITTEL, '%d fehlerhafte Streams (erster: %s)' % (nfehl, erster[:120])
    if noffen:
        return VER, MITTEL, '%d von %d Flate-Strömen ohne Abschlusskennung (kein Datenfehler)' % (noffen, nfl)
    if nfl + ndct == 0:
        return OK, SCHWACH, 'keine prüfbaren Streams; Rahmen ok'
    return OK, MITTEL, '%d Flate- und %d JPEG-Streams ok' % (nfl, ndct)


def chk_ole(b, ext):
    if b[:8] != b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        if ext in ('doc', 'xls', 'wri') and b[:2] in (b'\x31\xbe', b'\x32\xbe', b'\xdb\xa5', b'\x09\x00', b'\x09\x02', b'\x09\x04', b'\x09\x08'):
            return OK, SCHWACH, 'altes Format ohne OLE-Container; nur Kopf geprüft'
        kopf = b[:16].lstrip()
        if kopf[:5] == b'{\\rtf':
            r = chk_text(b); return r[0], r[1], 'RTF statt OLE2: ' + r[2]
        if kopf[:1] == b'<':
            r = chk_text(b); return r[0], r[1], 'HTML/XML statt OLE2: ' + r[2]
        if b[:4] == b'\xffWPC':
            return NP, KEINE, 'WordPerfect-Datei – nicht prüfbar'
        return VER, SCHWACH, 'keine OLE2-Signatur (Kopf %s); Byte 0-15 liegen außerhalb des Defektmusters' % b[:8].hex()
    ssz = 1 << u16(b, 30); mssz = 1 << u16(b, 32)
    if ssz not in (512, 4096) or mssz != 64:
        return DEF, MITTEL, 'Sektorgröße ungültig'
    n = len(b); nsect = (n - ssz) // ssz + (1 if (n - ssz) % ssz else 0)
    sec = lambda s: b[ssz + s * ssz: ssz + (s + 1) * ssz]
    SPEC = {0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFC}
    nfat = u32(b, 44); dirst = u32(b, 48); cut = u32(b, 56); mfst = u32(b, 60); nmf = u32(b, 64); dfst = u32(b, 68); ndf = u32(b, 72)
    difat = [u32(b, 76 + 4 * k) for k in range(109)]
    s, guard = dfst, 0
    while s not in SPEC and guard < ndf + 1:
        if s >= nsect: return DEF, MITTEL, 'DIFAT-Kette außerhalb der Datei'
        d = sec(s); difat += [u32(d, 4 * k) for k in range(ssz // 4 - 1)]; s = u32(d, ssz - 4); guard += 1
    fats = [x for x in difat if x not in SPEC][:nfat]
    if len(fats) != nfat or any(x >= nsect for x in fats):
        return DEF, MITTEL, 'FAT-Sektorliste ungültig'
    fat = []
    for x in fats:
        d = sec(x); fat += [u32(d, 4 * k) for k in range(len(d) // 4)]
    for x in fat[:nsect]:
        if x not in SPEC and x >= nsect:
            return DEF, MITTEL, 'FAT-Eintrag zeigt außerhalb der Datei'
    def kette(s, tab, lim):
        out = []; seen = set()
        while s not in SPEC:
            if s >= lim or s in seen or s >= len(tab): return None
            seen.add(s); out.append(s); s = tab[s]
        return out
    dk = kette(dirst, fat, nsect)
    if not dk: return DEF, MITTEL, 'Verzeichniskette gestört'
    dirb = b''.join(sec(x) for x in dk)
    ents = []
    for k in range(len(dirb) // 128):
        e = dirb[128 * k:128 * (k + 1)]; typ = e[66]
        if typ == 0: continue
        nl = u16(e, 64)
        if typ > 5 or nl > 64 or nl % 2: return DEF, MITTEL, 'Verzeichniseintrag %d ungültig' % k
        name = e[:max(0, nl - 2)].decode('utf-16-le', 'replace'); st = u32(e, 116); sz = u32(e, 120)
        ents.append((name, typ, st, sz))
    if not ents or ents[0][1] != 5: return DEF, MITTEL, 'Root-Eintrag fehlt'
    mfk = kette(mfst, fat, nsect) if nmf else []
    if mfk is None: return DEF, MITTEL, 'MiniFAT-Kette gestört'
    minifat = []
    for x in mfk:
        d = sec(x); minifat += [u32(d, 4 * k) for k in range(len(d) // 4)]
    rk = kette(ents[0][2], fat, nsect) if ents[0][3] else []
    if rk is None: return DEF, MITTEL, 'Ministream-Kette gestört'
    mini = b''.join(sec(x) for x in rk)
    def stream(st, sz):
        if sz < cut:
            k2 = kette(st, minifat, len(mini) // 64 + 1)
            if k2 is None or len(k2) * 64 < sz: return None
            return b''.join(mini[64 * x:64 * (x + 1)] for x in k2)[:sz]
        k2 = kette(st, fat, nsect)
        if k2 is None or len(k2) * ssz < sz: return None
        return b''.join(sec(x) for x in k2)[:sz]
    daten = {}
    for name, typ, st, sz in ents[1:]:
        if typ == 2:
            d = stream(st, sz)
            if d is None: return DEF, MITTEL, 'Stream %r: Sektorkette gestört' % name
            daten[name] = d
    zusatz = ''
    wb = daten.get('Workbook') or daten.get('Book')
    if wb is not None:
        i = 0; nrec = 0
        while i + 4 <= len(wb):
            t, L = u16(wb, i), u16(wb, i + 2)
            if t == 0 and L == 0 and not any(wb[i:]):
                break                                   # Füllbytes am Stream-Ende
            if L > 8224 or t == 0 or t > 0x1100:
                return DEF, MITTEL, 'BIFF-Satz ungültig @%d (Typ 0x%04X, Länge %d)' % (i, t, L)
            i += 4 + L; nrec += 1
            if i > len(wb): return DEF, MITTEL, 'BIFF-Satz über Stream-Ende'
        zusatz = ', %d BIFF-Sätze ok' % nrec
    pp = daten.get('PowerPoint Document')
    if pp is not None:
        def walk(a, e, tiefe=0):
            i = a
            while i + 8 <= e:
                vi, t, L = u16(pp, i), u16(pp, i + 2), u32(pp, i + 4)
                if tiefe == 0 and not any(pp[i:e]):
                    return None                         # Füllbytes am Stream-Ende
                if i + 8 + L > e or not (1000 <= t <= 12000 or 0xF000 <= t <= 0xF2FF):
                    return 'PPT-Satz ungültig @%d (Typ 0x%04X)' % (i, t)
                if (vi & 0xF) == 0xF and tiefe < 30:
                    r = walk(i + 8, i + 8 + L, tiefe + 1)
                    if r: return r
                i += 8 + L
            return None
        r = walk(0, len(pp))
        if r: return DEF, MITTEL, r
        zusatz = ', PPT-Satzstruktur ok'
    wd = daten.get('WordDocument')
    if wd is not None:
        if len(wd) < 0x22 or u16(wd, 0) not in (0xA5EC, 0xA5DC, 0xA5DB):
            return DEF, MITTEL, 'Word-FIB ungültig (0x%04X)' % (u16(wd, 0) if len(wd) >= 2 else 0)
        zusatz = ', Word-FIB ok (Textinhalt nicht prüfbar)'
    stufe = MITTEL if (wb is not None or pp is not None) else SCHWACH
    return OK, stufe, 'OLE2-Struktur (%d Einträge)%s' % (len(ents), zusatz)


def chk_text(b):
    if b[:2] in (b'\xff\xfe', b'\xfe\xff'):
        try:
            t = b.decode('utf-16')
        except UnicodeDecodeError as e:
            return DEF, MITTEL, 'UTF-16 ungültig: %s' % e
        bad = sum(1 for ch in t if ord(ch) < 9 or 13 < ord(ch) < 32 and ch not in '\x1a\x1b')
        return (OK, MITTEL, 'UTF-16, keine Steuerzeichen') if bad == 0 else (DEF, MITTEL, '%d Steuerzeichen (UTF-16)' % bad)
    tab = bytes(range(0, 9)) + bytes(range(14, 26)) + bytes(range(28, 32)) + b'\x7f'
    schlimm = []; summe = 0
    for k in range(0, len(b), 2048):
        blk = b[k:k + 2048]
        c = len(blk) - len(blk.translate(None, tab))
        if c:
            summe += c
            if c >= 3: schlimm.append(k // 2048)
    if b.endswith(b'\x00') and summe == len(b) - len(b.rstrip(b'\x00')):
        return VER, MITTEL, 'nur Nullbytes am Dateiende (%d)' % summe
    if schlimm:
        return DEF, MITTEL, '%d Steuerzeichen, gehäuft in Sektor(en) %s' % (summe, ','.join(map(str, schlimm[:8])))
    if summe:
        return VER, MITTEL, '%d vereinzelte Steuerzeichen' % summe
    return OK, MITTEL, 'Text ohne Steuerzeichen'


def chk_swf(b):
    sig = b[:3]
    if sig not in (b'FWS', b'CWS', b'ZWS'):
        return DEF, MITTEL, 'keine SWF-Signatur'
    L = u32(b, 4)
    try:
        if sig == b'CWS':
            d = zlib.decompressobj(); body = d.decompress(b[8:])
            if not d.eof: return DEF, STARK, 'zlib-Strom unvollständig'
            return (OK, STARK, 'zlib ok, Länge stimmt') if len(body) + 8 == L else (DEF, STARK, 'Länge %d statt %d' % (len(body) + 8, L))
        if sig == b'ZWS':
            return OK, SCHWACH, 'LZMA-SWF: nur Kopf geprüft'
    except zlib.error as e:
        return DEF, STARK, 'zlib: %s' % e
    return (OK, SCHWACH, 'unkomprimiert, Länge stimmt') if L == len(b) else (DEF, MITTEL, 'Längenfeld %d ≠ Dateigröße %d' % (L, len(b)))


def chk_class(b):
    if b[:4] != b'\xca\xfe\xba\xbe':
        return DEF, MITTEL, 'keine Class-Signatur'
    try:
        i = 8; n = b16(b, i); i += 2; k = 1
        while k < n:
            t = b[i]; i += 1
            if t == 1: i += 2 + b16(b, i)
            elif t in (3, 4, 9, 10, 11, 12, 17, 18): i += 4
            elif t in (5, 6): i += 8; k += 1
            elif t in (7, 8, 16, 19, 20): i += 2
            elif t == 15: i += 3
            else: return DEF, MITTEL, 'Konstantenpool-Tag %d ungültig' % t
            k += 1
        i += 6; ni = b16(b, i); i += 2 + 2 * ni
        for _ in range(2):
            nf = b16(b, i); i += 2
            for _ in range(nf):
                i += 6; na = b16(b, i); i += 2
                for _ in range(na): i += 6 + b32(b, i + 2)
        na = b16(b, i); i += 2
        for _ in range(na): i += 6 + b32(b, i + 2)
        return (OK, MITTEL, 'Class-Aufbau bis Dateiende ok') if i == len(b) else (DEF, MITTEL, 'Aufbau endet bei %d statt %d' % (i, len(b)))
    except (struct.error, IndexError):
        return DEF, MITTEL, 'Class-Aufbau über Dateiende'


def chk_bmp(b):
    if b[:2] != b'BM' or len(b) < 54:
        return DEF, SCHWACH, 'keine BMP-Signatur'
    if u32(b, 2) not in (len(b), 0) or u32(b, 10) >= len(b):
        return DEF, SCHWACH, 'Kopfangaben passen nicht zur Dateigröße'
    return OK, SCHWACH, 'Kopf ok; Bildpunkte nicht prüfbar'


def chk_riff(b):
    if b[:4] != b'RIFF' or len(b) < 12:
        return DEF, SCHWACH, 'keine RIFF-Signatur'
    if u32(b, 4) + 8 != len(b) and u32(b, 4) + 9 != len(b):
        return VER, SCHWACH, 'RIFF-Länge %d ≠ Datei %d' % (u32(b, 4) + 8, len(b))
    i = 12
    while i + 8 <= len(b):
        L = u32(b, i + 4); i += 8 + L + (L & 1)
    return (OK, SCHWACH, 'Chunk-Kette ok; Nutzdaten nicht prüfbar') if i in (len(b), len(b) + 1) else (DEF, SCHWACH, 'Chunk-Kette endet bei %d' % i)


def chk_tiff(b):
    if b[:4] not in (b'II*\x00', b'MM\x00*'):
        return DEF, SCHWACH, 'keine TIFF-Signatur'
    if PIL:
        try:
            im = Image.open(io.BytesIO(b)); im.load()
            return OK, MITTEL, 'Pillow-Decode ok'
        except Exception as e:
            return DEF, MITTEL, 'Pillow-Decode: %s' % str(e)[:120]
    le = b[:2] == b'II'; U16 = u16 if le else b16; U32 = u32 if le else b32
    o = U32(b, 4); seen = 0
    while o and seen < 50:
        if o + 2 > len(b): return DEF, SCHWACH, 'IFD außerhalb der Datei'
        n = U16(b, o)
        if o + 2 + 12 * n + 4 > len(b): return DEF, SCHWACH, 'IFD abgeschnitten'
        o = U32(b, o + 2 + 12 * n); seen += 1
    return OK, SCHWACH, '%d IFD ok; Bilddaten nicht geprüft (Pillow fehlt)' % seen


# ---------- Videos (nur --mit-video)
def chk_vob(path, size):
    with open(lp(path), 'rb') as f:
        k = 0; bad = 0; erster = -1
        while True:
            blk = f.read(2048)
            if not blk: break
            if blk[:4] != b'\x00\x00\x01\xba':
                bad += 1; erster = k if erster < 0 else erster
            k += 1
    if bad:
        return DEF, STARK, '%d Sektoren ohne Pack-Kopf (erster %d)' % (bad, erster)
    return OK, STARK, '%d Pack-Sektoren ok' % k


def chk_m2ts(path, pk, off):
    with open(lp(path), 'rb') as f:
        k = 0; bad = 0
        while True:
            blk = f.read(pk * 4096)
            if not blk: break
            for j in range(off, len(blk), pk):
                if blk[j] != 0x47: bad += 1
            k += len(blk) // pk
    return (DEF, STARK, '%d von %d Paketen ohne Sync' % (bad, k)) if bad else (OK, STARK, '%d Pakete Sync ok' % k)


def chk_mp4(path, size):
    with open(lp(path), 'rb') as f:
        i = 0; boxen = []
        while i < size:
            f.seek(i); h = f.read(16)
            if len(h) < 8: return DEF, SCHWACH, 'Box-Kopf abgeschnitten'
            L = b32(h, 0); t = h[4:8]
            if L == 1: L = struct.unpack('>Q', h[8:16])[0]
            elif L == 0: L = size - i
            if L < 8 or not re.match(rb'^[A-Za-z0-9 \xa9_-]{4}$', t): return DEF, SCHWACH, 'Box ungültig @%d' % i
            boxen.append(t.decode('latin-1')); i += L
    return (OK, SCHWACH, 'Boxen %s; Bilddaten nicht geprüft' % ','.join(boxen[:6])) if i == size else (DEF, SCHWACH, 'Box-Kette endet bei %d' % i)


DVDX = {'vob', 'ifo', 'bup'}


def pruefe(path, ext, size, data, mit_video, mit_dvd=False):
    if ext in VIDX:
        if not mit_video:
            return UEB, KEINE, 'Video – mit --ohne-video übersprungen'
        if ext in DVDX and not mit_dvd:
            return UEB, KEINE, 'DVD-Video (Gunter 29.10.2026: entfällt) – nur mit --mit-dvd'
        if ext == 'vob':
            return chk_vob(path, size)
        if ext in ('m2ts', 'mts'):
            return chk_m2ts(path, 192, 4)
        if ext == 'ts':
            return chk_m2ts(path, 188, 0)
        if ext in ('mpg', 'mpeg'):
            r = chk_vob(path, size)
            return r if r[0] == OK else (NP, KEINE, 'MPEG-PS ohne 2048-Byte-Packs – nicht prüfbar')
        if ext in ('mp4', 'mov', 'm4v', '3gp'):
            return chk_mp4(path, size)
        if ext in ('bup', 'ifo'):
            other = path[:-3] + ('IFO' if ext == 'bup' else 'BUP')
            if os.path.exists(lp(other)):
                with open(lp(other), 'rb') as f: o = f.read()
                return (OK, STARK, 'identisch mit ' + os.path.basename(other)) if o == data else (VER, STARK, 'weicht von %s ab (eine der beiden defekt)' % os.path.basename(other))
            return NP, KEINE, 'Gegenstück IFO/BUP fehlt'
        if ext == 'avi':
            return chk_riff(data) if data is not None else (NP, KEINE, 'zu groß')
        return NP, KEINE, 'Videoformat nicht prüfbar'
    if ext in ZIPX:
        return chk_zip(lp(path) if data is None else data)
    if data is None:
        return NP, KEINE, 'größer als %d MiB – nur SHA-256' % (MAXMEM >> 20)
    if ext in JPGX: return chk_jpeg(data)
    if ext == 'png': return chk_png(data)
    if ext == 'gif': return chk_gif(data)
    if ext == 'pdf': return chk_pdf(data)
    if ext in OLEX: return chk_ole(data, ext)
    if ext == 'dfm' and data[:4] == b'TPF0':
        return NP, KEINE, 'binäres Delphi-Formular – nicht prüfbar'
    if ext in TEXTX: return chk_text(data)
    if ext == 'swf': return chk_swf(data)
    if ext == 'class': return chk_class(data)
    if ext == 'bmp': return chk_bmp(data)
    if ext in ('wav', 'avi', 'ani'): return chk_riff(data)
    if ext in ('tif', 'tiff'): return chk_tiff(data)
    if data[:4] == b'PK\x03\x04': return chk_zip(data)
    if data[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1': return chk_ole(data, ext)
    return NP, KEINE, 'Format ohne Prüfmöglichkeit'


def main():
    ap = argparse.ArgumentParser(description='K-7 Formatprüfung (nur lesen)')
    ap.add_argument('--liste', default=LISTE)
    ap.add_argument('--log-ordner', default=LOGORDNER)
    ap.add_argument('--ohne-video', action='store_true', help='alle Videos überspringen (wie v1.0)')
    ap.add_argument('--mit-dvd', action='store_true', help='DVD-Video vob/ifo/bup zusätzlich prüfen')
    ap.add_argument('--max-dateien', type=int, default=0)
    ap.add_argument('--nur-disc', default='', help='z. B. 2633,2651')
    a = ap.parse_args()
    a.mit_video = not a.ohne_video
    os.makedirs(a.log_ordner, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y-%m-%d_%H%M')
    out = os.path.join(a.log_ordner, 'K7_Formatpruefung_Ergebnis_%s.csv' % ts)
    with open(a.liste, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f, delimiter=';'))
    if a.nur_disc:
        ds = set(a.nur_disc.split(',')); rows = [r for r in rows if r['Disc'] in ds]
    if a.max_dateien:
        rows = rows[:a.max_dateien]
    print('%s | Liste %s | %d Dateien | Pillow: %s | Videos: %s' % (VERSION, a.liste, len(rows), 'ja' if PIL else 'nein', ('ja' if a.mit_video else 'nein') + (' inkl. DVD' if a.mit_dvd else ' ohne DVD')))
    felder = ['Nr', 'Teil', 'Zeile', 'Disc', 'Risiko_Disc', 'Quelle', 'Ziel', 'Bytes', 'Endung', 'SHA256_ok', 'Ergebnis', 'Staerke', 'Detail', 'Sekunden']
    zaehl = Counter(); jeDisc = Counter(); t0 = time.time()
    with open(out, 'w', encoding='utf-8-sig', newline='') as fo:
        w = csv.DictWriter(fo, fieldnames=felder, delimiter=';'); w.writeheader()
        for k, r in enumerate(rows, 1):
            t1 = time.time(); p = r['Quelle']; ext = r['Endung']; size = int(r['Bytes'])
            erg = dict(Nr=r['Nr'], Teil=r['Teil'], Zeile=r['Zeile'], Disc=r['Disc'], Risiko_Disc=r['Risiko_Disc'], Quelle=p, Ziel=r['Ziel'],
                       Bytes=size, Endung=ext, SHA256_ok='', Ergebnis='', Staerke='', Detail='')
            try:
                data = None
                if ext in VIDX and (not a.mit_video or (ext in DVDX and not a.mit_dvd)):
                    res = (UEB, KEINE, 'DVD-Video – entfällt (nur mit --mit-dvd)' if a.mit_video else 'Video – --ohne-video'); shaok = 'nicht gelesen'
                else:
                    h = hashlib.sha256()
                    if size <= MAXMEM:
                        with open(lp(p), 'rb') as f: data = f.read()
                        h.update(data)
                    else:
                        with open(lp(p), 'rb') as f:
                            for blk in iter(lambda: f.read(8 << 20), b''): h.update(blk)
                    shaok = 'ja' if h.hexdigest().lower() == r['SHA256'].lower() else 'NEIN'
                    if shaok == 'NEIN':
                        res = (SHAX, KEINE, 'Quelle seit T0 verändert – nicht geprüft')
                    else:
                        try:
                            res = pruefe(p, ext, size, data, a.mit_video, a.mit_dvd)
                        except (struct.error, IndexError, ValueError, OverflowError, MemoryError) as e:
                            res = (DEF, MITTEL, 'Aufbau nicht lesbar: %s' % str(e)[:120])
            except OSError as e:
                res = (FEH, KEINE, str(e)[:150]); shaok = ''
            erg.update(SHA256_ok=shaok, Ergebnis=res[0], Staerke=res[1], Detail=res[2], Sekunden='%.2f' % (time.time() - t1))
            w.writerow(erg); zaehl[(res[0], res[1])] += 1; jeDisc[(r['Disc'], res[0])] += 1
            if k % 500 == 0:
                fo.flush(); print('  %d / %d  (%.0f s)' % (k, len(rows), time.time() - t0))
    # Zusammenfassung
    zf = out.replace('_Ergebnis_', '_Zusammenfassung_').replace('.csv', '.txt')
    erg_arten = [OK, DEF, VER, NP, UEB, SHAX, FEH]
    with open(zf, 'w', encoding='utf-8') as f:
        f.write('%s | %s | Liste %s | Pillow %s | Videos %s | Laufzeit %.0f s\n\n' % (VERSION, ts, a.liste, 'ja' if PIL else 'nein', ('ja' if a.mit_video else 'nein') + (' inkl. DVD' if a.mit_dvd else ' ohne DVD'), time.time() - t0))
        f.write('Ergebnis / Stärke\n')
        for (e, s), n in sorted(zaehl.items()):
            f.write('  %-15s %-8s %7d\n' % (e, s or '-', n))
        f.write('\nje Disc: ' + ' | '.join(erg_arten) + '\n')
        for d in sorted({d for d, _ in jeDisc}):
            f.write('  %s  ' % d + '  '.join('%6d' % jeDisc[(d, e)] for e in erg_arten) + '\n')
        f.write('\nNächster Schritt: Protokoll an Claude geben. DEFEKT-Dateien werden im Plan auf AUSLASSEN gesetzt (Quelle bleibt in D:\\Archiv_Medien),\n'
                'VERDACHT/NICHT_PRUEFBAR nach Risiko der Disc entschieden. Auf dem Rechner wurde nichts verändert.\n')
    print(open(zf, encoding='utf-8').read())
    print('Protokoll:', out)


if __name__ == '__main__':
    main()
