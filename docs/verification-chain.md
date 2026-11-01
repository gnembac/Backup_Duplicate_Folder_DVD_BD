# M-DISC verification chain

| Stage | Tool / switch | What is compared | Pass criterion |
|---|---|---|---|
| Plan | `mdisc_brennliste --disc n` | copy plan rows → disc assignment, redundancy layer, name/path limits (name ≤ 127 UTF-16, path ≤ 240, label ≤ 15) | no collision, no residual over-long path, all hashes known |
| Burn folder | `mdisc_brennliste --disc n --ausfuehren` | hardlinks into `D:\_MDISC\D<n>_V<k>`, files re-hashed against plan SHA-256, manifests written | `BRENNBEREIT (0 Abweichungen)` |
| ORDNER | `mdisc_pruefen --stufe ORDNER` | every manifest row read and hashed in the burn folder | OK = manifest rows, all other classes 0 |
| ISO | `mdisc_pruefen --stufe ISO --image … --label-soll …` | mounted ISO vs. its manifest; volume label | `BESTANDEN`, label equal |
| Burn | CDBurnerXP → *Burn ISO image* (never "Burn" from the compilation), program verify off | – | – |
| ROH | `mdisc_pruefen --stufe ROH --iso …` (admin) | raw sector read of the disc vs. ISO up to the UDF partition end | bit-identical; gaps and differing sectors listed separately |
| Root cause | `mdisc_sektorvergleich` | each differing sector mapped to UDF file extents → `NACH_EOF`, `DATEN`, `FREI`, `UNKLAR` | no `DATEN` sectors |
| Register | `mdisc_pruefen --stufe REGISTER` | append-only CSV row per verified disc; corrections as additional `UNGUELTIG` rows | – |

Measured on 01.11.2026 (Windows 11, Python 3.12): ISO stage for discs D3–D6 — 117,821 files, 324.27 GiB, 0 findings in every class; throughput 119–576 MB/s depending on file count.

Known limits: the ISO stage verifies the image against the manifest stored *inside* the image; which burn-folder version produced the image is inferred (file name, timestamps, content of known deviations), not yet checked by comparing the manifest hash of image and folder.
