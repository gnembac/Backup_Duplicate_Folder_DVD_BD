# Lessons learned (selection)

Each lesson comes from a concrete incident in this project. The full German log contains 130+ entries; this is the curated engineering subset. IDs refer to that log.

## Data integrity

| ID | Incident | Rule |
|---|---|---|
| E36, E64 | 6,289 files on 16 discs were read **without any read error** but with wrong content | "0 read errors" is not proof of correct data. Compare the same file across independent sources (path + size + date equal, hash different ⇒ defect suspicion) |
| E19 | Files without a hash shared the empty string as key and were treated as *one* content; a hash check after copying stopped the wrong source | Never treat empty keys as equality. Reconcile: number of unique keys vs. number of rows before releasing a plan |
| E53 | A folder was reported "covered" although 723 contents were missing | "Covered" only at 100 % hash coverage |
| E62 | A pilot copy was SHA-identical to the plan but 175 copied disc files were defective | SHA-OK proves plan fidelity, not content quality — add a format/content check |
| E129 | A known, accepted deviation (two rewritten `.lnk` files) was documented in prose only; the next tool version flagged it again | Accepted deviations must be a machine-readable list that every subsequent tool consumes |

## Verification design

| ID | Incident | Rule |
|---|---|---|
| E108 | A report showed "differences to ISO: 0" although no ISO had been passed | Never print a zero counter for a comparison that did not run; print "not compared" |
| E110 | A raw-image check read a still-mounted ISO of identical size instead of the disc image | Eject all other images, check drive letter and volume label before every image check |
| E115 | The burn software silently truncated a 129-character name to 127; path length had been checked, name length had not | Check *all* target limits (name, path, label, character set, collisions) before building the burn folder |
| E119 | The raw check's summary reported only unreadable gaps and hid 26,599 differing sectors | Report every finding class separately; no ranking that lets one class mask another |
| E123 | A sector comparison raised a false "data mismatch" alarm: padding after end-of-file differed (ISO buffer remnants vs. zeros on disc) | Derive padding regions from the file-system structure (UDF extents), not from assumptions about fill bytes |
| E130 | An expected value ("ZIP CRC test OK 7") came from a header comment, not from the code path | Derive expected test results from the code, not from its description |

## Process

| ID | Incident | Rule |
|---|---|---|
| E11 | A handover claimed a safety gate checked only "missing = 0"; the code also checked hash and size | Every statement about script behaviour that leads to an action is verified in the source (line reference) |
| E13, E20 | Mass moves were provably correct because the inventory was saved before the first move | Inventory → dry run → pilot with known target count → staged full run → reconciliation |
| E24 | A corrected script was delivered under the same file name; the old version ran | Every correction gets a new version number in the file name; scripts print their version first |
| E37, E101 | Python reported a CRC media error as `Errno 13 Permission denied` | Log the real Win32 code (`winerror`); never infer the cause from `errno` |
| E58, E124 | Timestamps in document headers were estimated and turned out late | Take timestamps from the system clock immediately before writing |
| E78 | A sum was carried forward over two handovers with an error of 10,000 | Recompute sums from their parts, never carry them forward |
| E103, E121 | A disc burned from the compilation instead of the ISO can never be bit-identical to the ISO | Burn from the verified ISO; ask for the exact click path before evaluating a raw check |
| E116 | A step "rename folder" was skipped and an old state was burned again | Never rename: each state goes into a new versioned folder that the tool detects itself |
| E125 | Blank-media planning ignored the measured failure rate (2 of 4 burns with CRC findings) | Consumables = units × (1 + failure rate) + reserve |
