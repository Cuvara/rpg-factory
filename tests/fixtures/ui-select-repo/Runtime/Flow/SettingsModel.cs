using System;
using UnityEngine;

namespace Cuvara.UIToolkit.Flow
{
    /// <summary>
    /// Data model for common game settings. Loads from and saves to PlayerPrefs.
    /// </summary>
    public sealed class SettingsModel
    {
        /// <summary>Raised when any setting changes.</summary>
        public event Action Changed;

        /// <summary>Master volume 0-1.</summary>
        public float MasterVolume { get; private set; }

        /// <summary>Music volume 0-1.</summary>
        public float MusicVolume { get; private set; }

        /// <summary>SFX volume 0-1.</summary>
        public float SfxVolume { get; private set; }

        /// <summary>Graphics quality index (0=Low, 1=Medium, 2=High, 3=Ultra).</summary>
        public int GraphicsQuality { get; private set; }

        /// <summary>Fullscreen mode.</summary>
        public bool Fullscreen { get; private set; }

        /// <summary>Language code (e.g. "en", "vi").</summary>
        public string Language { get; private set; }

        /// <summary>Loads all settings from PlayerPrefs with defaults.</summary>
        public void Load()
        {
            MasterVolume = PlayerPrefs.GetFloat("settings.master_volume", 1f);
            Changed?.Invoke();
        }
    }
}
