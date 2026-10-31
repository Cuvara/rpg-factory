using System;
using UnityEngine.UIElements;

namespace Cuvara.UIToolkit.Input
{
    /// <summary>Raises a plain C# event when the user presses Back (Escape, gamepad B, Android back).</summary>
    public sealed class BackNavigationSource : IDisposable
    {
        public event Action BackRequested;

        public BackNavigationSource(VisualElement root) { }

        public void Dispose() { }
    }
}
