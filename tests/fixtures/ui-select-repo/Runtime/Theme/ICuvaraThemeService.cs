namespace Cuvara.UIToolkit.Theme
{
    /// <summary>Applies the Cuvara theme (light or dark) to panel roots.</summary>
    public interface ICuvaraThemeService
    {
        CuvaraThemeMode Mode { get; }

        void SetMode(CuvaraThemeMode mode);
    }
}
