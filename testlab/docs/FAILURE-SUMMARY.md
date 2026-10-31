# failure-summary.json

Every testlab run that is not a clean PASS (FAIL, INCONCLUSIVE, INVALID, PASS_WITH_WARNINGS, or a harness error)
writes `failure-summary.json` next to `report.md` at the end of `analyze` (`lab/failsum.py`, called from
`report.write`, so `run`, `suite` and `testlab.py analyze [--out DIR]` all produce it). A clean PASS writes none
(and removes a stale one of an earlier analysis in the same directory). Nobody has to watch the run: open the file.

**Derived output only.** It reads the evidence and the check results `analyze` already decided. It never changes the
verdict, a check status or `results.json`; any failure while building, cleaning up, or writing it is caught so
analysis continues. The writer makes a best-effort attempt to replace a failed summary with a minimal document
containing the unchanged verdict and exit code plus an `error` field with the exception type and message. The rules
below are code (`lab/failsum.py`) and are pinned by `testlab/tests/test_failsum.py`; change both
and bump `RULES_VERSION`.

## Content

| Key | Meaning |
|---|---|
| `verdict`, `exit_code` | the run outcome and its exit code, copied |
| `scenario_start_utc` | wall clock of scenario time 0 (host guard start, else `start_scheduled`) |
| `earliest_event` | the earliest located event over all failures: `scenario_s`, `wall_utc`, `check`, `what` |
| `failures[]` | one per FAIL / INVALID / INCONCLUSIVE check, per informational check that would have failed, and a `harness_error` entry |
| `failures[].earliest_event` | `scenario_s`, `wall_utc`, `client`, `what`; `null` when the check cannot be placed in time (two-scrape counters, no counted event) |
| `failures[].evidence[]` | `file` (relative to the run directory), `line` (1-based line of an ndjson/txt file, or `null`), `find` (key to look up when no line is known), `note` |
| `failures[].notes` | optional; present only for `frame_time`, `snapshot_cadence`, `snapshot_update_gap` when a stall frame (>= 250 ms) coincided with a gen0 GC collection in the client `frames.csv` GC columns ("stall frame coincided with gen0 GC: ..."); absent otherwise and for runs without those columns |
| `failures[].suspected_layer`, `layer_rule`, `alternative_layer` | layer by the rule below; `alternative_layer` is the check's default layer when L3 overrides it |
| `failures[].confidence` | `high` / `medium` / `low` by the rule below |
| `failures[].guard_events_within_10s` | host guard events within +-10 s of the earliest event: AnyDesk log events, an AnyDesk session active at that instant, guard samples over the G3 CPU limit; `offset_s` is event minus instant |
| `failures[].next_action` | from the table below |

Scenario time maps to wall time as scheduled start + `st` (accurate to about 5 s, the guard sampling interval, same as
`host_quiet`'s nearest-guard-event column).

## Earliest event, per check

| Check | Earliest event |
|---|---|
| `host_guard` | first evidence stamp of each fired guard at or after the scenario start (minute-resolution connection entries only when nothing else exists); a condition already active at the start is scenario time 0 |
| `snapshot_cadence` | first snapshot gap over `max_gap_ms` inside the window, per failing client (`snapshots.ndjson` line) |
| `render_jumps` | earliest counted jump of a class whose limit is breached (left by `check_render_jumps` in `ev["_failsum"]`; teleports and stall-explained jumps are not counted). Not located when the summary is built without the in-process analysis |
| `entity_lifecycle` | earliest lingering / id-reuse / duplicate-id row; the process time `t` is mapped to scenario time with the client's first `events.ndjson` row that has both `t` and `st` |
| `cross_client_convergence` | the worst pair's render tick, mapped to scenario time through client a's `snapshots.ndjson` (tick to receive time) |
| `kcp_health` | not located: the counters are two scrapes. Evidence points at the failing counter lines of `server/metrics-end.txt` |
| other checks | earliest `st` found in the check detail, else not located |

## Suspected layer (first matching rule)

| Rule | Condition | Layer |
|---|---|---|
| L1 | the check is INVALID, or is `host_guard` / `host_quiet` | environment |
| L2 | harness error, the check raised or is unknown, or a harness check (`provenance`, `clients_*`, `distinct_user_ids`, `same_game_server`, `bots_joined`, `netem_applied/cleanup`) | harness |
| L3 | a guard event or an active AnyDesk session lies within +-10 s of the earliest event, or the event is in a host-wide stall window | environment (default layer kept as `alternative_layer`) |
| L4 | the default layer of the check (`LAYER_BY_CHECK`: kcp / snapshot / tick / enemy / redis / persistence checks are server; render, interpolation, prediction, convergence, netem checks are netcode; frame time, memory, client log are client) | per table |
| L5 | check not in the table | unknown |

The L4 table is a prior about where a check's failures usually originate, not a diagnosis.

## Confidence

- **high**: the layer comes from direct evidence (L1, L2 or L3) and the earliest event is located.
- **medium**: the earliest event is located, a host guard recorded the run, no guard event is within +-10 s, the run is not INVALID, and the layer is the L4 prior.
- **low**: anything else: event not located, no guard evidence, unknown layer, or an INVALID run where this failure is not near a guard event (the host was contaminated elsewhere in the window).

## Next action

The check's own entry (`NEXT_ACTIONS_BY_CHECK`: `kcp_health`, `snapshot_cadence`, `snapshot_update_gap`, `render_jumps`,
`entity_lifecycle`, `cross_client_convergence`, `prediction_bound`, `frame_time`, `provenance`) when the suspected layer
is the check's default layer; otherwise the layer's (`NEXT_ACTIONS_BY_LAYER`): environment: rerun on a quiet host;
harness: read `orchestrator.log` / `harness-error.txt` and fix the setup; server / netcode / client: open the cited
files around the earliest event and reproduce before changing code; unknown: read the check detail by hand.
Suggestions only; nothing runs automatically.

## Fixtures

`testlab/tests/fixtures/failsum/<run>/` are small scrubbed excerpts of real runs (S09 k4n5, ibz3, 9tgw, 3ng5), cut by
`tests/fixtures/failsum/extract.py <run_dir> <name>` (UUIDs replaced, paths relative). The ibz3 `render_jumps` FAIL was
graded by an older analyzer (a local respawn snap counted as `local_major`); today's check counts none, so its earliest
counted jump is correctly not located.
