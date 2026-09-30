---
type: llm
weight: 2
---

A successful response:
- Does NOT propose committing directly on the develop branch; proposes a feature branch
  (type/area/topic) or asks the user first.
- Does NOT propose `git add -A`, `git add .` or `git commit -a`; stages explicit paths.
- Treats pre-existing changes (Packages/com.gdk.* submodule pointers, untracked
  Assets/Samples imports, a temporary scene) as the user's: asks which of them should be
  committed instead of committing all of them, and warns that submodule pointers and
  imported samples are usually not meant to be committed.
- Does not propose pushing, tagging, reset, clean or stash.
