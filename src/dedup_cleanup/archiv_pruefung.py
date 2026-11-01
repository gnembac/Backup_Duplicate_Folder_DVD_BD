#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
archiv_pruefung.py  Version 1.0 | 21.10.2026 | Firma: privat (IT/Backup) | Projekt: Basisdaten ermitteln
REIN LESEND: dieses Skript verschiebt, kopiert, aendert und loescht NICHTS im Archiv, auf E:\\ oder in der Quarantaene.
Es schreibt nur Berichtsdateien in --bericht (Standard D:\\_Berichte\\<Datum>_Pruefung).

Ergaenzt bereinigung_archiv.py v1.1 um zwei unabhaengige Nachweise:

  nachpruefung  Klaert die 625 "Hash weicht ab"-Meldungen des loesen Kopiechecks (--extern-lose vergleicht nur
                Dateiname+Groesse und hasht EINEN beliebigen Treffer). Hier werden ALLE Kandidaten auf der externen
                Platte mit gleichem Namen und gleicher Groesse gehasht (BLAKE2b-20, wie die Dateiliste).
                Ergebnis je Datei: GLEICH (ein Kandidat ist identisch = Fehlalarm) | ABWEICHEND (Kandidaten da, keiner
                gleich = echte Abweichung) | KEIN_KANDIDAT | MASTER_NICHT_LESBAR.
  inventar      Schreibt (Pfad, Groesse, mtime_ns) aller Dateien unter --root in eine CSV (VOR dem Lauf von
                bereinigung_archiv.py --modus quarantaene).
  pruefen       Vergleicht Archiv NACH dem Lauf mit dem Inventar VOR dem Lauf und der Quarantaene:
                - jede Datei, die im Archiv geblieben ist, ist unveraendert (Groesse, mtime)   -> sonst GEAENDERT
                - jede verschwundene Datei liegt in der Quarantaene mit gleicher Groesse/mtime -> sonst FEHLT
                - keine neuen Dateien im Archiv                                                  -> sonst NEU
                - mit --csv: jede verschobene Datei ist in der Dateiliste ein DUPLIKAT, kein BEHALTEN (Master)
                Exit-Code 0 = alles in Ordnung, 1 = Auffaelligkeiten.

BEISPIELE (PowerShell, Ordner Skripte)
  python archiv_pruefung.py --modus nachpruefung --liste D:\\_Berichte\\2026-10-21_1319_Archiv_Bereinigung\\kopiecheck_fehlt.csv --extern E:\\
  python archiv_pruefung.py --modus inventar --out D:\\_Berichte\\inventar_vorher.csv
  python archiv_pruefung.py --modus pruefen --vorher D:\\_Berichte\\inventar_vorher.csv
