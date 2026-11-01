# mdisc_brenner_check_v1.0.ps1 - Projekt "Basisdaten ermitteln" (privat)
# Version 1.0 | Stand 30.10.2026, 10:05 MEZ | Autor: Claude fuer Gunter Nembach
#
# ZWECK (NUR LESEN, BRENNT NICHTS)
#   Test T0 der M-DISC-Bewertung: Brennermodell, Firmware, unterstuetzte Profile
#   und - mit eingelegtem LEEREN Rohling - ob das Laufwerk den Rohling als BD-R
#   mit BDXL-Kapazitaet (ca. 48,8 Mio. Sektoren = ca. 93,2 GiB) erkennt und
#   welche Schreibgeschwindigkeiten es anbietet. Der Rohling wird dabei nicht
#   beschrieben (nur Abfrage ueber die Windows-Brennschnittstelle IMAPI2).
#
# AUFRUF (PowerShell, PC-Windows)
#   1) ohne Disc oder mit beliebiger Disc:  Modell + Profile
#   2) mit leerem M-DISC-Rohling:           zusaetzlich Medientyp, Kapazitaet, Schreibtempo
#   powershell -ExecutionPolicy Bypass -File D:\_Berichte\kopierplan\skripte\mdisc_brenner_check_v1.0.ps1
#
# AUSGABE  Bildschirm + D:\_Berichte\mdisc\brenner_check_<Zeit>.txt
# GRENZEN  In der Linux-Sandbox nicht pruefbar: UNGETESTET bis zum ersten Lauf.
#          IMAPI2 meldet keine "M-DISC"-Eigenschaft; belegbar sind BD-R + Kapazitaet + Tempo.
# VERSIONSPROTOKOLL  1.0  30.10.2026, 10:05  Erstfassung

$Version = 'mdisc_brenner_check_v1.0'
$out = 'D:\_Berichte\mdisc'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$datei = Join-Path $out ("brenner_check_{0}.txt" -f (Get-Date -Format 'yyyy-MM-dd_HHmm'))
Start-Transcript -Path $datei | Out-Null
"$Version  $(Get-Date -Format 'dd.MM.yyyy HH:mm:ss')"

"--- Windows-Geraeteliste (Win32_CDROMDrive) ---"
Get-CimInstance Win32_CDROMDrive |
    Select-Object Drive, Name, Manufacturer, MfrAssignedRevisionLevel, MediaLoaded, MediaType |
    Format-List | Out-String | Write-Output

$phys = @{0='UNBEKANNT';1='CD-ROM';2='CD-R';3='CD-RW';4='DVD-ROM';5='DVD-RAM';6='DVD+R';7='DVD+RW';
          8='DVD+R DL';9='DVD-R';10='DVD-RW';11='DVD-R DL';12='DISK';13='DVD+RW DL';14='HD-DVD-ROM';
          15='HD-DVD-R';16='HD-DVD-RAM';17='BD-ROM';18='BD-R';19='BD-RE'}
$prof = @{0x40='BD-ROM';0x41='BD-R SRM';0x42='BD-R RRM';0x43='BD-RE'}
$BD1x = 4495.5 * 1000 / 2048   # Sektoren je Sekunde bei 1x BD (4,4955 MB/s)

try {
    $master = New-Object -ComObject IMAPI2.MsftDiscMaster2
} catch { "IMAPI2 nicht verfuegbar: $_"; Stop-Transcript | Out-Null; exit 2 }
if ($master.Count -eq 0) { "IMAPI2: kein Brenner gefunden"; Stop-Transcript | Out-Null; exit 2 }

foreach ($id in $master) {
    "--- IMAPI2-Brenner ---"
    $r = New-Object -ComObject IMAPI2.MsftDiscRecorder2
    $r.InitializeDiscRecorder($id)
    "Hersteller/Modell : {0} {1}" -f $r.VendorId.Trim(), $r.ProductId.Trim()
    "Firmware          : {0}" -f $r.ProductRevision
    "Laufwerk          : {0}" -f (($r.VolumePathNames) -join ', ')
    try {
        $bd = @($r.SupportedProfiles | Where-Object { $prof.ContainsKey([int]$_) } | ForEach-Object { $prof[[int]$_] })
        "BD-Profile        : {0}" -f ($(if ($bd.Count) { $bd -join ', ' } else { 'keine (kein BD-Brenner?)' }))
        "Alle Profile (hex): {0}" -f ((@($r.SupportedProfiles) | ForEach-Object { '0x{0:X2}' -f [int]$_ }) -join ' ')
    } catch { "Profile: k.A. ($_)" }

    $f = New-Object -ComObject IMAPI2.MsftDiscFormat2Data
    if (-not $f.IsRecorderSupported($r)) { "Brenner fuer Datenbrand laut IMAPI2 nicht unterstuetzt"; continue }
    $f.Recorder = $r
    $f.ClientName = $Version
    try {
        if ($f.IsCurrentMediaSupported($r)) {
            $t = [int]$f.CurrentPhysicalMediaType
            "Medium            : {0} (Typ {1})" -f $phys[$t], $t
            "Leer (heuristisch): {0}" -f $f.MediaHeuristicallyBlank
            $tot = [int64]$f.TotalSectorsOnMedia; $free = [int64]$f.FreeSectorsOnMedia
            "Sektoren gesamt   : {0:N0}  = {1:N2} GiB" -f $tot, ($tot * 2048 / 1GB)
            "Sektoren frei     : {0:N0}  = {1:N2} GiB" -f $free, ($free * 2048 / 1GB)
            if ($t -eq 18 -and $tot -gt 40000000) { "BEWERTUNG         : BD-R mit BDXL-Kapazitaet erkannt (Soll ca. 48,8 Mio. Sektoren)" }
            elseif ($t -eq 18) { "BEWERTUNG         : BD-R, aber KEINE BDXL-Kapazitaet erkannt" }
            try {
                $sp = @($f.SupportedWriteSpeeds) | Sort-Object -Unique
                "Schreibtempo      : {0}" -f (($sp | ForEach-Object { '{0:N1}x ({1:N1} MB/s)' -f ($_ / $BD1x), ($_ * 2048 / 1e6) }) -join ', ')
            } catch { "Schreibtempo      : k.A." }
        } else {
            "Medium            : keines eingelegt, abgeschlossen oder nicht beschreibbar"
        }
    } catch { "Medium            : Abfrage fehlgeschlagen ($_)" }
}
Stop-Transcript | Out-Null
"Bericht: $datei"
