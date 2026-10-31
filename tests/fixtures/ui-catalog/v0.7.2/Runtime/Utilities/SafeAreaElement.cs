using System;
using UnityEngine;
using UnityEngine.UIElements;

namespace Cuvara.UIToolkit.Utilities
{
    /// <summary>
    /// Keeps its content inside <see cref="Screen.safeArea"/> on notched devices.
    /// </summary>
    [UxmlElement]
    public partial class SafeAreaElement : VisualElement
    {
        /// <summary>USS class added to every instance, for styling and for UQuery.</summary>
        public const string UssClassName = "cuvara-safe-area";

        [UxmlAttribute("conform-x")] public bool ConformX { get; set; } = true;

        [UxmlAttribute("conform-y")] public bool ConformY { get; set; } = true;
    }
}
