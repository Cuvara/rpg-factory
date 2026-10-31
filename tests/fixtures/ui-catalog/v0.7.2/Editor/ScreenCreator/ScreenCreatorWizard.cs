namespace Cuvara.UIToolkit.Editor
{
    using UnityEditor;

    /// <summary>An Editor window that scaffolds a new screen, popup or collection item.</summary>
    public sealed class ScreenCreatorWizard : EditorWindow
    {
        [MenuItem("Assets/Cuvara/Create Screen")]
        public static void OpenWindow() => GetWindow<ScreenCreatorWizard>();
    }
}
