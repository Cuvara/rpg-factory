using System;
using UnityEngine.UIElements;

namespace Cuvara.UIToolkit.Flow
{
    /// <summary>Auto-dismissing toast notifications. Stackable, type-tinted.</summary>
    public sealed class ToastService : IDisposable
    {
        public ToastService(VisualElement parent) { }

        public void Show(string message, float duration = 3f, ToastType type = ToastType.Info) { }

        public void Dispose() { }
    }

    /// <summary>Visual type of a toast.</summary>
    public enum ToastType
    {
        Info,
        Success,
        Warning,
        Error,
    }
}
