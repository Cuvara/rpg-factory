### Fixed

- **Asset gen.** An external anchor's `external_source.origin` and `rights_note` now also refuse `file:` URIs (`file:///C:/...`, `file:/x`, `FILE://host/share`) and environment-variable paths (`$HOME/...`, `${HOME}/...`, `%USERPROFILE%\...`, `%USERPROFILE%/...`) in any letter case, with the existing "absolute path or credential" message; plain prose, `http(s)://` URLs, a price like `$5` and a percentage like `100%` are still accepted.
