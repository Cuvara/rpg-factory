### Fixed

- **asset-gen: `model-hashes` reads extra model path files in ComfyUI's order.** ComfyUI's `main.py` loads
  `<comfy root>/extra_model_paths.yaml` first and then the files named on its command line; `model-hashes` read the
  explicit `--extra-model-paths` files first, so a duplicate model name could resolve to another folder than the one
  ComfyUI loads. The order is now the root file, the Comfy Desktop `instance-model-paths/<instance id>.yaml` (Desktop
  passes it on the command line; it stays auto-discovered, so it comes before the explicit files), then every
  `--extra-model-paths FILE` as given; each file is still read once.
- **asset-gen: `model-hashes` treats `is_default` as ComfyUI does.** ComfyUI uses Python truthiness of the value
  `yaml.safe_load` returns, while the reader accepted only the words true/yes/on. The stdlib subset reader now keeps
  whether a scalar was quoted: a plain bool word (true/yes/on and false/no/off in the YAML 1.1 spellings), null, `~` or
  an empty value and a plain zero (`0`, `0.0`, `0x0`, `0b0`, `00`) are false, any other plain number or text is true,
  and a quoted or block scalar is a string, so `'false'`, `"no"` and `'0'` count as a default (only an empty quoted
  string does not).
- **Guard: two docstrings describe the code again.** `git_dir_in_scope` (`scripts/lib/rpgf_guard/language.py`) says a
  relative `-C` follows a preceding literal `cd` (`git_c_dirs`) before the hook's cwd, and `literal_cd_target`
  (`scripts/lib/rpgf_guard/git.py`) says `cd ~` and `cd ~/x` resolve through `os.path.expanduser` instead of giving None.
