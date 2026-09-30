# Pin chains

Facts checked 2026-09-30 against the repos. The sources are cited inline.

## The two chains

```
Shared.GameLogic (server)                      com.cuvara.* package repos
  package.json version bump (same commit)        package.json + '## [X.Y.Z] - date' CHANGELOG section
  lead tags sgl-vX.Y.Z                           lead tags vX.Y.Z  (release.yml: tag must equal package.json,
  verify-sgl-tag.yml: tag == package.json          notes from CHANGELOG, GitHub release + npm publish)
  sgl-notify-client.yml → client sgl-pin-check   Netcode sync-main.yml opens develop→main PR
            │                                              │
            └──────────────► client pin-bump ◄─────────────┘
                 manifest + lock (+ DOTS Sample for netcode) + CHANGELOG
                 CI: 02-package-pins.yml, sgl-pin-check.yml, 01-ci.yml
```

- History, 2026-08-11 → 09-24: 20 `sgl-v*` tags and 18 client sgl pin commits. The client skipped v0.2.0, v0.4.0 and v0.5.0. It moved Netcode 21 times against 77 tags, UnityDots 11 times against 30 tags, and UIToolkit 6 times against 8 tags.
- Pins in the client today (`scripts/checks/pin-status.py`): netcode v0.45.0, dots v0.29.0, uitoolkit v0.7.2, sgl-v0.6.0 and build-pipeline v5.2.0. The last one is the `unity-build-workflows` UPM package; its source is not in the workspace.

## Lock entry anatomy (from 17b7737)

```json
"com.cuvara.netcode": {
  "version": "https://github.com/Cuvara/Netcode.git#v0.45.0",   // == manifest string
  "depth": 0,
  "source": "git",
  "dependencies": { ... },                                        // must match package.json at the tag
  "hash": "2eb6ddbc4e0c62544fa860b3a4f7e64071918f0b"             // == tag commit
}
```

`pin-plan.py` computes the `version`/`hash` pair and lists the dependency changes between the old and the new tag.

## DOTS Sample (the #135 procedure, client `CLAUDE.md` "The DOTS Sample")

- `Assets/Samples/Netcode/DOTS Sample/` is tracked and version-free. The play client builds it.
- It is a byte-for-byte copy of `Netcode/Samples~/DOTSSample` at the version recorded in `.sample-source`:

  ```
  package=com.cuvara.netcode
  version=v0.45.0
  commit=2eb6ddbc4e0c62544fa860b3a4f7e64071918f0b
  ```

- `02-package-pins.yml` job `sample-matches-pin` fails when `version` differs from the lock pin.
- Recopy on every Netcode move, even when `pin-plan.py` reports 0 changed sample files. The copy must stay identical to the tag, and `.sample-source` must name the new tag.
- Safe copy that leaves no stray files:

  ```bash
  tmp=$(mktemp -d); git -C <ws>/Netcode archive <tag> Samples~/DOTSSample | tar -x -C "$tmp"
  cp "Assets/Samples/Netcode/DOTS Sample/.sample-source" "$tmp/.sample-source.keep"
  # replace folder contents with $tmp/Samples~/DOTSSample/*, restore .sample-source, edit version/commit
  diff -r "$tmp/Samples~/DOTSSample" "Assets/Samples/Netcode/DOTS Sample"   # only .sample-source may differ
  ```

- Removing a tracked file that the tag no longer has counts as part of the copy. Report every deletion.
- Never re-import the sample through the Package Manager. That creates `Assets/Samples/Cuvara Netcode/<version>/` and a second `DOTSSample` assembly.
- Other `Assets/Samples/Cuvara */<version>/` folders are different samples, frozen at the version they were accepted with. Untracked ones are the user's own imports.

## CI in the client that judges a bump

| Workflow | Checks | Trigger |
|---|---|---|
| `02-package-pins.yml` | manifest == lock for every git-URL dependency (at least 1 must match); every pinned ref exists on its remote; `.sample-source` == netcode pin | PRs touching the manifest, the lock or `Assets/Samples/Netcode/**` |
| `sgl-pin-check.yml` | SGL manifest == lock, and the tag exists | PR, a Monday cron, and a dispatch from the server's `sgl-notify-client.yml` |
| `uxml-codegen-drift.yml` | committed `*.uxml.g.cs` equal the output of the pinned UIToolkit codegen | PRs touching `*.uxml`, `*.uxml.g.cs` or the lock |
| `01-ci.yml` | Unity tests (unity-build-workflows@v6) | non-docs changes |

A UIToolkit bump can change codegen output. If `uxml-codegen-drift` fails after the bump, regenerating is `client-integration` work in the same PR.

## Incidents behind the rules

- `rpg-mmo-server#380`: the manifest stayed at sgl-v0.4.1 while a bump to v0.5.0 lived only in a working tree, so the repo and the dev machine built different libraries. This is why `02-package-pins` exists.
- #130: Netcode was pinned to a raw commit SHA, which carries no version. The rule is tags only.
- #135: a version-named sample folder claimed v0.35.0 but held v0.43.0 content. This is why `.sample-source` exists.
