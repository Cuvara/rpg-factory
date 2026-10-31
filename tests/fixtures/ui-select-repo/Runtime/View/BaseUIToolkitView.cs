using UnityEngine.UIElements;

namespace Cuvara.UIToolkit.View
{
    /// <summary>
    /// The base for a UI Toolkit screen: a plain C# class, no MonoBehaviour. Subclass it, query
    /// the elements in the constructor, and hold them.
    /// </summary>
    public abstract class BaseUIToolkitView : IUIToolkitView
    {
        public VisualElement Root { get; }

        public void Hide() { }

        public void Show() { }
    }
}
