### Fixed

- **Doctor.** `doctor` text output printed the Git Bash `python3` Microsoft Store stub twice, as the older `- python3:` hook-speed advice line and as the `python3-store-stub` setup fault, each with its own near-duplicate fix hint. It now prints the setup fault once with its fix hint and the hook-speed cost (every hook call starts about 70 ms slower). `doctor --json` is unchanged (`tools.python3.advice` and `tools.setup_faults` keep their fields and values).
