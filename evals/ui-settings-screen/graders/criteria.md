---
type: llm
weight: 2
---

Routes through `factory-core` with lead `client-integration`, then follows the UI plan from `ui-orchestrator`: loads only `ui-component-selection`, `ui-toolkit-screen` and `ui-validation` (not `ui-figma-import`, no Figma step). Selects components in the order reuse > configure > compose > missing from the real com.cuvara.uitoolkit catalog: reuses `SettingsModel` for the settings data, `ConfirmDialog.ShowAsync` for the reset confirmation and `IScreenNavigator.PopAsync` (or `BackNavigationSource`) for back/close; composes Unity built-ins (`ui:Toggle`, `ui:Slider`, `ui:DropdownField`) styled with `--cuvara-*` tokens instead of new custom controls; cites the catalog source for each reuse and invents no component, API or menu. Scaffolds the screen through ScreenCreator with a presenter/view on `BaseUIToolkitScreenPresenter`/`BaseUIToolkitView`. Names the validation (light and dark theme, layout, Play mode, EditMode/PlayMode tests) and does not claim any of it ran: unrun checks are NOT_RUN or HUMAN_REQUIRED. If the client pins a UIToolkit version older than v0.8.0, says so and names `pin-bump` as the follow-up.
