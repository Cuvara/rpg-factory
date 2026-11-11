# Releasing rpg-factory

The release procedure. Moved from `.claude/CLAUDE.md` (rule "Releases").

**Releases:** bump `VERSION`, `.claude-plugin/plugin.json`, `marketplace.json`, `.codex-plugin/plugin.json` (and the
Codex marketplace `.agents/plugins/marketplace.json` if it carries a version) and the README "Version" line, and gather the
fragments into the `CHANGELOG.md` section with `python3 -B scripts/changelog.py release X.Y.Z [--summary TEXT]` (run-all and
`release-check.py` check it: section present, `[Unreleased]` empty, no fragment left). The local directory marketplace loads this checkout in
place (what is checked out is what sessions run); the install record only updates on a version
change: `claude plugin marketplace update rpg-factory && claude plugin update rpg-factory@rpg-factory`,
restart, then `tests/run-all.sh --release` and `tests/dogfood.sh --installed`.

Tag and GitHub release: without explicit release authorization from the user in the current task, stop at
READY_TO_TAG - the maintainer tags and publishes. When the user explicitly authorizes the release in the current
task, perform the authorized merge, version bump, annotated tag (`vX.Y.Z`, message `rpg-factory X.Y.Z`, on the
verified merge commit) and GitHub release yourself, within that scope and only after `run-all.sh --release` and
dogfood pass on that exact commit. Never move, delete or reuse a tag, and never bypass a failing check.

Authorized release order (`scripts/release-check.py` is read-only; exit 0/1):

1. merge the release PR; 2. check out the merge commit (`main` == `origin/main`, clean tree);
3. `python3 -B scripts/release-check.py` (versions agree, Codex manifest included when present, `## [X.Y.Z]` present, `[Unreleased]` empty, tag
absent locally and on origin, HEAD == origin/main, clean); 4. `tests/run-all.sh --release` and
`tests/dogfood.sh --installed` on that commit; 5. `git tag -a vX.Y.Z -m "rpg-factory X.Y.Z"`;
6. `python3 -B scripts/release-check.py --verify-tag` (annotated, message, points to HEAD, VERSION at the tag);
7. push the tag, `python3 -B scripts/release-check.py --verify-tag --notes > notes.md` and
`gh release create vX.Y.Z --verify-tag -F notes.md`.
