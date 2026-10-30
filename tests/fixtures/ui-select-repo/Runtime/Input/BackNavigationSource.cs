using System;

namespace Cuvara.UIToolkit.Input
{
    /// <summary>Turns Escape, gamepad cancel and Android back into one back-navigation callback.</summary>
    public sealed class BackNavigationSource : IDisposable
    {
        public Func<bool> BackHandler { get; set; }

        public bool Enabled { get; set; } = true;

        public void Dispose() { }
    }
}
