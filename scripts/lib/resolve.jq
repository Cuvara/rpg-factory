# Resolve changed paths to Factory modules, dependents, checks, skills, contracts and gates.
#
# Input:  the registry (registry.json)
# Args:   $repo   repo key ("server" | "client" | "netcode" | ...)
#         $files  [{path, status, source}]   source = "worktree" | "branch" | "given"
#         $subst  {"{dotnet}": "...", "{plugin_root}": "..."}
#         $tools  {"go": "/usr/bin/go" | null, ...}
# Output: {files, touched, dependents, cross_repo_dependents, checks, obligations,
#          generated_hits, unmapped, contracts, suggested_skills, gates}
#
# Checks are computed for this repo only. Modules in OTHER repos reached through
# depends_on are reported as cross_repo_dependents (advisory): their checks run
# only when a skill works in that repo.

def path_matches($p; $f):
  if ($p | endswith("/")) then ($f | startswith($p)) or (($f + "/") == $p)
  else ($f == $p) or ($f | startswith($p + "/"))
  end;

def glob_matches($g; $f):
  if ($g | startswith("**/*")) then ($f | endswith($g[4:]))
  else path_matches($g; $f)
  end;

def subst($s): reduce ($s | to_entries[]) as $e (.; split($e.key) | join($e.value));

