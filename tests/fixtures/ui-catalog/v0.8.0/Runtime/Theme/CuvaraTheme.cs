namespace Cuvara.UIToolkit.Theme
{
    using UnityEngine;

    /// <summary>
    /// The package's theme contract: the default stylesheet and the USS class names its built-in
    /// UI carries.
    /// </summary>
    public static class CuvaraTheme
    {
        /// <summary><c>Resources.Load</c> path of the default theme stylesheet.</summary>
        public const string ResourcesPath = "CuvaraTheme";

        /// <summary><c>ConfirmDialog</c>'s full-screen overlay.</summary>
        public const string ConfirmDialogUssClassName = "cuvara-confirm-dialog";

        /// <summary>One toast.</summary>
        public const string ToastUssClassName = "cuvara-toast";
    }
}
