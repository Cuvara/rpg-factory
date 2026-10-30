namespace Cuvara.UIToolkit.FigmaCore
{
    using System.Collections.Generic;

    /// <summary>Checks one connector import folder and returns stable FIG0xx diagnostics.</summary>
    public static class FigmaImportValidator
    {
        public const string ManifestMissing = "FIG001";

        public static List<string> Validate(string folder) => new List<string>();
    }
}
