#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Archiv-Bereinigung D:\\2025_02_Backup_all_HDs anhand der Dateiliste_Master_Duplikate.csv (Stand 19.10.2026)

Version 1.1 | 20.10.2026 | Firma: privat (IT/Backup) | Massnahmen D-01, D-03 (Bereinigungsvorschlag Gesamt)
Aenderung v1.1: Wartezeit vor "leeren" (Standard 7 Tage, Marker _QUARANTAENE_START.json); Schutztor kann durch eine
dokumentierte Nutzerangabe ersetzt werden (--extern-nutzerangabe); Bericht nennt das fruehestmoegliche Loeschdatum.

WAS DAS SKRIPT TUT
  Die CSV enthaelt je Datei die Aktion BEHALTEN (Master) oder DUPLIKAT, dazu BLAKE2b-20-Hash (40 Hex-Zeichen),
  Groesse und Master-Pfad. Pfade sind relativ zum Archiv. Dateien mit eindeutiger Groesse tragen keinen Hash.
  Geprueft am 20.10.2026 (Claude, nur lesend): 338.976 Zeilen, 263.134 DUPLIKAT (791,97 GiB), 75.842 BEHALTEN
  (269,14 GiB), 57.924 Hash-Gruppen mit genau einem BEHALTEN, kein Master ist selbst DUPLIKAT, alle Master-Pfade
  vorhanden in der Liste, Hash und Groesse von Duplikat und Master stimmen ueberein.

  WICHTIG (Korrektur zum Vorschlag vom 19.10.): Die Ordner Bilder_kpl_Original_10_2015 (34 Master, 0,14 GiB) und
  <Ereignisordner> (Beispiel: 2.360 Master, 9,70 GiB) enthalten Master-Dateien. Sie duerfen daher NICHT als ganze Ordner
  verschoben werden. Dieses Skript verschiebt ausschliesslich DUPLIKAT-Zeilen; Master bleiben immer liegen.

MODI (--modus)
  report       Standard. Aendert nichts. Prueft CSV-Invarianten, Existenz und Groesse (mit --verifikation voll
               zusaetzlich den Hash von Duplikat und Master) und schreibt Berichte.
  quarantaene  Schutztor: nur mit bestandenem kopiecheck (gleiche Dateiliste, fehlen = 0, Stichprobe ohne Abweichung).
               Verschiebt jedes verifizierte DUPLIKAT nach <Quarantaene>\\<relativer Pfad> (gleiche Partition:
               nur Umbenennen, belegt keinen Platz) und entfernt danach leere Ordner im Archiv.
  kopiecheck   Prueft, ob alle BEHALTEN-Dateien auf einem externen Laufwerk vorhanden sind (--extern).
               Nur Lesen. Mit --extern-lose: Vergleich ueber Dateiname+Groesse, egal in welchem Unterordner.
  leeren       Loescht die Quarantaene endgueltig. Nur mit --bestaetigung LOESCHEN und erst nach der Wartezeit
               (--wartetage, Standard 7 Tage seit der letzten Verschiebung; Marker <Quarantaene>\\_QUARANTAENE_START.json).

BEISPIELE (PowerShell)
  python bereinigung_archiv.py                                   # 1. Trockenlauf mit Hash-Pruefung (ca. 10-40 Min.)
  python bereinigung_archiv.py --modus kopiecheck --extern L:\\ --extern-lose
  python bereinigung_archiv.py --modus quarantaene --nur-ordner 27122014_bckp_bilder --max-aktionen 200   # Pilot (braucht bestandenen kopiecheck)
  python bereinigung_archiv.py --modus quarantaene               # alles
  python bereinigung_archiv.py --modus quarantaene --extern-nutzerangabe "Kopie des Archivs auf externen Laufwerken (Gunter 20.10.2026)"
                                                                 # Schutztor durch dokumentierte Nutzerangabe ersetzt (wird im Bericht vermerkt)
  python bereinigung_archiv.py --modus quarantaene --ohne-kopiecheck   # NUR bewusst ohne jeden Nachweis der externen Kopie
  python bereinigung_archiv.py --modus leeren --bestaetigung LOESCHEN

