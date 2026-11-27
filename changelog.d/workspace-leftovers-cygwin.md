### Fixed

- **Workspace default on Cygwin.** `rpgf_platform_path` and the workspace default now map a WSL-form path to the cygdrive form (`/cygdrive/c/...`) or the `cygpath -u` answer when `cygpath` is on PATH; MINGW and MSYS keep the Git Bash drive form.
