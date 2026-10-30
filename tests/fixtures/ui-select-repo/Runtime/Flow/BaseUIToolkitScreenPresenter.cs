namespace Cuvara.UIToolkit.Flow
{
    /// <summary>Base presenter for a screen driven by the screen flow.</summary>
    public abstract class BaseUIToolkitScreenPresenter<TView> : IUIToolkitScreenPresenter, IFlowDriven
        where TView : class, IUIToolkitView
    {
        public ScreenLifecycleState State { get; private set; } = ScreenLifecycleState.Registered;
    }

    /// <summary>Makes "this is a popup" visible in the class name; behaviour comes from ScreenOptions.</summary>
    public abstract class BaseUIToolkitPopupPresenter<TView> : BaseUIToolkitScreenPresenter<TView>
        where TView : class, IUIToolkitView
    {
    }
}
