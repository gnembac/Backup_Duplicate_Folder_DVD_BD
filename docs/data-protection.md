# Data protection

This repository contains **code and aggregated metrics only**.

| Not published | Reason |
|---|---|
| Manifests, copy plans, inventories, reports, logs | contain private file and folder names |
| Media database (`medien.sqlite`), register CSV | contain disc labels and file paths |
| Credentials, keys, `.env` files | never part of the project data |

Sanitisation of the scripts (details and hashes: [../src/PROVENANCE.md](../src/PROVENANCE.md)):

- Windows user name in default paths → `<USER>`; Google account → `<google-account>`
- an example event folder name in a comment → `<Ereignisordner>`
- the personal folder-priority list in `mdisc_brennliste` → a shorter generic example list (behaviour unchanged otherwise)
- two project-specific report generators (`gesamtplan`, `kennzahlen`) were not published because they encode private decisions

Before each push: `gitleaks detect` (CI runs it as well) and a search for personal names and paths.
