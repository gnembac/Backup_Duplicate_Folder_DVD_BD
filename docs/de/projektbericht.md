# Projektbericht: Datenkonsolidierung und Langzeitarchivierung

**Stand:** 01.11.2026 | **Autor:** Gunter Nembach | **Status der Zahlen:** gemessen (Skriptberichte), sofern nicht anders gekennzeichnet

## 1. Ausgangslage
Daten aus rund 35 Jahren lagen verteilt auf 51 optischen Datenträgern (CD/DVD/BD), einem Alt-Festplattenarchiv (ca. 1 TB), Google Drive, einem Synology-NAS und vier Endgeräten (Windows 11, Ubuntu 24.04, TUXEDO OS). Es gab viele Dubletten, uneinheitliche Ordnerstrukturen, Lesefehler auf Alt-Medien und kein geprüftes Backup (Sync-Spiegel ≠ Backup, kein Restore-Test).

## 2. Ziel
Ein dublettenfreier, hash-geprüfter Gesamtbestand (`D:\Daten`) und eine 3-2-1-Sicherung: NAS + zwei Offline-Sätze M-DISC (einer außer Haus), jede Kopie nachweisbar gleich dem Master.

## 3. Vorgehen
| Phase | Inhalt | Ergebnis (gemessen) |
|---|---|---|
| 1 Alt-Archiv bereinigen | Inventar mit SHA-256, Dubletten in Quarantäne (7 Tage Sperre), Nachprüfung gegen Inventar | 339.345 Dateien inventarisiert, 263.134 byte-identische Dubletten (791,97 GiB) in Quarantäne, 0 Master verändert, nichts gelöscht |
| 2 Alt-Medien prüfen | Ein Befehl je Disc: Inventar (BLAKE2b), Vergleich mit Bestand, Import ungedeckter Dateien, Teilrettung, Bericht | 51 Discs, 193.601 Dateien, 457,64 GiB roh → 245,04 GiB eindeutig; 6.289 stille Lesefehler auf 16 Discs per Querprüfung erkannt |
| 3 Konsolidierung | Schreibgeschützter Snapshot der Live-Ordner, Kopierplan in 8 Teilen (138.584 Zeilen), Hardlinks statt Doppelkopien, Formatprüfung defekter Disc-Dateien | 128.584 Dateien, 336,03 GiB; VollHash-Prüfung 0 Fehler, 0 Abweichungen |
| 4 M-DISC | Brennordner mit Manifest und Redundanzschicht, Prüfkette ORDNER → ISO → Brand aus ISO → ROH (Sektorvergleich) → Register | ISO-Prüfung D3–D6: 117.821 Dateien, 324,27 GiB, 0 Befunde; Brandfehler D2 auf Byte-Ebene aufgeklärt |

## 4. Methodik (QM-Bezug)
- Messmittel vor Einsatz kalibriert (Formatprüfer v1.0 mit 82 % Fehlalarmen; Gegenprobe an 49 intakten PDF: v1.0 31 Fehlalarme, v1.1 0)
- Ursachenanalyse nach Muster 8D: Hypothesen mit vorab festgelegtem Unterscheidungskriterium, Nachweis auf Byte-Ebene
- Lückenlose Nachweise: Inventar vor jeder Massenänderung, Berichte je Lauf, Register nur fortschreibend (append-only)
- Fassungsprinzip: nie umbenennen, jede neue Fassung in einem neuen, versionierten Ordner
- Lessons Learned als fortlaufendes Register (130+ Einträge), daraus Regeln für Werkzeuge und Ablauf

## 5. Vorläufer
Phase 1 (Juli 2026): [gnembac/HDD_Duplicate_sort](https://github.com/gnembac/HDD_Duplicate_sort) – Inventar verschachtelter Backup-Ordner in SQLite, Dubletten per BLAKE2b, Bildvarianten, Strukturvorschlag. Dieses Repository ist Phase 2.

## 6. Rolle
Anforderungen, Risikoregeln, Abnahmekriterien, Testdesign, Ausführung auf Windows-Hardware, Auswertung aller Berichte und sämtliche Entscheidungen: Gunter Nembach. Programmierung im Mensch-KI-Paar mit Claude (Anthropic).

## 7. Offene Punkte (Stand 01.11.2026)
Brand der Discs D2 (Neubrand) bis D6 ab 03.11.2026, NAS-Kopie des Bestands, Satz B außer Haus, Restore-Test.
