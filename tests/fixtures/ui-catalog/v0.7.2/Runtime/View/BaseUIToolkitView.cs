using UnityEngine.UIElements;

namespace Cuvara.UIToolkit
{
    /// <summary>A UXML document plus a lifecycle: the base of every view.</summary>
    public abstract class BaseUIToolkitView : IUIToolkitView
    {
        public VisualElement Root { get; }

        protected BaseUIToolkitView(VisualTreeAsset asset) { Root = asset.Instantiate(); }
    }
}