Sicherheitsprinzip: Es wird nie ein Master angefasst; jedes Duplikat wird vor dem Verschieben gegen CSV-Groesse (und bei
--verifikation voll gegen CSV-Hash) und gegen den Master geprueft. Fehlt der Master oder weicht er ab, bleibt das
Duplikat liegen. Es werden keine Dateiinhalte ausgegeben.
"""
import argparse
import collections
import concurrent.futures
import csv
import datetime
import hashlib
import json
import os
import random
import shutil
import stat
import sys
import threading
import time

try:
    sys.stdout.reconfigure(errors='replace')
    sys.stderr.reconfigure(errors='replace')
except Exception:  # noqa
    pass

GIB = 2 ** 30
JUNK_NAMES = {'thumbs.db', 'desktop.ini', '.picasa.ini'}


def lp(path):
    """Langpfad-Praefix unter Windows (Pfade ab 240 Zeichen)."""
    if os.name == 'nt':
        p = os.path.abspath(path)
        if len(p) >= 240 and not p.startswith('\\\\?\\'):
            if p.startswith('\\\\'):
                return '\\\\?\\UNC\\' + p[2:]
            return '\\\\?\\' + p
        return p
    return path


def P(base, rel):
    """Basis + relativer CSV-Pfad (Backslash- oder Slash-getrennt) -> Pfad des laufenden Systems."""
    return os.path.join(base, *[x for x in rel.replace('/', '\\').split('\\') if x])


def b2(path):
    h = hashlib.blake2b(digest_size=20)
    with open(lp(path), 'rb') as fh:
        while True:
            b = fh.read(4 * 1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def is_junk(rel, size):
    base = rel.replace('/', '\\').split('\\')[-1].lower()
    return base in JUNK_NAMES or base.startswith('~$') or base.endswith('.tmp')


def gib(x):
    return '%.2f GiB' % (x / GIB)


def write_csv(path, header, rows):
    with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(header)
        w.writerows(rows)


def load_csv(path):
    rows = []
    with open(path, encoding='utf-8-sig', newline='') as fh:
        for x in csv.DictReader(fh, delimiter=';'):
            rows.append({'akt': x['Aktion'], 'rel': x['Pfad'], 'size': int(x['Groesse_Bytes']),
                         'hash': x['Hash'], 'master': x['Master_Pfad'], 'n': x['Anzahl_Kopien']})
    return rows


def check_invariants(rows):
    """Interne Konsistenz der Liste; liefert Liste von Fehlertexten."""
    err = []
    by_rel = {r['rel']: r for r in rows}
    keep_per_hash = collections.Counter(r['hash'] for r in rows if r['akt'] == 'BEHALTEN' and r['hash'])
    for r in rows:
        if r['akt'] not in ('BEHALTEN', 'DUPLIKAT'):
            err.append('Unbekannte Aktion: ' + r['akt'] + ' ' + r['rel'])
        if r['akt'] == 'DUPLIKAT':
            m = by_rel.get(r['master'])
            if m is None:
                err.append('Master fehlt in Liste: ' + r['rel'])
            elif m['akt'] != 'BEHALTEN':
                err.append('Master ist selbst DUPLIKAT: ' + r['rel'])
            elif m['hash'] != r['hash'] or m['size'] != r['size']:
                err.append('Master weicht ab (Hash/Groesse): ' + r['rel'])
            if not r['hash']:
                err.append('DUPLIKAT ohne Hash: ' + r['rel'])
    for h, n in keep_per_hash.items():
        if n != 1:
            err.append('Hash-Gruppe mit %d Mastern: %s' % (n, h))
    return err


MARKER = '_QUARANTAENE_START.json'


def write_marker(quar, heute, n, nbytes, gate_note):
    """Marker im Quarantaene-Ordner: erste/letzte Verschiebung (Grundlage der Wartezeit vor 'leeren')."""
    mp = os.path.join(quar, MARKER)
    erste = heute.isoformat()
    summe, sb = n, nbytes
    try:
        old = json.load(open(mp, encoding='utf-8'))
        erste = old.get('erste_verschiebung', erste)
        summe += old.get('verschoben_gesamt', 0)
        sb += old.get('bytes_gesamt', 0)
    except (OSError, ValueError):
        pass
    try:
        os.makedirs(quar, exist_ok=True)
        json.dump({'erste_verschiebung': erste, 'letzte_verschiebung': heute.isoformat(), 'verschoben_gesamt': summe,
                   'bytes_gesamt': sb, 'schutztor': gate_note}, open(mp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    except OSError as e:
        print('WARNUNG: Marker nicht geschrieben (Wartezeit dann nicht pruefbar):', e)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    home = os.path.expanduser('~')
    ap.add_argument('--csv', default=os.path.join(home, 'Documents', 'Claude', '180_KI_Basiskontext', '_Bereinigung',
                                                  'Dateiliste_Master_Duplikate.csv'))
    ap.add_argument('--archiv', default='D:\\2025_02_Backup_all_HDs')
    ap.add_argument('--quarantaene', default='D:\\_Quarantaene\\D03')
    ap.add_argument('--bericht', default=None)
    ap.add_argument('--modus', choices=['report', 'quarantaene', 'kopiecheck', 'leeren'], default='report')
    ap.add_argument('--verifikation', choices=['meta', 'voll'], default='voll',
                    help='meta = Existenz+Groesse; voll = zusaetzlich BLAKE2b-20-Hash von Duplikat und Master (Standard)')
    ap.add_argument('--threads', type=int, default=4)
    ap.add_argument('--max-aktionen', type=int, default=0, help='Obergrenze fuer Verschiebungen (Pilotlauf), 0 = unbegrenzt')
    ap.add_argument('--nur-ordner', default='', help='Nur Duplikate in diesen Top-Level-Ordnern (Komma-getrennt)')
    ap.add_argument('--auch-muell', action='store_true',
                    help='zusaetzlich BEHALTEN-Datenmuell (Thumbs.db, desktop.ini, ~$*, *.tmp, .picasa.ini) verschieben (D-01)')
    ap.add_argument('--extern', default=None, help='Wurzel der externen Kopie (Modus kopiecheck)')
    ap.add_argument('--extern-lose', action='store_true', help='kopiecheck ueber Dateiname+Groesse statt ueber den relativen Pfad')
    ap.add_argument('--hash-stichprobe', type=int, default=200, help='kopiecheck: Anzahl Stichproben-Hashes (Standard 200)')
    ap.add_argument('--bestaetigung', default='', help='fuer Modus leeren: LOESCHEN')
    ap.add_argument('--kopiecheck-datei', default=None,
                    help='Ergebnisdatei des letzten kopiecheck (Standard: <Berichtswurzel>\\kopiecheck_letzter.json)')
    ap.add_argument('--max-fehlend', type=int, default=0, help='Schutztor: erlaubte Anzahl fehlender Master im kopiecheck (Standard 0)')
    ap.add_argument('--ohne-kopiecheck', action='store_true',
                    help='NUR bewusst: Schutztor umgehen (Modus quarantaene ohne bestandenen kopiecheck)')
    ap.add_argument('--extern-nutzerangabe', default='',
                    help='Schutztor durch eine dokumentierte Nutzerangabe ersetzen (Text wird in Bericht und Marker geschrieben)')
    ap.add_argument('--wartetage', type=int, default=7,
                    help='Modus leeren: Mindestwartezeit seit der letzten Verschiebung in die Quarantaene (Standard 7; 0 = keine)')
    ap.add_argument('--heute', default=None, help='JJJJ-MM-TT (nur fuer Tests)')
    a = ap.parse_args()

    heute = datetime.date.fromisoformat(a.heute) if a.heute else datetime.date.today()
    gate_note = ''
    stamp = time.strftime('%Y-%m-%d_%H%M')
    rep = a.bericht or os.path.join('D:\\_Berichte' if os.path.isdir('D:\\') else home, stamp + '_Archiv_Bereinigung')
    os.makedirs(rep, exist_ok=True)
    ber_root = 'D:\\_Berichte' if os.path.isdir('D:\\') else home
    kc_file = a.kopiecheck_datei or os.path.join(ber_root, 'kopiecheck_letzter.json')
    arch = os.path.abspath(a.archiv)
    quar = os.path.abspath(a.quarantaene)
    print('Modus        :', a.modus)
    print('Archiv       :', arch)
    print('Quarantaene  :', quar)
    print('Bericht      :', rep)

    if a.modus == 'leeren':
        if not os.path.isdir(quar):
            sys.exit('Quarantaene nicht vorhanden: ' + quar)
        if a.wartetage > 0:
            try:
                mk = json.load(open(os.path.join(quar, MARKER), encoding='utf-8'))
                letzte = datetime.date.fromisoformat(mk['letzte_verschiebung'])
            except (OSError, ValueError, KeyError):
                sys.exit('ABBRUCH: Marker %s fehlt oder ist unlesbar - Wartezeit nicht pruefbar. '
                         'Nur bei bewusster Entscheidung: --wartetage 0' % os.path.join(quar, MARKER))
            frei = letzte + datetime.timedelta(days=a.wartetage)
            if heute < frei:
                sys.exit('ABBRUCH: Wartezeit %d Tage seit der letzten Verschiebung (%s) - fruehestens %s.' % (
                    a.wartetage, letzte.strftime('%d.%m.%Y'), frei.strftime('%d.%m.%Y')))
            print('Wartezeit    : %d Tage seit %s erfuellt' % (a.wartetage, letzte.strftime('%d.%m.%Y')))
        if a.bestaetigung != 'LOESCHEN':
            sys.exit('Abbruch: zum endgueltigen Loeschen --bestaetigung LOESCHEN angeben.')
        n = 0
        tot = 0
        for dp, dn, fn in os.walk(quar):
            for f in fn:
                n += 1
                try:
                    tot += os.path.getsize(lp(os.path.join(dp, f)))
                except OSError:
                    pass
        print('Loesche %d Dateien (%s) in %s ...' % (n, gib(tot), quar), flush=True)

        def _onerr(func, path, exc):
            try:
                os.chmod(path, stat.S_IWRITE)
                func(path)
            except Exception as e:  # noqa
                print('  Fehler:', path, e)
        shutil.rmtree(lp(quar), onerror=_onerr)
        print('Fertig.')
        return

    if not os.path.isfile(a.csv):
        sys.exit('CSV nicht gefunden: ' + a.csv)
    if not os.path.isdir(arch):
        sys.exit('Archiv nicht gefunden: ' + arch)
    t0 = time.time()
    rows = load_csv(a.csv)
    dups_all = [r for r in rows if r['akt'] == 'DUPLIKAT']
    keeps = [r for r in rows if r['akt'] == 'BEHALTEN']
    print('CSV          : %d Zeilen, %d DUPLIKAT (%s), %d BEHALTEN (%s)' % (
        len(rows), len(dups_all), gib(sum(r['size'] for r in dups_all)), len(keeps), gib(sum(r['size'] for r in keeps))))
    err = check_invariants(rows)
    print('Invarianten  : %s' % ('OK' if not err else '%d FEHLER (siehe invarianten_fehler.txt)' % len(err)))
    if err:
        with open(os.path.join(rep, 'invarianten_fehler.txt'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(err[:5000]))
        sys.exit('Abbruch: die Liste ist nicht konsistent. Nichts wurde geaendert.')
    by_rel = {r['rel']: r for r in rows}

    # ------------------------------------------------------------- kopiecheck
    if a.modus == 'kopiecheck':
        if not a.extern or not os.path.isdir(a.extern):
            sys.exit('--extern <Ordner der externen Kopie> angeben (muss existieren).')
        ext = os.path.abspath(a.extern)
        idx = None
        if a.extern_lose:
            print('Indexiere externe Kopie (Dateiname+Groesse) ...', flush=True)
            idx = {}
            nfiles = 0
            for dp, dn, fn in os.walk(ext):
                for f in fn:
                    try:
                        idx.setdefault((f.lower(), os.path.getsize(lp(os.path.join(dp, f)))), os.path.join(dp, f))
                        nfiles += 1
                    except OSError:
                        pass
            print('  extern: %d Dateien' % nfiles)
        missing, diff, ok = [], [], 0
        for r in keeps:
            if idx is not None:
                key = (r['rel'].replace('/', '\\').split('\\')[-1].lower(), r['size'])
                if key in idx:
                    ok += 1
                else:
                    missing.append((r['rel'], r['size'], 'nicht gefunden (Name+Groesse)'))
            else:
                p = P(ext, r['rel'])
                try:
                    s = os.path.getsize(lp(p))
                except OSError:
                    missing.append((r['rel'], r['size'], 'fehlt'))
                    continue
                if s != r['size']:
                    diff.append((r['rel'], r['size'], 'Groesse extern %d' % s))
                else:
                    ok += 1
        # Stichproben-Hash (Inhaltsvergleich Archiv <-> externe Kopie)
        hash_bad = []
        n_hash = 0
        if a.hash_stichprobe:
            pairs = []
            for r in keeps:
                if r['size'] <= 0:
                    continue
                if idx is not None:
                    q = idx.get((r['rel'].replace('/', '\\').split('\\')[-1].lower(), r['size']))
                else:
                    q = P(ext, r['rel'])
                    if not os.path.exists(lp(q)):
                        q = None
                if q:
                    pairs.append((r, q))
            random.seed(20261020)
            for r, q in random.sample(pairs, min(a.hash_stichprobe, len(pairs))):
                n_hash += 1
                try:
                    if b2(P(arch, r['rel'])) != b2(q):
                        hash_bad.append((r['rel'], r['size'], 'Hash weicht ab'))
                except OSError as e:
                    hash_bad.append((r['rel'], r['size'], 'Lesefehler ' + str(e)))
        write_csv(os.path.join(rep, 'kopiecheck_fehlt.csv'), ['Pfad', 'Groesse_Byte', 'Befund'], missing + diff + hash_bad)
        s = [
            'Kopiecheck BEHALTEN-Dateien (Master) gegen %s | %s' % (ext, time.strftime('%d.%m.%Y, %H:%M')),
            'Master gesamt: %d (%s) | vorhanden: %d | fehlen: %d (%s) | Groesse abweichend: %d | Hash-Stichprobe: %d geprueft, %d abweichend' % (
                len(keeps), gib(sum(r['size'] for r in keeps)), ok, len(missing), gib(sum(x[1] for x in missing)), len(diff), n_hash, len(hash_bad)),
            ('Hinweis: loser Modus = Treffer nur nach Dateiname+Groesse; Inhalt nur in der Hash-Stichprobe geprueft.' if idx is not None else 'Modus: relativer Pfad+Groesse; Inhalt in der Hash-Stichprobe geprueft.'),
            'Bewertung: Duplikate duerfen erst verschoben/geloescht werden, wenn "fehlen" = 0 oder die fehlenden Master bewusst akzeptiert sind.',
        ]
        open(os.path.join(rep, 'zusammenfassung_kopiecheck.txt'), 'w', encoding='utf-8').write('\n'.join(s) + '\n')
        print('\n'.join(s))
        erg = {'datum': time.strftime('%Y-%m-%d %H:%M'), 'extern': ext, 'csv': os.path.abspath(a.csv),
               'csv_bytes': os.path.getsize(a.csv), 'csv_mtime': int(os.path.getmtime(a.csv)),
               'master_gesamt': len(keeps), 'vorhanden': ok, 'fehlen': len(missing), 'groesse_abweichend': len(diff),
               'hash_geprueft': n_hash, 'hash_abweichend': len(hash_bad), 'lose': bool(idx is not None)}
        try:
            os.makedirs(os.path.dirname(os.path.abspath(kc_file)), exist_ok=True)
            json.dump(erg, open(kc_file, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
            json.dump(erg, open(os.path.join(rep, 'kopiecheck_ergebnis.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
            print('Ergebnisdatei :', kc_file)
        except OSError as e:
            print('WARNUNG: Ergebnisdatei nicht geschrieben:', e)
        return

    # ------------------------------------------------------------- report / quarantaene
    nur = {x.strip().lower() for x in a.nur_ordner.split(',') if x.strip()}
    dups = [r for r in dups_all if not nur or r['rel'].replace('/', '\\').split('\\')[0].lower() in nur]
    muell = []
    if a.auch_muell:
        muell = [r for r in keeps if is_junk(r['rel'], r['size']) and (not nur or r['rel'].split('\\')[0].lower() in nur)]
    print('Kandidaten   : %d Duplikate (%s)%s' % (len(dups), gib(sum(r['size'] for r in dups)),
                                                  ', %d Muell-Master' % len(muell) if muell else ''))
    if a.max_aktionen:
        print('Pilot        : hoechstens %d Aktionen' % a.max_aktionen)

    if a.modus == 'quarantaene':
        gate_ok, gate_msg = False, ''
        try:
            g = json.load(open(kc_file, encoding='utf-8'))
            same_csv = (g.get('csv_bytes') == os.path.getsize(a.csv) and g.get('csv_mtime') == int(os.path.getmtime(a.csv)))
            if not same_csv:
                gate_msg = 'kopiecheck wurde mit einer anderen Dateiliste ausgefuehrt'
            elif g.get('fehlen', 1) > a.max_fehlend or g.get('groesse_abweichend', 1) > 0 or g.get('hash_abweichend', 1) > 0:
                gate_msg = 'kopiecheck NICHT bestanden: fehlen=%s, Groesse abweichend=%s, Hash abweichend=%s (erlaubt fehlend: %d)' % (
                    g.get('fehlen'), g.get('groesse_abweichend'), g.get('hash_abweichend'), a.max_fehlend)
            else:
                gate_ok = True
                gate_note = 'kopiecheck bestanden (%s, extern %s, fehlen %s)' % (g.get('datum'), g.get('extern'), g.get('fehlen'))
                print('Schutztor    : kopiecheck bestanden (%s, extern %s, %d Master, fehlen %d)' % (
                    g.get('datum'), g.get('extern'), g.get('master_gesamt', 0), g.get('fehlen', 0)))
        except (OSError, ValueError):
            gate_msg = 'kein kopiecheck-Ergebnis gefunden (%s)' % kc_file
        if not gate_ok:
            if a.extern_nutzerangabe.strip():
                gate_note = 'ersetzt durch Nutzerangabe: ' + a.extern_nutzerangabe.strip()
                print('Schutztor    : %s (%s)' % (gate_note, gate_msg))
            elif a.ohne_kopiecheck:
                gate_note = 'UMGANGEN (--ohne-kopiecheck): ' + gate_msg
                print('WARNUNG      : Schutztor umgangen (--ohne-kopiecheck): %s' % gate_msg)
            else:
                sys.exit('ABBRUCH (Schutztor): %s.\nErst: --modus kopiecheck --extern <Laufwerk:\\Pfad>; oder Nutzerangabe dokumentieren: --extern-nutzerangabe "Text"; ohne jeden Nachweis: --ohne-kopiecheck.' % gate_msg)

    master_cache = {}
    lock = threading.Lock()

    def master_ok(mrel, msize, mhash):
        key = mrel
        with lock:
            c = master_cache.get(key)
        if c is not None:
            return c
        mp = P(arch, mrel)
        res = 'ok'
        try:
            if os.path.getsize(lp(mp)) != msize:
                res = 'Master-Groesse weicht ab'
            elif a.verifikation == 'voll' and b2(mp) != mhash:
                res = 'Master-Hash weicht ab'
        except OSError:
            res = 'Master fehlt'
        with lock:
            master_cache[key] = res
        return res

    def verify(r):
        p = P(arch, r['rel'])
        try:
            if os.path.getsize(lp(p)) != r['size']:
                return r, 'Groesse weicht ab'
        except OSError:
            try:
                if os.path.getsize(lp(P(quar, r['rel']))) == r['size']:
                    return r, 'schon_verschoben'
            except OSError:
                pass
            return r, 'Datei fehlt'
        m = by_rel[r['master']]
        mr = master_ok(m['rel'], m['size'], m['hash'])
        if mr != 'ok':
            return r, mr
        if a.verifikation == 'voll':
            try:
                if b2(p) != r['hash']:
                    return r, 'Hash weicht ab'
            except OSError as e:
                return r, 'Lesefehler ' + str(e)
        return r, 'ok'

    actions, problems = [], []
    n_ok = n_prob = n_skip = 0
    bytes_ok = 0
    moved_any = set()

    def do_move(r):
        src = P(arch, r['rel'])
        dst = P(quar, r['rel'])
        if os.path.exists(lp(dst)):
            return 'Ziel existiert bereits'
        os.makedirs(lp(os.path.dirname(dst)), exist_ok=True)
        shutil.move(lp(src), lp(dst))
        return 'verschoben'

    CH = 400
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, a.threads)) as ex:
        i = 0
        stop = False
        while i < len(dups) and not stop:
            chunk = dups[i:i + CH]
            i += CH
            for r, res in ex.map(verify, chunk):
                done += 1
                if res == 'schon_verschoben':
                    n_skip += 1
                    continue
                if res != 'ok':
                    n_prob += 1
                    problems.append((r['rel'], r['size'], res))
                    continue
                if a.modus == 'quarantaene':
                    if a.max_aktionen and n_ok >= a.max_aktionen:
                        stop = True
                        break
                    try:
                        out = do_move(r)
                    except Exception as e:  # noqa
                        out = 'FEHLER ' + str(e)
                    actions.append((r['rel'], out, P(quar, r['rel'])))
                    if out == 'verschoben':
                        n_ok += 1
                        bytes_ok += r['size']
                        moved_any.add(os.path.dirname(P(arch, r['rel'])))
                    else:
                        n_prob += 1
                        problems.append((r['rel'], r['size'], out))
                else:
                    n_ok += 1
                    bytes_ok += r['size']
            if done % 5000 < CH:
                print('  geprueft %d/%d | ok %d | Probleme %d | %.0f s' % (done, len(dups), n_ok, n_prob, time.time() - t0), flush=True)

    if a.modus == 'quarantaene' and muell:
        for r in muell:
            if a.max_aktionen and n_ok >= a.max_aktionen:
                break
            try:
                if os.path.getsize(lp(P(arch, r['rel']))) != r['size']:
                    problems.append((r['rel'], r['size'], 'Muell: Groesse weicht ab'))
                    continue
                out = do_move(r)
            except Exception as e:  # noqa
                out = 'FEHLER ' + str(e)
            actions.append((r['rel'], 'Muell ' + out, P(quar, r['rel'])))
            if out == 'verschoben':
                n_ok += 1
                bytes_ok += r['size']

    if a.modus == 'quarantaene' and n_ok:
        write_marker(quar, heute, n_ok, bytes_ok, gate_note)
    removed_dirs = 0
    if a.modus == 'quarantaene' and n_ok:
        for dp, dn, fn in os.walk(arch, topdown=False):
            if os.path.abspath(dp) == arch:
                continue
            try:
                if not os.listdir(lp(dp)):
                    os.rmdir(lp(dp))
                    removed_dirs += 1
            except OSError:
                pass

    # Berichte
    write_csv(os.path.join(rep, 'probleme.csv'), ['Pfad', 'Groesse_Byte', 'Befund'], problems)
    if actions:
        write_csv(os.path.join(rep, 'aktionen.csv'), ['Pfad', 'Ergebnis', 'Ziel'], actions)
    inst_keep = [(r['rel'], r['size']) for r in keeps if r['rel'].lower().endswith(('.exe', '.msi', '.dmg'))]
    write_csv(os.path.join(rep, 'installer_behalten.csv'), ['Pfad', 'Groesse_Byte'], inst_keep)
    junk_keep = [(r['rel'], r['size']) for r in keeps if is_junk(r['rel'], r['size'])]
    write_csv(os.path.join(rep, 'muell_behalten.csv'), ['Pfad', 'Groesse_Byte'], junk_keep)
    zero = [(r['rel'], 0) for r in rows if r['size'] == 0]
    write_csv(os.path.join(rep, 'null_byte.csv'), ['Pfad', 'Groesse_Byte'], zero)
    s = [
        'Archiv-Bereinigung | %s | Modus %s | Verifikation %s | %.0f s' % (time.strftime('%d.%m.%Y, %H:%M'), a.modus, a.verifikation, time.time() - t0),
        'Kandidaten: %d Duplikate | %s: %d ok (%s) | Probleme: %d (probleme.csv)' % (
            len(dups), 'verschoben' if a.modus == 'quarantaene' else 'verifiziert', n_ok, gib(bytes_ok), n_prob),
        'Bereits frueher verschoben (in Quarantaene gefunden): %d | Leere Ordner entfernt: %d' % (n_skip, removed_dirs),
        'Erwartet nach vollstaendigem Lauf (ohne --auch-muell, ohne --nur-ordner): 75.842 Dateien / 269,14 GiB im Archiv (Master); Abweichung = Probleme, Pilotlauf oder Filter.',
        ('Schutztor: ' + gate_note) if gate_note else 'Schutztor: nicht erforderlich (Modus %s)' % a.modus,
        ('Endgueltiges Loeschen fruehestens: %s (%d Tage Wartezeit; --modus leeren --bestaetigung LOESCHEN)' % (
            (heute + datetime.timedelta(days=a.wartetage)).strftime('%d.%m.%Y'), a.wartetage)) if (a.modus == 'quarantaene' and n_ok) else 'Keine Verschiebung in diesem Lauf.',
        'Zur manuellen Pruefung: installer_behalten.csv (%d), muell_behalten.csv (%d), null_byte.csv (%d)' % (len(inst_keep), len(junk_keep), len(zero)),
    ]
    open(os.path.join(rep, 'zusammenfassung.txt'), 'w', encoding='utf-8').write('\n'.join(s) + '\n')
    print('\n'.join(s))
    print('Berichte in:', rep)


if __name__ == '__main__':
    main()