. as $reg
| $reg.modules as $all
| ($all | map(select(.repo == $repo))) as $mods
| ([ $mods[] | select(.fallback == true) | .id ][0] // null) as $fallback
| ($files | map(
    . as $f
    # a folder's Unity .meta sibling belongs to the folder: Runtime.meta -> Runtime
    | ($f.path | if endswith(".meta") then .[:-5] else . end) as $key
    | ($mods
       | map(select(.fallback != true))
       | map({id, len: ([.paths[] | select(path_matches(.; $key)) | length] | max // -1)})
       | map(select(.len >= 0))
       | max_by(.len) // null) as $best
    | $f + {module: ($best.id // $fallback), fallback: ($best == null and $fallback != null)}
  )) as $mapped
| ($mapped | map(.module) | map(select(. != null)) | unique) as $direct
| # transitive closure over depends_on across ALL repos: X depends_on Y => change in Y affects X
  (def closure($set):
     ($set + [$all[] | select(any(.depends_on[]; . as $d | $set | index($d))) | .id] | unique) as $next
     | if ($next | length) == ($set | length) then $set else closure($next) end;
   closure($direct)) as $closed
| ($closed - $direct) as $reached
| ([$all[] | select(.repo == $repo) | .id] ) as $repo_ids
| ($reached | map(select(. as $id | $repo_ids | index($id)))) as $dependents
| ($reached - $dependents) as $cross_ids
| [ $mods[] | select(.id as $id | ($direct + $dependents) | index($id)) ] as $selected
| # contracts whose source or copies live in touched paths of this repo
  ([ ($reg.contracts // [])[] as $c
     | [ ([$c.source] + ($c.copies // []))[] | select(.repo == $repo) ] as $ends
     | [ $mapped[] as $f | $ends[] | select(path_matches(.path; $f.path) or glob_matches(.path; $f.path))
         | {path: $f.path, role: (if . == $c.source then "source" else "copy" end)} ] as $hits
     | select(($hits | length) > 0)
     | {id: $c.id, summary: $c.summary, hits: ($hits | unique), driver: ($c.driver // null),
        gate: ($c.gate // null),
        other_ends: [ ([$c.source] + ($c.copies // []))[] | . as $e
                      | select(($e.repo != $repo) or ([$hits[].path] | any(. as $hp | path_matches($e.path; $hp)) | not))
                      | {repo, path} ],
        upstream: ($c.upstream // []),
        watchers: ($c.watchers // [])}
   ]) as $contracts
| ([ $all[] | select(.id as $id | $cross_ids | index($id)) | {id, repo, skills: (.skills // [])} ]) as $cross
| {
    files: $mapped,
    touched: $direct,
    dependents: $dependents,
    cross_repo_dependents: ($cross | map({id, repo})),
    checks: [
      $selected[] as $m
      | ($m.tools | map(select(($tools[.] // null) == null))) as $missing
      | ("fast", "extended", "external") as $tier
      | $m.checks[$tier][]?
      | {
          module: $m.id,
          via: (if ($direct | index($m.id)) then "direct" else "dependent" end),
          tier: $tier,
          id,
          cwd: (.cwd // "."),
          run: (.run | subst($subst)),
          trigger: (.trigger // null),
          evidence,
          missing_tools: (if $tier == "external" then [] else $missing end)
        }
    ],
    obligations: [
      $mods[] | select(.id as $id | $direct | index($id))
      | {module: .id, changelog, docs, claude_md, rules, obligations}
    ],
    generated_hits: [
      $mapped[] as $f
      | $mods[] | select(.id == $f.module) | .generated[]
      | select(glob_matches(.; $f.path))
      | {path: $f.path, status: $f.status, generated_by: .}
    ] | unique,
    unmapped: [ $mapped[] | select(.module == null) | .path ],
    repo_level: [ $mapped[] | select(.fallback) | .path ],
    contracts: $contracts,
    suggested_skills: (
      def owner($r; $p): [ $all[] | select(.repo == $r)
          | {id, skills: (.skills // []), len: ([.paths[] | select(path_matches(.; $p)) | length] | max // -1)} ]
          | map(select(.len >= 0)) | max_by(.len) // null;
      def kind($s): ($reg.skills[$s].kind // "repo");
      ([ $contracts[] | select(.driver != null)
          | select(kind(.driver) == "cross-repo" or any(.hits[]; .role == "source")) ] | length > 0) as $driven
      | ([ $contracts[] | select(.driver != null and kind(.driver) == "cross-repo") ] | length > 0) as $cross_driven
      | [ ($contracts[] | select(.driver != null) | . as $c
            | {skill: .driver,
               role: (if kind($c.driver) == "cross-repo" or any($c.hits[]; .role == "source") then "lead" else "leg" end),
               class: (if kind($c.driver) == "cross-repo" then 0 else 1 end),
               reason: "contract \($c.id) (\([$c.hits[].role] | unique | join("/")) touched)"}),
          ($mods[] | select(.id as $id | $direct | index($id)) | .id as $mid | (.skills // []) | to_entries[]
            | {skill: .value, role: (if $driven then "leg" else "lead" end), class: (if .key == 0 then 2 else 3 end),
               reason: ("owns touched module \($mid)" + (if .key > 0 then " (secondary owner)" else "" end))}),
          ($contracts[] | select(any(.hits[]; .role == "source")) | . as $c | .other_ends[] | select(.repo == $repo) | owner(.repo; .path) as $o
            | select($o != null) | $o.skills[] | {skill: ., role: "leg", reason: "owns \($o.id), other end of contract \($c.id)"}),
          ($contracts[] | select(any(.hits[]; .role == "source")) | . as $c | .other_ends[] | select(.repo != $repo) | owner(.repo; .path) as $o
            | select($o != null) | $o.skills[] | {skill: ., role: "follow-up", reason: "\($o.id) [\($o.id | split(".")[0])] is an end of contract \($c.id)"}),
          (select($cross_driven) | $mods[] | select(.id as $id | $dependents | index($id))
            | select(any(.depends_on[]; . as $d | $direct | index($d)))
            | .id as $mid | (.skills // [])[]
            | {skill: ., role: "leg", reason: "first-hop dependent module \($mid)"}),
          ($cross[] | .id as $cid | .repo as $cr | .skills[0:1][] | {skill: ., role: "follow-up", reason: "cross-repo dependent \($cid) [\($cr)]"})
        ]
      | map(select(.skill != "factory-core"))
      | group_by(.skill)
      | map(. as $g | {skill: $g[0].skill,
             role: ($g | map(.role) | if index("lead") then "lead" elif index("leg") then "leg" else "follow-up" end),
             class: ([ $g[] | select(.role == "lead") | .class // 9 ] | min // 9),
             order: ($reg.skills[$g[0].skill].order // 999),
             reasons: ($g | map(.reason) | unique)})
      | sort_by({"lead": 0, "leg": 1, "follow-up": 2}[.role], .class, .order, .skill)
    ),
    gates: (
      [ ($mods[] | select(.id as $id | $direct | index($id)) | (.gates // [])[] | {gate: ., source: "module"}),
        ($contracts[] | select(.gate != null) | {gate: .gate, source: "contract \(.id)"}) ]
      | group_by(.gate) | map({gate: .[0].gate, sources: (map(.source) | unique)})
    )
  }
| . as $o
| ([ $o.suggested_skills[] | select(.role == "lead") ]) as $leads
| $o + {routing: {
    lead: ($leads[0].skill // null),
    co_leads: [ $leads[1:][] | .skill ],
    legs: [ $o.suggested_skills[] | select(.role == "leg") | .skill ],
    follow_ups: [ $o.suggested_skills[] | select(.role == "follow-up") | .skill ],
    ambiguous: (($leads | length) > 1 and $leads[0].class == $leads[1].class and $leads[0].order == $leads[1].order),
    precedence: "class (0 cross-repo contract driver, 1 contract owner via source, 2 primary module owner, 3 secondary owner), then skills.<name>.order",
    lead_basis: (if ($leads | length) == 0 then null else
      {class: $leads[0].class, order: $leads[0].order, reasons: $leads[0].reasons} end)
  }}
