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

        /// <summary>Music volume 0-1.</summary>
        public float MusicVolume { get; private set; }

        /// <summary>Graphics quality index (0=Low, 1=Medium, 2=High, 3=Ultra).</summary>
        public int GraphicsQuality { get; private set; }

        public void Load() { MusicVolume = PlayerPrefs.GetFloat("settings.music_volume", 0.8f); }
        public void Save() { PlayerPrefs.SetFloat("settings.music_volume", MusicVolume); }
        public void SetMusicVolume(float v) { MusicVolume = Mathf.Clamp01(v); Changed?.Invoke(); }
        public void SetGraphicsQuality(int q) { GraphicsQuality = Mathf.Clamp(q, 0, 3); Changed?.Invoke(); }
    }
}
