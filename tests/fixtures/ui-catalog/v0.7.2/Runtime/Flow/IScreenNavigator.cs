using Cysharp.Threading.Tasks;

namespace Cuvara.UIToolkit.Flow
{
    /// <summary>The one navigation abstraction. Opens, closes and orders screens.</summary>
    public interface IScreenNavigator
    {
        UniTask<TPresenter> PushAsync<TPresenter>() where TPresenter : class, IUIToolkitScreenPresenter;

        UniTask PopAsync();
    }
}
