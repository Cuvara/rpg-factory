### Changed

- **Asset-gen tests.** `tests/assetgen.test.sh` reads the core purposes, styles and templates from
  `templates/assetgen/` instead of hard-coded lists: the core list count, the listed-id check, the golden render and
  `workflow.ui.json` loops, the template prompt-link loop and the style lock data checks. Extra render params (the
  `image-edit` reference image) come from an optional `tests/fixtures/assetgen/cases/<purpose>.json`, which can also
  name template variants rendered against `golden/<purpose>--<template>.json`. A new core purpose or template no
  longer needs an edit of the test; the assertions and the pass count are unchanged.
