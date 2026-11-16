# Style verbs and structured fields: init, derive, bump, report

All verbs are `assetgen.py style <verb> --authoring <A> ...` (`assetgen.py` is
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/assetgen/assetgen.py`). Read a verb's docstring before describing or running it;
each refusal prints `assetgen: <message>` and exits 1, usage errors exit 2. None edits core data
(`templates/assetgen/`) and none activates anything.

## Structured fields

Data the QA rows read; each may stay prose (its `text` is the prompt hint). The validator is `scripts/assetgen/stylelock.py`
`style_errors`; the rows are in the `scripts/assetgen/consistency.py` docstring.

| Field | Shape | QA row |
|---|---|---|
| `palette` | `colors` `[{hex, role}]`, `max_distance` 0-441, `min_share` 0-1, `severity`, `text` | `style-palette` |
| `tone` | `tolerance` 0-1, `severity` | `style-tone` (needs anchors) |
| `outline.edge_darkness` | `max_luminance` 0-255, `min_ratio` 0-1, `severity` | `style-edges` (needs the purpose's `qa.outlines`) |
| `canvas` | per family: `aspect` W:H, `min_side`, `tolerance`, `severity` | `style-canvas` |
| `forbidden` | list of strings, shown to the prompt and the reviews | none |

`outline.edge_darkness` is a usable structured field like the others: set it when the art bible has a dark outline.
An absent, prose-only or empty (`{}`) field gives its row `NOT_AVAILABLE`. A miss is `WARN`, or `FAIL` when the field
sets `severity` `fail`.

## style init

`style init --id ID --extends CORE [--family FAM=STYLE]... [--title T] [--json]` (`scripts/assetgen/style_cmd.py` `init`)
writes a draft `assetgen/styles/<ID>.json` (version 1, status `draft`, no structured fields), draft stubs for family
styles that do not exist yet, and the `assetgen/project.json` skeleton. It checks every target first and never
overwrites. A family style that already exists must extend `ID`; a core-only family style is refused. Read its
`WARN:` line (text output) or `warnings` list (`--json`): it names the missing structured fields, and no `style-*`
QA row can grade an output until one is added. A draft style gets no lint WARN until it is made active.

## style derive

`style derive --authoring <A> --style ID [--family F] [--apply] [--json]` (`scripts/assetgen/style_derive.py`) proposes
`palette.colors`, `tone.tolerance` and `canvas` from the valid active anchors of the style's current version
(optionally only family `F`). The output is deterministic; without `--apply` nothing is written. `--apply` merges the
proposal into the game style file only when its status is exactly `draft`: it replaces `palette.colors` and
`tone.tolerance` from that family's anchors only (`--family F`), and `canvas` merges per family, so other families and
keys such as `palette.text`, `tone.severity` and `min_side` stay. Show the proposal and its numbers to the person
before `--apply`. An active style is refused: `--apply` works only on a `draft` `assetgen/styles/<ID>.json` (a
`style init` draft), never on the bump draft `assetgen/styles/<ID>/versions/<N+1>.json`. For an active style run
`style derive` without `--apply` (a read-only proposal from the version-N anchors), then `style bump`, and the person
merges the proposed values into the bump draft by hand before activating it.

## style bump

`style bump --authoring <A> --id ID [--list-only] [--json]` (`scripts/assetgen/style_cmd.py` `bump`) works on an
**active** game style of version N and never edits it. It writes the draft
`assetgen/styles/<ID>/versions/<N+1>.json` (status `draft`; not a layer file, so it changes no resolve, selection or
drift) and lists what needs re-approval:

- valid active anchors of version N whose PNG matches are **carried** as new anchors `<id>-v<N+1>` with status
  `proposed`, `approved_by` and `approved_on` null: a person activates them. Other version-N anchors are `reapprove`.
- runs of version N: `reapprove` (re-run or re-approve under N+1). Rejections of version N: `rerecord`; version
  null: `applies`.
- the artifact-quality check runs before and after the writes; a new FAIL, or a check that cannot run, removes the
  carried anchors this call wrote and limits the verb to listing (the draft stays). `--list-only` writes nothing.

A person activates the draft: replaces `assetgen/styles/<ID>.json` with it, sets status `active`, updates
`project.json` `style.version`, and activates the proposed anchors. Do none of that on your own. A draft style
is refused (edit it, or run `style derive --apply` into it), and so is a deprecated one.

## style report

`style report --authoring <A> [--style ID] [--json]` (`scripts/assetgen/style_report.py`) is read-only. Per style and
family it prints run counts by status, tone and palette statistics of the approved outputs, `style-*` QA states with
warn and fail rates, rejections by reason, and **suggested** thresholds (`palette.max_distance`, `tone.tolerance`) with
their supporting numbers. A suggestion is never applied: bring it to the person, who edits the style (in a bumped
draft when the style is active).