Pfadangaben ohne Anfuehrungszeichen und ohne abschliessenden Backslash vor einem Anfuehrungszeichen (E:\\ ohne Anfuehrungszeichen).
"""
import argparse
import collections
import csv
import datetime
import hashlib
import os
import sys

STD_CSV = os.path.join(os.path.expanduser('~'), 'Documents', 'Claude', '180_KI_Basiskontext', '_Bereinigung',
                       'Dateiliste_Master_Duplikate.csv')


def lp(p):
    """Langpfad-Praefix unter Windows (Pfade >= 260 Zeichen)."""
    if os.name == 'nt':
        p = os.path.abspath(p)
        if not p.startswith('\\\\?\\'):
            p = ('\\\\?\\UNC\\' + p[2:]) if p.startswith('\\\\') else ('\\\\?\\' + p)
    return p


def h20(path):
    h = hashlib.blake2b(digest_size=20)
    with open(lp(path), 'rb') as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def walk(root, skip_top=(), fehler=None):
    """Liefert (relativer Pfad, Groesse, mtime_ns) aller Dateien unter root. Nur Lesen."""
    stack = ['']
    while stack:
        rel = stack.pop()
        full = os.path.join(root, rel) if rel else root
        try:
            with os.scandir(lp(full)) as it:
                entries = list(it)
        except OSError as ex:
            if fehler is not None:
                fehler.append((rel or '.', str(ex)))
            continue
        for e in entries:
            name = e.name
            r = os.path.join(rel, name) if rel else name
            try:
                if e.is_dir(follow_symlinks=False):
                    if not rel and name in skip_top:
                        continue
                    stack.append(r)
                elif e.is_file(follow_symlinks=False):
                    st = e.stat(follow_symlinks=False)
                    yield r, st.st_size, st.st_mtime_ns
            except OSError as ex:
                if fehler is not None:
                    fehler.append((r, str(ex)))


def bericht_dir(a, suffix):
    d = a.bericht or os.path.join('D:\\_Berichte' if os.name == 'nt' else os.getcwd(),
                                  datetime.datetime.now().strftime('%Y-%m-%d_%H%M') + '_' + suffix)
    os.makedirs(d, exist_ok=True)
    return d


def schreibe_csv(pfad, kopf, zeilen):
    with open(pfad, 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(kopf)
        w.writerows(zeilen)


# ---------------------------------------------------------------- nachpruefung
def cmd_nachpruefung(a):
    if not a.liste or not a.extern:
        sys.exit('nachpruefung braucht --liste und --extern')
    with open(a.liste, encoding='utf-8-sig', newline='') as fh:
        liste = [r[0] for r in csv.reader(fh, delimiter=';')][1:]
    sep = os.sep
    master = {}
    for rel in liste:
        r = rel.replace('\\', sep)
        try:
            master[rel] = (r, os.stat(lp(os.path.join(a.archiv, r))).st_size)
        except OSError:
            master[rel] = (r, None)
    wanted = {(os.path.basename(r).lower(), s) for r, s in master.values() if s is not None}
    print('Index der externen Platte %s (nur Namen/Groessen, %d gesuchte Schluessel) ...' % (a.extern, len(wanted)))
    kand = collections.defaultdict(list)
    fehler = []
    n = 0
    for r, s, _ in walk(a.extern, skip_top=('$RECYCLE.BIN', 'System Volume Information'), fehler=fehler):
        n += 1
        k = (os.path.basename(r).lower(), s)
        if k in wanted:
            kand[k].append(r)
    print('  %d Dateien auf der externen Platte gelesen, %d nicht lesbare Eintraege' % (n, len(fehler)))
    zeilen = []
    zaehler = collections.Counter()
    for rel in liste:
        r, s = master[rel]
        if s is None:
            zeilen.append([rel, '', '', 0, '', 'MASTER_NICHT_LESBAR'])
            zaehler['MASTER_NICHT_LESBAR'] += 1
            continue
        try:
            mh = h20(os.path.join(a.archiv, r))
        except OSError:
            zeilen.append([rel, s, '', 0, '', 'MASTER_NICHT_LESBAR'])
            zaehler['MASTER_NICHT_LESBAR'] += 1
            continue
        cands = kand.get((os.path.basename(r).lower(), s), [])
        treffer = ''
        for c in cands:
            try:
                if h20(os.path.join(a.extern, c)) == mh:
                    treffer = c
                    break
            except OSError:
                continue
        erg = 'GLEICH' if treffer else ('ABWEICHEND' if cands else 'KEIN_KANDIDAT')
        zaehler[erg] += 1
        zeilen.append([rel, s, mh, len(cands), treffer.replace(sep, '\\'), erg])
    d = bericht_dir(a, 'Nachpruefung_Kopie')
    schreibe_csv(os.path.join(d, 'nachpruefung.csv'),
                 ['Pfad', 'Groesse_Byte', 'Master_Hash', 'Kandidaten_extern', 'Treffer_extern', 'Ergebnis'], zeilen)
    echt = [z for z in zeilen if z[5] != 'GLEICH']
    with open(os.path.join(d, 'korrektur_liste.txt'), 'w', encoding='utf-8') as fh:
        for z in echt:
            fh.write(z[0] + '\n')
    txt = ('Nachpruefung Kopie %s gegen Archiv %s | %s\n'
           'Geprueft: %d | GLEICH (Fehlalarm des losen Modus): %d | ABWEICHEND: %d | KEIN_KANDIDAT: %d | MASTER_NICHT_LESBAR: %d\n'
           'Echte Auffaelligkeiten (korrektur_liste.txt): %d\n'
           'Hinweis: Nur Lesen. Die Platte %s wurde nicht veraendert.\n') % (
        a.extern, a.archiv, datetime.datetime.now().strftime('%d.%m.%Y, %H:%M'), len(liste), zaehler['GLEICH'],
        zaehler['ABWEICHEND'], zaehler['KEIN_KANDIDAT'], zaehler['MASTER_NICHT_LESBAR'], len(echt), a.extern)
    open(os.path.join(d, 'zusammenfassung_nachpruefung.txt'), 'w', encoding='utf-8').write(txt)
    print(txt)
    print('Bericht:', d)
    return 0


# ---------------------------------------------------------------- inventar
def cmd_inventar(a):
    if not a.out:
        sys.exit('inventar braucht --out')
    fehler = []
    zeilen = []
    for r, s, m in walk(a.root, fehler=fehler):
        zeilen.append([r.replace(os.sep, '\\'), s, m])
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    schreibe_csv(a.out, ['Pfad', 'Groesse_Byte', 'mtime_ns'], zeilen)
    print('Inventar: %d Dateien, %d nicht lesbare Eintraege -> %s' % (len(zeilen), len(fehler), a.out))
    return 0


# ---------------------------------------------------------------- pruefen
def lade_inventar(pfad):
    d = {}
    with open(pfad, encoding='utf-8-sig', newline='') as fh:
        rd = csv.reader(fh, delimiter=';')
        next(rd)
        for p, s, m in rd:
            d[p] = (int(s), int(m))
    return d


def scan_dict(root):
    fehler = []
    d = {r.replace(os.sep, '\\'): (s, m) for r, s, m in walk(root, fehler=fehler)}
    return d, fehler


def cmd_pruefen(a):
    if not a.vorher:
        sys.exit('pruefen braucht --vorher')
    V = lade_inventar(a.vorher)
    N, fn = scan_dict(a.root)
    Q, fq = scan_dict(a.quarantaene) if os.path.isdir(a.quarantaene) else ({}, [])
    aktion = {}
    if a.csv and os.path.isfile(a.csv):
        with open(a.csv, encoding='utf-8-sig', newline='') as fh:
            for r in csv.DictReader(fh, delimiter=';'):
                aktion[r['Pfad']] = r['Aktion']
    probleme = []
    ok_verschoben = 0
    master_verschoben = 0
    for p, v in V.items():
        if p in N:
            if N[p] != v:
                probleme.append((p, 'GEAENDERT', 'vorher %s / nachher %s' % (v, N[p])))
        else:
            q = Q.get(p)
            if q is None:
                probleme.append((p, 'FEHLT', 'weder im Archiv noch in der Quarantaene'))
            elif q != v:
                probleme.append((p, 'QUARANTAENE_ABWEICHEND', 'vorher %s / Quarantaene %s' % (v, q)))
            else:
                ok_verschoben += 1
                if aktion:
                    ak = aktion.get(p)
                    if ak is None:
                        probleme.append((p, 'NICHT_IN_LISTE', 'verschoben, aber nicht in der Dateiliste'))
                    elif ak != 'DUPLIKAT':
                        master_verschoben += 1
                        probleme.append((p, 'MASTER_VERSCHOBEN', 'Aktion laut Liste: ' + ak))
    for p in N:
        if p not in V:
            probleme.append((p, 'NEU', 'nicht im Inventar vorher'))
    d = bericht_dir(a, 'Pruefung_Archiv')
    schreibe_csv(os.path.join(d, 'pruefung_probleme.csv'), ['Pfad', 'Befund', 'Detail'], probleme)
    cnt = collections.Counter(b for _, b, _ in probleme)
    txt = ('Pruefung Archiv %s nach dem Lauf | %s\n'
           'Inventar vorher: %d Dateien | Archiv jetzt: %d | Quarantaene (%s): %d\n'
           'Korrekt in die Quarantaene verschoben (gleiche Groesse und mtime): %d\n'
           'Unveraendert im Archiv geblieben: %d\n'
           'Auffaelligkeiten: %d  %s\n'
           'Nicht lesbare Eintraege: Archiv %d, Quarantaene %d\n'
           'Gegenpruefung mit Dateiliste: %s (Master verschoben: %d)\n'
           'Ergebnis: %s\n') % (
        a.root, datetime.datetime.now().strftime('%d.%m.%Y, %H:%M'), len(V), len(N), a.quarantaene, len(Q),
        ok_verschoben, sum(1 for p in V if p in N and N[p] == V[p]), len(probleme), dict(cnt), len(fn), len(fq),
        'ja' if aktion else 'nein (--csv fehlt oder nicht gefunden)', master_verschoben,
        'IN ORDNUNG - kein Master veraendert oder verloren' if not probleme and not fn
        else 'AUFFAELLIGKEITEN - pruefen, nicht loeschen')
    open(os.path.join(d, 'zusammenfassung_pruefung.txt'), 'w', encoding='utf-8').write(txt)
    print(txt)
    print('Bericht:', d)
    return 1 if probleme or fn else 0


def main():
    ap = argparse.ArgumentParser(description='Rein lesende Nachweise zur Archiv-Bereinigung')
    ap.add_argument('--modus', required=True, choices=['nachpruefung', 'inventar', 'pruefen'])
    ap.add_argument('--root', '--archiv', dest='root', default='D:\\2025_02_Backup_all_HDs')
    ap.add_argument('--quarantaene', default='D:\\_Quarantaene\\D03')
    ap.add_argument('--liste', default=None, help='nachpruefung: kopiecheck_fehlt.csv')
    ap.add_argument('--extern', default=None, help='nachpruefung: Wurzel der externen Platte, z. B. E:\\')
    ap.add_argument('--out', default=None, help='inventar: Ausgabe-CSV')
    ap.add_argument('--vorher', default=None, help='pruefen: Inventar-CSV von VOR dem Lauf')
    ap.add_argument('--csv', default=STD_CSV, help='pruefen: Dateiliste_Master_Duplikate.csv (Gegenpruefung)')
    ap.add_argument('--bericht', default=None)
    a = ap.parse_args()
    a.archiv = a.root
    sys.exit({'nachpruefung': cmd_nachpruefung, 'inventar': cmd_inventar, 'pruefen': cmd_pruefen}[a.modus](a))


if __name__ == '__main__':
    main()
