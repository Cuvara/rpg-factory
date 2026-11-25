### Fixed

- **Asset-gen external source.** A dollar sign followed by a word in an external anchor's `origin` or `rights_note`
  (for example "priced in $USD") is no longer refused as an environment-variable path. `$NAME` is refused only when a
  slash or backslash follows it, and the braced `${NAME}` is still refused with or without one; `file:` and
  `%NAME%` paths are unchanged.
