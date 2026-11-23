### Fixed

- **Pipeline.** Git path names are now read raw (unquoted), so a non-ASCII owned file is matched to its task instead of being reported as a change outside every task's owned paths, and a hand merge resolution in it names the file in plain UTF-8. A name git still quotes (a tab, newline, double quote or backslash) counts as every owned path (fail-safe).
