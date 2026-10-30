using Cysharp.Threading.Tasks;

namespace Cuvara.UIToolkit.Flow
{
    /// <summary>Base presenter of a navigator screen: owns its view and its subscriptions.</summary>
    public abstract class BaseUIToolkitScreenPresenter<TView> : IUIToolkitScreenPresenter
    {
        protected TView View { get; private set; }

        public virtual UniTask OnOpenAsync() => UniTask.CompletedTask;
    }

    /// <summary>A screen presenter that receives a model when pushed.</summary>
    public abstract class BaseUIToolkitScreenPresenter<TView, TModel> : BaseUIToolkitScreenPresenter<TView>
    {
        protected TModel Model { get; private set; }
    }

    /// <summary>Base presenter of a popup screen.</summary>
    public abstract class BaseUIToolkitPopupPresenter<TView> : BaseUIToolkitScreenPresenter<TView>
    {
    }
}
