### Added

- **Registry fragments.** `registry.json` is now built from `registry/` by `scripts/build-registry.py`: `core.json`
  (shared sections), `engineering/<repo>.json`, `engineering/skills.json`, `engineering/contracts.json` and
  `domains/<domain>.json` (a domain's modules, contracts, skills, kinds and lifecycles). Parallel domain branches
  edit different files; replaying this repository's merges found `registry.json` conflicts in every parallel domain
  merge of 1.3.0. Readers still read the one committed `registry.json`. `--check` (run-all) fails when it is not the
  build or an entry sits in the wrong fragment; `scripts/new-skill.py` writes the fragments. The one-time migration
  reorders `registry.json` (entries grouped by fragment) without changing its content (`tests/registry-fragments.test.sh`).
- **CODEOWNERS by domain.** `.github/CODEOWNERS` maps each domain's fragment, skills, templates, checks, adapters,
  docs and tests to an owner; the registry-fragments suite keeps its paths and domains current.
