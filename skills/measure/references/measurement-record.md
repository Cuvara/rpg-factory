# Measurement record

Fill this **before** running. It becomes the Measurements table of the Core report and the
header of the results README. Distilled from `rpg-mmo-server/backend/docs/MEASUREMENT.md`
(sections 1-9) and `backend/docs/BENCHMARK.md`; the incident behind each field is cited.

```markdown
### <claim, one sentence>
- Object:      <the exact thing the number describes: which process, map, arm, window>
- Metric:      <name as emitted, e.g. client rx_bytes_per_sec_per_player, server tick_p99_sec>
- Expected:    <value + units + where it comes from (prior run id, arithmetic, config)>
- Absolute bound: <what the arm must be in its own right: speed x seconds, rate vs configured Hz,
                  count vs sent>
- Control arm: <what differs: exactly one variable; same host, session, generator binary>
- Setup:       <server image/sha, SIM_CRITICAL_HZ/SIM_WORLD_HZ read from /status, encoding,
                transport, join mode, enemies/baseline-entities, capacity>
- Host load:   <what else ran: CD deploy? Docker Desktop, k3d? generator CPU from bench.sh stats>
- Run id / path: backend/loadtest/results/<YYYY-MM-DD>-<branch>-<shortsha>[-topic]/
- Measured:    <value + units, per repeat>
- Validity:    <VALID | INVALID (reason) | DEGRADED (which criterion)>
- Attribution: <who pays (server tick thread, write tasks, server egress, client CPU/GC,
                generator) and where it shows (metric/column/histogram)>
```

## Why each field is mandatory

| Field | Incident it prevents (source) |
|---|---|
| Object | a number describing the generator, the wrong arm or a stale window reported as the server's (MEASUREMENT.md 3) |
| Expected before running | rationalising after the fact; the 2026-09-07 first pass read 274 KB/s per client at 200 under the old `json` default: the JSON arm's number, not a regression against the 45.9 KB/s proto figure (BENCHMARK.md 10) |
| Absolute bound | deleting three quarters of held movement left a jittered/clean ratio of 1.0; only the bound (7.5 of 30 units) caught it (MEASUREMENT.md 4) |
| Control, one variable | a -73% delta that was a cross-build artefact (controlled: 32.2%); two bench projects sharing `obj/` printed identical columns (MEASUREMENT.md 4) |
| Host load | tick p99 swung 72.9 ms to 240.6 ms depending on a concurrent CD build while bytes moved 0.3% (`encoding-sweep.sh` header) |
| Zero proven movable | an empty result, a skipped test and a stopped instrument all read as good news (MEASUREMENT.md 1, 2, 2b) |
| Validity | INVALID levels (server restart mid-run, any failed client, received ratio > 1.05, more entities than requested) are excluded from aggregates, not counted as failures (`backend/loadtest/README.md` "Verdict") |
| Run id | CORE-BASELINE-V1.md section 6 rule 3: never promote a row without naming the run that demonstrated it |
| Attribution | a win on the wire that moved cost to the client or the write tasks is not a win; say where the cost now appears |

## Re-baselining `CORE-BASELINE-V1.md`

Source: that file's header table and section 6.

1. Trigger: a pin in the header table moved (server `develop` sha with CI **and** CD green,
   client `develop` sha with CI green, `com.cuvara.netcode` version + lock hash,
   `com.rpgmmo.shared-gamelogic` sgl tag + lock hash, wire protocol version, sim rates).
   The v1 -> v1.1 bump was a netcode pin move with no gameplay-facing change.
2. Re-demonstrate every row whose evidence the move could touch; name the run for each.
3. Update the version table and the "What moved" list in the same change. Wire / SGL /
   interpolation-budget changes update **both** repositories (rule 1).
4. Section 5 (release gate) items change only with evidence (issue + commit + observed result).
5. Stop at **"ready to tag core-baseline-v<N> in rpg-mmo-server and IndieRPGMMOAdventure"**.
   `publish-images.yml` publishes images for `core-baseline-*` tags when the lead pushes them.
