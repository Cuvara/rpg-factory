# ui-select-repo fixture

Copy-shaped excerpts of com.cuvara.uitoolkit v0.8.0 (`package.json`, `Runtime/**`), trimmed to the
public surface that `scripts/ui/ui_select.py` selects from. `tests/ui-skill-routing.test.sh` copies
this directory into a temp git repo named `UIToolkit`, tags it `v0.8.0` and pins a fixture client
manifest to `#v0.8.0`. Not a buildable package.
