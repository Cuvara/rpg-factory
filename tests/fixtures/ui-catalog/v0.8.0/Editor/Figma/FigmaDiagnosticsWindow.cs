namespace Cuvara.UIToolkit.Editor.Figma
{
    using UnityEditor;

    /// <summary>One place to see whether the Figma integration is healthy.</summary>
    public sealed class FigmaDiagnosticsWindow : EditorWindow
    {
        [MenuItem("Window/Cuvara/Figma Diagnostics")]
        public static void Open() => GetWindow<FigmaDiagnosticsWindow>();

        [MenuItem("Tools/Cuvara/Figma/Validate Profiles")]
        private static void ValidateProfiles() { }
    }
}
