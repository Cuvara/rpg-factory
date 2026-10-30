using System;
using UnityEngine.UIElements;

namespace Cuvara.UIToolkit.Collections
{
    /// <summary>A grid over a ListView: rows of cellsPerRow cells, one presenter per cell.</summary>
    public class UIToolkitGridAdapter<TModel, TView, TPresenter> : IDisposable
    {
        public const string RowUssClassName = "cuvara-grid-row";

        public UIToolkitGridAdapter(ListView listView, VisualTreeAsset cellTemplate, int cellsPerRow) { }

        public void Dispose() { }
    }
}
