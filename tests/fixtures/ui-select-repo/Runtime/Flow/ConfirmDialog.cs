using System;
using System.Threading;
using Cuvara.UIToolkit.Theme;
using Cysharp.Threading.Tasks;
using UnityEngine.UIElements;

namespace Cuvara.UIToolkit.Flow
{
    /// <summary>
    /// Reusable modal confirmation dialog. One static call, returns a bool.
    /// </summary>
    public static class ConfirmDialog
    {
        /// <summary>Shows a modal confirmation dialog and waits for the choice.</summary>
        public static async UniTask<bool> ShowAsync(
            VisualElement parent,
            string message,
            string confirmLabel = "OK",
            string cancelLabel = "Cancel",
            CancellationToken ct = default)
        {
            if (parent == null) throw new ArgumentNullException(nameof(parent));
            var tcs = new UniTaskCompletionSource<bool>();
            var overlay = new VisualElement();
            overlay.AddToClassList(CuvaraTheme.ConfirmDialogUssClassName);
            parent.Add(overlay);
            return await tcs.Task;
        }
    }
}
