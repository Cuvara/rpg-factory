# Integrating connector output (imported UXML)

How a screen is built on top of a UXML that the UI Toolkit Connector for Figma wrote. Paths starting `UIToolkit/`
are the package repo at `v0.8.0`. The connector facts below come from the real "Game Settings" import (connector
`0.3.0-exp.1`, Unity 6000.3.9f1; `docs/architecture/ui-figma-real-test.md` in the plugin). Re-check them on another
connector version.

## What the connector output looks like

- **No `name` attributes.** The imported `GameSettings.uxml` carried zero `name=` attributes (typed node-id bindings,
  audit gap G4, are deferred). `Require<T>("name")` and the UXML codegen have nothing to bind to.
- **Controls carry classes from the component name:** `ui:Toggle class="toggle ..."`, `ui:Slider class="slider ..."`,
  `ui:DropdownField class="dropdown ..."`, `ui:Button class="button-close ..."`, `button-primary`, `button-secondary`.
  Labels and buttons carry their Figma text (`text="Close"`), controls carry no value range or choices.
- **The document links its sheets itself:** `<Style src="tokens.uss" />`, `<Style src="light.uss" />`,
  `<Style src="GameSettings.uss" />` at the top of the file.
- **The folder belongs to the connector.** A re-push rewrites it and may reorder elements. Never add names, classes
  or code there (never add names to the connector file); ScreenCreator refuses it as an output folder.

## Binding by type and order, once, in the bind step

ScreenCreator with source "Existing UXML" still gives the view, presenter and test skeleton
(`ScreenCreatorPlan.Build`, `UIToolkit/Editor/ScreenCreator/ScreenCreatorPlan.cs:53`; `ExistingUxml` branch `:63-77`). The generated view says to
query with `Require` once elements carry names (`EXISTING_VIEW`, `UIToolkit/Editor/ScreenCreator/ScreenCreatorTemplates.cs:285-303`);
for connector output query by type and document order, or by the component class, instead:

```csharp
// Game-owned view over the connector's UXML (IGameSettingsView declares the same properties).
// Lookups happen once; a changed shape fails loudly. Buttons end in Button: the base view has Close().
public sealed class GameSettingsView : BaseUIToolkitView, IGameSettingsView
{
    public const string AssetKey = "GameSettings";

    public Toggle MusicToggle { get; }
    public Toggle SoundToggle { get; }
    public Slider Volume { get; }
    public DropdownField Quality { get; }
    public Button CloseButton { get; }
    public Button ApplyButton { get; }
    public Button CancelButton { get; }

    public GameSettingsView(VisualTreeAsset asset) : base(asset)
    {
        this.StretchToParent();
        var toggles = this.Root.Query<Toggle>().ToList();          // document order
        Expect(toggles.Count, 2, "Toggle");
        this.MusicToggle = toggles[0];
        this.SoundToggle = toggles[1];
        this.Volume  = One<Slider>("slider");
        this.Quality = One<DropdownField>("dropdown");
        this.CloseButton  = One<Button>("button-close");
        this.ApplyButton  = One<Button>("button-primary");
        this.CancelButton = One<Button>("button-secondary");
    }

    private T One<T>(string className) where T : VisualElement
    {
        var all = this.Root.Query<T>(className: className).ToList();
        Expect(all.Count, 1, $"{typeof(T).Name}.{className}");
        return all[0];
    }

    private static void Expect(int found, int expected, string what)
    {
        if (found != expected)
            throw new InvalidOperationException(
                $"GameSettings.uxml has {found} {what}, expected {expected}: the Figma frame changed; update this view.");
    }
}
```

- One control by class is `root.Q<Button>(className: "button-close")`; the `One` helper above queries all matches
  instead, so a duplicate fails as loudly as a missing one.
- Order is a contract with the designer: name it in the view (which toggle is first) and in a test.
- The exception names the element type and both counts, as `Require` does for names
  (`Require`, `UIToolkit/Runtime/Utilities/VisualElementQueryExtensions.cs:29-41`).
- When the screen needs names (codegen, many controls), wrap the import in a game-owned UXML outside the import
  folder, or wait for G4. Do not edit the connector file.

## Settings: map controls to members that exist

`SettingsModel` at `v0.8.0` has `MasterVolume` (`UIToolkit/Runtime/Flow/SettingsModel.cs:23`), `MusicVolume` (`:26`),
`SfxVolume` (`:29`), `GraphicsQuality` (`:32`), `Fullscreen` (`:35`), `VSync` (`:38`) and `Language` (`:41`), with a
setter each (`SetMasterVolume`, `:68-74`), `Load` (`:44`), `Save` (`:56`), `Apply` (`:77`) and a `Changed` event (`:20`).
It has **no music or sound on/off flag**. Map a mute toggle to game-owned state (a game settings class that owns
the flag and applies it to its audio mixer), or to a volume the game decides on; never add members to the package
model from the client.

