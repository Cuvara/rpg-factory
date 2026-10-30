using Cysharp.Threading.Tasks;

namespace Cuvara.UIToolkit.Flow
{
    /// <summary>Stack-based screen navigation.</summary>
    public interface IScreenNavigator
    {
        UniTask PushAsync<TPresenter>() where TPresenter : IUIToolkitScreenPresenter;

        UniTask PopAsync();
    }
}
