using System;
using System.Threading;
using Cysharp.Threading.Tasks;
using UnityEngine.UIElements;

namespace Cuvara.UIToolkit.Flow
{
    /// <summary>
    /// Reusable modal confirmation dialog. One static call, returns a bool.
    /// </summary>
    public static class ConfirmDialog
    {
        /// <summary>Shows a modal confirmation dialog and waits for the user's choice.</summary>
        public static async UniTask<bool> ShowAsync(
            VisualElement parent,
            string message,
            string confirmLabel = "OK",
            string cancelLabel = "Cancel",
            CancellationToken ct = default)
        {
            if (parent == null) throw new ArgumentNullException(nameof(parent));
            var tcs = new UniTaskCompletionSource<bool>();
            return await tcs.Task;
        }
    }
}