```csharp
public sealed class GameSettingsPresenter : BaseUIToolkitPopupPresenter<IGameSettingsView>
{
    private readonly SettingsModel settings;      // registered by the host
    private readonly GameAudioSettings audio;     // game-owned: music/sound on/off
    private readonly RootUIDocument document;

    public GameSettingsPresenter(SettingsModel settings, GameAudioSettings audio, RootUIDocument document)
    { this.settings = settings; this.audio = audio; this.document = document; }

    protected override UniTask OnBindAsync(ScreenSubscriptions subs, CancellationToken ct)
    {
        this.settings.Load();
        var v = this.View;
        v.Volume.lowValue = 0f; v.Volume.highValue = 1f;            // the import sets no range
        v.Volume.SetValueWithoutNotify(this.settings.MasterVolume);
        v.Quality.choices = new List<string>(QualitySettings.names); // the import sets no choices
        v.Quality.index = this.settings.GraphicsQuality;
        v.MusicToggle.SetValueWithoutNotify(this.audio.MusicOn);
        v.SoundToggle.SetValueWithoutNotify(this.audio.SoundOn);

        subs.On<ChangeEvent<float>>(v.Volume, e => this.settings.SetMasterVolume(e.newValue));
        subs.On<ChangeEvent<string>>(v.Quality, _ => this.settings.SetGraphicsQuality(v.Quality.index));
        subs.On<ChangeEvent<bool>>(v.MusicToggle, e => this.audio.MusicOn = e.newValue);
        subs.On<ChangeEvent<bool>>(v.SoundToggle, e => this.audio.SoundOn = e.newValue);
        subs.Clicked(v.ApplyButton, () => { this.settings.Apply(); this.settings.Save(); this.Close(); });
        subs.Clicked(v.CancelButton, () => { this.settings.Load(); this.Close(); });
        subs.Clicked(v.CloseButton, () => this.ConfirmDiscardAsync(ct).Forget());
        return UniTask.CompletedTask;
    }

    private async UniTaskVoid ConfirmDiscardAsync(CancellationToken ct)
    {
        var discard = await ConfirmDialog.ShowAsync(this.document.RootUIOverlayElement,
            "Discard unsaved changes?", "Discard", "Keep editing", ct);
        if (ct.IsCancellationRequested || !discard) return;
        this.settings.Load();
        this.Close();
    }
}
```

- `GameAudioSettings` stands for whatever the game already owns; it is not a package type.
- `SetGraphicsQuality` clamps to 0-3 (`SetGraphicsQuality`, `UIToolkit/Runtime/Flow/SettingsModel.cs:71`) while
  `QualitySettings.names` comes from the project: check that the project defines four levels, or map the index.
- `ConfirmDialog.ShowAsync` returns `false` on cancel or a cancelled token (`ShowAsync`,
  `UIToolkit/Runtime/Flow/ConfirmDialog.cs:29-34`); parent it into the overlay layer as the Figma Import sample does
  (`ConfirmDialog.ShowAsync`, `UIToolkit/Samples~/FigmaImport/ShopCardScreen.cs:135-140`).
- Register the popup with `RegisterPopup` (`UIToolkit/Runtime/VContainer/ScreenFlowRegistration.cs:96-103`) and the
  view's `AssetKey`, and register `SettingsModel` and the game-owned settings in the host scope.

## Light and dark

The connector UXML links `light.uss` itself, so switching the root's mode sheet alone leaves the open screen light.
Register every mode sheet once and attach the screen while it is open:

- `RegisterModeSheets` (`UIToolkit/Runtime/Theme/CuvaraThemeService.cs:76-88`) with both the light and the dark mode sheet.
- In `OnBindAsync`: `subs.Add(theme.AttachScreen(this.View.Root))` (`AttachScreen`, `UIToolkit/Runtime/Theme/CuvaraThemeService.cs:109-116`).
- How it works: `SyncScreen` (`UIToolkit/Runtime/Theme/CuvaraThemeService.cs:136-174`) walks the screen root's elements; on each element that links a registered
  mode sheet it puts the current mode sheet in place of the first one and drops any further one, keeping the sheet
  order (tokens, mode, screen). Without registered sheets or a current mode it does nothing (`knownModeSheets`, `:138`).
- Switch with `SetModeSheet` (`UIToolkit/Runtime/Theme/CuvaraThemeService.cs:92-106`); the attachment follows every later switch until it is disposed.
