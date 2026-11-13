### Fixed

- **Python alias detection.** On Windows, dispatch specs flag the Microsoft Store `python3` alias also when the
  dispatching session runs through a `python3` shim first on PATH: `%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe`
  is probed directly, since dispatched sessions start with a normal PATH and still hit the alias.
