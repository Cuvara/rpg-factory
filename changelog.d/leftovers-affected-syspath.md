### Changed

- **Affected suites.** `tests/affected.py` no longer treats every `scripts/lib` module that touches `sys.path` or
  `importlib` as unsure for selection. It resolves the plugin's own idiom statically (`sys.path.insert/append` of a
  directory built from `__file__` and string literals, and the `rpgf_guard` package loader in `gitguard.py`), so a
  change to `scripts/lib/workspace.py` or `scripts/lib/fstate.py` selects the suites of their real importers
  instead of every suite (75 to 55 and 75 to 50 suites). Computed entries, `importlib.import_module` and
  `__import__` stay unsure, and the suite reuse hashes keep the conservative rule.
