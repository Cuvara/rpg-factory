using UnityEngine.UIElements;

namespace Cuvara.UIToolkit.Utilities
{
    /// <summary>Pads its content to the device safe area.</summary>
    [UxmlElement]
    public partial class SafeAreaElement : VisualElement
    {
        [UxmlAttribute("conform-x")] public bool ConformX { get; set; }

        [UxmlAttribute("conform-y")] public bool ConformY { get; set; }
    }
}
