using System;
using UnityEngine.UIElements;

namespace Cuvara.UIToolkit.Flow
{
    /// <summary>Short non-blocking notifications parented into a visual element.</summary>
    public sealed class ToastService : IDisposable
    {
        public ToastService(VisualElement parent) { }

        public void Show(string message, float duration = 3f, ToastType type = ToastType.Info) { }

        public void Clear() { }

        public void Dispose() { }
    }

    public enum ToastType
    {
        Info,
        Success,
        Warning,
        Error,
    }
}
