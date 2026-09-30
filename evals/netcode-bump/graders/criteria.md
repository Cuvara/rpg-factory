---
type: llm
weight: 2
---

A successful response:
- Changes the pin in BOTH Packages/manifest.json and Packages/packages-lock.json and says
  they must agree (the lock is what Unity resolves).
- Recopies the DOTS Sample (Assets/Samples/Netcode/DOTS Sample from the package's
  Samples~/DOTSSample, with .meta files) and updates .sample-source; says not to re-import
  it through Package Manager.
- Never commits a file: package path.
- Adds a CHANGELOG entry.
- Lists the package-pin check (local or CI 02-package-pins) and Unity tests (Editor or CI)
  as validation, and does not claim they were run.
