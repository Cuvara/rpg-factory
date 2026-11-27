### Fixed

- **Guard.** Expand Git Bash `cmd //c` and `//k` wrappers, recognize additional process termination forms, and exempt PIDs obtained from `$!` or `Start-Process -PassThru`. Quoted process-command regression cases now also run inside the workspace.
