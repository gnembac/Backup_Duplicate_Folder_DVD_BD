#!/usr/bin/env bash
# medien_image_ddrescue v1.0 (27.10.2026) - Disc -> ISO-Image + Mapfile mit GNU ddrescue (Ubuntu), zeitbegrenzt, fortsetzbar.
# Anlass: Disc 2614 (und 2604/2607/2608/2610/2611): Direktlesen unter Windows zu langsam bzw. fehlerhaft.
# Vorgehen nach GNU-ddrescue-Handbuch, Kap. 10 "Copying CD-ROMs and DVDs" (Beispiel 1):
#   Pass 1:  ddrescue -n -b2048 DEV image mapfile        (gute Bereiche zuerst, kein Scraping)
#   Pass 2:  ddrescue -d -r1 -b2048 DEV image mapfile    (Direktzugriff, 1 Wiederholung der schlechten Sektoren)
# Aufruf:   sudo ./medien_image_ddrescue_v1.0.sh 2614 [ZIELORDNER] [GERAET]
#   ZIELORDNER  Standard ~/medien_images. Auf der NTFS-Datenpartition (D:) nur, wenn Windows vorher NEU GESTARTET (nicht
#               heruntergefahren) wurde (Schnellstart, K-36); sonst zuerst auf ext4 und spaeter kopieren.
#   GERAET      Standard: automatisch (einziges /dev/sr*)
# Umgebung:  MAXH_P1=6  MAXH_P2=3  (Stunden je Pass)   NOSTOP_MIN=30 (Abbruch, wenn so lange kein Sektor gelesen wurde)
#            SPEED=4 (optional: Laufwerk drosseln, eject -x; langsameres Lesen ist bei alten Discs oft zuverlaessiger)
# Wiederholter Aufruf mit gleicher Nummer setzt anhand der Mapfile fort (nichts wird neu gelesen, was schon sicher gelesen ist).
set -u
NR="${1:-}"; ZIEL="${2:-}"; DEV="${3:-}"
MAXH_P1="${MAXH_P1:-6}"; MAXH_P2="${MAXH_P2:-3}"; NOSTOP_MIN="${NOSTOP_MIN:-30}"; SPEED="${SPEED:-}"
die() { echo "FEHLER: $*" >&2; exit 2; }
[[ "$NR" =~ ^[0-9]{4}$ ]] || die "Aufruf: sudo $0 JJNN [ZIELORDNER] [GERAET]   (JJNN = Disc-Nummer, z. B. 2614)"
command -v ddrescue >/dev/null 2>&1 || die "ddrescue fehlt:  sudo apt install gddrescue"
command -v ddrescuelog >/dev/null 2>&1 || die "ddrescuelog fehlt (Paket gddrescue)"
H="${HOME:-/root}"; if [[ -n "${SUDO_USER:-}" ]]; then H="$(getent passwd "$SUDO_USER" | cut -d: -f6)"; fi
[[ -n "$ZIEL" ]] || ZIEL="$H/medien_images"
if [[ -z "$DEV" ]]; then
  mapfile -t ROMS < <(lsblk -dno NAME,TYPE 2>/dev/null | awk '$2=="rom"{print "/dev/"$1}')
  if   [[ ${#ROMS[@]} -eq 1 ]]; then DEV="${ROMS[0]}"
  elif [[ ${#ROMS[@]} -eq 0 ]]; then die "kein optisches Laufwerk gefunden (lsblk TYPE=rom). Kabel/Netzteil pruefen oder GERAET angeben."
  else die "mehrere Laufwerke: ${ROMS[*]} - als 3. Parameter angeben."; fi
fi
[[ -b "$DEV" ]] || die "$DEV ist kein Blockgeraet"
SZ="$(blockdev --getsize64 "$DEV" 2>/dev/null || echo 0)"
[[ "${SZ:-0}" -gt 0 ]] || die "keine Disc in $DEV erkannt (Groesse 0). Disc einlegen, 30 s warten, erneut starten."
echo "== Disc $NR | Geraet $DEV | Groesse $(awk -v s="$SZ" 'BEGIN{printf "%.2f GiB", s/1073741824}') | Ziel $ZIEL"
udevadm info -q property -n "$DEV" 2>/dev/null | grep -E '^(ID_MODEL|ID_CDROM_MEDIA_(BD|DVD|CD)[A-Z_]*|ID_FS_LABEL|ID_FS_TYPE)=' | sed 's/^/   /'
mkdir -p "$ZIEL" || die "Zielordner nicht anlegbar: $ZIEL"
IMG="$ZIEL/$NR.iso"; MAP="$ZIEL/$NR.map"
FREI="$(df --output=avail -B1 "$ZIEL" | tail -1 | tr -d ' ')"
if [[ "${FREI:-0}" -lt $((SZ + SZ / 10)) && ! -e "$IMG" ]]; then die "zu wenig Platz in $ZIEL (frei $((FREI/1073741824)) GiB, noetig ca. $((SZ/1073741824)) GiB)"; fi
if [[ -n "$SPEED" ]]; then eject -x "$SPEED" "$DEV" 2>/dev/null && echo "   Lesegeschwindigkeit auf ${SPEED}x gedrosselt" || echo "   Drosselung nicht unterstuetzt (ignoriert)"; fi
echo "   Hinweis: Laufwerk direkt an Rueck-USB (keine Hub), beide Kabel/Netzteil anschliessen; Abbruch jederzeit mit Strg+C, Aufruf wiederholen setzt fort."
echo
echo "== Pass 1 (gute Bereiche, ohne Scraping), max. ${MAXH_P1} h, Abbruch bei ${NOSTOP_MIN} min ohne erfolgreichen Sektor"
timeout -s INT "${MAXH_P1}h" ddrescue -n -b2048 -T "${NOSTOP_MIN}m" "$DEV" "$IMG" "$MAP"; R1=$?
[[ $R1 -eq 124 ]] && echo "   Zeitlimit Pass 1 erreicht - Aufruf wiederholen setzt fort."
echo; echo "== Zwischenstand"; ddrescuelog -t "$MAP"
if ddrescuelog -D "$MAP" >/dev/null 2>&1; then
  echo "   Mapfile: ALLES gelesen - Pass 2 nicht noetig."
else
  echo; echo "== Pass 2 (Direktzugriff, 1 Wiederholung), max. ${MAXH_P2} h"
  timeout -s INT "${MAXH_P2}h" ddrescue -d -r1 -b2048 -T "${NOSTOP_MIN}m" "$DEV" "$IMG" "$MAP"; R2=$?
  [[ $R2 -eq 124 ]] && echo "   Zeitlimit Pass 2 erreicht - Aufruf wiederholen setzt fort."
  echo; echo "== Ergebnis"; ddrescuelog -t "$MAP"
fi
echo
if ddrescuelog -D "$MAP" >/dev/null 2>&1; then
  echo "== VOLLSTAENDIG. Pruefsumme wird berechnet ..."; ( cd "$ZIEL" && sha256sum "$NR.iso" | tee "$NR.iso.sha256" )
  STAT=0
else
  echo "== UNVOLLSTAENDIG (siehe 'bad-sector'/'non-tried' oben). Image und Mapfile bleiben erhalten."
  echo "   Naechste Schritte: andere Laufwerk-Hardware probieren (Handbuch: ein anderes Laufwerk liest manchmal Sektoren, die das erste nicht schafft),"
  echo "   Aufruf mit anderem Laufwerk wiederholen (gleiche Mapfile), erst dann Luecken akzeptieren."
  STAT=1
fi
cat <<EOF

== Weiter unter Windows (PowerShell), Image liegt in $IMG:
   Mount-DiskImage -ImagePath 'D:\\Medien_Images\\$NR.iso'          # Pfad an den tatsaechlichen Ablageort anpassen
   (Get-DiskImage -ImagePath 'D:\\Medien_Images\\$NR.iso' | Get-Volume).DriveLetter
   cd <Skriptordner>
   py medien_pruefen_v1.3.py $NR --laufwerk <Laufwerksbuchstabe>:\\ --mapfile D:\\Medien_Images\\$NR.map
   Dismount-DiskImage -ImagePath 'D:\\Medien_Images\\$NR.iso'
EOF
exit $STAT
