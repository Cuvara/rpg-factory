---
type: llm
weight: 2
---

Routes through `factory-core` with lead `client-integration`, then follows the UI plan from `ui-orchestrator` in order: `ui-figma-import`, `ui-component-selection`, `ui-toolkit-screen`, `ui-validation`. Reads file key `AbC123xyz` and node id `12:34` from the URL and guesses nothing else. Imports through the official Unity UI Toolkit Figma connector (`com.unity.ui.figma`) and the existing com.cuvara.uitoolkit 0.8 tooling (FigmaImportValidator / `UxmlCodegenCli validate`, `Tools~/FigmaImport/figma-import.py`, ScreenCreator "Existing UXML"); never proposes a Figma REST importer or a hand-written UXML/USS generator. States the designer rule behind validator rule `FIG023` (variables only on component roots and `<Role>/Label` single-text components, because Unity 6000.3.9f1 cannot clone inline `var()`). Does not claim SafeArea emission, shadow or gradient import, or typed node-id bindings. Says the Figma integration is optional (gated Editor assembly) and needs a Figma login and an open Editor: without them the import is HUMAN_REQUIRED or NOT_RUN, never PASS.
