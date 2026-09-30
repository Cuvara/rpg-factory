# Resolve changed paths to Factory modules, dependents, checks and obligations.
#
# Input:  the registry (registry.json)
# Args:   $repo   repo key ("server" | "client")
#         $files  [{path, status, source}]   source = "worktree" | "branch"
#         $subst  {"{dotnet}": "...", "{plugin_root}": "..."}
#         $tools  {"go": "/usr/bin/go" | null, ...}
# Output: {files, touched, dependents, checks, obligations, generated_hits, unmapped}

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
| ($reg.modules | map(select(.repo == $repo))) as $mods
| ($files | map(
    . as $f
    | ($mods
       | map({id, len: ([.paths[] | select(path_matches(.; $f.path)) | length] | max // -1)})
       | map(select(.len >= 0))
       | max_by(.len) // null) as $best
    | $f + {module: ($best.id // null)}
  )) as $mapped
| ($mapped | map(.module) | map(select(. != null)) | unique) as $direct
| # transitive closure over depends_on: X depends_on Y => change in Y requires validating X
  (def closure($set):
     ($set + [$mods[] | select(any(.depends_on[]; . as $d | $set | index($d))) | .id] | unique) as $next
     | if ($next | length) == ($set | length) then $set else closure($next) end;
   closure($direct)) as $all
| ($all - $direct) as $dependents
| [ $mods[] | select(.id as $id | $all | index($id)) ] as $selected
| {
    files: $mapped,
    touched: $direct,
    dependents: $dependents,
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
    unmapped: [ $mapped[] | select(.module == null) | .path ]
  }
