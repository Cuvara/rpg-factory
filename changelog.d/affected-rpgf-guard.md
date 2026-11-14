### Changed

- **Affected suites.** A change to `scripts/lib/rpgf_guard/__init__.py`, the package `scripts/lib/gitguard.py` loads by a
  static `spec_from_file_location` path, now selects the suites that reach `scripts/lib/gitguard.py` instead of every
  suite: the loader gives the loaded package an importer edge. A package loaded by a computed path stays unsure, and the
  suite reuse hashes keep the conservative rule. The lines of `tests/affected.py` are wrapped to 120 characters.
