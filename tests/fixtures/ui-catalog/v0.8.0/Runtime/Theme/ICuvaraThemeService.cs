namespace Cuvara.UIToolkit.Theme
{
    using System;
    using UnityEngine.UIElements;

    /// <summary>Attaches the Cuvara theme to a visual-tree root: the base sheet plus overrides.</summary>
    public interface ICuvaraThemeService
    {
        void Apply(VisualElement root);

        void AddOverride(StyleSheet sheet);
    }
}
